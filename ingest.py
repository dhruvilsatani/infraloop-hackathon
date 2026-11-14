import os
import re
import subprocess
import tempfile

GITHUB_URL_RE = re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(?:\.git)?/?$")


def is_public_mode():
    return os.environ.get("INFRALOOP_PUBLIC") == "1"


def resolve_repo_path(path_or_url):
    """If given a GitHub URL (or any git URL), shallow-clones it to a temp
    directory and returns that local path plus a flag that it needs cleanup
    after use. If given a local path, returns it unchanged with no cleanup
    needed. Only works for repos reachable without credentials -- a private
    repo needs to be cloned locally first (with your own git credentials)
    and pointed at by local path instead."""
    path_or_url = path_or_url.strip()
    if is_public_mode() and not GITHUB_URL_RE.match(path_or_url):
        raise RuntimeError("Please paste a public GitHub link like https://github.com/owner/repo, or upload your project folder.")
    is_url = path_or_url.startswith("http://") or path_or_url.startswith("https://") or path_or_url.endswith(".git")
    if not is_url:
        local = os.path.abspath(os.path.expanduser(path_or_url.strip()))
        if not os.path.isdir(local):
            raise RuntimeError(f"Local path not found or not a folder: {path_or_url}. "
                               "Check the spelling, or paste a GitHub URL instead.")
        return local, False

    temp_dir = tempfile.mkdtemp(prefix="infra_designer_scan_")
    try:
        subprocess.run(
            ["git", "-c", "protocol.file.allow=never", "-c", "core.symlinks=false", "clone", "--depth", "1", "--", path_or_url, temp_dir],
            check=True, capture_output=True, text=True, timeout=180,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError("Cloning took too long (limit 3 minutes). Try a smaller repository or upload the folder.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(
            f"Could not clone {path_or_url} -- is it public and does the URL look right? "
            f"git said: {e.stderr.strip()}"
        ) from e

    return temp_dir, True
