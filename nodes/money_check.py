"""Mechanical guard for money claims. The model was told to use only prices from the computed
table and still wrote figures from memory (and one 10x arithmetic slip). This checks every
euro/dollar figure in the report body and marks the ones that cannot be traced to the table."""
import json
import re

MARK = " [not from the price table]"
FOOTNOTE = ("\n\n_Figures marked \"[not from the price table]\" were not calculated by this tool "
            "(they may be the AI's own estimates or recalled prices). Treat them as unverified._")

MONEY_RE = re.compile(
    r"(?P<r1>\d[\d,]*(?:\.\d+)?)\s?[\u2013\u2014-]\s?(?P<r2>\d[\d,]*(?:\.\d+)?)\+?\s?(?:(?:€|\$)(?:/\s?(?:month|mo)\b)?|/\s?(?:month|mo)\b|per month)"
    r"|(?P<c>\d[\d,]*(?:\.\d+)?)\s?€"
    r"|(?P<sym>[€$])\s?(?P<a>\d[\d,]*(?:\.\d+)?)(?P<k>\s?[kK]\b)?"
    r"|(?P<b>\d[\d,]*(?:\.\d+)?)(?P<k2>\s?[kK]\b)?\s?(?:euros?|EUR|USD|dollars)\b")
NUM_RE = re.compile(r"\d[\d,]*\.?\d*")
TABLE_COST_RE = re.compile(r"\d+\.\d{2}\b")


def _to_float(text):
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


SYMBOL_NUM_RE = re.compile(r"[€$]\s?(\d[\d,]*\.?\d*)")


def _allowed_numbers(cost_text, answers, allowed_totals):
    """Exact table values, symbol-prefixed rates from the table text, the user's own numbers,
    and the ready-made scenario totals. Nothing else is traceable."""
    allowed = set()
    for line in (cost_text or "").splitlines():
        if line.startswith("|"):
            for tok in TABLE_COST_RE.findall(line):
                v = _to_float(tok)
                if v is not None:
                    allowed.add(v)
        for tok in SYMBOL_NUM_RE.findall(line):
            v = _to_float(tok)
            if v is not None:
                allowed.add(v)
    for tok in NUM_RE.findall(json.dumps(answers or {})):   # the user's own numbers (budget, traffic)
        v = _to_float(tok)
        if v is not None:
            allowed.add(v)
    allowed.update(float(v) for v in (allowed_totals or []))
    # plain arithmetic on verified figures is traceable too: budget minus a total, a difference or a sum of two
    # totals, a yearly figure, and the exchange rate printed in the table text
    totals = sorted({round(float(v), 2) for v in (allowed_totals or [])})[:60]
    budgets = [v for v in (_to_float(t) for t in NUM_RE.findall(json.dumps(answers or {}))) if v and v >= 20]
    for t in totals:
        allowed.add(round(t * 12, 2))
        for b in budgets:
            allowed.add(round(b - t, 2))
            allowed.add(round(t - b, 2))
        for u in totals:
            allowed.add(round(abs(t - u), 2))
            allowed.add(round(t + u, 2))
    for line in (cost_text or "").splitlines():
        for tok in re.findall(r"(\d\.\d{3,5})\s*USD per EUR", line):
            allowed.add(float(tok))
    for v in list(allowed_totals or []):          # VAT (19%) on a ready-made total is plain arithmetic
        allowed.add(round(float(v) * 0.19, 2))
        allowed.add(round(float(v) * 1.19, 2))
    return allowed


def _is_traceable(value, allowed):
    tol = 0.5 if value >= 10 else 0.006   # rounding like "~€132" for 131.97; tiny rates must match exactly
    return any(abs(value - a) <= tol for a in allowed)


def mark_unverified_money(report, cost_text, answers=None, allowed_totals=None):
    """Returns the report with untraceable money figures tagged. No table -> nothing is traceable,
    so every figure is tagged."""
    allowed = _allowed_numbers(cost_text or "", answers, allowed_totals)
    changed = False

    def _tag(match):
        nonlocal changed
        if match.group("r1"):
            lo, hi = _to_float(match.group("r1")), _to_float(match.group("r2"))
            if lo is None or hi is None or (_is_traceable(lo, allowed) and _is_traceable(hi, allowed)):
                return match.group(0)
            changed = True
            return match.group(0) + MARK
        raw = match.group("a") or match.group("b") or match.group("c")
        value = _to_float(raw)
        if value is None:
            return match.group(0)
        if match.group("k") or match.group("k2"):
            value *= 1000
        if _is_traceable(value, allowed):
            return match.group(0)
        changed = True
        return match.group(0) + MARK

    marked = MONEY_RE.sub(_tag, report)
    return marked + FOOTNOTE if changed else marked


