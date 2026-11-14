"""The 'where will it run?' choices shown after the report.

Every option comes from the planner's own priced options (the same numbers as the report), plus a fixed set of escape hatches.
The AI model plays no part: it can neither invent an option nor pick one. Each option says honestly whether files exist for it yet."""
import re

HETZNER_FILES = ["infra/hetzner/main.tf", "infra/hetzner/variables.tf", "infra/hetzner/outputs.tf", "infra/hetzner/cloud-init.yaml",
                 "infra/hetzner/terraform.tfvars.example", "docker-compose.prod.yml", "deploy/Caddyfile"]
AWS_FILES = [f"infra/aws/{n}" for n in ("main.tf", "variables.tf", "outputs.tf", "cloud-init.yaml", "terraform.tfvars.example")] + ["docker-compose.prod.yml", "deploy/Caddyfile"]
AZURE_FILES = [f"infra/azure/{n}" for n in ("main.tf", "variables.tf", "outputs.tf", "cloud-init.yaml", "terraform.tfvars.example")] + ["docker-compose.prod.yml", "deploy/Caddyfile"]
NOT_YET = "not-yet"
OTHER = "other-cloud"
HETZNER = "hetzner-server"
AWS = "aws-server"
AZURE = "azure-server"
SERVER_FILES = {HETZNER: HETZNER_FILES, AWS: AWS_FILES, AZURE: AZURE_FILES}


def _retrieved_platforms():
    from knowledge import prices
    return prices.RETRIEVED_PLATFORMS


PLATFORM_PRICE_NOTES = {
    "aws_fargate": "From AWS's own price list for Frankfurt (read " + _retrieved_platforms() + "): the Fargate tasks, one Application Load Balancer (its fixed hourly fee and its public addresses) "
                   "and a public address for each task, converted to EUR, excluding VAT. Not included: what the load balancer charges for traffic, traffic out of AWS, backups.",
    "azure_container_apps": "From Azure's own price list for West Europe (read " + _retrieved_platforms() + "): Container Apps at the full running rate for the whole month, converted to EUR, "
                            "excluding VAT. Azure charges less while a copy is idle and gives a free allowance each month, so your real bill can be lower. Traffic out of Azure is not included.",
}


def _platform(label):
    l = (label or "").lower()
    for key, pid in (("gke", "gke_autopilot"), ("cloud run", "cloud_run"), ("fargate", "aws_fargate"), ("container apps", "azure_container_apps"), ("eks", "aws_eks")):
        if key in l:
            return pid
    return "other"


def _provider(pid):
    return {"gke_autopilot": "Google Cloud", "cloud_run": "Google Cloud", "aws_fargate": "AWS", "azure_container_apps": "Azure", "aws_eks": "AWS"}.get(pid, "")


def _server(scan, kind="hetzner"):
    """The smallest single server of that provider that fits the scan, or None. kind: hetzner | aws | azure."""
    from knowledge import prices
    try:
        from nodes import planner
        if kind == "aws":
            s = planner._cheapest_single_server(scan, prices.AWS_SERVERS, True, prices.RETRIEVED_VM)
            rows = prices.AWS_SERVERS
        elif kind == "azure":
            s = planner._cheapest_single_server(scan, prices.AZURE_SERVERS, True, prices.RETRIEVED_VM)
            rows = prices.AZURE_SERVERS
        else:
            s = planner._cheapest_single_server(scan)
            rows = prices.HETZNER_SERVERS
    except Exception:
        return None
    if not s:
        return None
    default = {"hetzner": "FSN1/NBG1/HEL1", "aws": "eu-central-1", "azure": "westeurope"}[kind]
    locs = next((x[5] for x in rows if x[0] == s[0]), default)
    return {"name": s[0], "vcpu": s[1], "ram": s[2], "eur": s[3], "locations": locs, "retrieved": s[4]}


