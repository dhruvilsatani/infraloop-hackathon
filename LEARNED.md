# What We've Learned — Infra Designer / Platform Engineer

## Already learned

### Python mechanics (from cost-agent)
- `sys.path` manipulation to import across folders
- `boto3` client pattern (service + endpoint + region)
- `datetime`/`timedelta` for time windows
- `dict.get()` with defaults to avoid KeyErrors
- `try/except` for resilient external calls
- `assert` for quick test checks
- monkeypatching to fake external calls in tests
- `python -m package.module` vs `python path/to/file.py` — the former resolves the current directory as part of the package path; the latter only adds the script's own folder to `sys.path`
- `os.path.isfile`/`isdir`, `os.walk` for filesystem scanning
- `boto3` pagination (`get_paginator`) — don't silently drop results past page 1

### LangGraph (from cost-agent)
- `StateGraph` / shared state dict
- `add_node`, `add_edge`
- parallel fan-out/fan-in — one node feeding several analysts, merging back into one aggregator

### AWS / cloud (from cost-agent)
- CloudWatch `get_metric_statistics` for CPU utilization
- EC2 rightsizing logic, unattached EBS detection
- Savings Plan discount economics
- LocalStack for free local AWS simulation

### Design principles (carried through both projects)
- Rule-based code vs LLM judgment vs RAG — use the cheapest, most deterministic tool that correctly does the job
- Validate before shipping — nothing goes out unchecked (e.g. `terraform validate`)
- Human always reviews and approves — the agent proposes, never applies
- "See the real gap before fixing it" — build the plain version first, observe where it's actually wrong, THEN add complexity to fix that specific gap

### New: separating data from logic
`dependency_map.py` is a plain dictionary — package name → category — with zero parsing logic in it. The parsing lives in `layer2_dependencies.py`. This split means the lookup table can grow forever (every time a real repo reveals an unrecognized package, you add one line) without ever touching the logic that uses it.

### New: layered scanner design
- Layer 1 — existence checks (Dockerfile, CI config, tests/, .tf, k8s yaml, Helm Chart.yaml) — done
- Layer 2 — manifest/dependency parsing via the lookup table (framework/DB/queue/AI-SDK/GPU detection) — in progress
- Layer 3 — folder/structural signals (controllers/, routes/, workers/, migrations/)
- Layer 4 — deep signals: entrypoints, env var names, third-party services, monorepo detection, secret-risk findings

### New: why RAG isn't needed yet
RAG solves "my knowledge base is too big to fit in one prompt." That's not this problem — a curated, hand-written `judgment_rules.md` (your own distilled principles from the SRE book, AWS Well-Architected Framework, Terraform book, plus real lessons from testing) fits entirely in context and gets included in every reasoning call. This is more auditable than retrieval (you always know exactly what the model saw) and avoids retrieval picking the wrong chunk. RAG only earns its place later if: the curated file genuinely outgrows context, or a case-log of past repos gets too large for exact-match filtering to find the right analogous case.

### New: SQLite over a vector store for project memory
Structured, per-project facts (scans, questionnaire answers, reports, decisions) are plain rows with exact-match lookups — a normal database, not a vector/embedding store. Vector search is for fuzzy "find something similar" queries at a scale this project isn't at yet.

### New: the secrets-safety rule
Deny-by-default: the LLM only ever sees an allowlist (manifest files, README, the scanner's structured output) — never raw source code, never a file flagged as containing a likely secret, and environment variables are passed as **names only, never values**. This has to be a hard architectural rule, not a best-effort filter, because leaking a client's secret through an LLM call would destroy the trust the whole business model depends on.

### Business / market learning
- "Vibe-coding to production" gap: AI-coding-tool users (Replit/Lovable/Cursor/bolt.new) who get a working app locally but never reach real production (no CI/CD, no monitoring, no backups, security holes)
- Diagnostic-as-lead-gen → high-touch service is a proven shape (AWS Well-Architected Review, Snyk's free-scan-then-paid-remediation) — not a new business model, a proven one applied to an underserved niche
- Productized-service-before-SaaS: use the tool yourself as a freelancer first; self-serve SaaS only makes sense after real paying engagements prove what the report should actually contain
- The free, personalized scan report beats generic outreach as a sales tool — concrete proof beats a claim of expertise
- Scaling path: solo freelancer → hire more freelancers once demand exceeds your own bandwidth → the tool becomes what keeps quality consistent across a team, not just your personal sales demo
- AI infra deployment (model serving, GPU provisioning, on-prem↔cloud migration) is a fast-growing, current, underserved niche the same engine can serve with a few added detection signals — not a separate product

## Still to learn

- `gpu_signals.py` — isolating which AI/ML packages specifically imply a GPU need (torch/tensorflow/jax) vs which just mean an API call (openai/anthropic)
- Layer 3 — folder/structural component mapping
- Layer 4 — entrypoint detection, env var inventory, third-party service detection, monorepo detection, secret-pattern scanning
- `questionnaire` node — building the adaptive, batched question set from what the scan couldn't determine
- `architecture_reasoner` node — the one LLM-powered step: reasoning from scan_result + answers + judgment_rules.md, with a single flexible fallback search tool for ambiguous cases
- `report_writer` node — turning everything into one cohesive narrative report
- `db.py` — the SQLite schema and read/write helpers for structured project memory
- `graph.py` — wiring every node into one LangGraph pipeline
- Testing methodology — validating accuracy across deliberately varied real repos (production-grade, vibe-coded, in-between, different stacks)
- Deferred until proven needed: a case-log for experience memory, RAG (only if the judgment file or case-log genuinely outgrows exact-match handling), and the SaaS shell (auth, dashboard, background jobs, audit logs) — built only after the reasoning engine is validated on real repos
