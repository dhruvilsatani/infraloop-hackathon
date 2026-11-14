import os
import re

from scanner.common import walk_repo, is_dev_only_path, is_test_path
from scanner.compose import is_compose_filename, parse_compose

TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs"}
MAX_FILE_BYTES = 1_000_000

CI_FILES = ("Jenkinsfile", ".gitlab-ci.yml", "azure-pipelines.yml", "bitbucket-pipelines.yml",
            ".travis.yml", "cloudbuild.yaml", "cloudbuild.yml", "appveyor.yml", "buildkite.yml")

# Kubernetes resource KINDS that really are monitoring configuration (not just the word "prometheus")
MONITORING_KINDS = {"ServiceMonitor", "PodMonitor", "PrometheusRule", "Alertmanager", "Prometheus",
                    "AlertmanagerConfig", "ScrapeConfig", "Probe", "GrafanaDashboard", "Grafana",
                    "OpenTelemetryCollector"}
MONITORING_WORDS = ("prometheus", "grafana", "loki", "jaeger", "tempo", "zipkin", "otelcol",
                    "opentelemetry-collector", "otel-collector", "alertmanager", "datadog", "victoriametrics")
GITOPS_ARGO_KINDS = {"Application", "ApplicationSet", "AppProject"}
GITOPS_FLUX_KINDS = {"GitRepository", "Kustomization", "HelmRelease", "HelmRepository", "OCIRepository"}

PAAS_FILES = {
    "vercel.json": "Vercel", "netlify.toml": "Netlify", "fly.toml": "Fly.io", "render.yaml": "Render",
    "Procfile": "Heroku-style Procfile", "railway.json": "Railway", "railway.toml": "Railway",
    "wrangler.toml": "Cloudflare Workers", "firebase.json": "Firebase", "amplify.yml": "AWS Amplify",
}
IAC_FILES = {
    "Pulumi.yaml": "Pulumi", "cdk.json": "AWS CDK", "serverless.yml": "Serverless Framework",
    "serverless.yaml": "Serverless Framework", "serverless.ts": "Serverless Framework",
    "skaffold.yaml": "Skaffold", "kustomization.yaml": "Kustomize", "kustomization.yml": "Kustomize",
    "Chart.yaml": "Helm", "ansible.cfg": "Ansible", "terragrunt.hcl": "Terragrunt",
    "main.bicep": "Bicep", "samconfig.toml": "AWS SAM",
}


def _looks_like_test_file(filename):
    name = filename.lower()
    if name.endswith(".py"):
        return name.startswith("test_") or name.endswith("_test.py")
    if name.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs")):
        return ".test." in name or ".spec." in name
    if name.endswith("_test.go"):
        return True
    if name.endswith((".cs", ".java", ".kt", ".php", ".swift")):
        return name.endswith(("test.cs", "tests.cs", "test.java", "tests.java", "test.kt", "test.php", "tests.php", "test.swift", "tests.swift"))
    if name.endswith(".rb"):
        return name.endswith(("_spec.rb", "_test.rb"))
    return False


def _is_dockerfile(filename):
    filename = filename.lower()                       # uptime-kuma names its files docker/dockerfile and base.dockerfile
    return (filename in ("dockerfile", "containerfile") or filename.startswith(("dockerfile.", "containerfile."))
            or filename.endswith((".dockerfile", ".containerfile")))


def _read(path):
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return ""
        with open(path, "r", errors="ignore") as fh:
            return fh.read()
    except (IOError, OSError):
        return ""


