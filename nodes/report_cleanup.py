"""Code-side clean-up of the written report, so the result does not depend on how careful the model was.

  * gap table: drop note rows, cap severities that rest on no evidence, put the most serious first, renumber,
    keep it to a readable length, and add the rows that only become gaps because of the user's answers
  * price dates: the model must not invent 'prices as of 2024'
  * scanner wording that leaked into the text
"""
import re

SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
GROUP_ORDER = {"required": 0, "recommended": 1, "optional": 2}
GROUP_LABEL = {"required": "Needed to run safely", "recommended": "Recommended", "optional": "Optional"}
MAX_GAP_ROWS = 12
_SECRET_WORDS = re.compile(r"secret|credential|password|private key|api key|token", re.I)
_TOOL_HIGH_OK = re.compile(r"ci/cd|ci\b|pipeline|tests?\b|secret|credential|password|authenticat|authoris|authoriz|rate limit|api key", re.I)


def _cells(line):
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def _row(cells):
    return "| " + " | ".join(cells) + " |"


def _find_gap_table(lines):
    """(start, end) line indexes of the table whose header has Gap and Severity columns, or None."""
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            head = [c.lower() for c in _cells(lines[i])]
            if any(c.startswith("gap") or c in ("issue", "finding") for c in head) and "severity" in head:
                return i, j
            i = j
        else:
            i += 1
    return None


def injected_rows(scan_result, answers, planner):
    """Rows that only exist because of what the user said. (gap, severity, source, risk)"""
    rows = []
    kind = scan_result.get("repo_kind")
    env = " ".join(str(v) for v in (scan_result.get("env_vars") or []))
    if kind == "library_or_tool" and planner.wants_hosting(answers) and re.search(r"API_KEY|_TOKEN|SECRET", env, re.I):
        rows.append(("No authentication or rate limiting once the tool is reachable over HTTP", "High", "My observation from the scan data (a paid API key plus a public URL)",
                     "Anyone who finds the URL can use your API key and your quota. Put authentication in front of it, limit requests per client, and set a spend cap with the API provider before launch."))
    if planner.parse_database_mode(answers) == "external" and (planner.parse_uptime(answers) == "zero" or planner.data_loss_none(answers)):
        rows.append(("The database you run yourself is where zero downtime and zero data loss are decided", "Medium", "My observation from your answers",
                     "A database you run yourself needs replication, automatic backups and a restore you have actually tested. Without them the application setup above cannot deliver the availability you asked for."))
    return rows


