"""Automatic review of LLM reports against the facts block the model was given.
  python tools/review_reports.py /tmp/run3/out            (searches */reports/prod/*.md)
Flags: structure, truncation, internal-name leaks, claims about technology that is not in the facts,
counts that disagree with the scan, euro figures that are not in the price appendix / facts / answers,
contradictions with the scan. Output is a list of flags per repo; a human (me) decides which are real."""
import glob, json, os, re, sys, collections

TECH = ["Kafka", "RabbitMQ", "MongoDB", "Redis", "Elasticsearch", "Celery", "GraphQL", "gRPC", "Jenkins", "Prometheus",
        "Grafana", "Argo CD", "Helm", "Terraform", "Ansible", "Kubernetes", "Docker Compose", "GitHub Actions", "GitLab CI",
        "MySQL", "PostgreSQL", "Memcached", "Nginx", "Traefik", "Istio", "Vault", "Sentry", "Datadog", "OpenTelemetry",
        "Serverless", "Lambda", "DynamoDB", "Cassandra", "ClickHouse", "SQLite", "S3"]
LEAK = re.compile(r"scan_result|repo_kind|\blayer\s?\d|_facts|judgment_rules|gap_identifier|in_cluster_\w+|infra_signals|\bnode_\w+|"
                  r"knowledge/|system prompt|as an AI|<\w+>|\bTODO\b|\bTBD\b|lorem", re.I)
NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(?:EUR|€|euro)|(?:€|EUR)\s*(\d[\d,]*(?:\.\d+)?)", re.I)


def words(text):
    return text.lower()


def review(rep, facts, scan):
    flags = []
    body = rep.split("## Appendix")[0]
    app = rep[len(body):]
    low_facts = facts.lower().replace("k8s", "kubernetes").replace("workload", "kubernetes workload")
    if len(body) < 2500:
        flags.append(f"short body ({len(body)} chars)")
    for h in ("1.", "2.", "3.", "4.", "5."):
        if not re.search(rf"^##\s*{re.escape(h)}", body, re.M):
            flags.append(f"missing section {h}")
    if "Next steps" not in body:
        flags.append("missing Next steps")
    if not app:
        flags.append("no price appendix")
    ns = body.split("## Next steps")[-1] if "## Next steps" in body else ""
    if ns and len(re.findall(r"^\s*\d+\.", ns, re.M)) < 2:
        flags.append("next steps has fewer than 2 items")
    m = LEAK.search(body)
    if m:
        flags.append(f"internal/placeholder text: {m.group(0)!r}")
    CLAIM = re.compile(r"\b(repo|repository|scan|found|detected|uses|using|contains|ships|includes|already)\b", re.I)
    ADVICE = re.compile(r"\b(recommend|consider|add|adopt|move|migrat|should|could|would|instead|option|alternative|if you|or a|such as|e\.g\.|like|replace|choose|introduce|switch|managed|set up|setup|enable|worth|evaluate|compare)\b", re.I)
    for sent in re.split(r"(?<=[.!?|])\s+|\n", body):
        if not CLAIM.search(sent) or ADVICE.search(sent) or re.search(r"\b(no|not|without|none|neither|nor|absent|missing|n't|lacks?)\b", sent, re.I):
            continue
        for t in TECH:
            if re.search(rf"\b{re.escape(t)}\b", sent, re.I) and t.lower() not in low_facts:
                flags.append(f"tech claimed but not in facts: {t} :: {sent.strip()[:110]}")
    svc = (scan.get("services") or {}).get("count", 0)
    dk = (scan.get("dockerfiles") or {}).get("count", 0)
    for n, what in re.findall(r"\b(\d+)\s+(?:separately deployable |separate |deployable )?(services|microservices)\b", body):
        if svc and int(n) not in (svc, svc - 1, svc + 1, 0, 1, 2) and int(n) > 2 and int(n) != dk:
            flags.append(f"service count {n} vs scan {svc}")
    for n in re.findall(r"\b(\d+)\s+(?:of\s+\d+\s+)?Dockerfiles?\b", body):
        if int(n) > dk:
            flags.append(f"Dockerfile count {n} > scan {dk}")
    sig = scan.get("infra_signals") or {}
    if dk and re.search(r"no Dockerfiles? (?:at all|anywhere|in the repo)|repo (?:has|contains) no Dockerfile", body, re.I):
        flags.append("says no Dockerfile but scan has some")
    if sig.get("has_cicd") and re.search(r"\bno CI\b|no CI/CD|no continuous integration", body, re.I):
        flags.append("says no CI but scan found CI")
    if sig.get("has_tests") and re.search(r"\brepo (?:has|contains) no tests?\b|\bno tests? (?:at all|anywhere in the repo)\b", body, re.I) and not scan.get("services_without_tests"):
        flags.append("says no tests but scan found tests")
    # euro figures
    allowed = set()
    for src in (facts, app):
        for a, b in NUM.findall(src):
            allowed.add((a or b).replace(",", "").rstrip("."))
        for x in re.findall(r"\d[\d,]*\.?\d*", src):
            allowed.add(x.replace(",", "").rstrip("."))
    bad = []
    for a, b in NUM.findall(body):
        v = (a or b).replace(",", "").rstrip(".")
        if v not in allowed:
            try:
                fv = float(v)
            except ValueError:
                continue
            if not any(abs(fv - float(x)) < 0.015 for x in allowed if re.fullmatch(r"\d+(\.\d+)?", x)):
                bad.append(v)
    if bad:
        flags.append("euro figures not in facts/appendix: " + ", ".join(sorted(set(bad))[:6]))
    sev = collections.Counter(re.findall(r"\|\s*(High|Medium|Low)\s*\|", body))
    if sev.get("High", 0) > 4:
        flags.append(f"{sev['High']} High-severity gaps")
    if "Confidence" not in body and "confidence" not in body:
        flags.append("no confidence statement")
    return flags


def main():
    root = sys.argv[1]
    total = 0
    agg = collections.Counter()
    out = []
    for rp in sorted(glob.glob(os.path.join(root, "*", "reports", "prod", "*.md"))):
        d = os.path.dirname(os.path.dirname(os.path.dirname(rp)))
        n = os.path.basename(rp)[:-3]
        fj = os.path.join(d, "facts", n + ".json")
        ft = os.path.join(d, "facts", n + ".txt")
        if not os.path.exists(fj):
            continue
        j = json.load(open(fj))
        fl = review(open(rp).read(), open(ft).read(), j["scan"])
        total += 1
        for f in fl:
            agg[re.sub(r"[:\d].*", "", f)] += 1
        if fl:
            out.append((n, fl))
    for n, fl in out:
        print(n)
        for f in fl:
            print("   -", f)
    print(f"\n{total} reports reviewed, {len(out)} with flags")
    for k, v in agg.most_common():
        print(f"  {v:4} {k}")


if __name__ == "__main__":
    main()
