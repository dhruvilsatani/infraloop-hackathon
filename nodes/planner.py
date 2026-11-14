"""The recommendation is decided HERE, in code, from the user's answers and the computed price options.

The language model that writes the report may be small. It must not have to compare totals, work out which setup meets
'zero downtime', or decide whether a database belongs in the total. This module does that and hands the model (and the
report) a finished decision to put into words.
"""
import re

_NUM = re.compile(r"(\d[\d,._]*)\s*(k|m|million|thousand)?(?![a-z])", re.I)


def _answer(answers, needle):
    for q, a in (answers or {}).items():
        if needle in str(q).lower() and str(a).strip():
            return str(a).strip()
    return ""


def parse_budget(answers):
    for q, a in (answers or {}).items():
        if "budget" in str(q).lower():
            m = _NUM.search(str(a))
            if m:
                try:
                    v = float(m.group(1).replace(",", "").replace("_", ""))
                except ValueError:
                    continue
                return v * {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}.get((m.group(2) or "").lower(), 1)
    return None


def parse_uptime(answers):
    """'zero' | 'minutes' | 'hours' | 'unknown'"""
    said = _answer(answers, "downtime").lower()
    if not said:
        return "unknown"
    if "don't know" in said or "dont know" in said or "not sure" in said:
        return "unknown"
    if re.search(r"\b(none|zero|no downtime|nothing|never|0)\b", said):
        return "zero"
    if re.search(r"few minutes|minutes", said):
        return "minutes"
    if re.search(r"hour|day|fine|ok|acceptable", said):
        return "hours"
    return "unknown"


def parse_database_mode(answers):
    """How the user will run their database: 'managed' (cloud service, price it), 'external' (they run it / it is local /
    handled elsewhere: do NOT put a database price in the totals) or 'unknown' (no usable answer)."""
    said = _answer(answers, "tell me about your database").lower()
    if not said:
        return "unknown"
    if re.search(r"\b(not|no|don't|dont|without)\s+(a\s+)?managed\b|\bunmanaged\b", said):
        return "external"
    if re.search(r"\b(managed|cloud sql|rds|aurora|atlas|azure database|cosmos ?db|dynamodb|firestore|memorystore|elasticache|"
                 r"supabase|neon|planetscale|upstash)\b", said):
        return "managed"
    if re.search(r"\b(my ?self|ourselves?|self[- ]?(host|manag|run|hosted)|own (server|vm|machine|infrastructure|infra|hardware)|"
                 r"local(ly)?|on[- ]?prem(ise)?s?|separately|outside|handled|handle (it|that|the)|we (will |'ll )?(run|host|manage|handle)|"
                 r"not in (the )?cloud|no database|none|no db|don't need|dont need|not needed)\b", said):
        return "external"
    return "unknown"


def wants_hosting(answers):
    """For a library/tool: did the user say they want to run it as a hosted service?"""
    said = _answer(answers, "hosted service").lower()
    return bool(said) and not said.startswith("no")


def addons_for(meta, option):
    """The managed database / secrets / Redis prices for the platform of this option (see cost_estimator._addons). Older data without them falls back to
    the Google Cloud values, which are what the flat meta keys always held."""
    ad = (meta.get("addons") or {}).get(option.get("platform"))
    if ad:
        return ad
    return {"db": meta["sql"], "db_ha": meta["sql_dedicated_ha"], "secrets": meta["secret_manager"],
            "db_note": "Cloud SQL single small shared-core instance + Secret Manager",
            "db_ha_note": "Cloud SQL high availability, dedicated 1 vCPU / 3.75 GiB, two zones (Iowa price; EU price not read) + Secret Manager",
            "unknown_line": f"A single small Cloud SQL instance would add {meta['sql']:.2f} EUR/month and a two-zone high-availability one {meta['sql_ha']:.2f} EUR/month (PostgreSQL rate).",
            "redis_ha": meta.get("redis_standard"),
            "redis_ha_note": "managed Redis Standard with failover instead of the in-cluster Redis (Memorystore Iowa price; EU price not read)",
            "redis_single": meta.get("redis_single_autopilot", 0.0)}


