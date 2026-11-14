"""Folder upload for the web app.

The browser sends a project folder as JSON batches of {path, text}. This module rebuilds the folder in a temporary
directory so the normal scanner can read it, and enforces every rule on the server side (the browser's own filtering is
only there to save bandwidth; it is never trusted):

  * paths are checked: no absolute paths, no "..", no empty or odd parts, no symlinks are ever created
  * folders that are only build output or dependencies (node_modules, .git, ...) are dropped
  * secret files (.env, private keys, ...) are NEVER stored with content: an empty placeholder is written so the scanner
    can still say "a secret file is committed" without the content ever reaching this server's disk or the model
  * binary or very large files become empty placeholders (their presence still counts, their content is not needed)
  * size and file-count limits, and a time limit after which stale uploads are deleted
"""
import os
import re
import shutil
import tempfile
import time
import uuid

UPLOAD_PREFIX = "infraloop_upload_"
MAX_FILES = 100000
MAX_TOTAL_BYTES = 120 * 1024 * 1024        # content actually stored
MAX_FILE_BYTES = 1024 * 1024               # bigger files become placeholders
MAX_BATCH_FILES = 1500
STALE_SECONDS = 3600

SKIP_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".next", ".nuxt",
    ".svelte-kit", ".gradle", ".terraform", ".idea", ".cache", "bower_components", "Pods", ".dart_tool", "target", "dist",
    "coverage", "vendor", ".parcel-cache", ".turbo", ".yarn", ".pnpm-store", "site-packages",
}
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg", ".pdf", ".zip", ".gz", ".tgz", ".tar", ".bz2", ".xz", ".7z",
    ".rar", ".jar", ".war", ".class", ".so", ".dll", ".dylib", ".exe", ".bin", ".o", ".a", ".pyc", ".woff", ".woff2", ".ttf",
    ".otf", ".eot", ".mp3", ".mp4", ".mov", ".avi", ".wav", ".webm", ".onnx", ".pt", ".pth", ".h5", ".pkl", ".parquet",
    ".sqlite", ".db", ".dmp", ".iso", ".dmg", ".pptx", ".docx", ".xlsx", ".ipynb_checkpoints",
}
SECRET_NAME_RE = re.compile(
    r"^(\.env(\..+)?|.*\.pem|.*\.key|.*\.p12|.*\.pfx|.*\.jks|.*\.keystore|id_(rsa|dsa|ecdsa|ed25519)(\.pub)?|\.npmrc|\.pypirc|\.netrc|"
    r"credentials(\.json)?|service[-_]account.*\.json|.*\.tfvars|secrets?\.(ya?ml|json|toml)|.*\.kdbx)$", re.I)
SECRET_ALLOWED_RE = re.compile(r"\.(example|sample|template|dist|defaults?)$|^\.env\.(example|sample|template|dist)$", re.I)


class UploadError(ValueError):
    pass


def classify(path, size=0):
    """'skip' (dropped), 'placeholder' (an empty file stands in for it) or 'send' (content is used)."""
    parts = path.split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return "skip"
    name = parts[-1]
    if SECRET_NAME_RE.match(name) and not SECRET_ALLOWED_RE.search(name):
        return "placeholder"
    if os.path.splitext(name)[1].lower() in BINARY_EXTENSIONS or size > MAX_FILE_BYTES:
        return "placeholder"
    return "send"


def clean_relative_path(raw):
    """Returns a normalised relative posix path or raises UploadError."""
    if not isinstance(raw, str) or not raw or len(raw) > 400 or "\x00" in raw or "\\" in raw:
        raise UploadError("bad file path")
    if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
        raise UploadError("absolute paths are not allowed")
    parts = raw.split("/")
    if any(p in ("", ".", "..") or len(p) > 200 for p in parts):
        raise UploadError("bad file path")
    return "/".join(parts)


def _upload_dir(upload_id):
    try:
        uuid.UUID(str(upload_id))
    except ValueError:
        raise UploadError("unknown upload")
    return os.path.join(tempfile.gettempdir(), UPLOAD_PREFIX + str(upload_id))


def cleanup_stale(now=None):
    now = now or time.time()
    tmp = tempfile.gettempdir()
    try:
        for name in os.listdir(tmp):
            if name.startswith(UPLOAD_PREFIX):
                p = os.path.join(tmp, name)
                try:
                    if now - os.path.getmtime(p) > STALE_SECONDS:
                        shutil.rmtree(p, ignore_errors=True)
                except OSError:
                    pass
    except OSError:
        pass


def start_upload():
    cleanup_stale()
    upload_id = str(uuid.uuid4())
    os.makedirs(_upload_dir(upload_id))
    with open(os.path.join(_upload_dir(upload_id), ".state"), "w") as f:
        f.write("0 0")
    return upload_id


def _read_state(base):
    try:
        a, b = open(os.path.join(base, ".state")).read().split()
        return int(a), int(b)
    except (OSError, ValueError):
        return 0, 0


def add_files(upload_id, files):
    """files: list of {"path": "myproject/src/app.py", "text": "...", "size": 123, "kind": "send|placeholder"}.
    Returns counts. The first path component is the project folder name."""
    base = _upload_dir(upload_id)
    if not os.path.isdir(base):
        raise UploadError("unknown or expired upload")
    if not isinstance(files, list) or len(files) > MAX_BATCH_FILES:
        raise UploadError("too many files in one batch")
    count, total = _read_state(base)
    stored = placeholders = skipped = 0
    root_name = None
    for item in files:
        if not isinstance(item, dict):
            raise UploadError("bad file entry")
        rel = clean_relative_path(item.get("path"))
        parts = rel.split("/")
        if len(parts) < 2:
            raise UploadError("files must be inside the project folder")
        text = item.get("text") or ""
        if not isinstance(text, str):
            raise UploadError("bad file content")
        verdict = classify("/".join(parts[1:]), len(text.encode("utf-8", "ignore")))
        if verdict == "skip":
            skipped += 1
            continue
        count += 1
        if count > MAX_FILES:
            raise UploadError(f"too many files (limit {MAX_FILES}); remove build output or dependencies from the folder")
        data = b"" if verdict == "placeholder" else text.encode("utf-8", "ignore")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise UploadError("the folder is too large (limit 120 MB of text)")
        dest = os.path.realpath(os.path.join(base, *parts))
        if not dest.startswith(os.path.realpath(base) + os.sep):
            raise UploadError("bad file path")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.islink(dest):
            raise UploadError("bad file path")
        with open(dest, "wb") as f:
            f.write(data)
        stored += verdict == "send"
        placeholders += verdict == "placeholder"
        root_name = root_name or parts[0]
    with open(os.path.join(base, ".state"), "w") as f:
        f.write(f"{count} {total}")
    return {"stored": stored, "placeholders": placeholders, "skipped": skipped}


def project_path(upload_id):
    """The folder to scan: the single project folder inside the upload directory."""
    base = _upload_dir(upload_id)
    if not os.path.isdir(base):
        raise UploadError("unknown or expired upload")
    tops = [d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))]
    if len(tops) != 1:
        raise UploadError("expected one project folder; nothing usable was uploaded" if not tops else "the upload contains more than one top folder")
    return os.path.join(base, tops[0])


def remove_upload(upload_id):
    try:
        shutil.rmtree(_upload_dir(upload_id), ignore_errors=True)
    except UploadError:
        pass
