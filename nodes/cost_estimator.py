"""Deterministic cost estimate. The LLM never invents these numbers: they are computed here
from knowledge/prices.py (published prices, with source + date) and the per-service CPU/memory
REQUESTS found in the repo's Kubernetes manifests."""
import re
from knowledge.prices import (
    PRICES_USD as P, HOURS_PER_MONTH, SECONDS_PER_MONTH, USD_PER_EUR, USD_PER_EUR_DATE,
    RETRIEVED, RETRIEVED_PLATFORMS, HETZNER_SERVERS, HETZNER_NOTE, HETZNER_LOAD_BALANCERS, NOT_PRICED, PRICES_EUR_AZURE as AZ,
)

ASSUMED_SIZE = {"cpu_cores": 0.25, "memory_gib": 0.5, "replicas": 1}   # used only when the repo states no sizes
HETZNER_FILL = 0.7   # keep ~30% headroom for the OS, Kubernetes/k3s and spikes


def _p(key):
    return P[key][0]


def _eur(usd):
    return usd / USD_PER_EUR


def _autopilot(w):
    per_hour = w["cpu_cores"] * _p("gke_autopilot_vcpu_hour") + w["memory_gib"] * _p("gke_autopilot_gib_hour")
    return per_hour * HOURS_PER_MONTH * w["replicas"]


def _cloud_run_always_on(w):
    per_second = w["cpu_cores"] * _p("cloud_run_cpu_per_vcpu_second_instance_based") \
        + w["memory_gib"] * _p("cloud_run_mem_per_gib_second_instance_based")
    return per_second * SECONDS_PER_MONTH * w["replicas"]


FARGATE_VCPU_STEPS = (0.25, 0.5, 1, 2, 4)


def fargate_size(w):
    """Smallest Fargate task that fits the request (AWS docs: 0.25 vCPU with 0.5 GB is the smallest; from 0.5 vCPU up, memory is at least 2 GB per vCPU)."""
    cpu = next((c for c in FARGATE_VCPU_STEPS if c >= w["cpu_cores"]), w["cpu_cores"])
    mem = max(w["memory_gib"], 0.5, 0 if cpu < 0.5 else 2 * cpu)
    return cpu, mem


