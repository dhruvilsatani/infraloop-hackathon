"""Independent ground-truth inspection (does NOT import the scanner)."""
import os, re, sys, collections, json

SKIP = {".git", "node_modules", ".venv", "venv", "__pycache__", "vendor", "target", "dist", "build"}
EXT_LANG = {".py": "Python", ".js": "JS", ".mjs": "JS", ".cjs": "JS", ".ts": "TS", ".tsx": "TS", ".jsx": "JS", ".go": "Go",
            ".java": "Java", ".kt": "Kotlin", ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".rs": "Rust",
            ".cpp": "C/C++", ".cc": "C/C++", ".c": "C/C++", ".h": "C/C++", ".hpp": "C/C++", ".ex": "Elixir", ".exs": "Elixir",
            ".scala": "Scala", ".swift": "Swift", ".dart": "Dart", ".jsonnet": "Jsonnet", ".libsonnet": "Jsonnet", ".vue": "Vue"}
MODEL_EXT = {".pkl", ".pickle", ".joblib", ".pt", ".pth", ".onnx", ".h5", ".hdf5", ".keras", ".safetensors", ".gguf", ".ckpt", ".tflite"}
SECRET_RES = {
    "aws_key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "github_token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "slack": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    "google_api": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "stripe": re.compile(r"sk_live_[0-9a-zA-Z]{20,}"),
    "db_url_with_pw": re.compile(r"[a-z]+://[^\s:/@]+:[^\s@/]{3,}@[\w.\-]+"),
}
MON_KINDS = {"ServiceMonitor", "PodMonitor", "PrometheusRule", "Alertmanager", "Prometheus", "AlertmanagerConfig", "ScrapeConfig"}
GITOPS_KINDS = {"Application", "ApplicationSet", "AppProject", "GitRepository", "HelmRelease", "Kustomization"}
STORE_IMG = ("redis", "postgres", "mysql", "mariadb", "mongo", "memcached", "rabbitmq", "kafka", "elasticsearch", "cassandra",
             "valkey", "opensearch", "clickhouse")


NOISE_PARTS = {"test", "tests", "testing", "testdata", "fixtures", "fixture", "e2e", "__tests__", "spec", "specs", ".devcontainer",
               "syntax-tests", "documentation", "docs", "doc"}


def noisy(rel):
    parts = rel.lower().replace("\\", "/").split("/")
    return any(p in NOISE_PARTS for p in parts[:-1])


def walk(root):
    for r, d, f in os.walk(root):
        d[:] = [x for x in d if x not in SKIP]
        yield r, d, f


