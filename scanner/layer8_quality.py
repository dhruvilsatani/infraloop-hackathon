"""Layer 8: quality of what exists (not just whether it exists).

Everything returned is booleans, short words (none / some / most / all) or file NAMES.
No file contents leave this module."""
import os
import re

from scanner.common import walk_repo, is_dev_only_path, dockerfile_role

MAX_FILE_BYTES = 400_000
MAX_DOCKERFILES = 60

TEST_WORDS = ("pytest", "npm test", "npm run test", "yarn test", "pnpm test", "go test", "mvn test", "mvn verify",
              "mvnw test", "gradle test", "gradlew test", "dotnet test", "cargo test", "rspec", "bundle exec rake test",
              "phpunit", "make test", "tox", "unittest", "ctest", "jest", "vitest", "playwright test", "cypress run",
              "bin/rails test", "rails test", "manage.py test")
TEST_CMD_RE = re.compile(
    r"(?:make|mage|task|just|nox|npm run|yarn|pnpm|bun|bazel|bazelisk|pants|rake|gradlew?|mvnw?|dotnet|cargo|go|"
    r"ctest|pytest|jest|vitest|phpunit|rspec|bundle exec|python -m|poetry run|uv run|hatch run|tox)\s+(?:-\S+\s+)*"
    r"(?:test|tests|check|verify|ci|spec|unittest|pytest)\b")
# Maven/Gradle lifecycle commands that run the unit tests unless tests are explicitly skipped.
JVM_BUILD_RE = re.compile(r"\b(?:mvnw?|gradlew?)\b([^\n]*)")
JVM_TEST_PHASES = re.compile(r"(?<![\w-])(?:package|install|verify|build|check|test|integration-test)(?![\w-])")
JVM_SKIP_RE = re.compile(r"-D(?:skipTests|maven\.test\.skip|skipITs)(?:=true)?\b|-x\s+test\b|--exclude-task\s+test", re.I)


def _jvm_build_runs_tests(blob):
    for m in JVM_BUILD_RE.finditer(blob):
        args = m.group(1)
        if JVM_TEST_PHASES.search(args) and not JVM_SKIP_RE.search(args):
            return True
    return False


BUILD_IMAGE_WORDS = ("docker build", "docker/build-push-action", "buildx", "kaniko", "podman build", "jib:build",
                     "ko build", "ko publish", "docker push", "buildah", "docker compose build", "docker-compose build")
DEPLOY_WORDS = ("kubectl apply", "kubectl set image", "helm upgrade", "helm install", "terraform apply",
                "aws ecs update-service", "aws-actions/amazon-ecs-deploy", "gcloud run deploy", "gcloud app deploy",
                "az webapp", "azure/webapps-deploy", "serverless deploy", "sls deploy", "vercel deploy", "vercel --prod",
                "flyctl deploy", "fly deploy", "argocd app sync", "cdk deploy", "ansible-playbook", "pulumi up",
                "pulumi/actions", "netlify deploy", "railway up", "heroku", "cloud-sdk-deploy", "deploy-cloudrun")
SECURITY_WORDS = ("trivy", "snyk", "codeql", "semgrep", "bandit", "gitleaks", "trufflehog", "dependency-review",
                  "grype", "sonarqube", "sonarcloud", "checkov", "tfsec", "osv-scanner", "npm audit", "pip-audit",
                  "safety check", "hadolint", "anchore", "ossf/scorecard", "govulncheck", "cargo audit",
                  "bundler-audit", "brakeman", "detect-secrets", "sonar", "kics", "docker scout", "docker/scout-action",
                  "veracode", "fossa", "whitesource", "dependency-check", "owasp", "gosec", "aquasecurity", "cargo-audit", "cargo deny", "cargo-deny")
LINT_WORDS = ("eslint", "ruff", "flake8", "pylint", "golangci", "black ", "prettier", "rubocop", "clippy", "checkstyle",
              "mypy", "tsc ", "spotless", "pre-commit", "standardrb", "phpcs", "phpstan", "biome", "shellcheck", "yamllint")

LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Pipfile.lock",
             "go.sum", "Cargo.lock", "Gemfile.lock", "composer.lock", "packages.lock.json", "gradle.lockfile",
             "bun.lockb", "bun.lock"}
MANIFESTS_NEEDING_LOCK = {"package.json", "pyproject.toml", "requirements.txt", "go.mod", "Cargo.toml", "Gemfile",
                          "composer.json"}


