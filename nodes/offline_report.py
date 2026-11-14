"""Offline report: sections 1, 3 and 5 are written by code from the scan result, the user's answers and the planner.
No AI model is called. Everything stated here is a scan fact or a planner line, so nothing can be invented.
The gap table (2) and the cost section (4) are rebuilt by the normal pipeline afterwards; this module only supplies a skeleton."""
import re

_KIND_TEXT = {
    "application": "a deployable application",
    "library_or_tool": "a library or tool, not a deployable application",
    "infrastructure_only": "infrastructure code only (no application code)",
    "ml_project": "a machine-learning project",
    "example_collection": "a collection of examples, not one deployable application",
    "project_template": "a project template, not a deployable application",
    "no_application_code": "a repository without application code",
}
_NOT_DEPLOYABLE = {"library_or_tool", "infrastructure_only", "example_collection", "project_template", "no_application_code"}


def _join(items, limit=6):
    items = [str(i) for i in items if i]
    if len(items) > limit:
        return ", ".join(items[:limit]) + f" and {len(items) - limit} more"
    return ", ".join(items)


def _section1(scan):
    kind = scan.get("repo_kind") or "application"
    langs = list((scan.get("languages") or {}).keys())[:4]
    svc = [x for x in ((scan.get("services") or {}).get("list") or []) if not x.get("client_app")]
    details = scan.get("infra_details") or {}
    s = [f"The scan classifies this repository as {_KIND_TEXT.get(kind, kind)}."]
    if langs:
        s.append(f"Main languages found: {_join(langs)}.")
    if svc and kind not in _NOT_DEPLOYABLE:
        s.append(f"It has {len(svc)} deployable service(s).")
    if details.get("iac_tools"):
        s.append(f"Infrastructure tooling found: {_join(details['iac_tools'])}.")
    ds = scan.get("datastore_summary") or {}
    if ds.get("default_in_cluster"):
        s.append(f"Datastore(s) deployed by default: {_join(ds['default_in_cluster'])}.")
    if kind in _NOT_DEPLOYABLE:
        s.append("It is not a deployable application, so traffic, hosting cost and architecture sizing do not apply the way they would for a service.")
    return " ".join(s)


def _needs_line(scan):
    """What the project needs to run, in provider-neutral words, from scan facts only."""
    svc = [x for x in ((scan.get("services") or {}).get("list") or []) if not x.get("client_app")]
    ds = (scan.get("datastore_summary") or {}).get("default_in_cluster") or []
    parts = []
    if svc:
        parts.append(f"{len(svc)} service{'s' if len(svc) != 1 else ''} running all the time")
    if ds:
        parts.append(f"a datastore ({_join(ds, 3)})")
    if not parts:
        return ""
    return "- What it needs to run, on any provider: " + " and ".join(parts) + "."


_PLATFORM = {"gke_autopilot": "GKE Autopilot", "cloud_run": "Cloud Run (always-on)", "aws_fargate": "AWS ECS Fargate", "azure_container_apps": "Azure Container Apps"}


def _section3(scan, plan, describe):
    kind = scan.get("repo_kind") or "application"
    if not plan:
        if kind in _NOT_DEPLOYABLE:
            return ("There is nothing to host here, so no architecture is recommended. A consumer or maintainer should check the gaps in section 2 "
                    "(tests, CI, licence, security policy, dependency pinning).")
        return "No setup was priced because the answers were not enough to choose one. Answer the questions about traffic, budget and downtime to get a recommendation."
    ss = plan.get("small_server")
    if ss:
        out = [x for x in (_needs_line(scan),) if x]
        out.append(f"- Setup: one small server ({ss['name']}, {ss['vcpu']} vCPU, {ss['ram']} GB RAM) is enough for your stated load. Any provider with a server of that size works; the priced example is Hetzner.")
        if plan.get("budget") is not None:
            out.append("- It fits your budget.")
        out.append("- It does not survive a server or zone outage: there is one copy and no failover.")
        out.append("- The exact setup, total, the managed-platform alternative and what is not included are in section 4.")
        return "\n".join(out)
    o = plan["chosen"]
    r = o.get("replicas") or 1
    n = o.get("stateless_services", o.get("services"))
    needs = _needs_line(scan)
    out = [needs] if needs else []
    out.append(f"- Platform: {_PLATFORM.get(o.get('platform'), o.get('platform') or 'see section 4')}, {r} cop{'y' if r == 1 else 'ies'} of each of {n} service{'s' if n != 1 else ''}. "
               "This is the setup that was priced, not a requirement: the same setup can run on any provider, and you do not need this one.")
    if plan.get("hypothetical"):
        out.append("- This is a hypothetical figure: the repository is not deployable today.")
    if plan.get("budget") is not None:
        out.append("- It fits your budget." if plan["total"] <= plan["budget"] else "- It does not fit your budget; see section 4 for the choices.")
    out.append("- It survives a zone outage." if o.get("zone_ha") else "- It does not survive a zone outage.")
    if plan.get("demo"):
        out.append(f"- Left out on purpose: {', '.join(plan['demo'])} (demo/test tooling).")
    out.append("- The exact setup, total, alternatives and what is not included are in section 4.")
    return "\n".join(out)


def _section5(scan, answers, plan):
    b = []
    if not answers or not any(str(v).strip() for v in answers.values()):
        b.append("You gave no answers about traffic, budget or downtime, so sizing and cost are not based on your needs.")
    if plan and plan.get("db_mode") == "unknown":
        b.append("You gave no usable database answer, so no database is in the total.")
    if plan and any("EU price not read" in str(n) for n in plan.get("notes", [])):
        b.append("Some managed-service prices are US prices because the EU price could not be read; the EU price may differ.")
    if plan and plan.get("hypothetical"):
        b.append("The priced setup is hypothetical because the repository is not deployable today.")
    if scan.get("secrets_findings"):
        b.append("The secret findings are pattern matches; each one needs a human check before it is called a real leak.")
    b.append("Only what the scanner can see in the repository is covered: runtime behaviour, real load and cloud account settings are not checked.")
    b.append("Prices come from the published price table with its retrieval date; actual bills depend on usage and discounts.")
    return "\n".join(f"- {x}" for x in b[:6])


def build_skeleton(scan, answers, plan, describe):
    return "\n\n".join([
        "## 1. What this project is\n\n" + _section1(scan),
        "## 2. What's missing for production\n\n| Gap | Severity | Source | Risk |\n|---|---|---|---|\n"
        "| None found by the scan | Low | Checked in your repo by the scan | The scan found no gaps in the areas it checks. |",
        "## 3. Recommended architecture and deployment\n\n" + _section3(scan, plan, describe),
        "## 4. Estimated monthly cost\n\nSee the computed section below.",
        "## 5. What this report cannot tell you\n\n" + _section5(scan, answers, plan),
    ])


def section5(scan, answers, plan):
    return _section5(scan, answers, plan)
