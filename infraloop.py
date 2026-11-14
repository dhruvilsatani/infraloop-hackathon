#!/usr/bin/env python3
"""InfraLoop command line.

  python infraloop.py scan <path-or-public-github-url> [--answers answers.json] [--format md|json] [--out FILE] [--ai]

By default the report is written by fixed rules (no AI model, nothing leaves your machine except a git clone of a URL).
--ai uses the model configured in OMNIROUTE_BASE_URL / OMNIROUTE_API_KEY / OMNIROUTE_API_MODEL.
answers.json is a plain {"question text": "answer"} object; without it the report is sized with no traffic/budget answers.
Exit code: 0 ok, 1 error, 2 high/critical gaps found with --fail-on-high (for CI and pre-commit hooks).
"""
import argparse, json, os, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="infraloop", description="Production-readiness report for a repository.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan", help="scan a repository and write a report")
    sc.add_argument("target", help="local folder or public git URL")
    sc.add_argument("--answers", help="JSON file with answers to the questionnaire")
    sc.add_argument("--format", choices=("md", "json"), default="md")
    sc.add_argument("--out", help="write to this file instead of the terminal")
    sc.add_argument("--ai", action="store_true", help="use the AI model for the report text")
    sc.add_argument("--fail-on-high", action="store_true", help="exit with code 2 when a high or critical gap is found")
    gn = sub.add_parser("generate", help="scan a repository and write starter files for the gaps (Dockerfile, CI, ...) into a NEW folder")
    gn.add_argument("target", help="local folder or public git URL")
    gn.add_argument("--out", default="infraloop-generated", help="new folder to write into (must not exist or be empty; nothing is ever overwritten)")
    gn.add_argument("--target", dest="run_on", choices=("hetzner-server", "aws-server", "azure-server", "not-yet"), default="not-yet",
                    help="where it will run: hetzner-server, aws-server or azure-server adds Terraform + docker-compose for one server there (default: just the basic files)")
    a = ap.parse_args(argv)
    if a.cmd == "generate":
        return _generate(a)

    os.environ["INFRALOOP_MODE"] = "ai" if a.ai else "offline"
    from ingest import resolve_repo_path
    from scanner.scan import scan_repo
    from nodes.gap_identifier import identify_gaps
    from nodes.architecture_reasoner import reason_about_architecture

    answers = {}
    if a.answers:
        with open(a.answers, encoding="utf-8") as f:
            answers = json.load(f)
        if not isinstance(answers, dict):
            print("answers file must be a JSON object", file=sys.stderr)
            return 1
    path, temp = resolve_repo_path(a.target)
    import contextlib
    try:
        with contextlib.redirect_stdout(sys.stderr):          # progress lines go to stderr so stdout is only the report
            scan = scan_repo(path)
            gaps = identify_gaps(scan)
            report = reason_about_architecture(scan, answers, gaps)
    finally:
        if temp:
            shutil.rmtree(path, ignore_errors=True)
    high = [g for g in gaps if str(g.get("severity", "")).lower() in ("high", "critical")]
    out = report if a.format == "md" else json.dumps({"tool": "InfraLoop", "target": a.target, "repo_kind": scan.get("repo_kind"),
                                                      "gaps": gaps, "report": report}, indent=2, ensure_ascii=False)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(out + "\n")
        print(f"wrote {a.out} ({len(gaps)} gap(s), {len(high)} high/critical)", file=sys.stderr)
    else:
        print(out)
    return 2 if (a.fail_on_high and high) else 0


def _generate(a):
    import contextlib
    from ingest import resolve_repo_path
    from scanner.scan import scan_repo
    from nodes.gap_identifier import identify_gaps
    import generators
    path, temp = resolve_repo_path(a.target)
    try:
        with contextlib.redirect_stdout(sys.stderr):
            scan = scan_repo(path)
            gaps = identify_gaps(scan)
    finally:
        if temp:
            shutil.rmtree(path, ignore_errors=True)
    chosen = generators.find_target(generators.build_targets(scan, None, gaps), a.run_on)
    if a.run_on != "not-yet" and not chosen:
        print("This project is too large for a single server of that provider (or has no service the templates cover).", file=sys.stderr)
        return 1
    bundle = generators.generate_files(scan, gaps, chosen)
    try:
        written = generators.write_to_dir(bundle, a.out)
    except FileExistsError as e:
        print(str(e), file=sys.stderr)
        return 1
    for w in written:
        print("wrote", w)
    for adv in bundle.advice:
        print(f"fix by hand (see MANIFEST.md): {adv.gap} -- {adv.title}")
    for sk in bundle.skipped:
        print(f"not generated: {sk.gap} -- {sk.reason}")
    print(f"\nRead {os.path.join(a.out, 'MANIFEST.md')} before you copy anything into your repository.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
