from scanner.common import walk_repo

COMPONENT_FOLDERS = {
    "controllers": "controllers",
    "routes": "routes",
    "routers": "routes",
    "models": "models",
    "migrations": "migrations",
    "workers": "workers",
    "jobs": "workers",
    "services": "services",
}


def detect_structure(repo_path):
    """Maps folder naming conventions to a rough component map --
    no code parsing, just recognizing common layout patterns."""
    found = set()
    for root, dirs, files in walk_repo(repo_path):
        for d in dirs:
            if d.lower() in COMPONENT_FOLDERS:
                found.add(COMPONENT_FOLDERS[d.lower()])
    return {"components_found": sorted(found)}


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    print(detect_structure(path))
