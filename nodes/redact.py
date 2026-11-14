"""Secrets must never reach the LLM. Free-text answers and notes are cleaned before they are used."""
import re

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"),                       # user:password@host in URLs
    re.compile(r"(?i)\b(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key)\b\s*[:=]\s*\S+"),
]
MARK = "[removed: looked like a secret]"


def redact_secrets(text):
    out = str(text or "")
    for rx in _PATTERNS:
        out = rx.sub(MARK, out)
    return out


def redact_answers(answers):
    return {k: redact_secrets(v) if isinstance(v, str) else v for k, v in (answers or {}).items()}


# ---- untrusted free text: answers and notes are DATA for the report, never instructions ----
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏‪-‮⁠﻿]")
_INJECTION_RES = [re.compile(p, re.I) for p in (
    r"ignore\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier)[^.\n]*",
    r"disregard\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|instructions|rules)[^.\n]*",
    r"forget\s+(?:everything|all|your|the)\s+(?:above|previous|instructions|rules)[^.\n]*",
    r"(?:reveal|show|print|repeat|leak|output)\s+(?:me\s+)?(?:your|the)\s+(?:system\s+prompt|instructions|rules|prompt|judgment\s+rules|hidden)[^.\n]*",
    r"\bsystem\s+prompt\b[^.\n]*",
    r"you\s+are\s+now\b[^.\n]*",
    r"\bact\s+as\s+(?:if\b|a\s+(?:different|new|jailbroken|unrestricted|hacker)|dan\b)[^.\n]*",
    r"\bnew\s+instructions?\s*:[^\n]*",
    r"</?\s*(?:system|assistant|user|instructions?|prompt)\s*>",
    r"^\s*(?:system|assistant)\s*:",
    r"\bjailbreak\b[^.\n]*",
    r"\bDAN\s+mode\b[^.\n]*",
)]
INJECTION_MARK = "[removed: looked like an instruction to the AI]"


def clean_free_text(text, limit=600):
    """Control characters out, secrets out, instruction-like sentences out, length capped."""
    out = _CONTROL_RE.sub("", str(text or ""))
    out = redact_secrets(out)
    out = out.replace("```", "'''")
    for rx in _INJECTION_RES:
        out = rx.sub(INJECTION_MARK, out)
    out = re.sub(r"[ \t]+", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out[:limit]


def clean_answers(answers, known_questions=None, choice_options=None, limit=600):
    """Keep only answers to questions we asked; choice answers must be one of the offered options."""
    cleaned = {}
    for key, value in (answers or {}).items():
        key = str(key)
        if known_questions is not None and key not in known_questions:
            continue
        value = str(value if value is not None else "")
        options = (choice_options or {}).get(key)
        if options is not None:
            if value in options:
                cleaned[key] = value
            continue
        value = clean_free_text(value, limit)
        if value:
            cleaned[key] = value
    return cleaned
