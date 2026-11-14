"""Runs every registered generator for the gaps of one scan and returns a Bundle.

Rules that hold for every file:
  * only files for gaps that exist in this scan (nothing is generated for something the repo already has)
  * deterministic: the same scan gives the same files; no AI model writes any file content
  * facts only: no source code is read, so it works from a saved scan result and the repo can already be deleted
  * every file says what it assumed and what the user must check; every gap without a generator says why"""
from .model import Bundle, Skipped
from .advice import advice_for
from .registry import GENERATORS
from . import docker, ci  # noqa: F401  (importing registers the generators)
from .context import services

# Gaps that are about a missing thing but that no generator covers yet, or that a file cannot fix.
SKIP_REASONS = {
    "no_tests": "Tests need to be written for your code; a generated test would only check that the file exists.",
    "no_iac": "Infrastructure files depend on the cloud you choose. This is the next phase.",
    "no_cloud_iac": "Infrastructure files depend on the cloud you choose. This is the next phase.",
    "no_observability": "Metrics and tracing need a change in your code (a library and an endpoint), not a new file.",
    "possible_hardcoded_secrets": "Move the secret out of the code, rotate it, and use environment variables. A file cannot do that for you.",
}
NO_TEMPLATE = "No template covers this yet, or it is a change to existing code or settings rather than a missing file. See the report for what to do."


def generate_files(scan, gaps=None, target=None):
    """target: one option dict from generators.targets.build_targets (what the user chose), or None for the basic files only."""
    if gaps is None:
        from nodes.gap_identifier import identify_gaps
        gaps = identify_gaps(scan)
    issues = {g["issue"] for g in gaps}
    bundle, seen, covered = Bundle(), set(), set()
    for wanted, fn in GENERATORS:
        if wanted and not (set(wanted) & issues):
            continue
        for art in fn(scan, gaps):
            if art.path in seen:
                continue
            seen.add(art.path)
            bundle.files.append(art)
            covered.add(art.gap)
    if target:
        bundle.target = {k: target.get(k) for k in ("id", "label", "provider", "monthly_eur", "zone_ha", "files", "profile", "benefits", "why", "price_note", "links", "short")}
        from . import targets, hetzner, aws, azure
        pack = {targets.HETZNER: hetzner.pack, targets.AWS: aws.pack, targets.AZURE: azure.pack}.get(target["id"])
        if pack:
            art_list, why = pack(scan, gaps, target)
            for art in art_list:
                if art.path not in seen:
                    seen.add(art.path)
                    bundle.files.append(art)
                    covered.add(art.gap)
            for w in why:
                bundle.skipped.append(Skipped(gap=f"{target['id']} pack", reason=w))
    if target:
        from . import choices, targets as targets_mod
        bundle.brief = choices.brief_markdown(bundle.target, scan, gaps, [f.path for f in bundle.files if targets_mod.is_cloud_file(f.path)] or None)
    _, svc_skipped = services(scan)
    for path, why in svc_skipped:
        bundle.skipped.append(Skipped(gap=f"service {path}", reason=why))
    by_issue = {g["issue"]: g for g in gaps}
    for issue in [i for i in dict.fromkeys(g["issue"] for g in gaps) if i not in covered]:
        a = advice_for(issue, by_issue[issue])
        if a:
            bundle.advice.append(a)
        else:
            bundle.skipped.append(Skipped(gap=issue, reason=SKIP_REASONS.get(issue, NO_TEMPLATE)))
    from .implement import implementation_md
    bundle.implementation = implementation_md(bundle, scan)
    return bundle
