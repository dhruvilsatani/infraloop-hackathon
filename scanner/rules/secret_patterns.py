import re

# Each pattern looks for the SHAPE of a secret, never confirms a real one.
# We only ever report the type and location of a match -- never the matched text itself.

SECRET_PATTERNS = {
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "aws_secret_key_assignment": re.compile(r"(?i)aws_?secret_?(?:access_?)?key\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}['\"]?"),
    "generic_api_key_assignment": re.compile(r"(?i)(api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[=:]\s*['\"]([A-Za-z0-9_\-]{16,})['\"]"),
    "stripe_live_key": re.compile(r"sk_live_[0-9a-zA-Z]{20,}"),
    "stripe_key_any": re.compile(r"\b[sr]k_(?:live|test)_[0-9a-zA-Z]{20,}"),
    "private_key_header": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----\s*(?:\\n|\\r\\n)?[A-Za-z0-9+/=]{40,}"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b|github_pat_[A-Za-z0-9_]{50,}"),
    "gitlab_token": re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    "google_api_key": re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    "sendgrid_key": re.compile(r"\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}"),
    "twilio_key": re.compile(r"\bSK[0-9a-f]{32}\b"),
    "npm_token": re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    "azure_storage_key": re.compile(r"AccountKey=[A-Za-z0-9+/=]{40,}"),
    "database_url_with_password": re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://([^\s:/@'\"]+):([^\s@/'\"$]{4,})@([\w.\-]+)"),
}

# Words that mean "this is a placeholder, not a real secret"
DEFAULT_PASSWORDS = {"postgres", "root", "admin", "pass", "secret", "changeme", "test", "1234", "12345", "123456",
                     "mysql", "redis", "dev", "guest", "default", "mongo", "rabbit", "toor", "letmein", "welcome",
                     "mypassword", "docker", "db", "database", "user", "demo"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "db", "postgres", "mysql", "redis", "mongo", "database", "host", "0.0.0.0"}

PLACEHOLDER_HINTS = ("devstoreaccount1", "eby8vdm02xnocqflqu", "xxxx", "example", "your_", "your-", "changeme", "change_me", "placeholder", "dummy",
                     "<", "${", "{{", "password", "secret", "redacted", "sample", "fake", "test", "todo")


# cheap substring that must be present before the (slower) regex is tried -- keeps big repos fast
TRIGGERS = {
    "aws_access_key": ("AKIA", "ASIA"), "aws_secret_key_assignment": ("aws",), "stripe_live_key": ("sk_live_",),
    "stripe_key_any": ("sk_live", "sk_test", "rk_live", "rk_test"), "private_key_header": ("PRIVATE KEY",), "github_token": ("ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"),
    "gitlab_token": ("glpat-",), "slack_token": ("xox",), "google_api_key": ("AIza",), "sendgrid_key": ("SG.",),
    "twilio_key": ("SK",), "npm_token": ("npm_",), "azure_storage_key": ("AccountKey=",),
    "database_url_with_password": ("://",),
}
TRIGGER_RE = {k: re.compile("|".join(re.escape(t) for t in v)) for k, v in TRIGGERS.items()}


GENERIC_GATE = re.compile(r"[=:]\s*['\"]([A-Za-z0-9_\-]{16,})['\"]")
GENERIC_KEY_END = re.compile(r"(?i)(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)['\"]?\s*$")


def _on_comment_line(text, pos):
    start = text.rfind("\n", 0, pos) + 1
    return text[start:pos].lstrip().startswith(("#", "//", "*", "/*", "--", "<!--", ";"))


PUBLIC_KEY_CONTEXT = re.compile(r"(?i)algolia|docsearch|typesense|recaptcha|sitekey|site_key|publishable|mapbox|measurement_?id|posthog|segment")


def _generic_assignment_found(text):
    """Fast path: find `= "<16+ chars>"` first (cheap), then look just before it for a key-like name.
    Returns True, "comment" (only found on commented-out lines) or False."""
    comment_hit = False
    for m in GENERIC_GATE.finditer(text):
        if not GENERIC_KEY_END.search(text[max(0, m.start() - 24):m.start()]):
            continue
        value = m.group(1)
        around = text[max(0, m.start() - 600):m.end() + 60]
        # keys that are public by design (search-only Algolia keys, reCAPTCHA site keys, ...) and sample keys inside documentation strings
        if PUBLIC_KEY_CONTEXT.search(around) or "\\n" in text[max(0, m.start() - 160):m.start()]:
            continue
        token = text[max(0, m.start() - 24):m.end()].lower()
        if any(h in token for h in PLACEHOLDER_HINTS):
            continue
        if not (re.search(r"\d", value) and re.search(r"[A-Za-z]", value)) or re.fullmatch(r"[A-Z_]+|[a-z_\-]+", value) \
                or len(re.findall(r"\d", value)) <= 2 or re.search(r"(.)\1{7,}", value):
            continue                      # a name like edischarge1Today is an identifier, a real key has many digits
        if _on_comment_line(text, m.start()):
            comment_hit = True
            continue
        return True
    return "comment" if comment_hit else False


def scan_text_for_secrets(text):
    """Returns a list of {'pattern_type': ...} dicts for any secret-shaped text found.
    Never returns the matched text itself -- only which pattern fired.
    Matches that look like placeholders (xxxx, example, ${VAR}...) are ignored."""
    findings = []
    low = None
    commented = False
    for pattern_type, pattern in SECRET_PATTERNS.items():
        commented = False
        if pattern_type == "generic_api_key_assignment":
            hit = _generic_assignment_found(text)
            if hit:
                findings.append({"pattern_type": pattern_type, "in_comment": hit == "comment"})
            continue
        else:
            trig = TRIGGER_RE.get(pattern_type)
            if trig and not trig.search(text):
                if pattern_type != "aws_secret_key_assignment":
                    continue
                low = low if low is not None else text.lower()
                if "aws" not in low:
                    continue
        for m in pattern.finditer(text):
            token = m.group(0).lower()
            if pattern_type not in ("private_key_header",) and any(h in token for h in PLACEHOLDER_HINTS):
                continue
            if pattern_type == "database_url_with_password":
                user, pw, host = m.group(1), m.group(2), m.group(3)
                line_start = text.rfind("\n", 0, m.start()) + 1
                if text[line_start:m.start()].lstrip().startswith(("#", "//", "*", "--", "<!--", ">")):
                    continue  # documentation / comment example, not configuration
                if pw.lower() in DEFAULT_PASSWORDS or pw.lower() == user.lower() or host.lower() in LOCAL_HOSTS:
                    findings.append({"pattern_type": "database_url_default_credentials"})
                    break
            if pattern_type == "generic_api_key_assignment":
                value = m.group(2)
                # a real secret mixes letters and digits; constant names like "HTTP_USER_API_KEY" do not
                if not (re.search(r"\d", value) and re.search(r"[A-Za-z]", value)) or \
                        re.fullmatch(r"[A-Z_]+|[a-z_\-]+", value) or len(re.findall(r"\d", value)) <= 2 or re.search(r"(.)\1{7,}", value):
                    continue
            if pattern_type != "private_key_header" and _on_comment_line(text, m.start()):
                commented = True              # a sample in a comment: keep looking for a real assignment, else report it as a comment
                continue
            findings.append({"pattern_type": pattern_type})
            commented = False
            break
        else:
            if commented and pattern_type != "private_key_header":
                findings.append({"pattern_type": pattern_type, "in_comment": True})
        commented = False
    return findings
