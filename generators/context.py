"""Turns the scanner's facts into a small, uniform description of each service, so the templates stay simple.
Only scan facts are used (file names, counts, flags): no source code is read, so this works from a saved scan result."""
from dataclasses import dataclass, field

KIND = {"Python": "python", "JavaScript": "node", "Go": "go"}
PY_ENTRY_ORDER = ("main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py")
NODE_ENTRY_ORDER = ("server.js", "index.js", "app.js", "main.js")
MAX_SERVICES = 5


@dataclass
class Svc:
    path: str                      # "." for the repository root
    kind: str                      # python | node | go
    entrypoint: str = ""
    frameworks: tuple = ()
    env_vars: tuple = ()
    has_tests: bool = False
    has_dockerfile: bool = False
    lockfile: bool = False
    slug: str = "app"
    port: int = 0                  # from the repo's own Dockerfile EXPOSE; 0 = not stated


def join(path, name):
    return name if path in ("", ".") else f"{path.rstrip('/')}/{name}"


def where(path):
    return "the repository root" if path in ("", ".") else path


def _slug(path):
    s = "".join(c if c.isalnum() else "-" for c in path.strip("./")).strip("-").lower()
    return s or "app"


def _pick(entries, order):
    names = {e.split("/")[-1]: e for e in entries}
    for o in order:
        if o in names:
            return names[o]
    return entries[0] if entries else ""


def services(scan):
    """(list of Svc that a template exists for, list of (path, reason) for those that are skipped)."""
    raw = ((scan.get("services") or {}).get("list")) or []
    if not raw:
        langs = list((scan.get("languages") or {}).keys())
        raw = [{"path": ".", "main_language": langs[0] if langs else "", "entrypoints": scan.get("entrypoints") or [],
                "has_tests": bool((scan.get("infra_signals") or {}).get("has_tests"))}] if langs else []
    deps = scan.get("dependencies") or {}
    frameworks = tuple(str(x).lower() for x in (deps.get("web_framework") or []))
    env = tuple(scan.get("env_vars") or [])
    lock = bool((scan.get("dependency_pinning") or {}).get("lockfile_present"))
    out, skipped = [], []
    for x in raw:
        if x.get("client_app") or x.get("container_only"):
            continue
        path = x.get("path") or "."
        kind = KIND.get(x.get("main_language") or "")
        if not kind:
            skipped.append((path, f"no template yet for {x.get('main_language') or 'an unrecognised language'}"))
            continue
        entries = [e for e in (x.get("entrypoints") or []) if isinstance(e, str)]
        entry = _pick(entries, PY_ENTRY_ORDER if kind == "python" else NODE_ENTRY_ORDER if kind == "node" else ())
        out.append(Svc(path=path, kind=kind, entrypoint=entry, frameworks=frameworks, env_vars=env,
                       has_tests=bool(x.get("has_tests")), has_dockerfile=bool(x.get("has_dockerfile")), lockfile=lock, slug=_slug(path), port=int(x.get("port") or 0)))
    if len(out) > MAX_SERVICES:
        skipped += [(s.path, f"more than {MAX_SERVICES} services: only the first {MAX_SERVICES} get files") for s in out[MAX_SERVICES:]]
        out = out[:MAX_SERVICES]
    return out, skipped
