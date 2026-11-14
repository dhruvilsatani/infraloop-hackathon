"""Layer 6: the 'whole repo picture' -- done with plain functions, one pass over the tree.

Everything here returns NAMES, COUNTS and TRUE/FALSE only. File contents are read
to look for markers but are never copied into the result, so nothing sensitive can
reach the LLM from this layer. Real .env files are never opened."""
import os
import re

from scanner.common import walk_repo, is_dev_only_path, is_test_path, path_dirs, dockerfile_role
from scanner.compose import is_compose_filename, parse_compose

MAX_FILE_BYTES = 1_000_000  # skip huge/generated files

LANGUAGE_BY_EXTENSION = {
    ".py": "Python", ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".go": "Go", ".java": "Java", ".kt": "Kotlin",
    ".cs": "C#", ".rb": "Ruby", ".php": "PHP", ".rs": "Rust",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".c": "C/C++", ".cc": "C/C++", ".cpp": "C/C++",
    ".h": "C/C++", ".hpp": "C/C++", ".ex": "Elixir", ".exs": "Elixir", ".scala": "Scala",
    ".swift": "Swift", ".dart": "Dart", ".jsonnet": "Jsonnet", ".libsonnet": "Jsonnet",
    ".vue": "Vue", ".svelte": "Svelte", ".lua": "Lua", ".pl": "Perl", ".hs": "Haskell", ".clj": "Clojure",
    ".zig": "Zig", ".jl": "Julia", ".r": "R", ".erl": "Erlang", ".groovy": "Groovy",
}
MODEL_EXTENSIONS = {".pkl", ".pickle", ".joblib", ".pt", ".pth", ".onnx", ".h5", ".hdf5", ".keras",
                    ".safetensors", ".gguf", ".ckpt", ".tflite"}
ML_MARKER_FILES = {"dvc.yaml", "dvc.lock", "MLproject"}          # params.yaml alone is also a Kustomize file name (kubeflow/manifests)
LIBRARY_DIR_NAMES = {"packages", "libs", "lib", "shared", "common", "pkg", "internal", "modules", "crates"}
MAX_ENTRYPOINTS_PER_SERVICE = 12
MAX_ENTRYPOINTS_TOTAL = 40
CANONICAL_STORE = {"mongo": "mongodb", "valkey": "redis", "mariadb": "mysql", "postgresql": "postgres",
                   "opensearch": "elasticsearch", "pgvector": "postgres"}
COMPOSE_STORE_WORDS = ("redis", "valkey", "postgres", "pgvector", "mysql", "mariadb", "mongo", "memcached",
                       "rabbitmq", "kafka", "elasticsearch", "opensearch", "cassandra", "clickhouse",
                       "qdrant", "weaviate", "milvus", "chroma", "neo4j", "influxdb", "couchdb", "timescaledb", "cockroach", "arangodb")

MANIFEST_NAMES = {"pubspec.yaml", "mix.exs", "build.sbt", "Package.swift", "CMakeLists.txt", "deno.json",
    "package.json", "requirements.txt", "pyproject.toml", "go.mod", "pom.xml",
    "build.gradle", "build.gradle.kts", "Cargo.toml", "Gemfile", "composer.json",
    "stack.yaml", "project.clj", "deps.edn", "cpanfile", "Project.toml",
}
REQUIREMENTS_RE = re.compile(r".*requirements?.*\.txt$", re.IGNORECASE)

CODE_SUFFIXES = tuple(LANGUAGE_BY_EXTENSION)
TEXT_SUFFIXES = CODE_SUFFIXES + (".yaml", ".yml", ".json", ".toml", ".xml", ".gradle", ".txt", ".mod", ".csproj")

ENTRYPOINT_NAMES = {
    "main.py", "manage.py", "app.py", "server.py", "index.js", "server.js", "app.js",
    "index.mjs", "server.mjs", "app.mjs", "main.mjs", "index.cjs", "server.cjs", "app.cjs",
    "main.cjs", "main.go", "Program.cs", "Main.java", "Application.java",
    "index.ts", "main.ts", "server.ts", "app.ts",
}