def _within(total, budget):
    return budget is None or total <= budget + 0.005


def choose_plan(scan_result, answers, cost_data):
    """Returns a dict describing the recommended setup, or None when there is nothing priced to choose from.
    status: fits | fits_after_dropping_shared_services | partial | over_budget | no_budget"""
    options = (cost_data or {}).get("plan_options") or []
    meta = (cost_data or {}).get("plan_meta") or {}
    if not options:
        return None
    budget = parse_budget(answers)
    uptime = parse_uptime(answers)
    db_mode = parse_database_mode(answers)
    infra = scan_result.get("infra_signals") or {}
    prefers_gke = bool(infra.get("has_k8s") or infra.get("has_helm"))
    data_loss_none = _answer(answers, "how much recent data").lower().startswith("none")
    demo, overlap = set(meta.get("demo") or []), set(meta.get("overlap") or [])

    def priced(o):
        """Total with the pieces that depend on the answers (database, managed Redis for state), each priced on the option's own platform."""
        t, notes = o["total"], []
        ad = addons_for(meta, o)
        if db_mode == "managed":
            ha = uptime == "zero" or data_loss_none
            t += (ad["db_ha"] if ha else ad["db"]) + ad["secrets"]
            notes.append(ad["db_ha_note"] if ha else ad["db_note"])
        if ad.get("redis_ha") and (uptime == "zero" or data_loss_none) and o["stateful_kept_single"]:
            t += ad["redis_ha"] - ad["redis_single"]
            notes.append(ad["redis_ha_note"])
        return round(t, 2), notes

    def ok_scope(o, allow_overlap_drop):
        if demo and not demo <= set(o["removed"]):
            return False                     # demo/test tooling never belongs in the production setup
        if set(o["removed"]) - demo and not allow_overlap_drop:
            return False
        return True

    def pick(cands):
        cands = [(priced(o), o) for o in cands]
        if budget is not None:
            cands = [c for c in cands if _within(c[0][0], budget)] or []
        if not cands:
            return None
        if prefers_gke:
            gke = [c for c in cands if c[1]["platform"].startswith("gke")]
            cands = gke or cands
        (t, notes), o = min(cands, key=lambda c: c[0][0])
        return o, t, notes

    def need(o):
        return o["zone_ha"] if uptime == "zero" else True

    pool = [o for o in options]
    status, chosen = None, None
    # 1) full requirement, keeping every service except demo tooling
    r = pick([o for o in pool if need(o) and ok_scope(o, False) and (uptime == "zero" or o["replicas"] == 1)])
    if r:
        status, chosen = ("fits" if budget is not None else "no_budget"), r
    if not chosen and budget is not None:
        # 2) full requirement if shared platform services (config/discovery server) are dropped
        r = pick([o for o in pool if need(o) and ok_scope(o, True) and (uptime == "zero" or o["replicas"] == 1)])
        if r:
            status, chosen = "fits_after_dropping_shared_services", r
    cheapest_full = None
    full = [(priced(o), o) for o in pool if need(o) and ok_scope(o, True) and (uptime == "zero" or o["replicas"] == 1)]
    if full:
        (t, notes), o = min(full, key=lambda c: c[0][0])
        cheapest_full = (o, t, notes)
    if not chosen and uptime == "zero" and budget is not None:
        # 3) cannot meet zone-level availability in the budget: the best that fits is 2 copies in one zone
        r = pick([o for o in pool if o["pod_ha"] and not o["zone_ha"] and ok_scope(o, True)])
        if r:
            status, chosen = "partial", r
    if not chosen:
        if cheapest_full:
            chosen, status = cheapest_full, "over_budget"
        else:
            return None
    o, total, notes = chosen
    alts = []
    for cand in pool:
        if cand is o or not ok_scope(cand, True):
            continue
        if uptime == "zero" and not cand["pod_ha"]:
            continue
        t, n = priced(cand)
        alts.append({"label": cand["label"], "total": t, "zone_ha": cand["zone_ha"], "notes": n, "platform": cand["platform"]})
    alts.sort(key=lambda a: a["total"])
    # Show the cheapest setup of each platform first, so Google, AWS and Azure can all be compared; then fill up with the next cheapest ones.
    first, seen = [], set()
    for a in alts:
        if a["platform"] not in seen:
            first.append(a)
            seen.add(a["platform"])
    alts = sorted(first[:4] + [a for a in alts if a not in first][:max(0, 4 - len(first))], key=lambda a: a["total"])
    without_state = None
    _ad = addons_for(meta, o)
    if any("Redis" in n for n in notes) and _ad.get("redis_ha"):
        without_state = round(total - (_ad["redis_ha"] - _ad["redis_single"]), 2)
    small_server = small_server_option(scan_result, answers, budget, uptime) if not scan_result.get("repo_kind") == "library_or_tool" else None
    return {"status": status, "chosen": o, "total": total, "small_server": small_server, "without_managed_state": without_state, "notes": notes, "budget": budget, "uptime": uptime, "db_mode": db_mode,
            "alternatives": alts[:4], "cheapest_full": ({"label": cheapest_full[0]["label"], "total": cheapest_full[1]} if cheapest_full else None),
            "demo": sorted(demo), "overlap": sorted(overlap), "prefers_gke": prefers_gke, "hypothetical": scan_result.get("repo_kind") == "library_or_tool", "data_loss_none": data_loss_none,
            "meta": meta}