def _walk_infra(repo_path):
    signals = {
        "has_dockerfile": False, "has_cicd": False, "has_tests": False, "has_terraform": False,
        "has_k8s": False, "has_helm": False, "has_monitoring_manifests": False, "has_gitops": False,
    }
    details = {
        "iac_tools": set(), "paas_config": set(), "has_docker_compose": False,
        "dev_only_dockerfiles": [], "monitoring_sources": set(), "prometheus_annotations_only": False,
        "gitops_tools": set(), "gitops_only_in_examples": True, "kubernetes_kinds_found": set(),
        "image_build_tools": set(),
        "terraform": {"root_configs": 0, "remote_backend": False, "lock_file": False, "required_version": False,
                      "providers_pinned": False, "backend_types": set()},
    }
    saw_prom_word = False
    if os.path.isdir(os.path.join(repo_path, ".github", "workflows")) or \
            os.path.isdir(os.path.join(repo_path, ".circleci")):
        signals["has_cicd"] = True

    for root, dirs, files in walk_repo(repo_path):
        rel_root = os.path.relpath(root, repo_path)
        if any(d in TEST_DIR_NAMES for d in dirs) and not any(p in ("templates", "chart", "charts") for p in rel_root.lower().split(os.sep)):
            signals["has_tests"] = True       # a tests/ folder inside a Helm chart holds chart smoke tests, not the project's tests
        if "roles" in dirs:
            roles_dir = os.path.join(root, "roles")
            try:
                if any(os.path.isdir(os.path.join(roles_dir, r, "tasks")) for r in os.listdir(roles_dir)):
                    details["iac_tools"].add("Ansible")
            except OSError:
                pass

        for f in files:
            rel = os.path.normpath(os.path.join(rel_root, f))
            full = os.path.join(root, f)
            if _is_dockerfile(f):
                if is_dev_only_path(rel):
                    details["dev_only_dockerfiles"].append(rel)
                else:
                    signals["has_dockerfile"] = True
            if f in CI_FILES:
                signals["has_cicd"] = True
            if _looks_like_test_file(f):
                signals["has_tests"] = True
            in_tests = is_test_path(rel)
            if f.endswith(".tf") and not in_tests:
                signals["has_terraform"] = True
                details["iac_tools"].add("Terraform")
                tf_text = _read(full)
                tfd = details["terraform"]
                if re.search(r'^\s*provider\s+"', tf_text, re.M) and not is_dev_only_path(rel):
                    tfd["root_configs"] += 1
                m = re.search(r'^\s*backend\s+"(\w+)"', tf_text, re.M)
                if m and m.group(1) != "local":
                    tfd["remote_backend"] = True
                    tfd["backend_types"].add(m.group(1))
                if re.search(r'^\s*cloud\s*\{', tf_text, re.M):
                    tfd["remote_backend"] = True
                    tfd["backend_types"].add("terraform cloud")
                if re.search(r'^\s*required_version\s*=', tf_text, re.M):
                    tfd["required_version"] = True
                if re.search(r'^\s*version\s*=\s*"', tf_text, re.M) and "required_providers" in tf_text:
                    tfd["providers_pinned"] = True
            if f == ".terraform.lock.hcl":
                details["terraform"]["lock_file"] = True
            if f in ("pom.xml", "build.gradle", "build.gradle.kts") or f.endswith(".csproj") or f in (".ko.yaml", "project.toml"):
                bt = _read(full)
                if "jib-maven-plugin" in bt or "com.google.cloud.tools.jib" in bt:
                    details["image_build_tools"].add("Jib")
                if "Aspire.Hosting" in bt:
                    details["image_build_tools"].add(".NET Aspire (AppHost)")
                if "EnableSdkContainerSupport" in bt or "PublishContainer" in bt or "ContainerRepository" in bt:
                    details["image_build_tools"].add(".NET SDK container publish")
                if "spring-boot:build-image" in bt or "bootBuildImage" in bt:
                    details["image_build_tools"].add("Spring Boot buildpacks")
                if f == ".ko.yaml":
                    details["image_build_tools"].add("ko")
                if f == "project.toml" and "[_]" in bt or (f == "project.toml" and "buildpacks" in bt):
                    details["image_build_tools"].add("Cloud Native Buildpacks")
            if f.endswith(".bicep"):
                details["iac_tools"].add("Bicep")
            if f == "Chart.yaml" and not in_tests:
                signals["has_helm"] = True
            if f in IAC_FILES and not in_tests:
                details["iac_tools"].add(IAC_FILES[f])
            if f in PAAS_FILES and not is_dev_only_path(rel):
                details["paas_config"].add(PAAS_FILES[f])
            if f == "app.yaml" and "runtime:" in _read(full):
                details["paas_config"].add("Google App Engine")

            if not f.endswith((".yaml", ".yml", ".json")):
                continue
            content = _read(full)
            if not content:
                continue

            if is_compose_filename(f):
                if not is_dev_only_path(rel):
                    details["has_docker_compose"] = True
                    for name, svc in parse_compose(content).items():
                        text = (name + " " + svc["image"]).lower()
                        if any(w in text for w in MONITORING_WORDS):
                            details["monitoring_sources"].add("docker-compose")
                continue

            if f.endswith(".json"):
                if "AWSTemplateFormatVersion" in content:
                    details["iac_tools"].add("CloudFormation")
                continue

            if re.match(r"(playbook|site).*\.ya?ml$", f) and re.search(r"^\s*-?\s*hosts:", content, re.M):
                details["iac_tools"].add("Ansible")
            if "AWSTemplateFormatVersion" in content:
                details["iac_tools"].add("AWS SAM" if "AWS::Serverless" in content else "CloudFormation")
            if "crossplane.io" in content:
                details["iac_tools"].add("Crossplane")
            if f in ("Chart.yaml", "requirements.yaml"):
                low = content.lower()
                if any(w in low for w in ("kube-prometheus-stack", "prometheus", "grafana", "loki", "tempo", "datadog")):
                    details["monitoring_sources"].add("helm dependency")

            if in_tests:
                continue
            if "apiVersion:" not in content or "kind:" not in content:
                if "prometheus.io/" in content.lower():
                    saw_prom_word = True
                continue
            if "prometheus.io/" in content.lower():
                saw_prom_word = True
            if any(p_ in ("docs", "doc", "documentation") for p_ in rel.lower().replace("\\", "/").split("/")[:-1]):
                continue       # manifests that only illustrate the documentation are not the project's own deployment
            for doc in re.split(r"^---\s*$", content, flags=re.MULTILINE):
                km = re.search(r"^kind:\s*(\w+)", doc, re.MULTILINE)
                av = re.search(r"^apiVersion:\s*(\S+)", doc, re.MULTILINE)
                if not km or not av:
                    continue
                kind, api = km.group(1), av.group(1)
                if api.startswith(("serving.knative.dev", "run.googleapis.com", "backstage.io", "swagger", "openapi", "mkdocs",
                                   "docusaurus", "ctlptl.dev")) or kind in ("ConformanceReport",):
                    continue          # a Cloud Run / Knative service descriptor, not a Kubernetes cluster
                signals["has_k8s"] = True
                details["kubernetes_kinds_found"].add(kind)
                if kind in MONITORING_KINDS and ("monitoring.coreos.com" in api or "grafana" in api
                                                  or "opentelemetry" in api or "monitoring.googleapis.com" in api):
                    details["monitoring_sources"].add("kubernetes manifests")
                if "argoproj.io" in api and kind in GITOPS_ARGO_KINDS:
                    details["gitops_tools"].add("Argo CD")
                    if not is_dev_only_path(rel):
                        details["gitops_only_in_examples"] = False
                if "fluxcd.io" in api and kind in GITOPS_FLUX_KINDS:
                    details["gitops_tools"].add("Flux")
                    if not is_dev_only_path(rel):
                        details["gitops_only_in_examples"] = False

    if not details["image_build_tools"]:
        for name in os.listdir(repo_path):
            if name.lower().startswith("readme") or name in ("Makefile", "justfile", "Taskfile.yml"):
                if re.search(r"spring-boot:build-image|bootBuildImage", _read(os.path.join(repo_path, name))):
                    details["image_build_tools"].add("Spring Boot buildpacks")
    if details["monitoring_sources"]:
        signals["has_monitoring_manifests"] = True
    elif saw_prom_word:
        details["prometheus_annotations_only"] = True
    if details["gitops_tools"]:
        signals["has_gitops"] = True
    else:
        details["gitops_only_in_examples"] = False
    if signals["has_helm"]:
        details["iac_tools"].add("Helm")
    if signals["has_k8s"]:
        details["iac_tools"].add("Kubernetes manifests")

    for k in ("iac_tools", "paas_config", "monitoring_sources", "gitops_tools", "kubernetes_kinds_found",
              "image_build_tools"):
        details[k] = sorted(details[k])
    details["terraform"]["backend_types"] = sorted(details["terraform"]["backend_types"])
    details["dev_only_dockerfiles"] = sorted(details["dev_only_dockerfiles"])[:10]
    return signals, details


def detect_infra_signals(repo_path):
    """Existence checks for production-readiness signals. Each is its own flag.
    Monitoring and GitOps now require real resource KINDS (ServiceMonitor, Argo Application...),
    not just a keyword somewhere in a YAML file."""
    return _walk_infra(repo_path)[0]


def detect_infra_details(repo_path):
    """Context behind the flags: IaC tools, PaaS config, where monitoring/GitOps comes from."""
    return _walk_infra(repo_path)[1]


if __name__ == "__main__":
    import sys, json
    p = sys.argv[1] if len(sys.argv) > 1 else "."
    s, d = _walk_infra(p)
    print(json.dumps({"signals": s, "details": d}, indent=2))