TEST_FILE_RE = re.compile(
    r"(^test_.*\.py$)|(.*_test\.py$)|(.*_test\.go$)|(.*\.(test|spec)\.(js|jsx|ts|tsx|mjs)$)"
    r"|(.*Tests?\.cs$)|(.*Tests?\.java$)|(.*Test\.kt$)|(.*Tests?\.php$)|(.*_(spec|test)\.rb$)|(.*Spec\.scala$)|(.*Tests?\.swift$)|(.*_test\.exs?$)", re.IGNORECASE)

WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet"}
INGRESS_CLASS_RE = re.compile(r"(?:kubernetes\.io/ingress\.class|ingressClassName)\s*:\s*[\"']?([A-Za-z0-9._-]+)")
KIND_RE = re.compile(r"^kind:\s*(\w+)", re.MULTILINE)
IMAGE_RE = re.compile(r"image:\s*[\"']?([^\s\"'{}]+)", re.IGNORECASE)

DATASTORE_IMAGES = ("redis", "postgres", "mysql", "mariadb", "mongo", "memcached",
                    "rabbitmq", "kafka", "elasticsearch", "cassandra", "valkey", "opensearch", "clickhouse", "mongodb",
                    "qdrant", "weaviate", "milvus", "chroma", "neo4j", "influxdb", "couchdb", "timescaledb", "cockroach", "arangodb")

# env-var NAME fragments that hint at a backing service
DATASTORE_ENV_HINTS = {
    "redis": ("REDIS",), "postgres": ("POSTGRES", "PGHOST", "PG_HOST", "DATABASE_URL"),
    "mysql": ("MYSQL", "MARIADB"), "mongodb": ("MONGO",), "alloydb": ("ALLOYDB",),
    "spanner": ("SPANNER",), "dynamodb": ("DYNAMO",), "memcached": ("MEMCACHE",),
    "rabbitmq": ("RABBIT", "AMQP"), "kafka": ("KAFKA",), "sqs": ("SQS_",),
}
_ALL_ENV_HINTS = tuple(sorted({h for hs in DATASTORE_ENV_HINTS.values() for h in hs}))
ENV_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")

# library names (lowercase substring) in manifests -> what they tell us
DATASTORE_LIBS = {
    "redis": "redis", "psycopg": "postgres", "pgx": "postgres", "lib/pq": "postgres",
    "postgres": "postgres", '"pg"': "postgres", "'pg'": "postgres", "pymongo": "mongodb", "mongo": "mongodb", "mysql": "mysql", "mysql2": "mysql",
    "sqlalchemy": "sql (ORM)", "npgsql": "postgres", "spanner": "spanner",
    "alloydb": "alloydb", "dynamodb": "dynamodb",
}
OBSERVABILITY_LIBS = {
    "tracing_opentelemetry": ("opentelemetry", "otel"),
    "metrics_prometheus": ("prometheus_client", "prometheus-client", "prom-client",
                           "promhttp", "micrometer-registry-prometheus", "prometheus-net",
                           "prometheus-fastapi-instrumentator",
                           "micrometer-core", "spring-boot-starter-actuator", "micrometer-registry-prometheus", "prometheus-flask-exporter", "prometheus_flask_exporter",
                           "starlette-exporter", "go-metrics", "metrics-exporter-prometheus", "prometheus_exporter",
                           "prometheus/client_golang", "prometheus/client_java", "prometheus/client_ruby", "VictoriaMetrics/metrics", "statsd", "datadog-go"),
    "error_tracking": ("sentry",),
    "vendor_apm": ("dd-trace", "ddtrace", "datadog", "newrelic", "elastic-apm"),
    "health_actuator": ("spring-boot-starter-actuator",),
}
ENTRYPOINT_CONTENT_MARKERS = {
    ".go": ("func main()",),
    ".py": ('__name__ == "__main__"', "__name__ == '__main__'"),
    ".cs": ("static void Main(", "static async Task Main(", "static int Main("),
    ".java": ("public static void main(",),
    ".js": ("require.main === module",), ".mjs": (), ".cjs": ("require.main === module",),
    ".ts": (),
}
HEALTH_CODE_RE = re.compile(r"/healthz?\b|/readyz?\b|/livez?\b|grpc\.health|grpc_health|health\.v1|HealthCheck|health_check",
                            re.IGNORECASE)