def describe(plan):
    """Plain-English lines for the report and for the model. Every number here comes from the price options."""
    if not plan:
        return []
    o, total, budget, uptime = plan["chosen"], plan["total"], plan["budget"], plan["uptime"]
    status = plan["status"]
    L = []
    pieces = f"{o['label']}" + (" + " + " + ".join(plan["notes"]) if plan["notes"] else "")
    ss = plan.get("small_server")
    if ss:
        L.append(f"Recommended for your small load (tier {ss['tier']} of 10, {ss['tier_name']}, about {ss['rate']} at peak): ONE {ss['name']} server "
                 f"({ss['vcpu']} vCPU, {ss['ram']} GB RAM) = {ss['total']:.2f} EUR/month excl. VAT (Hetzner, prices read {ss['retrieved']}). "
                 "It has no failover and you run it yourself (updates, backups). A database, a load balancer and traffic costs are not included.")
        if budget is not None:
            L.append(f"Against your budget of {budget:.0f}: {budget - ss['total']:.2f} under budget.")
        L.append(f"Managed-platform option for comparison: {pieces} = {total:.2f} EUR/month.")
    else:
        L.append(f"Recommended setup: {pieces} = {total:.2f} EUR/month.")
    if plan.get("hypothetical"):
        L.append("This is a HYPOTHETICAL figure: the repository is not deployable today, so it prices one small always-on service (0.25 vCPU / 0.5 GiB assumed). "
                 "The real size depends on the wrapper you build and on measured load.")
    if budget is not None and not ss:
        diff = budget - total
        L.append(f"Against your budget of {budget:.0f}: " + (f"{diff:.2f} under budget." if diff >= 0 else f"{-diff:.2f} OVER budget."))
    elif budget is not None:
        diff = budget - total
        L.append(f"The managed-platform option is " + (f"{diff:.2f} under budget." if diff >= 0 else f"{-diff:.2f} over budget."))
    if uptime == "zero":
        if o["zone_ha"]:
            spread = (" On GKE Autopilot the replicas are normally placed in different zones, but add a topologySpreadConstraints rule so this is guaranteed, not just likely."
                      if o.get("platform") == "gke_autopilot" else "")
            L.append("Availability: two or more copies of every service, spread over several zones of one region, so a pod, a node or a whole zone can fail without an outage. "
                     "This is not multi-region: a full regional outage would still stop it." + spread)
        else:
            L.append("Availability: two copies of every service in ONE zone. This survives a pod or node failure and rolling updates, but NOT an outage of the whole zone, "
                     "so it is not full zero downtime.")
    elif uptime in ("minutes", "hours", "unknown"):
        L.append("Availability: one copy of each service. A restart, node upgrade or deployment can cause a short outage; this matches what you said you can accept"
                 if uptime != "unknown" else "Availability: one copy of each service (you did not say how much downtime is acceptable, so this is an assumption).")
    L.extend(_platform_lines(o))
    if plan["db_mode"] == "external":
        L.append("Database: you said you run it yourself or elsewhere, so NO database price is in this total. A database you run yourself must have its own backups, replication and tested restores.")
    elif plan["db_mode"] == "unknown":
        L.append("Database: no usable answer, so no database is in this total. " + addons_for(plan["meta"], o)["unknown_line"])
    if o["stateful_kept_single"] and not any("Redis" in n for n in plan["notes"]):
        L.append("In-cluster datastore(s) " + ", ".join(o["stateful_kept_single"]) + " stay at ONE copy in these totals (a second copy would be a separate database, not a replica). "
                 "They need a persistent volume, and they are a single point of failure.")
    if plan.get("without_managed_state") is not None:
        L.append(f"Cheaper variant: keep the in-cluster Redis and give it a persistent volume = {plan['without_managed_state']:.2f} EUR/month. It stays a single copy on one node, "
                 "so cart/session data can still be lost if that node fails.")
    if status == "fits_after_dropping_shared_services":
        L.append("This only fits the budget WITHOUT " + " and ".join(o["removed"] if not plan["demo"] else [r for r in o["removed"] if r not in plan["demo"]])
                 + " (service discovery / central configuration, which the platform already provides). Dropping them needs code and configuration changes, so it is a decision, not a free saving.")
    if status == "partial":
        cf = plan["cheapest_full"]
        L.append(f"Zero downtime across a whole zone does NOT fit the budget: the cheapest setup that does is {cf['label']} = {cf['total']:.2f} EUR/month"
                 + (f", which is {cf['total'] - budget:.2f} over budget." if budget is not None else "."))
        L.append("The recommended setup above is the best that fits: it survives pod and node failures, not a zone outage.")
    if status == "over_budget" and not ss:
        if uptime == "zero":
            L.append("NO priced setup meets the availability you asked for within your budget. State this first. The choices: raise the budget, accept less availability, or reduce scope.")
        else:
            L.append("NO priced managed setup fits your budget. The choices: raise the budget, reduce scope, or run it on a single small server (see the small-project note, if shown).")
    if plan["demo"]:
        L.append("Left out on purpose (demo/test tooling, not part of production): " + ", ".join(plan["demo"]) + ".")
    return L


