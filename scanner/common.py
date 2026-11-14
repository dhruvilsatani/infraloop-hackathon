import re
import fnmatch
import os
import subprocess

# Directories we never want to walk into — noisy, huge, and irrelevant to production-readiness
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".next", "dist", "build", ".terraform", "vendor", "target", "obj"}


def walk_repo(repo_path):
    """Same as os.walk, but prunes noisy/irrelevant directories in place so every
    scanner layer that needs to walk the tree does it the same, fast, clean way."""
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        yield root, dirs, files


class GitIgnore:
    """Files that exist on disk but that git ignores (a local .env, a private key in a gitignored folder) are not part of the repository.
    Only available when the folder has a .git directory and git is installed; otherwise nothing is treated as ignored."""

    def __init__(self, repo_path):
        self.files, self.dirs, self.active = set(), [], False
        if not os.path.isdir(os.path.join(repo_path, ".git")):
            self._from_gitignore_file(repo_path)
            return
        try:
            out = subprocess.run(["git", "-C", repo_path, "ls-files", "-o", "-i", "--exclude-standard", "--directory", "-z"],
                                 capture_output=True, timeout=30).stdout.decode("utf-8", "ignore")
        except (OSError, subprocess.SubprocessError):
            return
        for p in out.split("\0"):
            if not p:
                continue
            if p.endswith("/"):
                self.dirs.append(p)
            else:
                self.files.add(p)
        self.active = True

    def _from_gitignore_file(self, repo_path):
        """No .git folder (a web upload): read every .gitignore ourselves (also one inside a wrapper folder such as
        repo-main/). Simple patterns only; negations are skipped so we never hide a file wrongly."""
        self.patterns = []                      # (folder prefix of the .gitignore, pattern)
        seen = 0
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__MACOSX", ".venv", "venv")]
            if ".gitignore" not in files:
                continue
            seen += 1
            if seen > 50:
                break
            prefix = os.path.relpath(root, repo_path).replace("\\", "/")
            prefix = "" if prefix == "." else prefix + "/"
            try:
                with open(os.path.join(root, ".gitignore"), encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        line = line.strip()
                        if line and not line.startswith(("#", "!")):
                            self.patterns.append((prefix, line))
            except OSError:
                continue
        self.active = bool(self.patterns)

    def _match_patterns(self, rel):
        for prefix, pat in self.patterns:
            if not rel.startswith(prefix):
                continue
            sub = rel[len(prefix):]
            parts = sub.split("/")
            anchored = pat.startswith("/") or ("/" in pat.rstrip("/"))
            dir_only = pat.endswith("/")
            pat = pat.strip("/")
            if not pat:
                continue
            if anchored:
                if fnmatch.fnmatch(sub, pat) or sub.startswith(pat + "/"):
                    return True
            else:
                cand = parts[:-1] if dir_only else parts
                if any(fnmatch.fnmatch(x, pat) for x in cand):
                    return True
        return False

    def __contains__(self, rel):
        rel = rel.replace("\\", "/")
        if getattr(self, "patterns", None):
            return self._match_patterns(rel)
        return rel in self.files or any(rel.startswith(d) for d in self.dirs)


# Paths whose contents describe a development/test setup, not the production system.
DEV_ONLY_PARTS = {".devcontainer", "devcontainer", ".vscode", ".examples", ".example", "test", "tests", "testing", "e2e",
                  "fixtures", "example", "examples", "sample", "samples", "docs", "doc",
                  "templates", "template", "skeleton", "scaffold", "boilerplate"}


def path_dirs(rel_path):
    """Directory parts of a path, lower-cased. Everything below src/main/java (or kotlin, scala) is a package name,
    not a folder: org/cloudfoundry/samples/music says nothing about the repo being a sample."""
    parts = rel_path.lower().replace("\\", "/").split("/")[:-1]
    for i in range(len(parts) - 1):
        if parts[i] in ("java", "kotlin", "scala", "groovy") and i >= 1 and parts[i - 1] in ("main", "test", "integrationtest", "testfixtures", "jmh"):
            return parts[:i + 1]
    return parts


def is_dev_only_path(rel_path):
    """True when a file sits in a dev/test/example folder, or is itself named like a test file."""
    parts = rel_path.lower().replace("\\", "/").split("/")
    name = parts[-1]
    if any(p in DEV_ONLY_PARTS for p in path_dirs(rel_path)):
        return True
    return ".test." in name or name.endswith(".test.yml") or name.endswith(".test.yaml")


TEST_PARTS = {"bdd", "t", "suites", "test_resources", "test", "tests", "testing", "e2e", "fixtures", "fixture", "testdata", "__tests__", "spec", "specs",
              "syntax-tests", "__fixtures__", "mocks", "__mocks__", "integrationtest", "integration-test", "integration-tests", "integration_tests", "integrationtests"}


def is_test_path(rel_path):
    """True for files inside test / fixture folders (a Terraform file in tests/ is not the project's infra)."""
    return any(p in TEST_PARTS for p in path_dirs(rel_path))


# ---- Dockerfiles that are not "the application's production image" ----------------------------------------------
DEV_DOCKERFILE_SUFFIXES = {"debug", "dev", "develop", "development", "local", "test", "tests", "ci", "e2e", "devcontainer", "sandbox"}
MONITORING_STACK_DIRS = {"grafana", "prometheus", "alertmanager", "loki", "promtail", "tempo", "mimir", "jaeger", "zipkin",
                         "kibana", "logstash", "fluentd", "fluent-bit", "fluentbit", "telegraf", "influxdb", "otel-collector",
                         "otelcol", "node-exporter", "cadvisor"}
_MONITORING_BASE_RE = re.compile(
    r"^\s*FROM\s+(?:--platform=\S+\s+)?(?:[\w.\-]+/)*?(grafana(?:/[\w.\-]+)?|prom/\S+|prometheus\S*|bitnami/prometheus\S*|quay\.io/prometheus/\S+|"
    r"jaegertracing/\S+|openzipkin/\S+|docker\.elastic\.co/\S+|elastic/\S+|fluent/\S+|otel/opentelemetry-collector\S*|grafana/(?:loki|tempo|mimir|promtail)\S*)",
    re.I | re.M)


def dockerfile_role(rel_path, text=""):
    """'dev' (a debug/dev/test variant), 'monitoring' (an image of the monitoring stack, e.g. docker/grafana/Dockerfile)
    or 'app'. Only 'app' Dockerfiles count as the project's production images."""
    parts = rel_path.replace("\\", "/").split("/")
    name = parts[-1].lower()
    suffix = ""
    if name.startswith(("dockerfile.", "containerfile.")):
        suffix = name.split(".", 1)[1]
    elif name.endswith((".dockerfile", ".containerfile")):
        suffix = name.rsplit(".", 2)[0].rsplit(".", 1)[-1] if name.count(".") >= 2 else ""
    # test fixtures and CI/editor helper images are not the project's images (goreleaser keeps 13 Dockerfiles under testdata/)
    if len(parts) > 1 and any(d.lower() in TEST_PARTS or d.lower() in (".github", ".codesandbox", ".devcontainer", ".gitlab") for d in parts[:-1]):
        return "dev"
    if suffix and any(tok in DEV_DOCKERFILE_SUFFIXES for tok in re.split(r"[._-]", suffix)):
        return "dev"
    if len(parts) > 1 and any(d.lower() in MONITORING_STACK_DIRS for d in parts[:-1]):
        return "monitoring"
    if text and _MONITORING_BASE_RE.search(text[:3000]) and len(re.findall(r"^\s*(?:COPY|ADD)\b", text, re.M)) <= 6 and not re.search(r"^\s*RUN\s+.*(?:npm|pip|mvn|gradle|go build|cargo|dotnet)", text, re.M):
        return "monitoring"
    return "app"
