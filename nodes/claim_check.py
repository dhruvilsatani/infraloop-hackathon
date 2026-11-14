"""Whitelist check for the parts of the report that the AI model writes (sections 1, 3 and 5).

Instead of banning bad phrases one by one, every sentence is checked against the facts the code already has
(scan result, the user's answers, the price table, the facts block, the gap list). A sentence is removed when:
  - it contains a number that appears nowhere in those facts (the model made it up or calculated it itself),
  - it contains a percentage that is not in the facts,
  - it names a file path that the scan did not find,
  - it is a question to the reader.
Every removal is recorded with its reason so the number of removals can be tracked from run to run.
"""
import re

CHECKED_SECTIONS = (1, 3, 5)
_NUM = re.compile(r"(?<![A-Za-z0-9_.])(\d[\d,]*(?:\.\d+)?)(\s*[kK](?![A-Za-z]))?(\s*%)?")
_PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w.-]+\.[A-Za-z0-9]{1,6}|(?:src|terraform|helm-chart|kubernetes-manifests|k8s|app|charts?)/[\w./-]+)")
_SENT = re.compile(r"(?<=[.!?])\s+")
_HEADING = re.compile(r"^## (\d)\.")


def _to_float(txt, k):
    try:
        v = float(txt.replace(",", ""))
    except ValueError:
        return None
    return v * 1000 if k else v


def numbers_in(text):
    """Returns (plain_values, percent_values) found in text."""
    plain, pct = set(), set()
    for m in _NUM.finditer(text or ""):
        v = _to_float(m.group(1), m.group(2))
        if v is None:
            continue
        (pct if m.group(3) else plain).add(round(v, 4))
        if m.group(3):
            plain.add(round(v, 4))          # "5%" in the facts also allows a plain 5
    return plain, pct


def build_allowed(*texts):
    plain, pct, paths = set(), set(), set()
    blob = "\n".join(t for t in texts if t)
    p, q = numbers_in(blob)
    plain |= p
    pct |= q
    low = blob.lower()
    return {"plain": plain, "pct": pct, "blob": low}


_UNIT_AFTER = re.compile(r"^\s*(?:millicores?|mcpu|m\b|mi?b\b|gi?b\b|ki?b\b|ms\b|milliseconds?|cores?|vcpus?)", re.I)


def _is_unit_conversion(v, plain, after=""):
    if not _UNIT_AFTER.match(after or ""):               # only a number written with a unit (70 millicores, 200 MiB) can be a conversion
        return False
    for x in plain:
        if x <= 0:
            continue
        for f in (1000, 1024, 1 / 1000, 1 / 1024):
            t = x * f
            if t > 0 and abs(v - t) / t <= 0.06:
                return True
    return False


def _number_problem(sentence, allowed):
    for m in _NUM.finditer(sentence):
        v = _to_float(m.group(1), m.group(2))
        if v is None:
            continue
        v = round(v, 4)
        if m.group(3):                                   # a percentage must be in the facts
            if v not in allowed["pct"]:
                return f"percentage not in the facts: {m.group(0).strip()}"
            continue
        if v in allowed["plain"]:
            continue
        if _is_unit_conversion(v, allowed["plain"], sentence[m.end():m.end() + 16]):       # 0.07 vCPU written as 70 millicores, 0.2 GiB as ~200 MiB
            continue
        if float(v).is_integer() and 0 <= v <= 12:        # small counts ("2 replicas", "3 sentences")
            continue
        if float(v).is_integer() and 1990 <= v <= 2100:   # years
            continue
        return f"number not in the facts: {m.group(0).strip()}"
    return ""


def _path_problem(sentence, allowed):
    for m in _PATH.finditer(sentence):
        full = m.group(1).lower()
        if full not in allowed["blob"] and full.rsplit("/", 1)[-1] not in allowed["blob"]:
            return f"file path not found by the scan: {m.group(1)}"
    return ""