def _platform_lines(o):
    """What is and is not inside the price of an AWS or Azure setup, and how to place it for availability. Words only."""
    plat = o.get("platform")
    if plat == "aws_fargate":
        out = ["Priced on AWS: ECS Fargate tasks in public subnets (each task has its own public IPv4 address, which AWS charges for) behind one Application Load Balancer "
               "(its fixed hourly fee and its two public addresses). Not included: the load balancer's charge for traffic, a NAT gateway, traffic out of AWS and storage for in-cluster datastores."]
        if o.get("zone_ha"):
            out.append("To get the availability described above on AWS, run the tasks in subnets of at least two availability zones so the load balancer can spread traffic over them.")
        return out
    if plat == "azure_container_apps":
        out = ["Priced on Azure: Container Apps (Consumption plan) at the full active rate for the whole month, with its built-in HTTPS entry point and no separate load balancer. "
               "Azure charges a lower rate while a replica is idle and gives a monthly free grant, so the real compute bill can be lower. Not included: request charges beyond the free grant and traffic out of Azure."]
        if o.get("zone_ha"):
            out.append("To get the availability described above on Azure, create the Container Apps environment with zone redundancy turned on, so the replicas are spread over zones.")
        return out
    return []


def facts_lines(plan):
    lines = describe(plan)
    if not lines:
        return []
    out = ["- DECISION MADE BY CODE (the report MUST recommend exactly this setup and quote these figures; do not choose a different one, do not add up your own totals):"]
    out.extend(f"    * {x}" for x in lines)
    if plan["alternatives"]:
        out.append("    * Other priced setups, for comparison only: " + "; ".join(f"{a['label']} = {a['total']:.2f}" for a in plan["alternatives"]))
    return out