def clean_gap_table(report, scan_result, answers, planner):
    lines = report.split("\n")
    loc = _find_gap_table(lines)
    if not loc:
        return report
    a, b = loc
    header = _cells(lines[a])
    low = [h.lower() for h in header]
    sev_i = low.index("severity")
    gap_i = next((k for k, h in enumerate(low) if h.startswith("gap") or h in ("issue", "finding")), 0)
    src_i = next((k for k, h in enumerate(low) if h.startswith("source")), None)
    num_i = 0 if low[0] in ("#", "no", "no.", "nr", "nr.", "number") else None
    risk_i = next((k for k, h in enumerate(low) if h.startswith("risk")), None)
    rows = []
    for ln in lines[a + 1:b]:
        cells = _cells(ln)
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
            continue
        if len(cells) < len(header):
            cells += [""] * (len(header) - len(cells))
        cells = cells[:len(header)]
        sev = cells[sev_i].strip().strip("*").lower()
        if sev not in SEV_ORDER:                     # a note that ended up in the table, not a gap
            continue
        rows.append(cells)

    kind = scan_result.get("repo_kind")
    uptime = planner.parse_uptime(answers)
    for cells in rows:
        gap = cells[gap_i]
        src = (cells[src_i].lower() if src_i is not None else "")
        sev = cells[sev_i].strip().strip("*").lower()
        # evidence rule: only a check that was run on the repo can be High; opinions are Medium at most
        if sev in ("high", "critical") and ("my observation" in src or "standard practice" in src or "not verified" in src) and not re.search(r"committed|hard-?coded|exposed", gap, re.I):
            sev = "medium"
        # a library or tool that is not deployed: to-do items for a future deployment are not High
        if kind == "library_or_tool" and sev in ("high", "critical") and not _TOOL_HIGH_OK.search(gap):
            sev = "medium"
        # you asked for no downtime: missing disruption protection is not 'Low'
        if uptime == "zero" and sev == "low" and re.search(r"disruption budget|\bpdb\b|autoscal", gap, re.I):
            sev = "medium"
        cells[sev_i] = sev.capitalize()

    have = " ".join(c[gap_i].lower() + " " + (c[risk_i].lower() if risk_i is not None else "") for c in rows)
    for gap, sev, source, risk in injected_rows(scan_result, answers, planner):
        key = "authentic" if "authentication" in gap else "database you run"
        if key == "database you run" and re.search(r"database[^|]{0,80}(?:local|yourself|self[- ]|single[- ]node)|(?:local|self[- ]?(?:hosted|managed|run))[^|]{0,60}database", have):
            continue                       # the model already has a row about the database you run yourself
        if key == "authentic" and re.search(r"authenticat", have) and re.search(r"rate limit", have):
            continue
        if key == "database you run" and re.search(r"backup", have) and re.search(r"replicat|restore", have):
            continue
        cells = [""] * len(header)
        cells[gap_i], cells[sev_i] = gap, sev
        if src_i is not None:
            cells[src_i] = source
        if risk_i is not None:
            cells[risk_i] = risk
        rows.append(cells)

    # two rows about the database you run yourself say the same thing; keep the first and fold the second into its risk text
    db_re = re.compile(r"database|postgres|\bdb\b", re.I)
    db_topic = re.compile(r"backup|replicat|point-in-time|\blocal\b|self[- ]?(?:run|hosted|managed)|yourself|hosting plan", re.I)
    first = None
    kept = []
    for cells in rows:
        text = cells[gap_i]
        if db_re.search(text) and db_topic.search(text + " " + (cells[risk_i] if risk_i is not None else "")):
            if first is None:
                first = cells
            else:
                if SEV_ORDER.get(cells[sev_i].strip().lower(), 9) < SEV_ORDER.get(first[sev_i].strip().lower(), 9):
                    first[sev_i] = cells[sev_i]
                if risk_i is not None and cells[risk_i].strip() and cells[risk_i].strip() not in first[risk_i]:
                    first[risk_i] = first[risk_i].rstrip(". ") + ". Also: " + cells[risk_i].strip()
                continue
        kept.append(cells)
    rows = kept

    rows.sort(key=lambda c: SEV_ORDER.get(c[sev_i].strip().lower(), 9))     # stable: the model's order survives inside a level
    if len(rows) > MAX_GAP_ROWS:
        keep, rest = rows[:MAX_GAP_ROWS - 1], rows[MAX_GAP_ROWS - 1:]
        merged = [""] * len(header)
        merged[gap_i] = f"{len(rest)} further minor findings: " + "; ".join(re.sub(r"\s+", " ", r[gap_i])[:70] for r in rest)
        merged[sev_i] = "Low"
        if src_i is not None:
            merged[src_i] = "Rule-based scan / my observation"
        if risk_i is not None:
            merged[risk_i] = "Each is small on its own; fix them after the rows above."
        rows = keep + [merged]
    out = [_row(header), _row(["---"] * len(header))]
    for n, cells in enumerate(rows, 1):
        if num_i is not None:
            cells[num_i] = str(n)
        out.append(_row(cells))
    after = lines[b:]
    if after and after[0].strip():
        after = [""] + after                      # a table must be followed by a blank line or the next heading is read as a row
    return "\n".join(lines[:a] + out + after)


_ASOF_RE = re.compile(r"(\bas of\s+)(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:\d{1,2},?\s+)?(20\d\d)(?:-\d\d(?:-\d\d)?)?", re.I)
_YEAR_PRICES_RE = re.compile(r"\b(20\d\d)\s+((?:list\s+|published\s+|public\s+)?(?:prices?|pricing|rates?))\b", re.I)


def fix_price_dates(report, retrieved, also_ok=()):
    """The price table says when its prices were read. A different date in the text is the model's invention."""
    keep = {retrieved, *also_ok}

    def _asof(m):
        return m.group(0) if any(k in m.group(0) for k in keep) else m.group(1) + retrieved

    def _yearprices(m):
        return m.group(0) if m.group(1) == retrieved[:4] else f"{m.group(2)} (read {retrieved})"

    out = []
    for line in report.split("\n"):
        if re.search(r"price|pricing|cost|rate", line, re.I):
            line = _ASOF_RE.sub(_asof, line)
            line = _YEAR_PRICES_RE.sub(_yearprices, line)
        out.append(line)
    return "\n".join(out)


