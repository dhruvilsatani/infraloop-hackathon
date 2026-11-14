import os
import re

from scanner.rules.secret_patterns import scan_text_for_secrets

README_FILENAME_PATTERN = re.compile(r"^readme(\.(md|rst|txt))?$", re.IGNORECASE)
MAX_README_CHARS = 1500

FENCED_BLOCK = re.compile(r"```.*?```", re.DOTALL)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
MD_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
HTML_TAG = re.compile(r"<[^>]+>")


def _sanitize_readme(text):
    """Deterministic cleanup so the README can't smuggle instructions in the places
    they usually hide: code blocks, HTML comments, link targets, image tags."""
    text = FENCED_BLOCK.sub("", text)
    text = HTML_COMMENT.sub("", text)
    text = MD_IMAGE.sub("", text)
    text = MD_LINK.sub(r"\1", text)
    text = HTML_TAG.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_project_docs(repo_path):
    """Reads the repo's root README so the LLM can understand what the project is
    FOR -- but only as sanitized, size-capped, untrusted text. The secret check runs
    on the RAW text first (a key inside a code block must still be caught); if
    anything secret-shaped is found the README is withheld entirely."""
    if not os.path.isdir(repo_path):
        return {"readme_excerpt": None}

    for fname in os.listdir(repo_path):
        if not README_FILENAME_PATTERN.match(fname):
            continue
        full_path = os.path.join(repo_path, fname)
        if not os.path.isfile(full_path):
            continue
        try:
            with open(full_path, "r", errors="ignore") as f:
                content = f.read()
        except (IOError, OSError):
            continue

        if scan_text_for_secrets(content):
            return {
                "readme_excerpt": None,
                "readme_withheld_reason": f"{fname} appears to contain secret-shaped text and was withheld from the LLM",
            }

        cleaned = _sanitize_readme(content)
        return {
            "readme_excerpt": cleaned[:MAX_README_CHARS],
            "readme_truncated": len(cleaned) > MAX_README_CHARS,
        }

    return {"readme_excerpt": None}


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    print(detect_project_docs(path))