def _zone_cell(o, notes=()):
    """'yes' only when everything survives. A datastore kept at one copy is a single point of failure, and a managed Redis note fixes only Redis."""
    if not o["zone_ha"]:
        return "no"
    single = [n for n in (o.get("stateful_kept_single") or []) if "redis" not in n.lower() or not any("Redis" in x for x in notes)]
    return f"yes, except {', '.join(single)} (one copy)" if single else "yes"


def decision_section(plan):
    """Markdown block appended to the report in code, so the figures are right whatever the model wrote."""
    lines = describe(plan)
    if not lines:
        return ""
    rows = ["| Setup | €/month | Survives a zone outage |", "|---|---|---|"]
    o = plan["chosen"]
    ss = plan.get("small_server")
    if ss:
        rows.append(f"| **Recommended (small load):** one Hetzner {ss['name']} server, excl. VAT | **{ss['total']:.2f}** | no |")
        rows.append(f"| Managed platform: {o['label']}" + (" + " + " + ".join(plan["notes"]) if plan["notes"] else "") + f" | {plan['total']:.2f} | {_zone_cell(o, plan['notes'])} |")
    else:
        rows.append(f"| **Recommended:** {o['label']}" + (" + " + " + ".join(plan["notes"]) if plan["notes"] else "") + f" | **{plan['total']:.2f}** | {_zone_cell(o, plan['notes'])} |")
    for a in plan["alternatives"]:
        rows.append(f"| {a['label']}" + (" + " + " + ".join(a["notes"]) if a["notes"] else "") + f" | {a['total']:.2f} | {_zone_cell(a, a['notes'])} |")
    return ("## 4. Estimated Monthly Cost (computed in code)\n\n" + "\n".join(f"- {x}" for x in lines) + "\n\n" + "\n".join(rows)
            + "\n\n_Not included: egress, NAT, monitoring, persistent disks beyond boot disks, LLM tokens, and any database you run yourself._")


def _cheapest_single_server(scan_result, servers=None, ram_in_gib=False, retrieved=None):
    """(name, vCPU, RAM, EUR/month excl. VAT, price date) of the smallest priced single server that fits the repo's own requests with 30% headroom, or None.
    servers: rows shaped like prices.HETZNER_SERVERS (the default), cheapest first. ram_in_gib: the rows state RAM in GiB, not GB (AWS and Azure do)."""
    from nodes import cost_estimator as ce
    from knowledge import prices
    w = ce._workloads(scan_result)[0]
    cpu = sum(x["cpu_cores"] * x.get("replicas", 1) for x in w.values())
    mem, _ = ce.realistic_memory_gib(scan_result, w)
    mem = max(mem, sum(x["memory_gib"] * x.get("replicas", 1) for x in w.values()))
    for srv in (servers if servers is not None else prices.HETZNER_SERVERS):
        need_ram = mem if ram_in_gib else mem * 1.073741824
        if srv[1] * ce.HETZNER_FILL >= cpu and srv[2] * ce.HETZNER_FILL >= need_ram:
            return srv[0], srv[1], srv[2], srv[4], retrieved or prices.RETRIEVED
    return None


def _tiny_load(answers):
    """(tier number, tier name, rate text) when the stated peak load is tier 1 or 2 of 10, else None."""
    from nodes import load_tiers
    ld = load_tiers.parse_load(answers)
    if not ld:
        return None
    mult, _ = load_tiers.peak_multiplier(answers)
    peak = ld["per_month"] / 2592000 * mult
    num, name = load_tiers.tier_of(peak)[:2]
    return (num, name, load_tiers.rate_text(peak)) if num <= 2 else None