def inspect_repo(path):
    T = collections.defaultdict(list)
    lang = collections.Counter()
    k8s_workloads, kinds = set(), collections.Counter()
    compose = {}
    manifests = collections.Counter()
    tests = 0
    secrets = collections.defaultdict(set)
    models = []
    for r, dirs, files in walk(path):
        rel_r = os.path.relpath(r, path)
        for f in files:
            full = os.path.join(r, f); rel = os.path.relpath(full, path)
            ext = os.path.splitext(f)[1].lower()
            if (f == "Dockerfile" or f.startswith("Dockerfile.") or f.endswith(".Dockerfile")) and not noisy(rel) and not f.endswith(".tt") \
                    and not re.search(r"\.(debug|dev|development|local|test|ci)(\.dockerfile)?$", f.lower()) \
                    and not (set(rel.lower().split("/")[:-1]) & {"grafana", "prometheus", "alertmanager", "loki", "jaeger", "zipkin", "kibana", "logstash", "fluentd"}):
                T["dockerfiles"].append(rel)
            if ext in EXT_LANG:
                lang[EXT_LANG[ext]] += 1
            for m in ("package.json", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile", "Cargo.toml",
                      "composer.json", "pyproject.toml", "requirements.txt"):
                if f == m: manifests[m] += 1
            if f.endswith(".csproj"): manifests[".csproj"] += 1
            if re.match(r"(docker-)?compose.*\.ya?ml$", f): T["compose_files"].append(rel)
            if not noisy(rel) and f in ("serverless.yml", "serverless.yaml", "cdk.json", "Pulumi.yaml", "skaffold.yaml", "vercel.json",
                     "netlify.toml", "fly.toml", "render.yaml", "Procfile", "app.yaml", "kustomization.yaml", "Chart.yaml",
                     "dvc.yaml", "MLproject", "Jenkinsfile", ".gitlab-ci.yml", "tox.ini", "Makefile"):
                T["markers"].append(rel)
            if ext == ".tf" and not noisy(rel): T["tf"].append(rel)
            if rel.startswith(".github/workflows/"): T["gha"].append(f)
            if re.search(r"(^test_.*\.py$|_test\.py$|_test\.go$|_test\.exs?$|\.(test|spec)\.(js|ts|tsx|mjs)$|Tests?\.(cs|java|php)$|_spec\.rb$|_test\.rb$)", f) \
                    or any(x in ("test", "tests", "__tests__", "spec") for x in rel.lower().split("/")[:-1]) and ext in EXT_LANG:
                tests += 1
            if ext in MODEL_EXT:
                try: models.append((rel, round(os.path.getsize(full) / 1e6, 2)))
                except OSError: pass
            if ext in (".ipynb",): T["notebooks"].append(rel)
            # text scan
            try:
                if os.path.getsize(full) > 1_000_000: continue
                raw = open(full, "rb").read()
            except OSError:
                continue
            if b"\0" in raw[:2000]: continue
            text = raw.decode("utf-8", "ignore")
            if f.startswith("package-lock") or f.endswith(".lock"): continue
            for name, rx in SECRET_RES.items():
                if rx.search(text): secrets[name].add(rel)
            if ext in (".yaml", ".yml"):
                for doc in re.split(r"^---\s*$", text, flags=re.M):
                    km = re.search(r"^kind:\s*(\w+)", doc, re.M)
                    if km and "apiVersion" in doc and not noisy(rel):
                        kinds[km.group(1)] += 1
                        if km.group(1) in ("Deployment", "StatefulSet", "DaemonSet") and "{{" not in doc:
                            nm = re.search(r"^metadata:\s*\n(?:[ \t]+.*\n)*?[ \t]+name:\s*(\S+)", doc, re.M)
                            if nm: k8s_workloads.add(nm.group(1))
                if re.match(r"(docker-)?compose.*\.ya?ml$", f):
                    svcs = {}
                    cur = None; in_services = False
                    for line in text.splitlines():
                        if line.lstrip().startswith("#"): continue
                        if re.match(r"^services:\s*$", line): in_services = True; continue
                        if re.match(r"^\S", line) and in_services: in_services = False
                        if in_services:
                            m = re.match(r"^  ([\w.\-]+):\s*$", line)
                            if m: cur = m.group(1); svcs[cur] = {"image": None, "build": False, "volumes": False}
                            elif cur:
                                if re.match(r"^    image:", line): svcs[cur]["image"] = line.split(":", 1)[1].strip()
                                if re.match(r"^    build", line): svcs[cur]["build"] = True
                                if re.match(r"^    volumes:", line): svcs[cur]["volumes"] = True
                    compose[rel] = svcs
    stores_k8s = set()
    for r, d, f in walk(path):
        for fn in f:
            if fn.endswith((".yaml", ".yml")):
                try: t = open(os.path.join(r, fn), errors="ignore").read()
                except OSError: continue
                for m in re.finditer(r"image:\s*[\"']?([^\s\"'{}]+)", t):
                    base = m.group(1).split("/")[-1].split(":")[0].lower()
                    if base in STORE_IMG and "kind: Deployment" in t or base in STORE_IMG and "kind: StatefulSet" in t:
                        stores_k8s.add(base)
    dock_info = []
    for rel in T["dockerfiles"]:
        try:
            lines = open(os.path.join(path, rel), errors="ignore").read().splitlines()
        except OSError:
            continue
        last_user = None
        health = False
        for ln in lines:
            m = re.match(r"\s*USER\s+(\S+)", ln, re.I)
            if m: last_user = m.group(1)
            if re.match(r"\s*HEALTHCHECK\b", ln, re.I) and "NONE" not in ln.upper().split("HEALTHCHECK", 1)[1][:8]: health = True
        root = last_user is None or last_user.split(":")[0].lower() in ("root", "0")
        dock_info.append({"path": rel, "root": root, "healthcheck": health})
    ci = bool(T["gha"]) or any(m.endswith((".gitlab-ci.yml", "Jenkinsfile")) for m in T["markers"])
    for r_, d_, f_ in walk(path):
        if any(x in f_ for x in (".travis.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml")) or os.path.basename(r_) in (".circleci", ".buildkite", ".drone"):
            ci = True
    return {
        "dockerfiles": T["dockerfiles"], "dock_info": dock_info, "compose_files": T["compose_files"],
        "languages": dict(lang), "manifests": dict(manifests), "tests": tests,
        "gha": len(T["gha"]), "ci": ci, "tf": len(T["tf"]), "notebooks": len(T["notebooks"]),
        "markers": T["markers"], "k8s_workloads": sorted(k8s_workloads), "kinds": dict(kinds),
        "helm": any(m.endswith("Chart.yaml") for m in T["markers"]),
        "compose": compose, "stores_k8s": sorted(stores_k8s),
        "secrets": {k: sorted(v) for k, v in secrets.items()}, "models": models,
    }