OPTIONAL_PATH_PARTS = {"components", "overlays", "overlay", "optional", "examples", "example", "samples", ".github"}


def _is_optional_path(rel_path):
    return any(part.lower() in OPTIONAL_PATH_PARTS for part in rel_path.split(os.sep))


def _parse_cpu(text):
    text = text.strip().strip("\"'")
    try:
        return float(text[:-1]) / 1000 if text.endswith("m") else float(text)
    except ValueError:
        return None


_MEM_UNITS = {"Ki": 1 / 1024 / 1024, "Mi": 1 / 1024, "Gi": 1.0, "Ti": 1024.0,
              "K": 1e3 / 2**30, "M": 1e6 / 2**30, "G": 1e9 / 2**30}


def _parse_memory_gib(text):
    text = text.strip().strip("\"'")
    for unit in ("Ki", "Mi", "Gi", "Ti", "K", "M", "G"):
        if text.endswith(unit):
            try:
                return float(text[:-len(unit)]) * _MEM_UNITS[unit]
            except ValueError:
                return None
    try:
        return float(text) / 2**30  # plain bytes
    except ValueError:
        return None


def _workload_resources(doc):
    """CPU/memory REQUESTS (what you pay for on pay-per-resource platforms), summed over containers."""
    cpu_total, mem_total, found = 0.0, 0.0, False
    for block in re.finditer(r"^([ \t]*)requests:[ \t]*\n((?:\1[ \t]+.*\n?)+)", doc, flags=re.MULTILINE):
        body = block.group(2)
        cpu = re.search(r"cpu:\s*(\S+)", body)
        mem = re.search(r"memory:\s*(\S+)", body)
        if cpu and _parse_cpu(cpu.group(1)) is not None:
            cpu_total += _parse_cpu(cpu.group(1)); found = True
        if mem and _parse_memory_gib(mem.group(1)) is not None:
            mem_total += _parse_memory_gib(mem.group(1)); found = True
    return (round(cpu_total, 3), round(mem_total, 4)) if found else None


