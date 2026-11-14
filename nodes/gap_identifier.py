import os
_DOC_DIRS = {"docs", "doc", "dev-docs", "documentation", "website", "examples", "example", "scripts", "tools", "samples", "sample", "benchmarks", "extra", "contrib", "spec", "specs", "test", "tests", "e2e", "perf", "script", "composer", "vendor"}
_MAIN_NAMES = {"main.py", "app.py", "server.py", "manage.py", "wsgi.py", "asgi.py", "index.js", "server.js", "app.js", "main.go", "main.ts", "index.ts",
               "server.ts", "main.js", "program.cs", "main.java", "application.java", "main.rs", "main.kt"}


def _drop_non_services(service_list):
    """Documentation sites, example folders and a repository root that only holds helper scripts are not services:
    reporting 'no tests' or 'no Dockerfile' for them is noise."""
    out = [x for x in service_list if not (set(x["path"].replace("\\", "/").lower().split("/")) & _DOC_DIRS)]
    if len(out) > 1:
        out = [x for x in out if not (x["path"] == "." and not x.get("has_dockerfile")
                                       and not ({e.lower() for e in x.get("entrypoints", [])} & _MAIN_NAMES))]
    return out


def _dockerfiles_without_ignore(scan_result, hy):
    """None = unknown (keep the gap); False = every Dockerfile folder (or a parent folder) has a .dockerignore; list = folders without one."""
    dirs = set(hy.get("dockerignore_dirs") or [])
    locs = (scan_result.get("dockerfiles") or {}).get("locations") or []
    if not dirs or not locs:
        return None
    missing = []
    for loc in locs:
        d = os.path.dirname(loc.replace("\\", "/")) or "."
        chain = [d]
        while d not in ("", "."):
            d = os.path.dirname(d) or "."
            chain.append(d)
        if not any(c in dirs for c in chain):
            missing.append(os.path.dirname(loc) or ".")
    return missing if missing else False


def _is_small(scan_result):
    """A small project: one service (or none) and no cloud deployment config of its own. For these, missing CI,
    monitoring or IaC is a recommendation, not an alarm -- a hobby app that runs fine on one free server is not 'high risk'."""
    infra = scan_result.get("infra_signals") or {}
    svc = ((scan_result.get("services") or {}).get("list") or [])
    svc = [x for x in svc if not x.get("client_app")]
    return len(svc) <= 1 and not (infra.get("has_k8s") or infra.get("has_helm") or infra.get("has_terraform"))


_ELSEWHERE = " If you have this outside the repository (for example a separate CI service or hosted monitoring), this does not apply to you."

# How each gap is grouped in the report. required = the project is unsafe or cannot be trusted to run without it;
# recommended = production practice; optional = hardening and nice-to-have. Anything not listed is 'recommended'.
GROUP_ORDER = {"required": 0, "recommended": 1, "optional": 2}
GROUP_LABEL = {"required": "Needed to run safely", "recommended": "Recommended", "optional": "Optional"}
_REQUIRED = ("possible_hardcoded_secrets", "sensitive_files_in_repo", "env_file_in_repo", "no_run_files_found")
_OPTIONAL = ("no_dependency_update_bot", "ci_no_security_scanning", "ci_does_not_build_images", "no_dockerignore", "terraform_no_lock_file",
             "dev_env_files_in_repo", "secret_shaped_values_in_tests_or_examples", "k8s_no_network_policies", "k8s_no_disruption_or_autoscaling_config",
             "k8s_ingress_class_not_gke", "tracing_without_metrics_alerting", "error_tracking_only", "no_cloud_iac", "unpinned_base_images", "services_without_dockerfile")


def gap_group(gap):
    issue = gap["issue"]
    if issue.startswith(_REQUIRED):
        return "required"
    if issue.startswith("in_cluster_") and gap.get("severity") == "high":
        return "required"              # a database that loses its data on every restart
    if issue.startswith(_OPTIONAL):
        return "optional"
    return "recommended"