_ONLY_RE = re.compile(r"\bthe only (?:setup|option|way|platform|choice|approach|configuration|service|solution)\b", re.I)
_ONLY_CLAUSE_RE = re.compile(r"\s*[\u2014\u2013;:,-]+\s*(?:this|that|it) is the only [^.!?]*", re.I)
_LOSS_RE = re.compile(r"\b(?:meet|meets|meeting|satisf\w+|guarantee\w*|ensur\w+|deliver\w*|achiev\w+|provid\w+)\b[^.]{0,40}\b(?:zero|no)[- ]data[- ]loss\b"
                      r"|\bzero[- ]data[- ]loss\b[^.]{0,30}\brequirement\b", re.I)
_HANDLE_RE = re.compile(r"\b(?:will|can|should|would|able to|designed to|able)\s+(?:easily\s+)?handle\b|\bhandles?\b[^.]{0,30}\b(?:requests?|users?|traffic|load)\b|\bguarantee[sd]?\b|\bno (?:downtime|data loss) (?:is|will be) possible\b", re.I)
_FIT_RE = re.compile(r"\b(?:sizing|tier|setup|plan|capacity|size)s?\b[^.]{0,40}\b(?:is|are|looks?|seems?)\s+(?:more than |plenty |quite |very )?(?:appropriate|sufficient|adequate|enough|right|fine|comfortable|generous)\b", re.I)
_GUESS_RE = re.compile(r"\b(?:is|are) (?:likely|probably) (?:needed|required|used)\b|\bprobably (?:needs?|requires?|uses?)\b", re.I)


def check_sentence(sentence, allowed):
    s = sentence.strip()
    if not s:
        return ""
    if s.endswith("?"):
        return "question to the reader"
    if _ONLY_RE.search(s):
        return "claims it is the only option (other priced setups may also fit)"
    if _FIT_RE.search(s):
        return "judges that the size is sufficient (the report does not measure capacity)"
    if _HANDLE_RE.search(s):
        return "capacity or outcome promise (the report does not measure capacity)"
    if _LOSS_RE.search(s):
        return "claims a zero-data-loss guarantee (failover copies are not a guarantee of no data loss)"
    if _GUESS_RE.search(s):
        return "guess about the project, not from the scan"
    return _number_problem(s, allowed) or _path_problem(s, allowed)


def _check_line(line, allowed, removed, section):
    stripped = line.strip()
    if not stripped or stripped.startswith("|") or stripped.startswith("#"):
        return line
    lead = re.match(r"^\s*(?:[-*]\s+|\d+\.\s+)?", line).group(0)
    body = line[len(lead):]
    kept = []
    for sent in _SENT.split(body):
        cut = _ONLY_CLAUSE_RE.sub("", sent) if _ONLY_CLAUSE_RE.search(sent) and not _ONLY_RE.match(sent.strip()) else sent
        if cut != sent:
            removed.append({"section": section, "sentence": sent.strip()[:160], "reason": "claims it is the only option: clause cut"})
            sent = cut.rstrip() + ("." if not cut.rstrip().endswith((".", "!", "?")) else "")
        why = check_sentence(sent, allowed)
        if why:
            removed.append({"section": section, "sentence": sent.strip()[:160], "reason": why})
        else:
            kept.append(sent)
    if not kept:
        return ""
    return lead + " ".join(kept)


def verify(report, allowed):
    """Returns (cleaned report, list of removals)."""
    out, removed, section = [], [], 0
    for line in report.split("\n"):
        m = _HEADING.match(line)
        if m:
            section = int(m.group(1))
        elif line.startswith("## "):
            section = 0
        if section in CHECKED_SECTIONS:
            line = _check_line(line, allowed, removed, section)
        out.append(line)
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return text, removed


def summary(removed):
    if not removed:
        return "claim check: nothing removed"
    reasons = {}
    for r in removed:
        key = r["reason"].split(":")[0]
        reasons[key] = reasons.get(key, 0) + 1
    return "claim check: removed %d sentence(s) (%s)" % (len(removed), ", ".join(f"{n} x {k}" for k, n in sorted(reasons.items())))
