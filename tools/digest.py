"""One-screen digest of what the scanner knows about a repo (what the report writer will be told). Usage: digest.py REPO..."""
import os, sys, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scanner.scan import scan_repo
from nodes.gap_identifier import identify_gaps


def digest(path):
    t = time.time()
    s = scan_repo(path)
    g = identify_gaps(s)
    sv = s["services"]
    sig = {k.replace("has_", ""): v for k, v in s["infra_signals"].items() if v}
    det = s.get("infra_details") or {}
    L = []
    L.append(f"## {os.path.relpath(path, '/tmp/pc/h')}  [{s['repo_kind']}]  {time.time()-t:.0f}s  langs={list(s['languages'])[:4]}")
    L.append(f"  signals={sorted(sig)} iac={sorted(det.get('iac_tools') or [])} dockerfiles={s['dockerfiles']['count']} compose={det.get('has_docker_compose')}")
    L.append(f"  services({sv['count']}): " + ", ".join(f"{x['path']}[{(x.get('main_language') or '?')[:6]}{'+D' if x['has_dockerfile'] else ''}{'+T' if x['has_tests'] else ''}]" for x in sv['list'][:14]) + (" ..." if sv['count'] > 14 else ""))
    L.append(f"  datastores={[(d['type'], d.get('where')) for d in s['in_cluster_datastores']][:8]} managed={list(s.get('managed_services') or [])[:5]} 3rd={list(s.get('third_party_services') or [])[:6]}")
    k = s.get("kubernetes_details") or {}
    L.append(f"  k8s workloads={k.get('workloads_found')} live={k.get('liveness_probes')} ready={k.get('readiness_probes')} limits={k.get('resource_limits')} wl_res={len(s.get('workload_resources') or {})}")
    L.append(f"  obs={ {a:b for a,b in s['observability'].items() if b} } ci={ (s.get('ci_quality') or {}).get('analysed')} entrypoints={s.get('entrypoints_total')} env_vars={len(s.get('env_vars') or [])}")
    L.append("  gaps: " + ", ".join(f"{x['issue'][:28]}:{x['severity'][0]}" for x in g))
    return "\n".join(L)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        try:
            print(digest(p), flush=True)
        except Exception as e:
            print(f"## {p} CRASH {type(e).__name__}: {e}", flush=True)
