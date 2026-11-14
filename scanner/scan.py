import json
import os
import re

from scanner.layer1_signals import detect_infra_signals, detect_infra_details
from scanner.layer2_dependencies import detect_dependencies
from scanner.layer3_structure import detect_structure
from scanner.layer4_deep import (
    detect_entrypoints,
    detect_env_vars_and_secrets,
    detect_sensitive_files,
    detect_third_party_services,
    detect_managed_services,
    detect_monorepo,
)
from scanner.layer5_docs import detect_project_docs
from scanner.layer6_runtime import detect_runtime_picture
from scanner.layer8_quality import detect_quality


CONFIG_ONLY_LANGUAGES = {"Jsonnet"}


_INSTALL_RE = re.compile(r"(?:pip3?\s+install\s+(?!-[re]\b|\.|-r)[\w\"'\[]|cargo\s+install\s+\w|go\s+install\s+\S|brew\s+install\s+\w|gem\s+install\s+\w|composer\s+require\s+\w|"
                         r"npm\s+i(?:nstall)?\s+(?:-g|--global)|yarn\s+global\s+add|dotnet\s+tool\s+install)", re.I)


def _own_name(repo_path):
    names = set()
    base = os.path.basename(os.path.abspath(repo_path)).lower()
    names.add(base)
    try:
        pj = json.load(open(os.path.join(repo_path, "package.json"), errors="ignore"))
        if isinstance(pj.get("name"), str):
            names.add(pj["name"].lower())
    except (OSError, ValueError):
        pass
    return {n for n in names if len(n) >= 3}


def _installs_itself(repo_path):
    """README tells people to install this very package (npm install bull, pip install foo, cargo add foo ...)."""
    names = _own_name(repo_path)
    cmd = re.compile(r"(?:npm\s+i(?:nstall)?|yarn\s+add|pnpm\s+(?:add|i(?:nstall)?)|bun\s+add|pip3?\s+install|poetry\s+add|uv\s+add|cargo\s+(?:add|install)|"
                     r"go\s+(?:get|install)|gem\s+install|composer\s+require|dotnet\s+add\s+package|brew\s+install)\s+(?:-{1,2}[\w-]+\s+)*[\w@/.\-]*?([\w.\-]+)(?=[\s`\"'@]|$)", re.I)
    try:
        for n in os.listdir(repo_path):
            if n.lower().startswith("readme"):
                text = open(os.path.join(repo_path, n), errors="ignore").read(80000)
                for m in cmd.finditer(text):
                    if m.group(1).lower() in names:
                        return True
    except OSError:
        pass
    return False


_SKIP_WALK = {".git", "node_modules", "vendor", "target", "examples", "example", "samples", "sample", "test", "tests", "testdata",
              "bench", "benches", "benchmarks", "docs", "doc", "fuzz", "e2e", "integration", "_examples", "demo", "demos", "third_party"}


def _has_binary_entrypoint(repo_path):
    """For Rust and Go repos: is there a program to run (src/main.rs, [[bin]], package main) outside examples and tests?
    Returns None when the repo is neither Rust nor Go."""
    is_rust = os.path.isfile(os.path.join(repo_path, "Cargo.toml"))
    is_go = os.path.isfile(os.path.join(repo_path, "go.mod"))
    if not (is_rust or is_go):
        return None
    seen = 0
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in _SKIP_WALK and not d.startswith(".")]
        if root[len(repo_path):].count(os.sep) > 5:
            dirs[:] = []
        for f in files:
            seen += 1
            if seen > 20000:
                return None
            p = os.path.join(root, f)
            if is_rust and f == "main.rs":
                return True
            if is_rust and f == "Cargo.toml":
                try:
                    if re.search(r"^\[\[bin\]\]", open(p, errors="ignore").read(20000), re.M):
                        return True
                except OSError:
                    pass
            if is_rust and root.endswith(os.sep + "bin") and f.endswith(".rs") and os.sep + "src" + os.sep in root + os.sep:
                return True
            if is_go and f.endswith(".go") and not f.endswith("_test.go"):
                try:
                    if re.search(r"^package main\b", open(p, errors="ignore").read(4000), re.M):
                        return True
                except OSError:
                    pass
    return False


def _is_github_action(repo_path):
    for f in ("action.yml", "action.yaml"):
        p = os.path.join(repo_path, f)
        if os.path.isfile(p):
            try:
                if re.search(r"^runs:", open(p, errors="ignore").read(), re.M):
                    return True
            except OSError:
                pass
    return False