def _read(path, limit=MAX_FILE_BYTES):
    try:
        if os.path.getsize(path) > limit:
            return ""
        with open(path, "r", errors="ignore") as fh:
            return fh.read()
    except (IOError, OSError):
        return ""


def _words(part, total):
    if total == 0 or part == 0:
        return "none"
    r = part / total
    return "all" if r >= 1 else ("most" if r >= 0.7 else "some")


PROD_STAGE_NAMES = ("production", "prod", "release", "runtime", "final", "deploy", "app", "server")


def _stages(lines):
    """[(name_or_None, base_image, lines_of_stage)] in file order."""
    stages = []
    for l in lines:
        m = re.match(r"^\s*FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", l, re.IGNORECASE)
        if m:
            stages.append([(m.group(2) or "").lower() or None, m.group(1), [l]])
        elif stages:
            stages[-1][2].append(l)
    return stages


def _target_stage(stages):
    """The stage that ships: one named like production/runtime/final if present, otherwise the last (Docker's default)."""
    for st in reversed(stages):
        if st[0] in PROD_STAGE_NAMES:
            return st
    return stages[-1] if stages else None


def _stage_property(stages, stage, pattern, depth=0):
    """Last line matching pattern in the stage; if none, inherited from the stage it was built FROM."""
    hits = [m for m in (re.match(pattern, l, re.IGNORECASE) for l in stage[2]) if m]
    if hits:
        return hits[-1]
    if depth < 10:
        for parent in stages:
            if parent is not stage and parent[0] and parent[0] == stage[1].lower():
                return _stage_property(stages, parent, pattern, depth + 1)
    return None


def _final_stage(lines):
    """Lines of the stage that ships (kept for callers that only need the text)."""
    st = _target_stage(_stages(lines))
    return st[2] if st else lines