def build_targets(scan, plan=None, gaps=None):
    """List of option dicts, the recommended one first. Keys: id, label, provider, monthly_eur, zone_ha, recommended, files, note, server,
    profile, catch (one line: what you give up) and brief (the plain-language 'Your chosen setup' section, markdown)."""
    out = []
    ss = (plan or {}).get("small_server")
    hz = _server(scan)
    if hz:
        out.append({"id": HETZNER, "label": f"One Hetzner Cloud server ({hz['name']}: {hz['vcpu']} vCPU, {hz['ram']} GB RAM), excl. VAT",
                    "provider": "Hetzner", "monthly_eur": hz["eur"], "zone_ha": False, "recommended": bool(ss), "files": True,
                    "note": "Cheapest. One machine, so no survival of a server or zone outage. Files: Terraform, docker-compose and a reverse proxy.",
                    "server": hz})
    aws, az = _server(scan, "aws"), _server(scan, "azure")
    if aws:
        out.append({"id": AWS, "label": f"One AWS server (EC2 {aws['name']}: {aws['vcpu']} vCPU, {aws['ram']} GiB RAM, Frankfurt), excl. VAT",
                    "provider": "AWS", "monthly_eur": aws["eur"], "zone_ha": False, "recommended": False, "files": True,
                    "note": "One machine, so no survival of a server or zone outage. Files: Terraform, docker-compose and a reverse proxy.", "server": aws,
                    "price_note": f"From AWS's own price list for Frankfurt (read {aws['retrieved']}): the server, a 20 GB disk and one public IPv4 address, on-demand, converted to EUR, excluding VAT. "
                                  "Traffic out of AWS, backups and anything you add later are not included."})
    if az:
        out.append({"id": AZURE, "label": f"One Azure server (VM {az['name']}: {az['vcpu']} vCPU, {az['ram']} GiB RAM, West Europe), excl. VAT",
                    "provider": "Azure", "monthly_eur": az["eur"], "zone_ha": False, "recommended": False, "files": True,
                    "note": "One machine, so no survival of a server or zone outage. Files: Terraform, docker-compose and a reverse proxy.", "server": az,
                    "price_note": f"From Azure's own price list for West Europe (read {az['retrieved']}): the server, a 32 GiB SSD disk and one static public IPv4 address, pay-as-you-go, excluding VAT. "
                                  "Traffic out of Azure, disk operations, backups and anything you add later are not included."})
    if plan:
        opts = [(plan["chosen"], plan["total"], plan.get("notes") or [])] + [(a, a["total"], a.get("notes") or []) for a in plan.get("alternatives", [])]
        for i, (o, total, notes) in enumerate(opts):
            pid = o.get("platform") or _platform(o.get("label"))
            card = {"id": f"plan-{i}", "label": o["label"] + (" + " + " + ".join(notes) if notes else ""), "provider": _provider(pid),
                    "monthly_eur": round(total, 2), "zone_ha": bool(o.get("zone_ha")), "recommended": i == 0 and not ss, "files": False,
                    "note": "Priced in the report. No infrastructure files for this yet: you still get the basic files and the report.", "server": None}
            if pid in PLATFORM_PRICE_NOTES:
                card["price_note"] = PLATFORM_PRICE_NOTES[pid]
            out.append(card)
    out.append({"id": OTHER, "label": "A different cloud or platform (Fly.io, Kubernetes on AWS or Azure, your own servers, ...)", "provider": "", "monthly_eur": None,
                "zone_ha": None, "recommended": False, "files": False,
                "note": "No infrastructure files for it yet. You still get the basic files; the report's advice is provider-neutral.", "server": None})
    out.append({"id": NOT_YET, "label": "Not decided yet: just the basic files", "provider": "", "monthly_eur": None, "zone_ha": None,
                "recommended": not out, "files": True, "note": "Dockerfile, CI and the other starter files only.", "server": None})
    from . import choices
    priced = [t["monthly_eur"] for t in out if t["monthly_eur"] is not None]
    cheapest = min(priced) if priced else None
    for t in out:
        plat = _platform(t["label"]) if t["id"].startswith("plan-") else ""
        t["profile"] = choices.profile_id(t["id"], plat)
        t["catch"] = choices.catch(t["profile"])
        t["drawbacks"] = list(choices.PROFILES[t["profile"]]["give_up"])
        if (plan or {}).get("uptime") == "zero" and t["id"] in (HETZNER, AWS, AZURE):
            warn = "You asked for no downtime. One server does NOT meet that: it is down while it restarts or if its zone fails."
            t["drawbacks"].insert(0, warn)
            t["note"] = warn + " " + t["note"]
            t["recommended"] = False
        t["benefits"] = _benefits(t, cheapest)
        t["links"] = [{"label": n, "url": u} for n, u in choices.PROFILES[t["profile"]].get("links", [])]
        t["short"] = {HETZNER: "one Hetzner server", AWS: "one AWS server", AZURE: "one Azure server"}.get(t["id"]) or t["label"].split(",")[0].split(" (")[0].strip()
    if not any(t["recommended"] for t in out):
        first_plan = next((t for t in out if t["id"].startswith("plan-")), None)
        if first_plan:
            first_plan["recommended"] = True
    for t in out:
        t["why"] = _why(t, plan) if t["recommended"] else []
        t["brief"] = choices.brief_markdown(t, scan, gaps, SERVER_FILES.get(t["id"]))
    out.sort(key=lambda t: not t["recommended"])
    return out