_PHRASE_SCRUBS = [
    (r"\bthat the (?:analysis|decision|planning|pricing) (?:code|logic|engine|planner) (?:recommends|selected|chose|picked)", "that the price comparison recommends"),
    (r"\bthe (?:analysis|decision|planning|pricing) (?:code|logic|engine|planner)\b", "the price comparison"),
    (r"Follow the exact setup that (?:the )?(?:automatic |deterministic )?(?:decision )?(?:logic|planner|engine|code) selected\s*:?", "Recommended setup (chosen by the price comparison):"),
    (r"\b(?:the )?automatic (?:decision )?(?:logic|planner|engine)\b", "the price comparison"),
    (r"\s*\(\s*`?[a-z][a-z0-9]*(?:_[a-z0-9]+)+`?\s*\)", ""),          # scanner ids such as ( env_file_in_repo ) are not for the reader
    (r"\b[Tt]he deterministic (?:decision )?(?:logic|pass|planner|engine)\b", "the price comparison"),
    (r"\bdeterministic (?:decision )?(?:logic|planner)\b", "price comparison"),
    (r"\bDECISION MADE BY CODE\b", "the recommended setup"),
    (r"\b(?:organi[sz]ed|structured) as (?:a )?single logical service at the repo(?:sitory)? root with (\w+) librar(?:y|ies) folders? excluded from the service count",
     r"a single project at the repository root with \1 shared-code folder(s)"),
    (r"\b(\w+) librar(?:y|ies) folders? excluded from the service count", r"\1 shared-code folder(s) that are not services of their own"),
    (r"\bexcluded from the service count\b", "treated as shared code, not as a service"),
    (r"\bsingle logical service\b", "single service"),
    (r"\bthe scan (?:data )?(?:flag|field)s?\b", "the scan"),
]


def scrub_scanner_words(report):
    # "The DECISION MADE BY CODE ..." (any quoting) must not become "The the recommended setup"
    report = re.sub(r"\b(The|the)\s+[*_\"'`(]*DECISION MADE BY CODE[*_\"'`)]*(?:\s+(?:line|section|setup|recommendation))?",
                    lambda m: "The recommended setup" if m.group(1) == "The" else "the recommended setup", report)
    report = re.sub(r"\b(?:provides|gives|states|makes) the exact recommendation\b(:|,)?", lambda m: "is" + (m.group(1) or ""), report, flags=re.I)
    for pat, repl in _PHRASE_SCRUBS:
        report = re.sub(pat, repl, report, flags=re.I)
    return re.sub(r"\b(the|The)\s+(?:the)\b", r"\1", report)


_H4_RE = re.compile(r"^[ \t]*(?P<hash>#{1,4}[ \t]*)?[*_]*[ \t]*(?:4[.)][ \t]*)?[*_]*[ \t]*Estimated[ \t]+Monthly[ \t]+Cost\b.*$", re.I | re.M)
_H5_RE = re.compile(r"^[ \t]*(?:#{1,4}[ \t]*)?[*_]*[ \t]*(?:5[.)][ \t]*)[*_]*[ \t]*\S", re.M)


def replace_cost_section(report, decision_markdown):
    """The model's cost section is replaced by the computed one, so a small model cannot quote the wrong setup's total.
    Returns (report, True) when a section was replaced."""
    m = _H4_RE.search(report)
    if not m or not decision_markdown:
        return report, False
    m5 = _H5_RE.search(report, m.end())
    end = m5.start() if m5 else len(report)
    # never swallow the gap table or the appendix by accident: only replace when the section is plausibly the cost section
    if end - m.end() > 12000:
        return report, False
    hash_ = m.group("hash") or ""
    body = decision_markdown.split("\n", 1)[1].lstrip("\n") if decision_markdown.startswith("## ") else decision_markdown
    new = f"{hash_}4. Estimated Monthly Cost (computed in code)\n\n{body}\n\n"
    return report[:m.start()] + new + report[end:], True