def identify_gaps(scan_result):
    """Turns the scanner's structured findings into a ranked list of
    production-readiness gaps. Still fully rule-based -- nothing here is a
    judgment call, just facts translated into risks."""
    gaps = []
    infra = scan_result["infra_signals"]
    details = scan_result.get("infra_details") or {}
    repo_kind = scan_result.get("repo_kind", "application")

    small = _is_small(scan_result)
    if not infra["has_cicd"]:
        gaps.append({
            "issue": "no_cicd",
            "severity": "low" if small else "high",
            "detail": "No CI/CD config was found in the repository -- if deploys are manual, they are slow and error-prone." + _ELSEWHERE
                      + (" (Low because this looks like a small, single-service project.)" if small else ""),
        })

    if not infra["has_tests"]:
        gaps.append({
            "issue": "no_tests",
            "severity": "medium" if small else "high",
            "detail": "No tests folder was found in the repository -- changes can't be verified automatically before shipping."
                      + (" (Medium because this looks like a small, single-service project.)" if small else ""),
        })

    if not infra["has_dockerfile"] and repo_kind in ("application", "ml_project") \
            and not details.get("image_build_tools") and not details.get("paas_config"):
        dev_only = details.get("dev_only_dockerfiles") or []
        gaps.append({
            "issue": "no_dockerfile",
            "severity": "medium",
            "detail": "No Dockerfile found for the application -- it isn't packaged for consistent deploys."
                      + (f" (Only development/test Dockerfiles exist: {', '.join(dev_only[:3])}.)" if dev_only else ""),
        })

    if repo_kind == "application" and scan_result.get("entrypoints_total", 1) == 0 and not infra["has_dockerfile"] \
            and not details.get("has_docker_compose") and not details.get("paas_config") and not scan_result.get("dependencies"):
        gaps.append({
            "issue": "no_run_files_found",
            "severity": "medium",
            "detail": "The scan found no recognisable entry point, dependency list, Dockerfile or compose file -- it cannot tell how this project starts. "
                      "Entry points are matched against common naming conventions, so a custom layout can be missed; confirm how the project is started.",
        })

    iac_real = [t for t in (details.get("iac_tools") or []) if t not in ("Kubernetes manifests", "Helm")]
    if not infra["has_terraform"] and not infra["has_k8s"] and not infra["has_helm"] and not iac_real \
            and repo_kind == "application":
        if details.get("paas_config"):
            pass  # deploys through a managed platform config (Vercel, Heroku-style...) -- that is the IaC here
        elif details.get("has_docker_compose"):
            gaps.append({
                "issue": "no_cloud_iac",
                "severity": "low",
                "detail": "A docker-compose file exists (good for local/single-host runs) but no Terraform, Kubernetes, Helm or other cloud infrastructure-as-code -- cloud infrastructure isn't reproducible from the repo.",
            })
        else:
            gaps.append({
                "issue": "no_iac",
                "severity": "low" if small else "medium",
                "detail": "No Terraform, Kubernetes, Helm, serverless or other infrastructure-as-code was found in the repository -- infra isn't reproducible or version-controlled." + _ELSEWHERE,
            })

    by_kind = {}
    default_creds = []
    for f in scan_result["secrets_findings"]:
        if f["pattern_type"] == "database_url_default_credentials":
            if f.get("location_kind", "source") in ("source", "ci"):
                default_creds.append(f)
            continue
        by_kind.setdefault(f.get("location_kind", "source"), []).append(f)
    if default_creds:
        files = sorted({f["file"] for f in default_creds})
        gaps.append({
            "issue": "default_credentials_in_config",
            "severity": "medium",
            "detail": f"Database connection strings with default/weak credentials (e.g. user=password, localhost) appear in {len(files)} file(s), e.g. {', '.join(files[:3])} -- fine for local development, but make sure production uses secrets from a secrets manager.",
        })
    if by_kind.get("source") or by_kind.get("ci"):
        n = len(by_kind.get("source", [])) + len(by_kind.get("ci", []))
        hits = by_kind.get("source", []) + by_kind.get("ci", [])
        where = "; ".join(sorted({f"{f['file']} ({f['pattern_type'].replace('_', ' ')})" for f in hits})[:4])
        gaps.append({
            "issue": "possible_hardcoded_secrets",
            "severity": "high",
            "detail": f"{n} possible hardcoded secret(s) found in application or CI files: {where}. The scanner matched the shape of a secret and did not judge whether it is real -- open each file; real ones need to move to a secrets manager or environment variables before this goes anywhere near production.",
        })
    if by_kind.get("test_or_example"):
        gaps.append({
            "issue": "secret_shaped_values_in_tests_or_examples",
            "severity": "low",
            "detail": f"{len(by_kind['test_or_example'])} secret-shaped value(s) found only in test/example/docs files -- probably fixtures, but worth confirming none is a real credential.",
        })

    tf = details.get("terraform") or {}
    if infra["has_terraform"] and tf.get("root_configs"):
        if not tf.get("remote_backend"):
            gaps.append({
                "issue": "terraform_no_remote_state",
                "severity": "medium",
                "detail": "Terraform configuration with providers was found but no remote state backend (S3, GCS, azurerm, Terraform Cloud) -- state lives on one machine and cannot be shared or locked.",
            })
        if not tf.get("lock_file"):
            gaps.append({
                "issue": "terraform_no_lock_file",
                "severity": "low",
                "detail": "No .terraform.lock.hcl is committed -- provider versions can change between runs.",
            })

    sens = scan_result.get("sensitive_files") or {}
    if sens.get("dev_env_files") and not sens.get("env_files"):
        gaps.append({
            "issue": "dev_env_files_in_repo",
            "severity": "low",
            "detail": f"Development/test env files are committed ({', '.join(sens['dev_env_files'][:3])}); contents were not read -- confirm they hold no real credentials.",
        })
    if sens.get("env_files"):
        gaps.append({
            "issue": "env_file_in_repo",
            "severity": "medium",
            "detail": f"Real environment file(s) exist in the repository ({', '.join(sens['env_files'][:3])}); the scanner did not open them. Env files often hold credentials, so confirm they contain only non-secret defaults."
                      + ("" if not sens.get("env_ignored_by_gitignore") else " (.gitignore lists .env, so check whether it is tracked.)"),
        })
    src_files = [x for x in sens.get("sensitive_file_names") or [] if x["location_kind"] == "source"]
    risky = [x for x in src_files if not x["file"].endswith(".tfvars")]
    tfvars = [x for x in src_files if x["file"].endswith(".tfvars")]
    if risky:
        gaps.append({
            "issue": "sensitive_files_in_repo",
            "severity": "high",
            "detail": f"Files that normally hold keys or state are in the repository: {', '.join(x['file'] for x in risky[:4])} (names only; contents were not read).",
        })
    if tfvars:
        gaps.append({
            "issue": "tfvars_file_in_repo",
            "severity": "medium",
            "detail": f"A Terraform variables file is committed ({', '.join(x['file'] for x in tfvars[:3])}); these often contain project IDs or credentials -- the contents were not read, so check them.",
        })

    # ---- gaps from the whole-repo picture (all optional keys: older scans lack them) ----
    k8s = scan_result.get("kubernetes_details") or {}
    if k8s.get("workloads_found") and k8s.get("liveness_probes") == "none" \
            and k8s.get("readiness_probes") == "none":
        gaps.append({
            "issue": "no_health_probes",
            "severity": "medium",
            "detail": "Kubernetes workloads were found but none define liveness or readiness probes -- a broken instance keeps receiving traffic.",
        })

    obs = scan_result.get("observability")
    if obs is not None and repo_kind == "application":
        has_metrics = obs.get("metrics_library") or obs.get("vendor_apm") or infra.get("has_monitoring_manifests")
        if not (obs.get("tracing_opentelemetry") or has_metrics or obs.get("error_tracking")):
            deployed = infra.get("has_k8s") or infra.get("has_helm") or infra.get("has_terraform") or details.get("has_docker_compose")
            gaps.append({
                "issue": "no_observability",
                "severity": "high" if (deployed and not small) else ("low" if small else "medium"),
                "detail": "No tracing, metrics library, APM or monitoring manifests were found in the repository -- failures would go unnoticed until users report them." + _ELSEWHERE
                          + ("" if (deployed and not small) else " (Lower because this looks like a small project or the repository has no deployment configuration of its own.)"),
            })
        elif not has_metrics:
            if obs.get("tracing_opentelemetry"):
                gaps.append({
                    "issue": "tracing_without_metrics_alerting",
                    "severity": "medium",
                    "detail": "Tracing instrumentation was found, but no metrics library or alerting/monitoring config -- nothing in the repo would warn you before users notice a problem.",
                })
            else:
                gaps.append({
                    "issue": "error_tracking_only",
                    "severity": "medium",
                    "detail": "Error tracking (e.g. Sentry) was found, but no metrics library, tracing or alerting/monitoring config -- exceptions get reported, but slowdowns and outages would not trigger an alert.",
                })

    for store in scan_result.get("in_cluster_datastores") or []:
        if store.get("any_persistent_volume"):
            continue
        where = store.get("where") or ["kubernetes"]
        if "kubernetes" in where:
            cache_like = store["type"] in ("redis", "memcached")
            gaps.append({
                "issue": f"in_cluster_{store['type']}_without_persistent_volume",
                "severity": "medium" if cache_like else "high",
                "detail": f"A {store['type']} instance runs inside the cluster with no persistent volume (data lives only as long as the pod) -- a restart loses its data."
                          + (" Fine if it is only a cache; if it holds queues or sessions you cannot lose, add a volume or use a managed service." if cache_like else ""),
            })
        else:
            gaps.append({
                "issue": f"compose_{store['type']}_without_volume",
                "severity": "medium",
                "detail": f"A {store['type']} container is defined in docker-compose without a volume (data is lost when the container is recreated). Fine for local development; not for production data.",
            })

    services = (scan_result.get("services") or {})
    service_list = services.get("list") or []
    if len(service_list) > 1:
        service_list = [x for x in service_list if not x.get("client_app")]
        # folders that hold only a Dockerfile (packaging/, build images) are not services: they have no code to test,
        # and their presence means the code services are built from those Dockerfiles
        packaging_only = [x for x in service_list if x.get("container_only")]
        service_list = _drop_non_services(service_list)
        service_list = [x for x in service_list if not x.get("container_only")]
        untested = [x["path"] for x in service_list if not x.get("has_tests")]
        if untested and len(untested) < len(service_list):
            gaps.append({
                "issue": "services_without_tests",
                "severity": "medium",
                "detail": f"{len(untested)} of {len(service_list)} services have no test files: {', '.join(untested[:10])}.",
            })
        no_docker = [x["path"] for x in service_list if not x.get("has_dockerfile")]
        if no_docker and infra.get("has_dockerfile") and not services.get("shared_container_dirs") and not packaging_only:
            gaps.append({
                "issue": "services_without_dockerfile",
                "severity": "low",
                "detail": f"{len(no_docker)} service folder(s) have no Dockerfile: {', '.join(no_docker[:10])}.",
            })

    # ---- quality of what exists (Dockerfiles, CI, Kubernetes, dependencies) ----
    dq = scan_result.get("dockerfile_quality") or {}
    ci = scan_result.get("ci_quality") or {}
    kq = scan_result.get("kubernetes_quality") or {}
    dp = scan_result.get("dependency_pinning") or {}
    hy = scan_result.get("repo_hygiene") or {}
    if dq.get("analysed"):
        root = dq.get("runs_as_root", "none")
        if root != "none":
            mitigated = kq.get("run_as_non_root") in ("most", "all")
            gaps.append({
                "issue": "containers_run_as_root",
                "severity": "low" if (root == "some" or mitigated) else "medium",
                "detail": f"{root} of the {dq['analysed']} analysed Dockerfiles never switch to a non-root USER (e.g. {', '.join(dq.get('runs_as_root_examples', [])[:3])})"
                          + (" -- Kubernetes manifests set runAsNonRoot for most workloads, which mitigates this when deployed there." if mitigated else " -- a container escape or app bug then runs with root rights."),
            })
        if dq.get("unpinned_base_image") != "none":
            gaps.append({
                "issue": "unpinned_base_images",
                "severity": "medium" if dq["unpinned_base_image"] in ("most", "all") else "low",
                "detail": f"{dq['unpinned_base_image']} of the Dockerfiles use a base image without a version tag or digest (latest) (e.g. {', '.join(dq.get('unpinned_base_examples', [])[:3])}) -- builds are not reproducible and can break or change silently.",
            })
        uncovered = _dockerfiles_without_ignore(scan_result, hy)
        if not hy.get("dockerignore") and uncovered is not False:
            where = (f" (none found for {', '.join(uncovered[:3])}{' and more' if len(uncovered) > 3 else ''})" if uncovered else "")
            gaps.append({
                "issue": "no_dockerignore",
                "severity": "low",
                "detail": "Dockerfiles exist but there is no .dockerignore at the repository root" + where + " -- build contexts may ship .git, local env files or large folders into images.",
            })
    if infra["has_cicd"] and ci.get("files_count") and not ci.get("runs_tests"):
        gaps.append({
            "issue": "ci_does_not_run_tests",
            "severity": "low" if (scan_result.get("repo_kind") == "infrastructure_only" and ci.get("linting")) else "medium",
            "detail": "CI pipelines exist but none of them appear to run a test command -- broken code can still be merged and shipped.",
        })
    if infra["has_cicd"] and ci.get("files_count") and not ci.get("security_scanning"):
        gaps.append({
            "issue": "ci_no_security_scanning",
            "severity": "low",
            "detail": "No dependency, image, secret or code scanning step (e.g. CodeQL, Trivy, Snyk, gitleaks) was found in the CI pipelines.",
        })
    if infra["has_dockerfile"] and infra["has_cicd"] and ci.get("files_count") and not ci.get("builds_container_image"):
        gaps.append({
            "issue": "ci_does_not_build_images",
            "severity": "low",
            "detail": "Dockerfiles exist and CI exists, but no pipeline step builds a container image -- image build problems would only show up at deploy time.",
        })
    if not hy.get("dependency_update_bot"):
        gaps.append({
            "issue": "no_dependency_update_bot",
            "severity": "low",
            "detail": "No Dependabot or Renovate configuration was found in the repository -- dependency and base-image updates (including security fixes) depend on someone remembering.",
        })
    if (dp.get("manifests_without_lockfile_nearby") or 0) > 0 and not dp.get("lockfile_present"):
        gaps.append({
            "issue": "no_dependency_lockfile",
            "severity": "medium",
            "detail": "Dependency manifests exist but no lock file (package-lock.json, poetry.lock, go.sum...) was found -- installs can resolve to different versions on every build.",
        })
    if kq.get("workloads_checked"):
        if kq.get("security_context") == "none":
            gaps.append({
                "issue": "k8s_no_security_context",
                "severity": "medium",
                "detail": "None of the Kubernetes workloads set a securityContext (non-root user, read-only filesystem, dropped capabilities).",
            })
        if kq.get("image_tag_latest") != "none":
            gaps.append({
                "issue": "k8s_images_use_latest_tag",
                "severity": "medium",
                "detail": f"{kq['image_tag_latest']} of the Kubernetes workloads use an image tagged :latest -- a redeploy can silently pull different code.",
            })
        if not kq.get("network_policies"):
            gaps.append({
                "issue": "k8s_no_network_policies",
                "severity": "low",
                "detail": "No NetworkPolicy objects found -- every pod can talk to every other pod in the cluster.",
            })
        ing = set((scan_result.get("kubernetes_details") or {}).get("ingress_classes") or [])
        foreign = sorted(c for c in ing if c not in ("gce", "gce-internal", "gke", "gke-l7-global-external-managed"))
        if foreign and not (ing & {"gce", "gce-internal"}):
            gaps.append({
                "issue": "k8s_ingress_class_not_gke",
                "severity": "low",
                "detail": f"The Ingress objects use the class {', '.join(foreign)}. On GKE the built-in HTTP load balancer needs the gce class; with another class you must install that controller yourself "
                          "(and pay for its load balancer) or change the class before deploying.",
            })
        if not kq.get("pod_disruption_budgets") and not kq.get("autoscaling"):
            gaps.append({
                "issue": "k8s_no_disruption_or_autoscaling_config",
                "severity": "low",
                "detail": "No PodDisruptionBudget or autoscaler found -- node upgrades can take all replicas down at once and traffic spikes are not absorbed automatically.",
            })

    if repo_kind in ("example_collection", "no_application_code", "infrastructure_only"):
        keep = ("possible_hardcoded_secrets", "secret_shaped", "env_file_in_repo", "sensitive_files_in_repo")
        if repo_kind == "infrastructure_only":
            keep += ("no_health_probes", "in_cluster_", "compose_", "no_cicd", "terraform_", "k8s_", "ci_",
                     "no_dependency_update_bot")
        gaps = [g for g in gaps if g["issue"].startswith(keep)]
    if repo_kind == "project_template":
        keep = ("possible_hardcoded_secrets", "secret_shaped", "env_file_in_repo", "sensitive_files_in_repo",
                "no_cicd", "no_tests")
        gaps = [g for g in gaps if g["issue"].startswith(keep)]
    if repo_kind == "library_or_tool":
        drop = ("containers_run_as_root", "unpinned_base_images", "no_dockerignore", "ci_does_not_build_images",
                "no_dependency_lockfile", "k8s_", "no_dockerfile", "no_iac", "no_cloud_iac", "no_observability", "error_tracking_only",
                "tracing_without_metrics_alerting", "services_without_dockerfile", "no_health_probes", "compose_", "in_cluster_")
        gaps = [g for g in gaps if not g["issue"].startswith(drop)]
    for gap in gaps:
        gap["source"] = "rule-based scan"
        gap["group"] = gap_group(gap)
    return gaps


if __name__ == "__main__":
    fake_scan = {
        "infra_signals": {
            "has_cicd": False, "has_tests": False, "has_dockerfile": True,
            "has_terraform": False, "has_k8s": False, "has_helm": False,
        },
        "secrets_findings": [],
        "gpu_signals": {"gpu_likely": False, "frameworks_found": []},
    }
    print(identify_gaps(fake_scan))