def _benefits(t, cheapest):
    """The profile's benefits plus the two that depend on this option's own numbers."""
    from . import choices
    out = list(choices.PROFILES[t["profile"]].get("benefits", []))
    if cheapest is not None and t["monthly_eur"] is not None and t["monthly_eur"] == cheapest:
        out.insert(0, "The lowest price in this list.")
    if t["zone_ha"] is True and t["profile"] in ("aws_fargate", "azure_container_apps"):
        out.insert(1 if out else 0, "Can keep running if one zone of the data centre has a problem, when the copies are placed in more than one zone (the report says how).")
    elif t["zone_ha"] is True and t["profile"] in ("gke_autopilot", "cloud_run"):
        out.insert(1 if out else 0, "Keeps running if one zone of the data centre has a problem, because it has copies in more than one.")
    return out


def _why(t, plan):
    """Why this option is the recommended one, from what the planner knows. Only statements the plan's own numbers support."""
    plan = plan or {}
    out = []
    ss = plan.get("small_server")
    budget, uptime, status = plan.get("budget"), plan.get("uptime"), plan.get("status")
    if t["id"] == HETZNER and ss:
        tier = ss.get("tier_name")
        out.append(f"Your expected traffic is small{f' ({tier})' if tier else ''}, so one small server is enough.")
        if budget is not None and ss.get("total") is not None and ss["total"] <= budget:
            out.append(f"It is {budget - ss['total']:.0f} EUR under your budget of {budget:.0f} EUR/month.")
        return out
    if status == "fits" and budget is not None:
        out.append(f"It fits your budget of {budget:.0f} EUR/month.")
    if uptime == "zero" and t["zone_ha"]:
        out.append("You asked for no downtime, and it keeps running if a zone fails.")
    elif uptime == "zero" and not t["zone_ha"]:
        out.append("Surviving a whole zone outage does not fit your budget. This is the best setup that does fit.")
    elif uptime in ("minutes", "hours"):
        out.append("It matches the downtime you said you can accept.")
    if status == "over_budget":
        out.append("Nothing in this list fits your budget, so read the cost section of the report before you choose.")
    return out


def is_cloud_file(path):
    """True for the files that belong to the chosen hosting setup (as opposed to the basic files that fit any provider)."""
    return path.startswith(("infra/", "deploy/")) or path == "docker-compose.prod.yml"


def find(targets, target_id):
    return next((t for t in targets if t["id"] == target_id), None)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "app"