def small_server_option(scan_result, answers, budget, uptime):
    """The single cheap server that becomes the headline recommendation for a tiny load. None unless: the load is tier 1-2, zero downtime
    is not required, the repo is a deployable application and the server's priced total fits the budget (when one was given)."""
    if uptime == "zero" or scan_result.get("repo_kind") != "application":
        return None
    try:
        tiny = _tiny_load(answers)
        srv = _cheapest_single_server(scan_result) if tiny else None
    except Exception:
        return None
    if not srv or (budget is not None and srv[3] > budget + 0.005):
        return None
    return {"name": srv[0], "vcpu": srv[1], "ram": srv[2], "total": srv[3], "retrieved": srv[4], "tier": tiny[0], "tier_name": tiny[1], "rate": tiny[2]}


def small_project_note(plan, answers, scan_result):
    """Markdown note for projects whose stated load is tiny (tier 1 or 2 of 10) and that do not need zero downtime.
    It points at the cheapest option already priced in this report and at free tiers WITHOUT quoting any free-tier figure:
    free-tier limits are not in the verified price table, so none is invented here."""
    if not plan or plan.get("uptime") == "zero":
        return ""
    try:
        tiny = _tiny_load(answers)
        if not tiny:
            return ""
        num, name, rate = tiny
        server = _cheapest_single_server(scan_result)
    except Exception:
        return ""
    return ("\n\n### Small project? You may not need the setups above\n\n"
            f"Your stated load is about {rate} at peak (tier {num} of 10, {name}). A load this small can often be served by one small server, "
            "so the managed platforms priced above may be more than you need.\n"
            + ("- The recommended setup above is that single server: it is the cheapest priced option that fits your load" + (" and your budget" if plan.get("budget") is not None else "") + ". No failover, and you run it yourself.\n"
               if plan.get("small_server") else "") + ("" if plan.get("small_server") else "") + (f"- Cheapest single server in this report's price table that fits the repo's requested size with about 30% headroom: {server[0]} ({server[1]} vCPU, {server[2]} GB RAM) = {server[3]:.2f} EUR/month excl. VAT (Hetzner, retrieved {server[4]}). "
               "No failover, and you run it yourself.\n" if (server and not plan.get("small_server")) else "" if plan.get("small_server") else
               "- The cheapest option priced in this report is the single self-managed server in the cost table (no failover; VAT is not included).\n")
            + 
            "- Some providers also offer free tiers or always-free virtual machines with usage limits. This report has no verified free-tier prices, "
            "so check the provider's own pricing page before you rely on one.\n"
            "- A single free or cheap server means one copy of everything: no failover, and nobody takes backups for you.\n"
            "- If you already run this project for free, the paid figures in this section do not apply to you. The gaps in section 2 still do.")


def data_loss_none(answers):
    return _answer(answers, "how much recent data").lower().startswith("none")


def allowed_numbers(plan):
    """Every figure the decision text may contain, so the unverified-money marker does not flag them."""
    if not plan:
        return []
    vals = [plan["total"], plan.get("without_managed_state")]
    if plan.get("small_server"):
        vals.append(plan["small_server"]["total"])
    vals += [a["total"] for a in plan["alternatives"]]
    if plan.get("cheapest_full"):
        vals.append(plan["cheapest_full"]["total"])
    meta = plan["meta"]
    vals += [meta.get("sql"), meta.get("sql_ha"), meta.get("sql_dedicated"), meta.get("sql_dedicated_ha"), meta.get("secret_manager"), meta.get("redis_standard")]
    for ad in (meta.get("addons") or {}).values():
        vals += [ad.get(k) for k in ("db", "db_ha", "secrets", "redis_ha", "redis_single")]
    out = [round(v, 2) for v in vals if v is not None]
    if plan["budget"] is not None:
        out += [round(abs(plan["budget"] - v), 2) for v in out]
        out.append(plan["budget"])
    return out
