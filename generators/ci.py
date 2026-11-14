"""GitHub Actions workflow, dependabot config and .env.example. Only first-party actions are used (checkout, setup-*)."""
from .model import Artifact, HEADER
from .registry import generator
from .context import services, join
from .docker import _commented

_DOCKER_GAPS = {"no_dockerfile", "services_without_dockerfile"}
ECOSYSTEM = {"python": "pip", "node": "npm", "go": "gomod"}


def _job(s, with_docker):
    wd = "" if s.path == "." else f"    defaults:\n      run:\n        working-directory: {s.path}\n"
    steps = ["      - uses: actions/checkout@v4"]
    if s.kind == "python":
        steps += ['      - uses: actions/setup-python@v5', '        with:', '          python-version: "3.12"',
                  "      - run: pip install -r requirements.txt"]
        if s.has_tests:
            steps += ["      - run: pip install pytest", "      - run: python -m pytest"]
        else:
            steps += ["      # No tests were found by the scan: add a test step here once you have tests.", "      - run: python -m compileall -q ."]
    elif s.kind == "node":
        steps += ["      - uses: actions/setup-node@v4", "        with:", '          node-version: "22"']
        steps += [f"      - run: {'npm ci' if s.lockfile else 'npm install'}", "      - run: npm test --if-present"]
    else:
        steps += ["      - uses: actions/setup-go@v5", "        with:", "          go-version-file: " + join(s.path, "go.mod"),
                  "      - run: go vet ./...", "      - run: go test ./...", "      - run: go build ./..."]
    if with_docker:
        steps.append("      - run: docker build -t app:ci .")
    return f"  {s.slug}:\n    runs-on: ubuntu-latest\n{wd}    steps:\n" + "\n".join(steps) + "\n"


@generator("no_cicd")
def workflow(scan, gaps):
    svcs, _ = services(scan)
    if not svcs:
        return []
    head = _commented(HEADER) + """name: CI
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
"""
    issues = {g["issue"] for g in gaps}
    body = "".join(_job(s, with_docker=s.has_dockerfile or bool(_DOCKER_GAPS & issues)) for s in svcs)
    review = ["Check the branch name under `on: push` (main is assumed).", "The workflow only builds and tests. It does not deploy anything."]
    if any(s.has_dockerfile or bool(_DOCKER_GAPS & issues) for s in svcs):
        review.append("The last step of each job builds the Docker image from the Dockerfile in that folder.")
    if any(not s.has_tests for s in svcs):
        review.append("Some services have no tests: the workflow only checks that they compile or start installing. Add real tests.")
    return [Artifact(path=".github/workflows/ci.yml", content=head + body, gap="no_cicd", title="GitHub Actions workflow (build and test)",
                     confidence="medium", assumptions=["GitHub is the host (the file is a GitHub Actions workflow).", "One job per service folder."], review=review)]


@generator("no_dependency_update_bot")
def dependabot(scan, gaps):
    svcs, _ = services(scan)
    if not svcs:
        return []
    blocks = []
    for s in svcs:
        d = "/" if s.path == "." else "/" + s.path.strip("/")
        blocks.append(f'  - package-ecosystem: "{ECOSYSTEM[s.kind]}"\n    directory: "{d}"\n    schedule:\n      interval: "weekly"\n')
        blocks.append(f'  - package-ecosystem: "docker"\n    directory: "{d}"\n    schedule:\n      interval: "weekly"\n')
    blocks.append('  - package-ecosystem: "github-actions"\n    directory: "/"\n    schedule:\n      interval: "weekly"\n')
    seen, uniq = set(), []
    for b in blocks:
        if b not in seen:
            seen.add(b)
            uniq.append(b)
    return [Artifact(path=".github/dependabot.yml", content=_commented(HEADER) + "version: 2\nupdates:\n" + "".join(uniq), gap="no_dependency_update_bot",
                     title="Dependabot configuration", confidence="high", assumptions=["The repository is hosted on GitHub."],
                     review=["The docker entries only matter once a Dockerfile exists in that folder."])]


@generator()
def env_example(scan, gaps):
    """Config names found in the code, with empty values. Never any real value: the scanner does not keep them."""
    names = [n for n in (scan.get("env_vars") or []) if isinstance(n, str)]
    if not names or (scan.get("repo_hygiene") or {}).get("env_example"):
        return []
    lines = "".join(f"{n}=\n" for n in sorted(set(names)))
    return [Artifact(path=".env.example", content=_commented(HEADER) + "# Copy to .env and fill in real values. Never commit .env.\n" + lines, gap="",
                     title=".env.example (names only)", confidence="medium",
                     assumptions=["The names come from environment variables the scan found in the code."],
                     review=["Remove names you do not need, and add a short comment for each.", "Make sure .env itself is listed in .gitignore."])]