def _looks_distributed_as_package(repo_path):
    """Evidence that the repo's product is a package or CLI that people install, not a service someone runs:
    packaging metadata plus an install command in the README."""
    try:
        names = os.listdir(repo_path)
    except OSError:
        return False
    metadata = False
    if "setup.py" in names or any(n.endswith(".gemspec") for n in names):
        metadata = True
    elif "pyproject.toml" in names:
        try:
            metadata = re.search(r"^\[project\]", open(os.path.join(repo_path, "pyproject.toml"), errors="ignore").read(), re.M) is not None
        except OSError:
            pass
    elif "package.json" in names:
        try:
            pj = json.load(open(os.path.join(repo_path, "package.json"), errors="ignore"))
            metadata = not pj.get("private") and any(k in pj for k in ("main", "exports", "bin", "module", "types"))
        except (OSError, ValueError):
            pass
    elif "Cargo.toml" in names:
        metadata = True
    elif "go.mod" in names:
        metadata = True
    if not metadata:
        return False
    for n in names:
        if n.lower().startswith("readme"):
            try:
                if _INSTALL_RE.search(open(os.path.join(repo_path, n), errors="ignore").read(60000)):
                    return True
            except OSError:
                pass
    return False


def _repo_kind(repo_path, runtime, infra, details, monorepo, deps=None, gpu=None):
    """application / infrastructure_only / ml_project / example_collection -- used to avoid
    reporting gaps that make no sense for the kind of repo (e.g. 'no Dockerfile' on a config-only repo)."""
    base = os.path.basename(os.path.abspath(repo_path)).lower()
    if any(os.path.isfile(os.path.join(repo_path, t)) for t in ("cookiecutter.json", "copier.yml", "copier.yaml")):
        return "project_template"
    ml = runtime.get("ml_artifacts") or {}
    if ml.get("markers") or (ml.get("model_files") and not runtime["services"]["list"]) \
            or ((ml.get("notebooks") or (gpu or {}).get("gpu_likely")) and not (deps or {}).get("web_framework")
                and not infra["has_dockerfile"]):
        return "ml_project"
    locs = monorepo.get("manifest_locations", [])
    example_locs = [l for l in locs if any(p in ("example", "examples", "sample", "samples") for p in l.lower().split(os.sep))]
    app_files = sum(n for lang, n in runtime["languages"].items() if lang not in CONFIG_ONLY_LANGUAGES)
    if base.endswith(("examples", "example-apps", "samples", "exercises", "guides", "tutorials", "quickstarts", "cookbook", "recipes",
                        "best-practices", "bestpractices", "practices", "cheatsheet", "cheatsheets", "roadmap", "interview-questions")) \
            or base.endswith("hard-way") or base.startswith(("awesome-", "learn-")) or (len(locs) >= 8 and len(example_locs) * 2 >= len(locs) and app_files < 150):   # istio has samples/ too, but 1500 Go files: a product
        return "example_collection"
    if runtime["dockerfiles"]["count"] >= 20 and app_files < runtime["dockerfiles"]["count"] * 3:
        return "example_collection"          # an image catalogue (bitnami/containers): recipes, not one product
    tf_roots = (details.get("terraform") or {}).get("root_configs", 0)
    if (infra["has_k8s"] or infra["has_terraform"] or infra["has_helm"]) and app_files < 25 \
            and (not infra["has_dockerfile"] or (tf_roots >= 5 and runtime["dockerfiles"]["count"] <= 3)):
        return "infrastructure_only"
    if app_files == 0 and not (infra["has_k8s"] or infra["has_terraform"] or infra["has_helm"]):
        return "no_application_code"
    names = os.listdir(repo_path) if os.path.isdir(repo_path) else []
    if any(n.endswith(".gemspec") for n in names) and "config.ru" not in names and not infra["has_dockerfile"] and not infra["has_k8s"]:
        return "library_or_tool"                      # a Ruby gem, not a Rails app
    if "composer.json" in names and not infra["has_dockerfile"] and not infra["has_k8s"]:
        try:
            if json.load(open(os.path.join(repo_path, "composer.json"), errors="ignore")).get("type") in ("library", "metapackage", "composer-plugin", "project-template-x"):
                return "library_or_tool"
        except (OSError, ValueError):
            pass
    app_markers = [m for m in ("config/routes.rb", "artisan", "manage.py", "odoo-bin", "next.config.js", "next.config.mjs",
                               "next.config.ts", "nuxt.config.ts", "angular.json", "mix.exs", "Program.cs")
                   if os.path.isfile(os.path.join(repo_path, m))]
    if app_markers:
        return "application"
    # a Python framework/library repo contains a top-level package named like its own main dependency (django/django)
    if any(os.path.isfile(os.path.join(repo_path, f)) for f in ("pyproject.toml", "setup.py", "setup.cfg")):
        for dep in (deps or {}).get("web_framework", []):
            if os.path.isdir(os.path.join(repo_path, dep)) or os.path.isdir(os.path.join(repo_path, "src", dep)):
                return "library_or_tool"
    if _has_binary_entrypoint(repo_path) is False and not infra["has_dockerfile"] and not infra["has_k8s"] and not infra["has_helm"]:
        return "library_or_tool"
    if _is_github_action(repo_path) and not infra["has_helm"]:
        return "library_or_tool"
    if not infra["has_dockerfile"] and not infra["has_k8s"] and not infra["has_helm"] and _installs_itself(repo_path) \
            and not any(os.path.isfile(os.path.join(repo_path, m)) for m in ("Procfile", "app.json", "fly.toml", "render.yaml")):
        return "library_or_tool"
    deploys = infra["has_dockerfile"] or infra["has_k8s"] or details.get("has_docker_compose") or details.get("paas_config")
    if not deploys and not infra["has_helm"] and _looks_distributed_as_package(repo_path):
        return "library_or_tool"
    if not deploys and not (deps or {}).get("web_framework") and not runtime["services"]["list"][:0]:
        return "library_or_tool"
    return "application"