def container_apps_size(w):
    """Smallest Container Apps (Consumption) size that fits: 0.25 vCPU with 0.5 GiB is the smallest, memory is always twice the vCPU."""
    cpu = max(w["cpu_cores"], w["memory_gib"] / 2, 0.25)
    cpu = -(-cpu * 4 // 1) / 4          # round up to a quarter vCPU
    return cpu, cpu * 2


def _fargate(w):
    cpu, mem = fargate_size(w)
    per_hour = cpu * _p("fargate_x86_vcpu_hour") + mem * _p("fargate_x86_gb_hour")
    return per_hour * HOURS_PER_MONTH * w["replicas"]


def _container_apps(w):
    """Azure Container Apps, Consumption plan, West Europe, at the ACTIVE rate for every second of the month. Azure bills a lower rate while a
    replica is idle and gives a monthly free grant; neither is subtracted here, so the real bill can be lower."""
    cpu, mem = container_apps_size(w)
    per_second = cpu * _p("container_apps_vcpu_second_active") + mem * _p("container_apps_gib_second_active")
    return per_second * SECONDS_PER_MONTH * w["replicas"]


def _aws_load_balancer_eur():
    """One Application Load Balancer: the fixed hourly fee plus the public IPv4 address it holds in each of two zones.
    The per-use part (LCU) depends on traffic and is NOT included."""
    return _eur((_p("alb_per_hour") + 2 * _p("aws_public_ipv4_per_hour")) * HOURS_PER_MONTH)


def _aws_task_address_eur(tasks):
    """Each Fargate task in a public subnet holds one public IPv4 address, and AWS charges for it."""
    return _eur(tasks * _p("aws_public_ipv4_per_hour") * HOURS_PER_MONTH)


PLATFORM_FN = {"gke_autopilot": _autopilot, "cloud_run": _cloud_run_always_on, "aws_fargate": _fargate, "azure_container_apps": _container_apps}
DB_GIB = {"gcp": 10, "aws": 20, "azure": 32}   # the disk each managed database is priced with: a stated assumption, shown in the report


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


_STATEFUL_NAME_TOKENS = ("redis", "postgres", "mysql", "mariadb", "mongo", "kafka", "rabbitmq", "elasticsearch", "opensearch",
                         "memcached", "cassandra", "zookeeper", "etcd", "clickhouse", "mlflow")


def _workloads(scan_result):
    """Returns (workloads dict, source_note). Repo-stated sizes win; services that have no workload in the manifests get one
    assumed size each (a manifest may cover only one of three services), and the note says which."""
    found = scan_result.get("workload_resources") or {}
    services = [x for x in ((scan_result.get("services") or {}).get("list") or []) if not x.get("client_app")]
    if found:
        out = dict(found)
        stateless = [w for w in out if not any(t in w.lower() for t in _STATEFUL_NAME_TOKENS)]
        missing = len(services) - len(stateless)
        added = []
        if missing > 0:
            def covered(x):
                key = _norm(x["path"].split("/")[-1] or x["path"])
                return bool(key) and any(key in _norm(w) or _norm(w) in key for w in out)
            # the manifest workload that matches no folder name is most likely the app at the repo root, so other services are added first
            unmatched = sorted([x for x in services if not covered(x)], key=lambda x: (x["path"] in (".", ""), x["path"]))
            for x in unmatched[:missing]:
                name = x["path"].split("/")[-1]
                name = name if name not in ("", ".") else "application"
                while name in out:
                    name += "-2"
                out[name] = dict(ASSUMED_SIZE)
                added.append(name)
        note = "CPU/memory requests read from the repo's Kubernetes manifests"
        if added:
            note += (f"; {len(added)} service(s) with no workload in the manifests ({', '.join(added)}) are ASSUMED to need "
                     f"{ASSUMED_SIZE['cpu_cores']} vCPU / {ASSUMED_SIZE['memory_gib']} GiB each")
        return out, note
    skipped = []
    if len(services) > 8 and any(x.get("has_dockerfile") for x in services):
        # in a big monorepo most folders are libraries and modules; only the ones with a Dockerfile are plausible deployables
        skipped = [x["path"] for x in services if not x.get("has_dockerfile")]
        services = [x for x in services if x.get("has_dockerfile")]
    assumed = {s["path"].split("/")[-1] or s["path"]: dict(ASSUMED_SIZE) for s in services}
    if assumed and skipped:
        return assumed, (f"ASSUMPTION: the repo states no resource sizes, so each service is assumed to need "
                         f"{ASSUMED_SIZE['cpu_cores']} vCPU / {ASSUMED_SIZE['memory_gib']} GiB; only the {len(assumed)} folders that have a Dockerfile are priced, "
                         f"the other {len(skipped)} folders have no Dockerfile or manifest and are treated as libraries or modules, not deployments")
    if assumed:
        return assumed, (f"ASSUMPTION: the repo states no resource sizes, so each service is assumed to need "
                         f"{ASSUMED_SIZE['cpu_cores']} vCPU / {ASSUMED_SIZE['memory_gib']} GiB")
    return {"application": dict(ASSUMED_SIZE)}, (
        f"ASSUMPTION: no services or resource sizes were found, so the project is treated as ONE application of "
        f"{ASSUMED_SIZE['cpu_cores']} vCPU / {ASSUMED_SIZE['memory_gib']} GiB")


# Memory a service realistically needs when it is really running. Repo-stated requests are often placeholders
# (0.001 CPU / a few MiB), and a single server dies from out-of-memory if the sum is taken at face value.
# These are labelled ASSUMPTIONS in the report, not measurements.
_FLOOR_BY_LANGUAGE = {"Java": 0.5, "Kotlin": 0.5, "Scala": 0.5, "C#": 0.5, "F#": 0.5}
_DEFAULT_FLOOR_GIB = 0.25
_STORE_FLOOR_GIB = {"postgres": 1.0, "postgresql": 1.0, "mysql": 1.0, "mariadb": 1.0, "mongodb": 1.0, "mongo": 1.0, "redis": 0.25,
                    "kafka": 1.0, "elasticsearch": 2.0, "opensearch": 2.0, "rabbitmq": 0.5, "cassandra": 2.0, "clickhouse": 1.0}


def realistic_memory_gib(scan_result, workloads):
    """Returns (gib, note): each service counts at least a language-based floor, plus in-cluster datastores."""
    langs = {}
    for x in (scan_result.get("services") or {}).get("list") or []:
        langs[(x.get("path") or "").split("/")[-1].lower()] = x.get("languages") or []
    total = 0.0
    for name, w in workloads.items():
        floor = max([_FLOOR_BY_LANGUAGE.get(l, _DEFAULT_FLOOR_GIB) for l in langs.get(name.lower(), [])] or [_DEFAULT_FLOOR_GIB])
        total += max(w["memory_gib"], floor) * w["replicas"]
    names = " ".join(workloads).lower()
    for d in scan_result.get("in_cluster_datastores") or []:
        t = str(d.get("type", "")).lower()
        if t in _STORE_FLOOR_GIB and t not in names:
            total += _STORE_FLOOR_GIB[t]
    note = (f"ASSUMPTION, not measured: at least {_DEFAULT_FLOOR_GIB} GiB per service ({_FLOOR_BY_LANGUAGE['Java']} GiB for Java/.NET) "
            f"plus about 0.25-2 GiB per in-cluster datastore")
    return total, note


PLATFORM_OVERLAP_WORDS = ("discovery", "eureka", "config-server", "configserver", "config_server")


DEMO_TOOLING_WORDS = ("load-gen", "loadgen", "load_gen", "docs", "react-native")


def demo_tooling_services(scan_result):
    """Services that look like demo/test/doc tooling rather than part of a real deployment."""
    out = []
    for x in (scan_result.get("services") or {}).get("list") or []:
        name = (x.get("path") or "").lower().split("/")[-1]
        if any(w in name for w in DEMO_TOOLING_WORDS):
            out.append(x["path"].split("/")[-1])
    return out


def overlap_services(scan_result):
    """Spring Cloud discovery/config servers do what Kubernetes/Cloud Run already provide."""
    out = []
    for x in (scan_result.get("services") or {}).get("list") or []:
        name = (x.get("path") or "").lower()
        if any(w in name for w in PLATFORM_OVERLAP_WORDS):
            out.append(x["path"].split("/")[-1])
    return out


_STATEFUL_TOKENS = ("redis", "postgres", "mysql", "mariadb", "mongo", "kafka", "rabbitmq", "elasticsearch", "opensearch",
                    "memcached", "cassandra", "zookeeper", "etcd", "clickhouse", "mlflow")


def _is_stateful_workload(name, scan_result):
    low = name.lower()
    types = {str(d.get("type", "")).lower() for d in (scan_result.get("in_cluster_datastores") or [])}
    return any(t in low for t in _STATEFUL_TOKENS) or any(t and t in low for t in types)


def _dedicated_sql_hour():
    """db-custom-1-3840 (1 vCPU, 3.75 GiB): the smallest dedicated-core Cloud SQL instance, which has an SLA, unlike the shared-core db-g1-small."""
    return _p("cloud_sql_dedicated_vcpu_hour") * 1 + _p("cloud_sql_dedicated_gib_hour") * 3.75


def plan_options(scan_result, workloads=None):
    """Structured comparison of setups, so the choice is made in code and not by the model.
    Each option: platform, replicas, which services are kept, total EUR/month (compute + cluster fee + 1 load balancer).
    In-cluster datastores (Redis, Postgres...) are NOT doubled: two copies of a database are two different databases.
    Returns (options, meta)."""
    workloads = workloads if workloads is not None else _workloads(scan_result)[0]
    if not workloads:
        return [], {}
    fee_regional = _eur(_p("gke_cluster_fee_per_hour") * HOURS_PER_MONTH)
    # An Autopilot cluster is regional by design and the $74.40 monthly credit (one Autopilot or zonal cluster per billing account) covers its fee
    fee_autopilot = max(0.0, _eur(_p("gke_cluster_fee_per_hour") * HOURS_PER_MONTH - _p("gke_free_credit_per_month")))
    lb_eur = _eur(_p("gcp_lb_forwarding_rule_hour_first5") * HOURS_PER_MONTH)
    demo = set(demo_tooling_services(scan_result))
    overlap = set(overlap_services(scan_result))
    sets = [("all", set())]
    if demo:
        sets.append(("no_demo", demo))
    if overlap:
        sets.append(("no_overlap", overlap))
    if demo and overlap:
        sets.append(("no_demo_no_overlap", demo | overlap))
    options = []
    for set_key, removed in sets:
        kept = {n: w for n, w in workloads.items() if n not in removed}
        if not kept:
            continue
        stateful = {n for n in kept if _is_stateful_workload(n, scan_result)}
        def comp(fn, r):
            return _eur(sum(fn(dict(w, replicas=1)) * (1 if n in stateful else r) for n, w in kept.items()))
        stateless = len(kept) - len(stateful)
        base = {"set": set_key, "removed": sorted(removed), "services": len(kept), "stateless_services": stateless,
                "stateful_kept_single": sorted(stateful), "service_names": sorted(kept)}
        for plat, label, r, zone in (
                ("gke_autopilot", "GKE Autopilot", 1, False),
                ("gke_autopilot", "GKE Autopilot", 2, True),
                ("cloud_run", "Cloud Run always-on", 2, True),
                ("aws_fargate", "AWS ECS Fargate", 1, False),
                ("aws_fargate", "AWS ECS Fargate", 2, True),
                ("azure_container_apps", "Azure Container Apps", 1, False),
                ("azure_container_apps", "Azure Container Apps", 2, True)):
            fn = PLATFORM_FN[plat]
            copies = len(stateful) + stateless * r            # running copies, which is what AWS charges a public address for
            if plat == "aws_fargate":
                fixed, tail = _aws_load_balancer_eur() + _aws_task_address_eur(copies), ", 1 Application Load Balancer"
            elif plat == "azure_container_apps":
                fixed, tail = 0.0, ", no separate load balancer"
            else:
                fixed, tail = (fee_autopilot if plat == "gke_autopilot" else 0.0) + lb_eur, ", 1 load balancer"
            total = comp(fn, r) + fixed
            if plat == "cloud_run":
                unit = "instance" if r == 1 else "instances"
            elif plat == "aws_fargate":
                unit = "task" if r == 1 else "tasks"
            else:
                unit = "replica" if r == 1 else "replicas"
            options.append(dict(base, platform=plat, replicas=r, zone_ha=zone and r >= 2, pod_ha=r >= 2, copies=copies,
                                total=round(total, 2),
                                label=f"{label}, {r} {unit} per service, {len(kept) - len(stateful)} service" + ("" if len(kept) - len(stateful) == 1 else "s")
                                      + (f" + {', '.join(sorted(stateful))} (in-cluster, one copy)" if stateful else "")
                                      + (f" (without {', '.join(sorted(removed))})" if removed else "") + tail))
    stores = {d["type"] for d in (scan_result.get("in_cluster_datastores") or [])}
    redis_names = [n for n in workloads if "redis" in n.lower()]
    meta = {"lb": round(lb_eur, 2), "fee_regional": round(fee_regional, 2), "fee_autopilot": round(fee_autopilot, 2),
            "sql": round(_eur(_p("cloud_sql_db_g1_small_hour") * HOURS_PER_MONTH + _p("cloud_sql_ssd_gib_hour") * HOURS_PER_MONTH * 10), 2),
            "sql_dedicated": round(_eur(_dedicated_sql_hour() * HOURS_PER_MONTH + _p("cloud_sql_ssd_gib_hour") * HOURS_PER_MONTH * 10), 2),
            "sql_dedicated_ha": round(_eur(2 * _dedicated_sql_hour() * HOURS_PER_MONTH + 2 * _p("cloud_sql_ssd_gib_hour") * HOURS_PER_MONTH * 10), 2),
            "sql_ha": round(_eur(_p("cloud_sql_db_g1_small_ha_hour") * HOURS_PER_MONTH + 2 * _p("cloud_sql_ssd_gib_hour") * HOURS_PER_MONTH * 10), 2),
            "secret_manager": round(_eur(max(0, 10 - 6) * _p("secret_manager_per_version_month")), 2),
            "redis_standard": round(_eur(_p("memorystore_redis_standard_1_4gib_per_gib_hour") * HOURS_PER_MONTH), 2) if "redis" in stores and redis_names else None,
            "redis_single_autopilot": round(_eur(sum(_autopilot(dict(workloads[n], replicas=1)) for n in redis_names)), 2) if redis_names else 0.0,
            "demo": sorted(demo), "overlap": sorted(overlap)}
    meta["addons"] = _addons(meta, workloads, redis_names, stores)
    return options, meta


def _addons(meta, workloads, redis_names, stores):
    """For each platform: the managed database, the secret store and the failover Redis that go with it, priced from THAT provider's own table
    (EUR/month). Each entry also has the plain-words notes the plan prints. redis_single is what the in-cluster Redis costs on that platform, so
    swapping it for the managed one adds only the difference. A value is None when it does not apply."""
    has_redis = "redis" in stores and bool(redis_names)
    def single(fn):
        return round(_eur(sum(fn(dict(workloads[n], replicas=1)) for n in redis_names)), 2) if redis_names else 0.0
    gcp = {"db": meta["sql"], "db_ha": meta["sql_dedicated_ha"], "secrets": meta["secret_manager"],
           "db_note": "Cloud SQL single small shared-core instance + Secret Manager",
           "db_ha_note": "Cloud SQL high availability, dedicated 1 vCPU / 3.75 GiB, two zones (Iowa price; EU price not read) + Secret Manager",
           "unknown_line": f"A single small Cloud SQL instance would add {meta['sql']:.2f} EUR/month and a two-zone high-availability one {meta['sql_ha']:.2f} EUR/month (PostgreSQL rate).",
           "redis_ha": meta["redis_standard"],
           "redis_ha_note": "managed Redis Standard with failover instead of the in-cluster Redis (Memorystore Iowa price; EU price not read)"}
    gib = DB_GIB["aws"]
    aws_db = round(_eur(_p("rds_pg_db_t4g_micro_single_az_hour") * HOURS_PER_MONTH + _p("rds_pg_gp3_gb_month_single_az") * gib), 2)
    aws_ha = round(_eur(_p("rds_pg_db_t4g_medium_multi_az_hour") * HOURS_PER_MONTH + _p("rds_pg_gp3_gb_month_multi_az") * gib), 2)
    aws = {"db": aws_db, "db_ha": aws_ha, "secrets": round(_eur(10 * _p("aws_secrets_manager_per_secret_month")), 2),
           "db_note": f"Amazon RDS for PostgreSQL, one small instance (db.t4g.micro, {gib} GiB, Frankfurt) + Secrets Manager",
           "db_ha_note": f"Amazon RDS for PostgreSQL Multi-AZ (db.t4g.medium, {gib} GiB, Frankfurt) + Secrets Manager",
           "unknown_line": f"A single small Amazon RDS database would add {aws_db:.2f} EUR/month and a Multi-AZ one {aws_ha:.2f} EUR/month (PostgreSQL rate).",
           "redis_ha": round(_eur(2 * _p("elasticache_redis_t4g_small_node_hour") * HOURS_PER_MONTH), 2) if has_redis else None,
           "redis_ha_note": "ElastiCache Redis with a replica (2 x cache.t4g.small, Frankfurt) instead of the in-cluster Redis"}
    gib = DB_GIB["azure"]
    az_db = round(_eur(_p("azure_pg_flex_b1ms_hour") * HOURS_PER_MONTH + _p("azure_pg_flex_storage_gb_month") * gib), 2)
    az_ha = round(_eur(2 * (_p("azure_pg_flex_gp_2vcore_ddsv5_hour") * HOURS_PER_MONTH + _p("azure_pg_flex_storage_gb_month") * gib)), 2)
    azure = {"db": az_db, "db_ha": az_ha, "secrets": round(_eur(_p("azure_key_vault_per_10k_operations")), 2),
             "db_note": f"Azure Database for PostgreSQL, one small server (Burstable B1ms, {gib} GiB, West Europe) + Key Vault",
             "db_ha_note": f"Azure Database for PostgreSQL with high availability (General Purpose 2 vCore, {gib} GiB, the standby is billed like the primary, West Europe) + Key Vault",
             "unknown_line": f"A single small Azure PostgreSQL server would add {az_db:.2f} EUR/month and a high-availability one {az_ha:.2f} EUR/month (PostgreSQL rate).",
             "redis_ha": round(AZ["azure_redis_standard_c1_1gb_per_hour"][0] * HOURS_PER_MONTH, 2) if has_redis else None,
             "redis_ha_note": "Azure Cache for Redis Standard C1 (replicated pair, West Europe) instead of the in-cluster Redis"}
    out = {}
    for plat, ad in (("gke_autopilot", gcp), ("cloud_run", gcp), ("aws_fargate", aws), ("azure_container_apps", azure)):
        out[plat] = dict(ad, redis_single=single(PLATFORM_FN[plat]))
    return out


def build_cost_estimate(scan_result):
    """Returns (markdown_text, structured_dict). Empty text if there is nothing to size."""
    workloads, size_note = _workloads(scan_result)
    if not workloads:
        return "", {}
    # A manifest may ask for 2 copies of one service. The tables price ONE copy of each workload and every total states its replica
    # count, otherwise "2 replicas per service" would silently mean 4 for that service and the report would disagree with itself.
    stated = {n: w.get("replicas", 1) for n, w in workloads.items() if w.get("replicas", 1) != 1}
    workloads = {n: dict(w, replicas=1) for n, w in workloads.items()}
    if stated:
        size_note += ("; the manifests ask for more than one copy of " + ", ".join(f"{n} ({r})" for n, r in sorted(stated.items()))
                      + ", but the table prices ONE copy of every workload and each total below states its own replica count")

    rows, totals = [], {"cpu": 0.0, "mem": 0.0, "autopilot": 0.0, "run": 0.0, "fargate": 0.0, "aca": 0.0}
    for name, w in sorted(workloads.items()):
        ap, run, fg, aca = _autopilot(w), _cloud_run_always_on(w), _fargate(w), _container_apps(w)
        rows.append((name, w, ap, run, fg, aca))
        totals["cpu"] += w["cpu_cores"] * w["replicas"]
        totals["mem"] += w["memory_gib"] * w["replicas"]
        totals["autopilot"] += ap; totals["run"] += run; totals["fargate"] += fg; totals["aca"] += aca

    L = []
    L.append(f"### Per-service compute price (always-on, {len(workloads)} workloads)")
    L.append(f"_Sizing: {size_note}. Google Cloud prices read from the providers' pages on {RETRIEVED}; AWS (Frankfurt) and Azure (West Europe) prices "
             f"read from their own price lists on {RETRIEVED_PLATFORMS}; USD converted to EUR at {USD_PER_EUR} USD per EUR ({USD_PER_EUR_DATE} reference rate)._\n")
    L.append("| Service | vCPU | Memory GiB | GKE Autopilot €/mo | Cloud Run (always-on) €/mo | AWS Fargate (Frankfurt) €/mo | Azure Container Apps (West Europe) €/mo |")
    L.append("|---|---|---|---|---|---|---|")
    for name, w, ap, run, fg, aca in rows:
        L.append(f"| {name} | {w['cpu_cores']:g} | {w['memory_gib']:.2f} | {_eur(ap):.2f} | {_eur(run):.2f} | {_eur(fg):.2f} | {_eur(aca):.2f} |")
    L.append(f"| **Total** | **{totals['cpu']:.2f}** | **{totals['mem']:.2f}** | **{_eur(totals['autopilot']):.2f}** | "
             f"**{_eur(totals['run']):.2f}** | **{_eur(totals['fargate']):.2f}** | **{_eur(totals['aca']):.2f}** |")
    L.append("\nAzure Container Apps is priced at the full ACTIVE rate for every second of the month. Azure bills a lower rate while a replica is idle and gives a "
             "monthly free grant, and neither is subtracted here, so the real Container Apps bill can be lower. AWS Fargate and Azure Container Apps do not run anything smaller than "
             "0.25 vCPU with 0.5 GB, so smaller services are priced at that size. Google Cloud prices use the requested size as written, so a real bill can be higher "
             "than the table where a platform rounds sizes up in other ways (treat the totals as a lower bound).\n")

    # ---- fixed per-month items -----------------------------------------------------
    fee = _p("gke_cluster_fee_per_hour") * HOURS_PER_MONTH
    lb = _p("gcp_lb_forwarding_rule_hour_first5") * HOURS_PER_MONTH
    L.append("### Fixed and add-on items")
    L.append("| Item | €/month | Basis |")
    L.append("|---|---|---|")
    L.append(f"| GKE Autopilot cluster fee (Autopilot is regional by design) | {max(0.0, _eur(fee - _p('gke_free_credit_per_month'))):.2f} | "
             f"$0.10/h; the $74.40 monthly free credit covers one Autopilot or zonal cluster per billing account; add {_eur(fee):.2f} if the credit is already used by another cluster |")
    L.append(f"| GKE Standard regional cluster fee | {_eur(fee):.2f} | $0.10/h, the free credit does not apply to regional Standard clusters (node VMs not priced) |")
    L.append(f"| AKS cluster fee, Standard tier with SLA (West Europe, already in EUR) | {AZ['aks_standard_uptime_sla_cluster_fee_per_hour'][0] * HOURS_PER_MONTH:.2f} | €0.088/h |")
    L.append("| AKS cluster fee, Free tier | 0.00 | no SLA; you pay only for node VMs (not priced) |")
    L.append(f"| EKS cluster fee | {_eur(_p('eks_cluster_fee_per_hour') * HOURS_PER_MONTH):.2f} | $0.10/h |")
    L.append(f"| Google HTTPS load balancer (1 forwarding rule) | {_eur(lb):.2f} | $0.025/h + $0.008/GiB processed (traffic unknown) |")
    L.append(f"| AWS Application Load Balancer, fixed hourly part (Frankfurt) | {_eur(_p('alb_per_hour') * HOURS_PER_MONTH):.2f} | $0.027/h; the part that depends on traffic "
             f"(${_p('alb_per_lcu_hour')} per capacity-unit hour) is not included |")
    L.append(f"| AWS public IPv4 address, one (Frankfurt) | {_eur(_p('aws_public_ipv4_per_hour') * HOURS_PER_MONTH):.2f} | $0.005/h each; the load balancer holds one in each "
             "of two zones, and every Fargate task in a public subnet holds one |")
    L.append(f"| Azure Container Apps load balancer | 0.00 | the service has its own HTTPS entry point; no separate Azure load balancer is priced |")
    L.append(f"| Hetzner load balancer LB11 (only if you run more than one Hetzner server) | {HETZNER_LOAD_BALANCERS[0][1]:.2f} | EUR excl. VAT, read {RETRIEVED_PLATFORMS}; "
             + ", ".join(f"{n} is {v:.2f}" for n, v in HETZNER_LOAD_BALANCERS[1:]) + " |")

    stores = {d["type"]: d for d in (scan_result.get("in_cluster_datastores") or [])}
    optional = (scan_result.get("datastore_signals") or {}).get("only_in_optional_overlays", {})
    if "redis" in stores:
        mem = _p("memorystore_redis_basic_1_4gib_per_gib_hour") * HOURS_PER_MONTH
        L.append(f"| Managed Redis, Basic 1 GiB (replaces in-cluster Redis) | {_eur(mem):.2f} | Memorystore Iowa price -- EU price not read |")
        std = _p("memorystore_redis_standard_1_4gib_per_gib_hour") * HOURS_PER_MONTH
        L.append(f"| Managed Redis, Standard 1 GiB (with failover) | {_eur(std):.2f} | Memorystore Iowa price -- EU price not read |")
    if "redis" in stores:
        L.append(f"| Amazon ElastiCache Redis, 2 x cache.t4g.small (primary and replica, Frankfurt) | {_eur(2 * _p('elasticache_redis_t4g_small_node_hour') * HOURS_PER_MONTH):.2f} | "
                 f"$0.036 per node-hour |")
    if "redis" in stores:
        L.append(f"| Azure Cache for Redis Basic C1 1 GB (West Europe) | {AZ['azure_redis_basic_c1_1gb_per_hour'][0] * HOURS_PER_MONTH:.2f} | single node, no SLA; Azure announced retirement in 2028 |")
        L.append(f"| Azure Cache for Redis Standard C1 1 GB (West Europe) | {AZ['azure_redis_standard_c1_1gb_per_hour'][0] * HOURS_PER_MONTH:.2f} | replicated pair |")
    sql = _p("cloud_sql_db_g1_small_hour") * HOURS_PER_MONTH + _p("cloud_sql_ssd_gib_hour") * HOURS_PER_MONTH * 10
    sql_ha = _p("cloud_sql_db_g1_small_ha_hour") * HOURS_PER_MONTH + 2 * _p("cloud_sql_ssd_gib_hour") * HOURS_PER_MONTH * 10
    _db = (scan_result.get("dependencies") or {}).get("database_client") or []
    engines = {str(_d).lower() for _d in _db}
    uses_mysql = any(("mysql" in e or "mariadb" in e) for e in engines) or any(
        s_.get("type") == "mysql" for s_ in (scan_result.get("in_cluster_datastores") or []))
    engine_note = ("PRICE IS THE POSTGRESQL RATE -- this repo uses MySQL; the MySQL shared-core price was not read, so treat as approximate"
                   if uses_mysql else "shared-core, no SLA")
    L.append(f"| Cloud SQL PostgreSQL db-g1-small + 10 GiB SSD (OPTIONAL -- only if the app needs a relational DB) | {_eur(sql):.2f} | {engine_note} |")
    L.append(f"| Same, high availability (two zones) | {_eur(sql_ha):.2f} | shared-core, no SLA |")
    L.append(f"| Cloud SQL PostgreSQL dedicated-core 1 vCPU / 3.75 GiB + 10 GiB SSD (has an SLA; needed for production data) | "
             f"{_eur(_dedicated_sql_hour() * HOURS_PER_MONTH + _p('cloud_sql_ssd_gib_hour') * HOURS_PER_MONTH * 10):.2f} | Iowa rate, EU price not read |")
    L.append(f"| Same, high availability (two zones) | {_eur(2 * _dedicated_sql_hour() * HOURS_PER_MONTH + 2 * _p('cloud_sql_ssd_gib_hour') * HOURS_PER_MONTH * 10):.2f} | Iowa rate, EU price not read |")
    L.append(f"| Secret Manager, 10 secrets, light use | {_eur(max(0, 10 - 6) * _p('secret_manager_per_version_month')):.2f} | first 6 versions free |")
    _aws_gib, _az_gib = DB_GIB["aws"], DB_GIB["azure"]
    L.append(f"| Amazon RDS for PostgreSQL db.t4g.micro + {_aws_gib} GiB gp3, one instance (Frankfurt) | "
             f"{_eur(_p('rds_pg_db_t4g_micro_single_az_hour') * HOURS_PER_MONTH + _p('rds_pg_gp3_gb_month_single_az') * _aws_gib):.2f} | no standby copy; {_aws_gib} GiB is an assumed disk size |")
    L.append(f"| Amazon RDS for PostgreSQL db.t4g.medium Multi-AZ + {_aws_gib} GiB gp3 (Frankfurt) | "
             f"{_eur(_p('rds_pg_db_t4g_medium_multi_az_hour') * HOURS_PER_MONTH + _p('rds_pg_gp3_gb_month_multi_az') * _aws_gib):.2f} | a standby copy in a second zone |")
    L.append(f"| AWS Secrets Manager, 10 secrets, light use | {_eur(10 * _p('aws_secrets_manager_per_secret_month')):.2f} | $0.40 per secret per month, no free allowance |")
    L.append(f"| Azure Database for PostgreSQL Burstable B1ms + {_az_gib} GiB (West Europe) | "
             f"{_eur(_p('azure_pg_flex_b1ms_hour') * HOURS_PER_MONTH + _p('azure_pg_flex_storage_gb_month') * _az_gib):.2f} | one server, no standby; {_az_gib} GiB is an assumed disk size |")
    L.append(f"| Azure Database for PostgreSQL General Purpose 2 vCore with high availability + {_az_gib} GiB (West Europe) | "
             f"{_eur(2 * (_p('azure_pg_flex_gp_2vcore_ddsv5_hour') * HOURS_PER_MONTH + _p('azure_pg_flex_storage_gb_month') * _az_gib)):.2f} | "
             "Microsoft: the standby server is billed at the same rate as the primary |")
    L.append(f"| Azure Key Vault, light use | {_eur(_p('azure_key_vault_per_10k_operations')):.2f} | $0.03 per 10,000 operations, no monthly fee per secret |")
    L.append("\nOnly list the OPTIONAL rows in the baseline if the app really needs them.\n")

    # ---- Hetzner single-server alternative -----------------------------------------
    real_mem, real_note = realistic_memory_gib(scan_result, workloads)
    sizing_mem = max(totals["mem"], real_mem)
    fits = [s for s in HETZNER_SERVERS
            if s[1] * HETZNER_FILL >= totals["cpu"] and s[2] * HETZNER_FILL >= sizing_mem * 1.073741824]
    L.append("### Cheapest self-managed alternative (one Hetzner server running k3s/Docker)")
    if fits:
        best = fits[0]
        mem_txt = (f"{totals['mem']:.2f} GiB as requested in the repo, but about {real_mem:.1f} GiB once each service gets a realistic "
                   f"minimum ({real_note})" if real_mem > totals["mem"] * 1.2 else f"{totals['mem']:.2f} GiB")
        L.append(f"Total requests are {totals['cpu']:.2f} vCPU and {mem_txt}. With ~30% headroom that fits "
                 f"**{best[0]}** ({best[1]} vCPU, {best[2]} GB RAM): **€{best[4]:.2f}/month excl. VAT**. {HETZNER_NOTE} "
                 f"A single server has no failover: it cannot meet a true zero-downtime requirement.")
    else:
        L.append(f"No single Hetzner server in the table fits with headroom: about {sizing_mem:.1f} GiB of memory is needed "
                 f"({real_note if sizing_mem > totals['mem'] else 'from the repo requests'}) and {totals['cpu']:.2f} vCPU. "
                 f"Use several servers or fewer services; a single server would risk out-of-memory kills.")

    # ---- ready-made monthly totals: the ONLY totals the report may quote ---------------
    scenarios = []
    lb_eur = _eur(lb)
    fee_regional = _eur(fee)
    ap_total = _eur(totals["autopilot"])
    scenarios.append(("GKE Autopilot (cluster fee covered by the free credit), 1 load balancer",
                      ap_total + 0.0 + lb_eur))
    redis_workloads = {n: w for n, w in workloads.items() if "redis" in n.lower()}
    if "redis" in stores and redis_workloads:
        redis_ap = _eur(sum(_autopilot(w) for w in redis_workloads.values()))
        basic = _eur(_p("memorystore_redis_basic_1_4gib_per_gib_hour") * HOURS_PER_MONTH)
        standard = _eur(_p("memorystore_redis_standard_1_4gib_per_gib_hour") * HOURS_PER_MONTH)
        _iowa = " (Memorystore Iowa price; EU price not read)"
        scenarios.append(("GKE Autopilot + managed Redis Basic (replaces in-cluster Redis)" + _iowa,
                          ap_total - redis_ap + lb_eur + basic))
        scenarios.append(("GKE Autopilot + managed Redis Standard (replaces in-cluster Redis)" + _iowa,
                          ap_total - redis_ap + lb_eur + standard))
        non_redis = ap_total - redis_ap
        scenarios.append(("GKE Autopilot, 2 replicas per service + managed Redis Standard with failover (replaces in-cluster Redis) + 1 load balancer" + _iowa,
                          2 * non_redis + lb_eur + standard))
        _lg = [w for n, w in workloads.items() if "load" in n.lower() and "gen" in n.lower()]
        if _lg:
            lg_ap = _eur(sum(_autopilot(w) for w in _lg))
            scenarios.append(("GKE Autopilot, 2 replicas per service WITHOUT the load generator + managed Redis Standard with failover + 1 load balancer" + _iowa,
                              2 * (non_redis - lg_ap) + lb_eur + standard))
            scenarios.append(("Saving from removing the load generator at 2 replicas per service on GKE Autopilot", 2 * lg_ap))
    scenarios.append(("Cloud Run always-on, 1 load balancer, no cluster fee", _eur(totals["run"]) + lb_eur))
    has_db_option = bool((scan_result.get("dependencies") or {}).get("database_client")) and not stores
    opts, opt_meta = plan_options(scan_result, workloads)
    # Same rule as every other platform row: in-cluster datastores stay at ONE copy (a second copy would be a different database)
    for plat, fallback in (("gke_autopilot", None), ("cloud_run", None)):
        o2 = next((o for o in opts if o["platform"] == plat and o["set"] == "all" and o["replicas"] == 2), None)
        if o2:
            scenarios.append((o2["label"], o2["total"]))
    for o in opts:
        if o["set"] == "all" and o["platform"] in ("aws_fargate", "azure_container_apps"):
            scenarios.append((o["label"], o["total"]))
    if has_db_option:
        _sec = _eur(max(0, 10 - 6) * _p('secret_manager_per_version_month'))
        _ap = " (MySQL repo: PostgreSQL rate, approximate)" if uses_mysql else ""
        scenarios.append((f"GKE Autopilot + 1 load balancer + Cloud SQL db-g1-small (no HA) + Secret Manager{_ap}",
                          ap_total + lb_eur + _eur(sql) + _sec))
        scenarios.append((f"GKE Autopilot + 1 load balancer + Cloud SQL db-g1-small HA + Secret Manager{_ap}",
                          ap_total + lb_eur + _eur(sql_ha) + _sec))
        scenarios.append((f"GKE Autopilot, 2 replicas per service + 1 load balancer + Cloud SQL db-g1-small HA + Secret Manager{_ap}",
                          2 * ap_total + lb_eur + _eur(sql_ha) + _sec))
        scenarios.append((f"Cloud Run always-on, 2 instances per service + 1 load balancer + Cloud SQL db-g1-small HA + Secret Manager{_ap}",
                          2 * _eur(totals["run"]) + lb_eur + _eur(sql_ha) + _sec))
    demo = demo_tooling_services(scan_result)
    if demo and len(demo) < len(workloads):
        keep_d = {n: w for n, w in workloads.items() if n not in demo}
        ap_d = _eur(sum(_autopilot(w) for w in keep_d.values()))
        dtag = f"without demo/test tooling ({', '.join(demo)}; {len(keep_d)} services)"
        scenarios.append((f"GKE Autopilot, 1 replica per service {dtag}, 1 load balancer", ap_d + lb_eur))
        scenarios.append((f"GKE Autopilot, 2 replicas per service {dtag}, 1 load balancer", 2 * ap_d + lb_eur))
    overlap = overlap_services(scan_result)
    if overlap and len(overlap) < len(workloads):
        keep = {n: w for n, w in workloads.items() if n not in overlap}
        ap_keep = _eur(sum(_autopilot(w) for w in keep.values()))
        run_keep = _eur(sum(_cloud_run_always_on(w) for w in keep.values()))
        tag = f"without {', '.join(overlap)}"
        scenarios.append((f"GKE Autopilot, 2 replicas per service {tag} ({len(keep)} services), 1 load balancer",
                          2 * ap_keep + lb_eur))
        if has_db_option:
            _sec2 = _eur(max(0, 10 - 6) * _p('secret_manager_per_version_month'))
            _ap2 = " (MySQL repo: PostgreSQL rate, approximate)" if uses_mysql else ""
            scenarios.append((f"GKE Autopilot, 2 replicas per service {tag} ({len(keep)} services) + 1 load balancer + Cloud SQL db-g1-small HA + Secret Manager{_ap2}",
                              2 * ap_keep + lb_eur + _eur(sql_ha) + _sec2))
            scenarios.append((f"Cloud Run always-on, 2 instances per service {tag} ({len(keep)} services) + 1 load balancer + Cloud SQL db-g1-small HA + Secret Manager{_ap2}",
                              2 * run_keep + lb_eur + _eur(sql_ha) + _sec2))
    if has_db_option:
        approx = " (MySQL repo: PostgreSQL rate, approximate)" if uses_mysql else ""
        for o in opts:
            if o["set"] == "all" and o["platform"] in ("aws_fargate", "azure_container_apps"):
                ad = opt_meta["addons"][o["platform"]]
                ha = o["replicas"] >= 2
                scenarios.append((f"{o['label']} + " + (ad["db_ha_note"] if ha else ad["db_note"]) + approx,
                                  o["total"] + (ad["db_ha"] if ha else ad["db"]) + ad["secrets"]))
    if has_db_option:
        approx = " (MySQL repo: PostgreSQL rate, approximate)" if uses_mysql else ""
        extra = _eur(sql) + _eur(max(0, 10 - 6) * _p('secret_manager_per_version_month'))
        scenarios.append((f"Cloud Run always-on + 1 load balancer + Cloud SQL db-g1-small (no HA) + Secret Manager{approx}",
                          _eur(totals["run"]) + lb_eur + extra))
        scenarios.append((f"Same with Cloud SQL high availability{approx}",
                          _eur(totals["run"]) + lb_eur + _eur(sql_ha) + _eur(max(0, 10 - 6) * _p('secret_manager_per_version_month'))))
    if fits:
        scenarios.append((f"Hetzner {fits[0][0]} single server (excl. VAT, no failover)", fits[0][4]))
        _parts = []
        _extra = 0.0
        if "redis" in stores:
            _parts.append("managed Redis Basic (Memorystore Iowa price; EU price not read)")
            _extra += _eur(_p("memorystore_redis_basic_1_4gib_per_gib_hour") * HOURS_PER_MONTH)
        if has_db_option or any(t in stores for t in ("postgres", "mysql")):
            _parts.append("Cloud SQL db-g1-small (no HA)" + (" at the PostgreSQL rate, approximate" if uses_mysql else ""))
            _extra += _eur(sql)
        if _parts:
            _extra += _eur(max(0, 10 - 6) * _p('secret_manager_per_version_month'))
            scenarios.append((f"Hetzner {fits[0][0]} single server (excl. VAT, no failover) + " + " + ".join(_parts) + " + Secret Manager (mixed providers)",
                              fits[0][4] + _extra))
    for name, w in workloads.items():
        if "load" in name.lower() and "gen" in name.lower():
            scenarios.append((f"Saving from removing {name} on GKE Autopilot", _eur(_autopilot(w))))
    L.append("\n### Ready-made monthly totals (quote these; do not add up your own)")
    L.append("| Setup | €/month |")
    L.append("|---|---|")
    for label, value in scenarios:
        L.append(f"| {label} | {value:.2f} |")
    L.append("\nThese totals contain compute, cluster fee, load balancer and the stated Redis/Cloud SQL option only. "
             "Persistent disks, egress, NAT, monitoring, databases and LLM tokens are not included.")

    L.append("\n### Not priced (no verified price available -- say so, do not guess)")
    L.extend(f"- {item}" for item in NOT_PRICED)
    L.append("- Cloud SQL instance sizes other than db-g1-small and the 1 vCPU / 3.75 GiB dedicated instance (larger machines are priced by vCPU and GiB; your real size depends on your data and load)")
    L.append("- Read replicas, cross-region replicas, and database backups beyond the included amount (Cloud SQL, Amazon RDS and Azure PostgreSQL)")
    L.append("- Amazon RDS and Azure PostgreSQL sizes other than the ones in the table above (your real size depends on your data and load)")
    L.append("- Cost of more than two replicas per service, and any other replica count (only 1 and 2 replicas are in the totals)")

    structured = {"plan_options": opts, "plan_meta": opt_meta, "workloads": len(workloads), "total_cpu": round(totals["cpu"], 2),
                  "total_memory_gib": round(totals["mem"], 2),
                  "autopilot_eur": round(_eur(totals["autopilot"]), 2),
                  "cloud_run_eur": round(_eur(totals["run"]), 2),
                  "allowed_totals": [round(v, 2) for _, v in scenarios] + [o["total"] for o in opts],
                  "scenarios": [(l, round(v, 2)) for l, v in scenarios]}
    return "\n".join(L), structured


if __name__ == "__main__":
    import sys
    from scanner.scan import scan_repo
    text, data = build_cost_estimate(scan_repo(sys.argv[1] if len(sys.argv) > 1 else "."))
    print(text); print(data)
