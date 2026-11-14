# Infra Designer — Architecture

## What this is
A tool that scans a GitHub repo, understands what it is and what's missing for production, asks a few adaptive business questions, and produces one detailed written report: architecture summary, infra inventory, production-readiness scorecard, a cost estimate grounded in real cloud pricing, a cloud/service recommendation, what's right/wrong, and what the customer should have — written like one real expert would, not a shallow checklist.

## Scope boundary (firm, current phase)
Report/design only. No cloud account connection, no code generation, no automated deploy, no GitHub PR automation, no load testing.

Phase 2 (later, only after the report is proven accurate on real repos): generate the actual Terraform/Docker/CI/k8s files matching the approved design — strictly for a human to review and apply themselves. Never automated, never given write access to a client's cloud.

## Two journeys, one engine
1. **New / vibe-coded project** — analysis + questionnaire + cost estimate + cloud/service comparison (e.g. managed K8s vs self-host vs serverless)
2. **Existing production system wanting to scale or switch cloud** — same engine, different inputs (detects what's already running instead of what's missing), includes a deployment-strategy recommendation (blue-green/canary/rolling/feature flags) based on actual constraints (downtime tolerance, rollback needs, stateful services, release frequency)

## Design principles
- Rule-based vs LLM judgment vs RAG: use the simplest correct tool for each decision
- Validate before shipping: every generated artifact gets checked before a human sees it as "ready"
- Human always reviews and approves: the agent proposes, never applies
- See the real gap before fixing it: build the plain version, observe what's actually wrong on real repos, then add complexity to fix that specific gap
- Secrets never reach the LLM: deny-by-default allowlist (manifest files, README, structured scan output only); env vars as names, never values; flagged-secret files excluded entirely

## Project structure
```
platform-engineer/
├── state.py                        # shared state schema for the LangGraph pipeline
├── graph.py                        # orchestrator — wires all nodes together
├── ingest.py                        # resolves a GitHub URL or local path to a scannable folder
├── db.py                           # structured project memory — SQLite read/write helpers
├── requirements.txt
├── LEARNED.md
├── ARCHITECTURE.md
│
├── scanner/                         # deterministic fact layer — no LLM involved
│   ├── scan.py                     # orchestrator — runs layers 1-4, merges into one scan_result dict
│   ├── layer1_signals.py           # Dockerfile, CI config, tests/, .tf, k8s yaml, Helm Chart.yaml
│   ├── layer2_dependencies.py      # manifest parsing + lookup-table classification
│   ├── layer3_structure.py         # folder/file naming convention component map
│   ├── layer4_deep.py              # entrypoints, env var names, third-party services, monorepo, secrets, GPU signals
│   └── rules/
│       ├── dependency_map.py       # package name → category lookup table
│       ├── gpu_signals.py          # ML framework + GPU requirement rules
│       └── secret_patterns.py      # regex patterns for likely hardcoded secrets
│
├── nodes/                           # the LangGraph pipeline
│   ├── gap_identifier.py           # scan_result → ranked production-readiness gaps (rule-based)
│   ├── questionnaire.py            # adaptive, batched question set from what the scan couldn't determine
│   ├── architecture_reasoner.py    # the one LLM node — scan_result + answers + judgment file → recommendation
│   └── report_writer.py            # final written report
│
├── knowledge/
│   └── judgment_rules.md           # hand-curated reference doc (distilled book principles + lessons from real test repos) — read in full every reasoner call, no retrieval
│
├── web/                             # local FastAPI UI ("InfraLoop") — thin HTTP front door onto the same graph.py pipeline
│   ├── api.py                      # /scan and /answer endpoints, invoking build_scan_graph()/build_report_graph()
│   └── static/
│       └── index.html              # single-page UI — scan, answer questions, view rendered report
│
└── tests/                           # one test file per node, same pattern as cost-agent
```

## Pipeline flow

```
GitHub repo
     |
     v
scanner (layers 1-4, fully deterministic)
     |
     v
gap_identifier (rule-based ranking of findings)
     |
     v
questionnaire (adaptive, batched — only asks what code can't answer)
     |
     v
architecture_reasoner (the one LLM step — grounded on structured facts + judgment_rules.md,
                        one fallback search tool for ambiguous cases, never sees raw source or secrets)
     |
     v
report_writer (one cohesive narrative report)
     |
     v
[ human reviews the report — nothing is deployed or changed automatically ]
```

`db.py` (SQLite) sits alongside every step, persisting scan results, questionnaire answers, the final report, and any decisions/accepted risks per project.

## Business model (for context, not engineering)
Free/low-cost scan report = "front desk" lead-gen, showing a prospect their own app's real mistakes instead of a generic pitch → client hires Dhruvil directly as a freelancer to implement → once demand exceeds solo capacity, hire more freelancers, with the tool keeping analysis quality consistent across them → Phase 2 code generation speeds up that implementation work → a long-term monitoring/maintenance retainer becomes a second, recurring revenue stream.

## Current status
Full pipeline proven end to end on two real repos (`cost-agent`, and an external FastAPI/K8s project) through both the CLI (`graph.py`) and a local web UI (`web/`). Found and fixed real scanner/judgment gaps along the way (test detection, entrypoint depth, K8s content blindness, missing AI-usage question, a scope-boundary leak in report output). `report_writer.py` and `db.py`-backed persistence are still unbuilt/unconfirmed — `architecture_reasoner` currently produces the full written report directly, and sessions are in-memory only. Not yet tested against a repo the project owner didn't build or doesn't already know well.

## Known shortcuts in the web UI — revisit before a real deployment
This local prototype intentionally skips things a real deployment would need:
- Synchronous FastAPI routes block a whole worker thread for the full LLM call (OmniRoute response can take 1-2+ minutes) — a real version needs `async def` + an async HTTP client, or a background job queue, instead of holding one HTTP request open.
- No streaming — the report arrives as one blob after the full wait, instead of streaming token-by-token via SSE/WebSocket.
- `SESSIONS = {}` is in-memory only — lost on restart, breaks with more than one concurrent user. Needs Redis/a database once this isn't single-user-local.
- No retries/backoff around the OmniRoute call, no tracing (LangSmith is the natural fit for this LangGraph stack), no auth — all fine for a local prototype, all required before anyone else can reach this.
- OmniRoute is only reachable from this Mac's own localhost — a cloud-deployed version needs either a real hosted API key or a tunnel back to this machine.