_JUNK = {"__MACOSX", ".DS_Store", "Thumbs.db", ".git"}


_MARKERS = ("readme", "license", "package.json", "pyproject.toml", "go.mod", "pom.xml", "dockerfile", "docker-compose", "compose.y",
            ".github", "makefile", ".gitignore", "requirements.txt", "cargo.toml", "gemfile", "composer.json", "build.gradle")


def _has_project_marker(folder):
    try:
        return any(n.lower().startswith(_MARKERS) for n in os.listdir(folder))
    except OSError:
        return False


def unwrap_single_folder(path, max_levels=3):
    """A zip often unpacks into one wrapper folder (repo-main/). Step into it when it is the only real thing there."""
    for _ in range(max_levels):
        try:
            names = [n for n in os.listdir(path) if n not in _JUNK]
        except OSError:
            return path
        inner = os.path.join(path, names[0]) if len(names) == 1 else ""
        if inner and os.path.isdir(inner) and not os.path.islink(inner) and _has_project_marker(inner):
            path = inner
        else:
            return path
    return path


def scan_repo(repo_path):
    """Runs every scanner layer and merges the results into one structured dict --
    this is the only object every downstream node (gap_identifier, questionnaire,
    architecture_reasoner, report_writer) ever reads from."""
    repo_path = unwrap_single_folder(repo_path)
    infra_signals = detect_infra_signals(repo_path)
    infra_details = detect_infra_details(repo_path)
    dependency_result = detect_dependencies(repo_path)
    structure = detect_structure(repo_path)
    entrypoints = detect_entrypoints(repo_path)
    env_vars, secrets_findings, uses_config_framework = detect_env_vars_and_secrets(repo_path)
    third_party_services = detect_third_party_services(dependency_result["all_dependencies_found"])
    managed_services = detect_managed_services(dependency_result["all_dependencies_found"], env_vars)
    monorepo = detect_monorepo(repo_path)
    docs = detect_project_docs(repo_path)
    runtime = detect_runtime_picture(repo_path)
    sensitive_files = detect_sensitive_files(repo_path)
    quality = detect_quality(repo_path, infra_details)

    entrypoints = sorted(set(entrypoints) | set(runtime.get("entrypoints_detected", [])))
    entrypoints_total = len(entrypoints)
    entrypoints = entrypoints[:40]

    repo_kind = _repo_kind(repo_path, runtime, infra_signals, infra_details, monorepo, dependency_result['categorized'], dependency_result['gpu_signals'])
    monorepo["manifest_locations_total"] = len(monorepo["manifest_locations"])
    if repo_kind in ("example_collection", "project_template"):
        # hundreds of near-identical samples add noise, not insight: keep a sample and the true totals
        monorepo["manifest_locations"] = monorepo["manifest_locations"][:25]
        svc = runtime["services"]
        svc_list = svc.get("list") or []
        if len(svc_list) > 25:
            svc_list = sorted(svc_list, key=lambda x: (not x.get("has_dockerfile"), x.get("path", "")))
            runtime["services"] = {**svc, "list": svc_list[:25], "list_truncated": True, "list_total": len(svc_list)}
        runtime["entrypoints_detected"] = (runtime.get("entrypoints_detected") or [])[:15]
        runtime["dockerfiles"] = (runtime.get("dockerfiles") or [])[:10] if isinstance(runtime.get("dockerfiles"), list) else runtime.get("dockerfiles")
        entrypoints = entrypoints[:15]

    return {
        "repo_kind": repo_kind,
        "infra_signals": infra_signals,
        "infra_details": infra_details,
        "sensitive_files": sensitive_files,
        **quality,
        "dependencies": dependency_result["categorized"],
        "gpu_signals": dependency_result["gpu_signals"],
        "structure": structure,
        "entrypoints": entrypoints,
        "entrypoints_total": entrypoints_total,
        "env_vars": env_vars,
        "uses_config_framework": uses_config_framework,
        "third_party_services": third_party_services,
        "managed_services": managed_services,
        "monorepo": monorepo,
        "secrets_findings": secrets_findings,
        **runtime,
        "readme_excerpt": docs.get("readme_excerpt"),
        "readme_truncated": docs.get("readme_truncated", False),
        "readme_withheld_reason": docs.get("readme_withheld_reason"),
    }


if __name__ == "__main__":
    import sys
    import json
    path = sys.argv[1] if len(sys.argv) > 1 else "."
    result = scan_repo(path)
    print(json.dumps(result, indent=2))
