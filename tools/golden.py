"""Golden-set check: scan each repo in tools/golden_set.json and compare with hand-checked expectations.

Usage:  python3 tools/golden.py ROOT_DIR      (ROOT_DIR holds one folder per repo, named as in the spec)
Each spec entry may have:  repo_kind, must_have (gap ids), must_not (gap ids), max_high (max number of High gaps).
Exit code 1 when any expectation fails, so it can run before every release."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from scanner.scan import scan_repo            # noqa: E402
from nodes.gap_identifier import identify_gaps  # noqa: E402


def check(name, spec, root):
    path = os.path.join(root, name)
    if not os.path.isdir(path):
        return None, [f"folder missing: {path}"]
    scan = scan_repo(path)
    gaps = identify_gaps(scan)
    ids = {g["issue"] for g in gaps}
    problems = []
    if spec.get("repo_kind") and scan.get("repo_kind") != spec["repo_kind"]:
        problems.append(f"repo_kind is {scan.get('repo_kind')!r}, expected {spec['repo_kind']!r}")
    for i in spec.get("must_have", []):
        if i not in ids:
            problems.append(f"missing finding: {i}")
    for i in spec.get("must_not", []):
        if i in ids:
            problems.append(f"false finding: {i}")
    high = [g["issue"] for g in gaps if g["severity"] in ("high", "critical")]
    if "max_high" in spec and len(high) > spec["max_high"]:
        problems.append(f"{len(high)} High findings ({', '.join(high)}), expected at most {spec['max_high']}")
    return (scan.get("repo_kind"), sorted(ids)), problems


def main(root):
    spec = json.load(open(os.path.join(HERE, "golden_set.json")))
    bad = 0
    for name, exp in spec.items():
        info, problems = check(name, exp, root)
        status = "OK  " if not problems else "FAIL"
        print(f"{status} {name}" + (f"  kind={info[0]}  findings={len(info[1])}" if info else ""))
        for p in problems:
            print("       -", p)
        bad += bool(problems)
    print(f"\n{len(spec) - bad}/{len(spec)} repos match their expectations")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "."))