# ---------------------------------------------------------------------------------------------------------------------
# The gap table is built from the scan, not from the model: every row that says "checked in your repo" is a finding the
# scanner produced, with its own evidence text. The model may add a few opinions, clearly labelled as such.
# ---------------------------------------------------------------------------------------------------------------------
GAP_TITLES = {
    "no_cicd": "No CI/CD pipeline", "no_tests": "No automated tests", "no_dockerfile": "No Dockerfile",
    "no_cloud_iac": "No infrastructure-as-code for the cloud resources", "no_iac": "No infrastructure-as-code",
    "default_credentials_in_config": "Default credentials in configuration", "possible_hardcoded_secrets": "Possible hard-coded secrets in code or config",
    "secret_shaped_values_in_tests_or_examples": "Secret-looking values in tests or examples",
    "terraform_no_remote_state": "Terraform state is not stored remotely", "terraform_no_lock_file": "Terraform provider lock file missing",
    "dev_env_files_in_repo": "Development env files are committed", "env_file_in_repo": ".env file exists in the repository",
    "sensitive_files_in_repo": "Sensitive files (keys, certificates) in the repository", "tfvars_file_in_repo": "Terraform variable files committed",
    "no_health_probes": "No health probes / health endpoint", "no_observability": "No metrics, tracing or error tracking",
    "tracing_without_metrics_alerting": "Tracing without metrics or alerting", "error_tracking_only": "Only error tracking, no metrics or alerts",
    "services_without_tests": "Some services have no tests", "services_without_dockerfile": "Some services have no Dockerfile",
    "containers_run_as_root": "Containers run as root", "unpinned_base_images": "Base images are not pinned to a version",
    "no_dockerignore": "No .dockerignore", "ci_does_not_run_tests": "CI does not run the tests", "ci_no_security_scanning": "CI has no security scanning step",
    "ci_does_not_build_images": "CI does not build container images", "no_dependency_update_bot": "No Dependabot / Renovate configuration",
    "no_dependency_lockfile": "No dependency lockfile", "k8s_no_security_context": "Kubernetes workloads have no securityContext",
    "k8s_images_use_latest_tag": "Kubernetes images use the :latest tag", "k8s_ingress_class_not_gke": "Ingress class does not match GKE", "k8s_no_network_policies": "No NetworkPolicy objects",
    "k8s_no_disruption_or_autoscaling_config": "No PodDisruptionBudget or autoscaler",
}


def gap_title(issue):
    if issue in GAP_TITLES:
        return GAP_TITLES[issue]
    m = re.fullmatch(r"in_cluster_(.+)_without_persistent_volume", issue)
    if m:
        return f"In-cluster {m.group(1)} has no persistent volume (data lost on restart)"
    m = re.fullmatch(r"compose_(.+)_without_volume", issue)
    if m:
        return f"Compose {m.group(1)} has no volume (data lost on restart)"
    return issue.replace("_", " ").capitalize()


_STOP = set("the a an of to in is are for and or no not on with without this that it be by as at from your you".split())


def _words(text):
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in _STOP}


def _overlaps(a, b, thr=0.25):
    wa, wb = _words(a), _words(b)
    return bool(wa and wb) and len(wa & wb) / len(wa | wb) >= thr


_TOPICS = [r"monitor|alert|metrics?|prometheus|grafana|observab|tracing|logging", r"\btests?\b|testing", r"backup|restore|disaster",
           r"secret|credential|password|api key", r"ci/cd|\bci\b|pipeline|continuous", r"health ?(check|probe|endpoint)|liveness|readiness",
           r"\bdocker(file|ignore)?\b|container image|base image", r"network ?polic|firewall", r"autoscal|disruption|pdb|replicas?"]


def _same_topic(a, b):
    """True when both texts are about the same subject, so the model's opinion is not shown next to the scanner's finding on it."""
    return any(re.search(t, a, re.I) and re.search(t, b, re.I) for t in _TOPICS)


