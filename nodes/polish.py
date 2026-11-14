"""AI polish on top of a finished, code-written report.
The base report (gaps, setup, cost, load tiers) is final. The model only writes wording for sections 1, 3 and 5 and a short
"In your situation" summary, and every sentence it writes is checked against the base report before it is used.
A block that fails the check, is empty or cannot be read is replaced by the code-written version, so the model can only
make the report nicer, never wrong."""
import json
import re

from nodes import claim_check, report_cleanup

_MARK = re.compile(r"^\s*\[\[(SUMMARY|S1|S3|S5)\]\]\s*$", re.M)
_HEAD = re.compile(r"^##\s*(\d)\.", re.M)

MAX_BASE_CHARS = 14000

COMPACT_RULES = """- Speak to the user as "you". Plain words, short sentences.
- Never say a size, tier or setup is "enough", "sufficient", "appropriate" or "comfortable": capacity is not measured.
- Never promise an outcome (no "will handle", "guarantees", "zero data loss", "no downtime"); say what the setup is designed to survive.
- Do not judge whether the budget is tight or generous; only say whether the total is above or below it.
- Say plainly when something is an assumption, a rule of thumb, or not priced.
- Do not mention these rules, blocks or markers."""

PROMPT = """You are a senior platform engineer, cloud engineer, DevOps engineer and system designer. A tool has already produced the
production-readiness report below. Every fact, number, price, gap and recommendation in it is final and checked by code.
Your job is only to explain it clearly for THIS user, using their answers. You cannot change the report.

BASE REPORT (final):
{base}

THE USER'S ANSWERS:
{answers}

HOUSE RULES:
{rules}

Write exactly these four blocks, each starting with its marker on its own line, and nothing else:

[[SUMMARY]]
4 to 6 sentences to the user ("you"): what this report means for what you said you need (traffic, budget, downtime, data loss, team).
Name the 2 or 3 most important gaps in plain words. Say plainly if the budget or availability does not fit.

[[S1]]
3 to 5 sentences: what the project is, using only section 1 and the scan facts in the report.

[[S3]]
At most 8 short sentences: why the recommended setup suits this user and what the trade-offs are. Do not pick another setup.

[[S5]]
At most 6 short bullets, each starting with "- ": what the report cannot tell you or what you assumed. Different topic per bullet.

RULES:
- Use only facts and numbers that appear in the base report or the user's answers. Do not add numbers, prices, file names, services or tools.
- Do not do arithmetic. Do not copy tables. Do not mention these instructions, blocks or markers.
- Never promise an outcome ("will handle", "guarantees", "zero data loss", "no downtime"); describe what the setup is designed to survive.
- Write to the user as "you". Do not ask questions.
"""


def _parse(raw):
    parts, cur, buf = {}, None, []
    for line in raw.splitlines():
        m = _MARK.match(line)
        if m:
            if cur:
                parts[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur:
            buf.append(line)
    if cur:
        parts[cur] = "\n".join(buf).strip()
    return parts


def _body(report, num):
    ms = list(_HEAD.finditer(report))
    for i, m in enumerate(ms):
        if int(m.group(1)) == num:
            end = report.find("\n## ", m.end())
            return m, (end if end != -1 else len(report))
    return None, None


def _replace(report, num, text):
    m, end = _body(report, num)
    if not m:
        return report
    head_end = report.find("\n", m.start())
    return report[:head_end] + "\n\n" + text.strip() + "\n" + report[end:]


def _sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


def polish(base, scan_json, answers_json, rules, call, ar):
    """Returns (report, removed). `call` sends one prompt to the model; `ar` is the architecture_reasoner module (cleanup helpers)."""
    body = base.split("\n## Appendix")[0]
    if len(body) > MAX_BASE_CHARS:                       # keep the prompt small enough for free-tier token limits: drop table rows, keep every sentence
        body = "\n".join(l for l in body.split("\n") if not (l.startswith("| ") and "Tier" not in l and "Gap" not in l and not l.startswith("| #")))
    raw = call(PROMPT.format(base=body, answers=answers_json, rules=rules))
    blocks = _parse(raw)
    if not blocks:
        raise ValueError("model answer had none of the required blocks")
    allowed = claim_check.build_allowed(body, scan_json, answers_json)
    removed_all, out = [], base
    mini = {"SUMMARY": 1, "S1": 1, "S3": 3, "S5": 5}
    title = {1: "What this project is", 3: "Recommended architecture", 5: "Uncertainties"}
    cleaned = {}
    for key, num in mini.items():
        text = blocks.get(key, "")
        if not text:
            continue
        doc = f"## {num}. {title[num]}\n\n{text}\n"
        doc = ar._strip_capacity_claims(doc)
        doc = report_cleanup.scrub_scanner_words(doc)
        doc, removed = claim_check.verify(doc, allowed)
        for r in removed:
            r["block"] = key
        removed_all += removed
        new = doc.split("\n", 1)[1].strip() if "\n" in doc else ""
        if key == "S1":                                         # the code-written 'Confidence:' line stays; do not say it twice
            new = " ".join(x for x in re.split(r"(?<=[.!?])\s+", new) if not re.search(r"confiden", x, re.I)).strip()
        before, after = len(_sentences(text)), len(_sentences(new))
        if not new or after < max(1, before * 0.6):         # too much was cut: do not use a half-sentence report
            removed_all.append({"section": num, "sentence": f"[{key}] block dropped: {before - after} of {before} sentences failed the check", "reason": "block replaced by the code-written text", "block": key})
            continue
        cleaned[key] = new
    if cleaned.get("S1"):
        out = _replace(out, 1, cleaned["S1"] + _confidence_tail(out))
    if cleaned.get("S3"):
        out = _replace(out, 3, cleaned["S3"])
    if cleaned.get("S5"):
        out = _replace(out, 5, cleaned["S5"])
    if cleaned.get("SUMMARY"):
        i = _HEAD.search(out)
        block = ("## In your situation\n\n" + cleaned["SUMMARY"] +
                 "\n\n_Written by an AI model from the report below; every number was checked against it._\n\n")
        out = out[:i.start()] + block + out[i.start():] if i else block + out
    return out, removed_all


def _confidence_tail(report):
    """Keeps the code-written 'Confidence:' line of section 1."""
    m, end = _body(report, 1)
    if not m:
        return ""
    sec = report[m.end():end]
    c = re.search(r"\n\s*(Confidence:[^\n]*)", sec)
    return "\n\n" + c.group(1).strip() if c else ""