def _analyse_dockerfile(text):
    lines = [l for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    stages = _stages(lines)
    stage_names = {st[0] for st in stages if st[0]}
    target = _target_stage(stages)
    base = target[1] if target else ""
    unpinned = False
    if base and base.lower() != "scratch" and base.lower() not in stage_names and "$" not in base:
        name = base.split("@")[0]
        tag = name.rsplit(":", 1)[1] if ":" in name.split("/")[-1] else ""
        unpinned = ("@sha256" not in base) and (tag == "" or tag.lower() in ("latest", "stable", "lts", "current"))
    user = _stage_property(stages, target, r"^\s*USER\s+(\S+)") if target else None
    runs_as_root = user is None or user.group(1).strip("\"'").lower() in ("root", "0", "0:0", "root:root")
    hc = False
    if target:
        for l in _stage_lines_with_inheritance(stages, target):
            if re.match(r"^\s*HEALTHCHECK\s", l, re.IGNORECASE):
                hc = "NONE" not in l.upper()
    return {
        "multi_stage": len(stages) > 1,
        "unpinned_base": unpinned,
        "runs_as_root": runs_as_root,
        "healthcheck": hc,
    }


def _stage_lines_with_inheritance(stages, stage, depth=0):
    parent_lines = []
    if depth < 10:
        for parent in stages:
            if parent is not stage and parent[0] and parent[0] == stage[1].lower():
                parent_lines = _stage_lines_with_inheritance(stages, parent, depth + 1)
                break
    return parent_lines + stage[2]


def _chart_root_has_chart_yaml(repo_path, rel):
    """True when a templates/ folder belongs to a Helm chart (a Chart.yaml sits next to it)."""
    parts = rel.replace("\\", "/").split("/")
    if "templates" not in parts:
        return False
    idx = parts.index("templates")
    return os.path.isfile(os.path.join(repo_path, *parts[:idx], "Chart.yaml"))


def detect_quality(repo_path, infra_details=None):
    infra_details = infra_details or {}
    docker = {"analysed": 0, "multi_stage": 0, "unpinned_base": 0, "runs_as_root": 0, "healthcheck": 0}
    root_examples, unpinned_examples = [], []
    ci_texts = []
    ci_files = []
    lock_found, manifest_dirs, lock_dirs = False, set(), set()
    hygiene = {"license": False, "security_policy": False, "codeowners": False, "gitignore": False,
               "dockerignore": False, "pre_commit": False, "contributing": False, "env_example": False,
               "dependency_update_bot": False}
    k8s_ctx = {"workloads": 0, "with_security_context": 0, "run_as_non_root": 0, "latest_image_tag": 0,
               "from_helm_templates": False}
    script_candidates = set()
    makefile_texts = []
    files_seen = {}

    for root, dirs, files in walk_repo(repo_path):
        rel_root = os.path.relpath(root, repo_path)
        depth = 0 if rel_root == "." else rel_root.count(os.sep) + 1
        rel_root_n = "" if rel_root == "." else rel_root.replace("\\", "/")
        for f in files:
            rel = (rel_root_n + "/" + f) if rel_root_n else f
            low = f.lower()
            if depth == 0:
                if low.startswith(("license", "licence", "copying")): hygiene["license"] = True
                if low == "security.md": hygiene["security_policy"] = True
                if low == "codeowners": hygiene["codeowners"] = True
                if low == ".gitignore": hygiene["gitignore"] = True
                if low == ".dockerignore": hygiene["dockerignore"] = True
                if low == ".pre-commit-config.yaml": hygiene["pre_commit"] = True
                if low.startswith("contributing"): hygiene["contributing"] = True
                if low in (".env.example", ".env.sample", ".env.template", "example.env"): hygiene["env_example"] = True
                if low in ("renovate.json", ".renovaterc", ".renovaterc.json", ".renovaterc.json5", "renovate.json5"):
                    hygiene["dependency_update_bot"] = True
            if low == ".dockerignore":
                hygiene.setdefault("dockerignore_dirs", []).append(rel_root_n or ".")
            if rel in (".github/dependabot.yml", ".github/dependabot.yaml", ".github/renovate.json", ".github/renovate.json5",
                       ".gitlab/renovate.json", ".gitlab/renovate.json5", ".renovaterc.json5",
                       ".github/security.md", ".github/codeowners", "docs/codeowners"):
                if "dependabot" in rel or "renovate" in rel: hygiene["dependency_update_bot"] = True
                if rel.endswith("security.md"): hygiene["security_policy"] = True
                if rel.endswith("codeowners"): hygiene["codeowners"] = True
            if f in LOCKFILES:
                lock_found = True
                lock_dirs.add(rel_root_n)
            if f in MANIFESTS_NEEDING_LOCK and not is_dev_only_path(rel):
                manifest_dirs.add(rel_root_n)

            if (f.lower() in ("dockerfile", "containerfile") or f.lower().startswith(("dockerfile.", "containerfile.")) or f.lower().endswith((".dockerfile", ".containerfile"))) \
                    and not is_dev_only_path(rel) and docker["analysed"] < MAX_DOCKERFILES:
                text = _read(os.path.join(root, f))
                if text and dockerfile_role(rel, text) != "app":
                    text = ""            # debug variants and monitoring-stack images are not the production application images
                if text:
                    a = _analyse_dockerfile(text)
                    docker["analysed"] += 1
                    for k in ("multi_stage", "unpinned_base", "runs_as_root", "healthcheck"):
                        docker[k] += 1 if a[k] else 0
                    if a["runs_as_root"] and len(root_examples) < 5: root_examples.append(rel)
                    if a["unpinned_base"] and len(unpinned_examples) < 5: unpinned_examples.append(rel)

            is_ci = (rel.startswith(".github/workflows/") and f.endswith((".yml", ".yaml"))) or \
                f in (".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml",
                      "cloudbuild.yaml", "cloudbuild.yml", ".travis.yml", ".drone.yml", "appveyor.yml") or \
                rel in (".circleci/config.yml",) or \
                (rel.startswith((".buildkite/", ".woodpecker/", ".gitlab/ci/", ".github/actions/")) and
                 f.endswith((".yml", ".yaml")))
            if is_ci and len(ci_files) < 80:
                ci_files.append(rel)
                ci_texts.append(_read(os.path.join(root, f)).lower())

            files_seen[rel] = os.path.join(root, f)
            if f in ("Makefile", "makefile", "Taskfile.yml", "Taskfile.yaml", "justfile", "noxfile.py", "tox.ini"):
                makefile_texts.append(_read(os.path.join(root, f), 100_000).lower())
            in_chart_templates = (os.path.basename(root) == "templates" or "/templates/" in rel.replace("\\", "/")) \
                and _chart_root_has_chart_yaml(repo_path, rel)
            dev_check_rel = rel
            if in_chart_templates:
                dev_check_rel = rel.replace("\\", "/").replace("/templates/", "/_chart_/")
            if f.endswith((".yaml", ".yml")) and not is_dev_only_path(dev_check_rel) and "{{" not in f:
                text = _read(os.path.join(root, f), 200_000)
                if "kind:" in text and re.search(r"kind:\s*(Deployment|StatefulSet|DaemonSet)\b", text):
                    is_template = "{{" in text
                    for doc in re.split(r"^---\s*$", text, flags=re.M):
                        if re.search(r"^kind:\s*(Deployment|StatefulSet|DaemonSet)\b", doc, re.M):
                            if is_template:
                                k8s_ctx["from_helm_templates"] = True
                            k8s_ctx["workloads"] += 1
                            if "securityContext:" in doc: k8s_ctx["with_security_context"] += 1
                            if "runAsNonRoot: true" in doc: k8s_ctx["run_as_non_root"] += 1
                            if re.search(r"image:\s*[\"']?[^\s\"']+:latest\b", doc): k8s_ctx["latest_image_tag"] += 1

    # CI often just calls a script or a make target: read those too (keywords only, nothing is stored)
    raw_blob = "\n".join(ci_texts)
    for m in re.finditer(r"(?:\./|bash\s+|sh\s+|source\s+)?([\w./\-]+\.(?:sh|bash))", raw_blob):
        script_candidates.add(m.group(1).lstrip("./"))
    extra = []
    for sc in list(script_candidates)[:60]:
        for rel, full in files_seen.items():
            if rel == sc or rel.endswith("/" + sc):
                extra.append(_read(full, 100_000).lower())
                break
    if re.search(r"\b(make|task|just|nox|tox)\b", raw_blob):
        extra += makefile_texts[:6]
    blob = raw_blob + "\n" + "\n".join(extra)
    ci = {
        "files_count": len(ci_files),
        "runs_tests": any(w in blob for w in TEST_WORDS) or bool(TEST_CMD_RE.search(blob)) or _jvm_build_runs_tests(blob) or
        any("test" in os.path.basename(c).lower() for c in ci_files),
        "builds_container_image": any(w in blob for w in BUILD_IMAGE_WORDS),
        "deploys": any(w in blob for w in DEPLOY_WORDS),
        "security_scanning": any(w in blob for w in SECURITY_WORDS),
        "linting": any(w in blob for w in LINT_WORDS),
    }
    n = docker["analysed"]
    kinds = set(infra_details.get("kubernetes_kinds_found") or [])
    unlocked = sorted(d for d in manifest_dirs if d not in lock_dirs and "" not in lock_dirs
                      and not any(d == l or d.startswith(l + "/") for l in lock_dirs if l))
    return {
        "dockerfile_quality": {
            "analysed": n,
            "multi_stage": _words(docker["multi_stage"], n),
            "unpinned_base_image": _words(docker["unpinned_base"], n),
            "runs_as_root": _words(docker["runs_as_root"], n),
            "healthcheck": _words(docker["healthcheck"], n),
            "counts": {"of": n, "runs_as_root": docker["runs_as_root"], "unpinned_base_image": docker["unpinned_base"],
                       "multi_stage": docker["multi_stage"], "with_healthcheck": docker["healthcheck"]},
            "runs_as_root_examples": root_examples,
            "unpinned_base_examples": unpinned_examples,
        },
        "ci_quality": ci,
        "kubernetes_quality": {
            "security_context": _words(k8s_ctx["with_security_context"], k8s_ctx["workloads"]),
            "run_as_non_root": _words(k8s_ctx["run_as_non_root"], k8s_ctx["workloads"]),
            "image_tag_latest": _words(k8s_ctx["latest_image_tag"], k8s_ctx["workloads"]),
            "network_policies": "NetworkPolicy" in kinds,
            "pod_disruption_budgets": "PodDisruptionBudget" in kinds,
            "autoscaling": "HorizontalPodAutoscaler" in kinds or "VerticalPodAutoscaler" in kinds,
            "ingress": "Ingress" in kinds or "Gateway" in kinds or "HTTPRoute" in kinds,
            "workloads_checked": k8s_ctx["workloads"] > 0,
            "from_helm_templates": k8s_ctx["from_helm_templates"],
        },
        "dependency_pinning": {
            "lockfile_present": lock_found,
            "manifests_without_lockfile_nearby": len(unlocked),
        },
        "repo_hygiene": hygiene,
    }