def rebuild_gap_table(report, scan_result, answers, planner, gaps):
    """Replace the model's gap table by one built from the scanner's findings. Returns the report unchanged if there is no table or no findings."""
    lines = report.split("\n")
    loc = _find_gap_table(lines)
    if not loc or not gaps:
        return report
    a, b = loc
    header = _cells(lines[a])
    low = [h.lower() for h in header]
    sev_i = low.index("severity")
    gap_i = next((k for k, h in enumerate(low) if h.startswith("gap") or h in ("issue", "finding")), 0)
    src_i = next((k for k, h in enumerate(low) if h.startswith("source")), None)
    risk_i = next((k for k, h in enumerate(low) if h.startswith("risk")), None)

    kind = scan_result.get("repo_kind")
    uptime = planner.parse_uptime(answers)
    code_rows = []
    for g in gaps:
        sev = str(g.get("severity", "low")).lower()
        if sev not in SEV_ORDER:
            sev = "low"
        title = gap_title(g.get("issue", ""))
        if uptime == "zero" and sev == "low" and g.get("issue") == "k8s_no_disruption_or_autoscaling_config":
            sev = "medium"
        if kind == "library_or_tool" and sev in ("high", "critical") and not _TOOL_HIGH_OK.search(title + " " + g.get("detail", "")):
            sev = "medium"
        code_rows.append([title, sev.capitalize(), "Checked in your repo by the scan", str(g.get("detail", "")).strip(), g.get("group", "recommended")])

    model_rows = []
    for ln in lines[a + 1:b]:
        cells = _cells(ln)
        if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c) or len(cells) < len(header):
            continue
        sev = cells[sev_i].strip().strip("*").lower()
        src = cells[src_i].lower() if src_i is not None else ""
        if sev not in SEV_ORDER or not ("observation" in src or "standard practice" in src or "opinion" in src):
            continue                      # rule-based rows are the scanner's job; a "rule-based" row the scanner does not have is invented
        text = cells[gap_i] + " " + (cells[risk_i] if risk_i is not None else "")
        if any(_overlaps(text, r[0] + " " + r[3]) or _same_topic(text, r[0] + " " + r[3]) for r in code_rows):
            continue
        model_rows.append([cells[gap_i], "Low" if "standard practice" in src else ("Medium" if sev in ("critical", "high", "medium") else "Low"),
                           "AI observation (not checked by the scan)", cells[risk_i] if risk_i is not None else "", "optional"])
    model_rows = model_rows[:3]

    all_text = " ".join(r[0].lower() + " " + r[3].lower() for r in code_rows + model_rows)
    extra = []
    for gap, sev, source, risk in injected_rows(scan_result, answers, planner):
        if "authentication" in gap and re.search(r"authenticat", all_text) and re.search(r"rate limit", all_text):
            continue
        if "database you run" in gap and re.search(r"database[^|]{0,80}(?:local|yourself|self[- ]|single[- ]node|backup)|(?:local|self[- ]?(?:hosted|managed|run))[^|]{0,60}database", all_text):
            continue
        extra.append([gap, sev, "From your answers", risk, "recommended"])

    while model_rows and len(code_rows) + len(extra) + len(model_rows) > MAX_GAP_ROWS:
        model_rows.pop()                  # the model's own opinions go first when the table is too long
    rows = code_rows + extra + model_rows
    # things the project needs to be safe to run come first, then recommendations, then optional hardening; most serious first inside each group
    rows.sort(key=lambda r: (GROUP_ORDER.get(r[4], 1), SEV_ORDER.get(r[1].lower(), 9)))
    if len(rows) > MAX_GAP_ROWS:
        keep, rest = rows[:MAX_GAP_ROWS - 1], rows[MAX_GAP_ROWS - 1:]
        srcs = {r[2] for r in rest}
        label = next(iter(srcs)) if len(srcs) == 1 else "Mixed (scan, your answers, AI observation)"
        rows = keep + [[f"{len(rest)} further minor findings: " + "; ".join(r[0] for r in rest)[:300], "Low", label,
                        "Each is small on its own; fix them after the rows above.", "optional"]]
    out = [_row(["#", "Gap", "Group", "Severity", "Source", "Risk and evidence"]), _row(["---"] * 6)]
    for n, r in enumerate(rows, 1):
        cells = [r[0], GROUP_LABEL.get(r[4], "Recommended"), r[1], r[2], r[3]]
        out.append(_row([str(n)] + [c.replace("|", "/").replace("\n", " ") for c in cells]))
    after = lines[b:]
    if after and after[0].strip():
        after = [""] + after
    return "\n".join(lines[:a] + out + after)