def _read(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return ""
        with open(path, "r", errors="ignore") as fh:
            return fh.read()
    except (IOError, OSError):
        return ""


def _read_head(path, limit=3000):
    try:
        with open(path, "r", errors="ignore") as fh:
            return fh.read(limit)
    except (IOError, OSError):
        return ""


def _is_dockerfile(name):
    name = name.lower()
    return (name in ("dockerfile", "containerfile") or name.startswith(("dockerfile.", "containerfile."))
            or name.endswith((".dockerfile", ".containerfile")))


def _is_manifest(name):
    return name in MANIFEST_NAMES or name.endswith((".csproj", ".rockspec", ".cabal")) or bool(REQUIREMENTS_RE.match(name))


def _manifest_language(name):
    if name == "package.json": return "JavaScript/Node"
    if name == "go.mod": return "Go"
    if name in ("pom.xml", "build.gradle", "build.gradle.kts"): return "Java"
    if name.endswith(".csproj"): return "C#"
    if name.endswith(".rockspec"): return "Lua"
    if name.endswith(".cabal") or name == "stack.yaml": return "Haskell"
    if name in ("project.clj", "deps.edn"): return "Clojure"
    if name == "cpanfile": return "Perl"
    if name == "Project.toml": return "Julia"
    if name == "Cargo.toml": return "Rust"
    if name == "Gemfile": return "Ruby"
    if name == "composer.json": return "PHP"
    if name == "pubspec.yaml": return "Dart"
    if name == "mix.exs": return "Elixir"
    if name == "build.sbt": return "Scala"
    if name == "Package.swift": return "Swift"
    if name == "CMakeLists.txt": return "C/C++"
    if name == "deno.json": return "TypeScript"
    return "Python"  # requirements*.txt, pyproject.toml


def _yaml_documents(text):
    return re.split(r"^---\s*$", text, flags=re.MULTILINE)


def _datastore_summary(in_cluster, env_names, files_by_kind):
    """One plain answer to 'which database does this project use?':
    default = deployed in the base manifests, optional = only in optional overlays,
    unconfirmed = mentioned but the scanner cannot tell whether it is used."""
    default = sorted({_canon(d["type"]) for d in in_cluster})
    optional, unconfirmed = [], []
    for kind in sorted(env_names):
        if kind in default:
            continue
        files_ = files_by_kind.get(kind)
        if files_ and all(_is_optional_path(p) for p in files_):
            optional.append(kind)
        else:
            unconfirmed.append(kind)
    return {"default_in_cluster": default, "optional_components": optional, "unconfirmed": unconfirmed}


def _coverage(part, total):
    if total == 0 or part == 0:
        return "none"
    ratio = part / total
    return "all" if ratio >= 1 else ("most" if ratio >= 0.7 else "some")


def _coverage_words(k8s):
    """Raw counts include Helm/Kustomize/release copies of the same workload, so a
    'N of M' number would be wrong. Words are all the model needs (and all it may say)."""
    total = k8s["workload_manifests"]
    return {
        "workloads_found": total > 0,
        "liveness_probes": _coverage(k8s["with_liveness_probe"], total),
        "readiness_probes": _coverage(k8s["with_readiness_probe"], total),
        "resource_limits": _coverage(k8s["with_resource_limits"], total),
    }


COMPOSE_DEV_PARTS = {"_archived", "archived", "archive", "legacy", "deprecated", "old", "tools", "dev", "debug", "hack", "examples", "example", "samples", "sample", "sandbox",
                     "sandboxes", "contrib", "scripts", "benchmarks", "demo", "demos", "development", "devenv", "dev-env"}


def _compose_dev_path(rel):
    return any(p in COMPOSE_DEV_PARTS for p in path_dirs(rel))


SHARED_DOCKER_DIR_NAMES = {"docker", "dockerfiles", ".docker", "containers", "container", "images", "deploy", "build"}


def _compose_role(rel):
    """Guess whether a compose file is meant for production or local development, from its name only."""
    name = os.path.basename(rel).lower()
    if any(w in name for w in ("prod", "production", "deploy", "stack", "swarm", "release")):
        return "production_like"
    if any(w in name for w in ("override", "dev", "local", "debug", "test", "ci")):
        return "local_dev"
    return "unspecified"


def _canon(kind):
    return CANONICAL_STORE.get(kind, kind)


def _collapse_datastores(found):
    """Helm/Kustomize/release copies of the same manifest would repeat one finding 4 times.
    'where' says whether it runs in a cluster (kubernetes) or only in a docker-compose file."""
    by_type = {}
    for item in found:
        kind = _canon(item["type"])
        entry = by_type.setdefault(kind, {"type": kind, "example_file": item["file"],
                                          "any_persistent_volume": False, "where": set(), "compose_role": set()})
        entry["any_persistent_volume"] = entry["any_persistent_volume"] or item["persistent_volume"]
        entry["where"].add(item.get("where", "kubernetes"))
        if item.get("compose_role"):
            entry["compose_role"].add(item["compose_role"])
    for entry in by_type.values():
        entry["where"] = sorted(entry["where"])
        entry["compose_role"] = sorted(entry["compose_role"])
        if not entry["compose_role"]:
            del entry["compose_role"]
    return list(by_type.values())


def _hidden_or_tooling(rel_dir):
    parts = rel_dir.replace("\\", "/").split("/")
    return any(p.startswith(".") and p not in (".",) for p in parts) or \
        any(p.lower() in ("test", "tests", "testing", "e2e", "fixtures", "docs", "doc", "_archived", "archived", "archive",
                          "fuzz", "fuzzing", "bench", "benchmark", "benchmarks", "integration_test", "integration-test",
                          "integration_tests", "integration-tests", "test-stability", "dev", "document", "documents", "documentation", "example", "examples", "sample", "samples")
            or "snippet" in p.lower() for p in parts)


def _exposed_port(path):
    """First port from an EXPOSE line of a Dockerfile (0 when there is none or it is a variable)."""
    for line in _read_head(path, 20000).splitlines():
        m = re.match(r"\s*EXPOSE\s+(\d{2,5})", line, re.I)
        if m and 0 < int(m.group(1)) < 65536:
            return int(m.group(1))
    return 0


def detect_runtime_picture(repo_path):
    docker_port_by_dir = {}
    dockerfiles, test_dirs_files = [], set()
    language_counts = {}
    language_counts_nontest = {}
    manifests_by_dir = {}          # dir -> set(languages)
    dockerfile_dirs = set()
    entrypoints_by_dir = {}
    code_files_by_dir = {}         # dir -> {language: count}
    k8s = {"workload_manifests": 0, "with_liveness_probe": 0, "with_readiness_probe": 0,
           "with_resource_limits": 0}
    in_cluster_datastores = []
    ingress_classes = set()
    datastore_env = {}
    datastore_files = {}          # kind -> set of files that mention it (to spot "optional overlay only")
    datastore_libs = set()
    obs = {k: set() for k in OBSERVABILITY_LIBS}
    health_files = 0
    detected_entrypoints = []
    workload_resources = {}
    compose_stores = []
    dev_only_dockerfiles = []
    support_dockerfiles = []
    deploy_config_dirs = set()
    ml = {"model_files": [], "markers": [], "notebooks": 0, "lfs_pointers": 0}
    notebooks_seen = 0

    for root, dirs, files in walk_repo(repo_path):
        rel_root = os.path.relpath(root, repo_path)
        rel_root = "." if rel_root == "." else rel_root
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, repo_path)
            ext = os.path.splitext(f)[1].lower()

            if _is_dockerfile(f):
                role = "dev" if is_dev_only_path(rel) else dockerfile_role(rel, _read_head(full))
                if role == "dev":
                    dev_only_dockerfiles.append(rel)
                elif role == "monitoring":
                    support_dockerfiles.append(rel)
                else:
                    dockerfiles.append(rel)
                    dockerfile_dirs.add(rel_root)
                    docker_port_by_dir.setdefault(rel_root, _exposed_port(full))
            if f in ("vercel.json", "netlify.toml", "fly.toml", "render.yaml", "Procfile", "serverless.yml",
                     "serverless.yaml", "wrangler.toml", "app.yaml", "railway.json", "firebase.json"):
                deploy_config_dirs.add(rel_root)
            if ext in MODEL_EXTENSIONS:
                try:
                    ml["model_files"].append({"file": rel, "size_mb": round(os.path.getsize(full) / 1e6, 2)})
                except OSError:
                    pass
            if f in ML_MARKER_FILES or f.endswith(".dvc"):
                ml["markers"].append(rel)
            if ext == ".ipynb":
                notebooks_seen += 1
            if _is_manifest(f) and not _hidden_or_tooling(rel_root):
                manifests_by_dir.setdefault(rel_root, set()).add(_manifest_language(f))
            if f in ENTRYPOINT_NAMES:
                entrypoints_by_dir.setdefault(rel_root, []).append(f)
            if TEST_FILE_RE.match(f):
                test_dirs_files.add(rel_root)
            if ext in LANGUAGE_BY_EXTENSION:
                lang = LANGUAGE_BY_EXTENSION[ext]
                language_counts[lang] = language_counts.get(lang, 0) + 1
                if not is_test_path(rel) and not _compose_dev_path(rel):
                    language_counts_nontest[lang] = language_counts_nontest.get(lang, 0) + 1
                bucket = code_files_by_dir.setdefault(rel_root, {})
                bucket[lang] = bucket.get(lang, 0) + 1

            # never open real env files; .env.example is fine (names only)
            if f == ".env" or (f.startswith(".env.") and f != ".env.example"):
                continue
            if not (f.endswith(TEXT_SUFFIXES) or f == ".env.example" or _is_dockerfile(f) or _is_manifest(f)):
                continue
            if f in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "Cargo.lock", "go.sum",
                     "composer.lock", "Gemfile.lock", "uv.lock") or f.endswith(".lock"):
                continue  # lock files list every transitive library and would give false hints
            content = _read(full)
            if not content:
                continue
            lowered = content.lower()

            if is_compose_filename(f) and not is_dev_only_path(rel) and not _compose_dev_path(rel):
                for cname, csvc in parse_compose(content).items():
                    text = (cname + " " + csvc["image"]).lower()
                    if any(x in text for x in ("exporter", "-ui", "-admin", "commander", "insight", "proxy", "sidecar")):
                        continue
                    for word in COMPOSE_STORE_WORDS:
                        if word in text:
                            compose_stores.append({"type": word, "file": rel, "where": "docker-compose",
                                                   "compose_role": _compose_role(rel),
                                                   "persistent_volume": csvc["volumes"]})
                            break

            if _is_manifest(f):
                for lib, label in DATASTORE_LIBS.items():
                    if lib in lowered:
                        datastore_libs.add(label)
                for key, needles in OBSERVABILITY_LIBS.items():
                    if any(n in lowered for n in needles):
                        obs[key].add(rel_root)

            if ext in CODE_SUFFIXES and ("ealth" in content or "readyz" in lowered or "livez" in lowered) \
                    and HEALTH_CODE_RE.search(content):
                health_files += 1

            # entrypoint by CONTENT, not just filename (server.go, email_server.py, ...)
            if ext in ENTRYPOINT_CONTENT_MARKERS and not TEST_FILE_RE.match(f) \
                    and any(m in content for m in ENTRYPOINT_CONTENT_MARKERS[ext]):
                if ext != ".go" or "package main" in content:
                    entrypoints_by_dir.setdefault(rel_root, []).append(f)
                    detected_entrypoints.append(rel)

            if ext in (".yaml", ".yml"):
                if "apiVersion:" in content and "kind:" in content and not is_test_path(rel) \
                        and not (set(path_dirs(rel)) & {"example", "examples", "sample", "samples"}):      # manifests of a test suite or a sample are not the project's cluster
                    for doc in _yaml_documents(content):
                        km = KIND_RE.search(doc)
                        if not km:
                            continue
                        kind = km.group(1)
                        if kind == "Ingress":
                            for cls in INGRESS_CLASS_RE.findall(doc):
                                ingress_classes.add(cls.lower())
                        if kind in WORKLOAD_KINDS:
                            k8s["workload_manifests"] += 1
                            name_match = re.search(r"^metadata:\s*\n(?:[ \t]+.*\n)*?[ \t]+name:\s*(\S+)", doc, re.MULTILINE)
                            if name_match and "{{" not in doc:
                                res = _workload_resources(doc)
                                rep = re.search(r"^\s*replicas:\s*(\d+)", doc, re.MULTILINE)
                                name = name_match.group(1).strip("\"'")
                                if res and (name not in workload_resources or rel.startswith("kubernetes-manifests")):
                                    workload_resources[name] = {"cpu_cores": res[0], "memory_gib": res[1],
                                                                "replicas": int(rep.group(1)) if rep else 1}
                            if "livenessProbe:" in doc: k8s["with_liveness_probe"] += 1
                            if "readinessProbe:" in doc: k8s["with_readiness_probe"] += 1
                            if "limits:" in doc: k8s["with_resource_limits"] += 1
                            for image in IMAGE_RE.findall(doc):
                                base = image.split("/")[-1].split(":")[0].lower()
                                if base in DATASTORE_IMAGES:
                                    in_cluster_datastores.append({
                                        "type": base,
                                        "file": rel,
                                        "persistent_volume": ("volumeClaimTemplates" in doc
                                                              or "persistentVolumeClaim" in doc),
                                        "uses_emptydir_only": "emptyDir" in doc and "persistentVolumeClaim" not in doc
                                                              and "volumeClaimTemplates" not in doc,
                                    })
                if ("otel" in lowered or "opentelemetry" in lowered) and \
                        re.search(r"\botel\b|\botel-|opentelemetry", lowered):
                    obs["tracing_opentelemetry"].add(rel_root)

            # datastore hints from env-var NAMES (never values)
            if (ext in CODE_SUFFIXES + (".yaml", ".yml") or f == ".env.example") and \
                    any(h in content for h in _ALL_ENV_HINTS):
                for token in set(ENV_TOKEN_RE.findall(content)):
                    for kind, hints in DATASTORE_ENV_HINTS.items():
                        if any(h in token for h in hints):
                            names = datastore_env.setdefault(kind, set())
                            if len(names) < 8:
                                names.add(token)
                            if ext in (".yaml", ".yml"):
                                datastore_files.setdefault(kind, set()).add(rel)
            if ext in CODE_SUFFIXES and ("OTEL_" in content or "opentelemetry" in lowered):
                obs["tracing_opentelemetry"].add(rel_root)

    # ---- group directories into services -------------------------------------
    all_cands = set(manifests_by_dir) | dockerfile_dirs
    if not all_cands and code_files_by_dir:
        all_cands = {"."}  # code but no build manifest (scripts, notebooks, small ML projects)
    candidates = {c for c in all_cands
                  if not (c != "." and (_hidden_or_tooling(c) or _compose_dev_path(c + "/x")))}
    if not candidates:
        candidates = all_cands
    non_root = sorted((c for c in candidates if c != "."), key=lambda p: p.count(os.sep))
    service_of = {}
    for c in non_root:
        parent = None
        for other in non_root:
            if other != c and c.startswith(other + os.sep):
                parent = other
                break
        service_of[c] = parent or c
    for c in list(service_of):
        top = service_of[c]
        if os.path.basename(top) in ("src", "app", "server", "cmd"):
            service_of[c] = os.path.dirname(top) or "."
    services = {}
    for c in candidates:
        key = "." if c == "." else service_of[c]
        svc = services.setdefault(key, {"path": key, "languages": set(), "dockerfiles": 0,
                                        "manifests": 0, "entrypoints": [], "has_tests": False,
                                        "deploy_config": False, "port": 0})
        svc["port"] = svc["port"] or docker_port_by_dir.get(c, 0)
        svc["languages"] |= manifests_by_dir.get(c, set())
        svc["dockerfiles"] += 1 if c in dockerfile_dirs else 0
        svc["manifests"] += 1 if c in manifests_by_dir else 0
        svc["deploy_config"] = svc["deploy_config"] or c in deploy_config_dirs
        svc["entrypoints"] += entrypoints_by_dir.get(c, [])
    other_keys = [k for k in services if k != "."]

    _owner_cache = {}

    def owner(d):
        if d in _owner_cache:
            return _owner_cache[d]
        _owner_cache[d] = _owner(d)
        return _owner_cache[d]

    def _owner(d):
        best = None
        for k in other_keys:
            if d == k or d.startswith(k + os.sep):
                if best is None or len(k) > len(best):
                    best = k
        return best or "."

    for d, names in entrypoints_by_dir.items():
        if d in candidates:
            continue
        if "." in services or owner(d) != ".":
            services[owner(d)]["entrypoints"] += names if owner(d) in services else []
    for key, svc in services.items():
        prefix = "" if key == "." else key + os.sep
        counts = {}
        for d, langs in code_files_by_dir.items():
            if owner(d) == key if key != "." else owner(d) == ".":
                for l, n in langs.items():
                    counts[l] = counts.get(l, 0) + n
        if counts:
            svc["languages"] = {max(counts, key=counts.get)} if not svc["languages"] else svc["languages"]
            svc["main_language"] = max(counts, key=counts.get)
            # a build manifest (pom.xml, go.mod...) names the real stack better than a file count
            manifest_lang = {"Java": "Java", "Go": "Go", "C#": "C#", "Rust": "Rust", "Ruby": "Ruby", "PHP": "PHP"}
            for l in svc["languages"]:
                if l in manifest_lang and manifest_lang[l] in counts:
                    svc["main_language"] = manifest_lang[l]
                    break
        svc["has_tests"] = any(owner(d) == key for d in test_dirs_files)
        svc["languages"] = sorted(svc["languages"])
        svc["has_dockerfile"] = svc.pop("dockerfiles") > 0
        manifests = svc.pop("manifests")
        all_eps = sorted(set(svc["entrypoints"]))
        svc["entrypoints"] = [e for e in all_eps if e][:MAX_ENTRYPOINTS_PER_SERVICE]
        if len(all_eps) > MAX_ENTRYPOINTS_PER_SERVICE:
            svc["entrypoints_total"] = len(all_eps)
        # library vs deployable: shared-code folders without a Dockerfile / deploy config / strong entrypoint
        parts = [x.lower() for x in key.split(os.sep)]
        strong = [e for e in all_eps if e not in ("index.ts", "index.js", "index.mjs", "index.cjs", "main.ts")]
        in_lib_dir = any(x in LIBRARY_DIR_NAMES for x in parts[:-1]) or (parts and parts[0] in LIBRARY_DIR_NAMES and key != ".")
        in_app_dir = any(x in ("apps", "services", "microservices", "app-services") for x in parts[:-1]) and manifests > 0
        top_named = key != "." and len(parts) == 1 and parts[0] in ("backend", "frontend", "api", "web", "server",
                                                                    "client", "worker", "app") and manifests > 0
        svc["container_only"] = bool(svc["has_dockerfile"] and not svc.get("main_language") and not manifests
                                     and key != ".")
        svc["deployable"] = bool(svc["has_dockerfile"] or svc["deploy_config"] or in_app_dir or top_named
                                 or (strong and not in_lib_dir) or (key == "." and (strong or manifests or svc.get("main_language"))))
        svc["client_app"] = "Dart" in svc["languages"] and not svc["has_dockerfile"]
        svc.pop("deploy_config")

    service_list = sorted(services.values(), key=lambda x: x["path"])
    deployable = [x for x in service_list if x["deployable"]]
    if len(deployable) > 1:  # a root manifest that merely wraps sub-projects is not a service itself
        deployable = [x for x in deployable if not (x["path"] == "." and not x["has_dockerfile"]
                                                    and not [e for e in x["entrypoints"]])]
    libraries = [x["path"] for x in service_list if not x["deployable"]]
    # a Dockerfile-only folder (docker/, deploy/...) next to real code services is a shared build
    # recipe, not a service of its own
    shared_container_dirs = []
    code_services = [x for x in deployable if not x.get("container_only")]
    if len(code_services) >= 2:
        shared_container_dirs = [x["path"] for x in deployable
                                 if x.get("container_only") and x["path"].lower().replace("\\", "/").split("/")[-1] in SHARED_DOCKER_DIR_NAMES]
        deployable = [x for x in deployable if x["path"] not in shared_container_dirs]
    if not deployable:
        deployable = service_list
        libraries = []
    for x in deployable:
        x.pop("deployable", None)

    store_found = list(in_cluster_datastores) + compose_stores
    ml["notebooks"] = notebooks_seen
    ml["model_files"] = sorted(ml["model_files"], key=lambda m: -m["size_mb"])[:10]
    ml["markers"] = sorted(ml["markers"])[:10]
    ml_present = bool(ml["model_files"] or ml["markers"] or notebooks_seen)

    return {
        "dockerfiles": {"count": len(dockerfiles), "locations": sorted(dockerfiles)[:40],
                        "dev_only_count": len(dev_only_dockerfiles),
                        "monitoring_stack_images": sorted(support_dockerfiles)[:10]},
        "languages": dict(sorted((language_counts_nontest or language_counts).items(), key=lambda kv: -kv[1])),
        "services": {"count": len(deployable), "list": deployable[:40],
                     "shared_container_dirs": shared_container_dirs,
                     "list_truncated": len(deployable) > 40,
                     "library_folders_ignored": len(libraries)},
        "entrypoints_detected": sorted(set(detected_entrypoints))[:MAX_ENTRYPOINTS_TOTAL],
        "entrypoints_detected_total": len(set(detected_entrypoints)),
        "kubernetes_details": dict(_coverage_words(k8s), ingress_classes=sorted(ingress_classes)),
        "workload_resources": workload_resources,
        "in_cluster_datastores": _collapse_datastores(store_found),
        "datastore_summary": _datastore_summary(store_found, datastore_env, datastore_files),
        "datastore_signals": {
            "env_var_names": {k: sorted(v) for k, v in sorted(datastore_env.items())},
            # True = every file that mentions it sits in an optional overlay/component folder,
            # so it is an OPTION the project offers, not something the app requires.
            # (judged from deployment YAML only: code may support several backends)
            "only_in_optional_overlays": {k: all(_is_optional_path(p) for p in files_)
                                          for k, files_ in sorted(datastore_files.items())},
            "libraries": sorted(datastore_libs),
        },
        "ml_artifacts": {"present": ml_present, **ml},
        "observability": {
            "tracing_opentelemetry": bool(obs["tracing_opentelemetry"]),
            "metrics_library": bool(obs["metrics_prometheus"]),
            "error_tracking": bool(obs["error_tracking"]),
            "vendor_apm": bool(obs["vendor_apm"]),
            "health_endpoint_in_code": health_files > 0 or bool(obs["health_actuator"]),
        },
    }


if __name__ == "__main__":
    import sys, json
    print(json.dumps(detect_runtime_picture(sys.argv[1] if len(sys.argv) > 1 else "."), indent=2))
