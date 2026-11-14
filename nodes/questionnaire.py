def _q(qid, question, kind="text", options=None, depends_on=None, optional=False):
    """Question object. 'kind' is text | choice; depends_on = {"id": ..., "not": value} shows it only when that earlier
    choice is answered with something else. The UI keys answers by the question text, so wording matters."""
    out = {"id": qid, "question": question, "kind": kind}
    if options:
        out["options"] = options
    if depends_on:
        out["depends_on"] = depends_on
    if optional:
        out["optional"] = True
    return out


NOT_LAUNCHED = "Not launched yet"
DONT_KNOW = "Don't know"


def _database_question(scan_result):
    """One fixed question, always asked for deployable apps, so the report never guesses the database."""
    stores = sorted({x.get("type") for x in (scan_result.get("in_cluster_datastores") or []) if x.get("type")})
    drivers = [str(d) for d in ((scan_result.get("dependencies") or {}).get("database_client") or [])][:6]
    found = []
    if stores:
        found.append("containers defined in the repo: " + ", ".join(stores))
    if drivers:
        found.append("database libraries in the code: " + ", ".join(drivers))
    seen = "The scan found " + "; ".join(found) + ". " if found else "The scan found no database containers or libraries. "
    return (seen + "Please tell me about your database in one answer: "
            "(1) which database(s) will you really use in production (e.g. PostgreSQL, MySQL, MongoDB, Redis, Kafka, Elasticsearch/OpenSearch, none)? "
            "(2) run it yourself on a server, or use a managed service from a cloud provider? "
            "(3) roughly how much data now and after 12 months (GB)? "
            "(4) how much data loss or restore time could you accept after a failure? "
            "(5) do you need replicas or automatic failover? "
            "Example answer: PostgreSQL, managed by a cloud provider, 20 GB now and 60 GB in 12 months, a few minutes of lost data is acceptable, no replicas.")


HOSTING_NO = "No, review it as a library/tool"
HOSTING_YES = "Yes, I want to run it as a hosted service"


def _library_questions(scan_result):
    """A library or tool: ask what the review should focus on, and whether the owner wants to host it. Only the second
    answer unlocks the business questions (budget, traffic, uptime), because otherwise they would be noise."""
    obs = scan_result.get("observability") or {}
    names = {str(v).upper() for v in (scan_result.get("env_vars") or [])}
    server_hint = bool(obs.get("health_endpoint_in_code")) or "PORT" in names
    lead = ("This repository looks like a library or tool rather than a deployable application"
            + (", but it has a health endpoint or a PORT setting, so it may also run as a server" if server_hint else "") + ". ")
    qs = [{"id": "focus", "kind": "text", "question": lead + "What would you like the review to focus on (for example release process, security, maintainability, how people consume it, or what it would take to deploy it)?"},
          _q("hosting", "Do you want to run this as a hosted service (for example behind an HTTP API)?", "choice", [HOSTING_NO, HOSTING_YES])]
    dep = {"id": "hosting", "not": HOSTING_NO}           # hidden until a choice is made, and again if the answer is "No"

    def when_hosted(qid, question, kind="text", options=None, optional=False):
        return _q(qid, question, kind, options, depends_on=dep, optional=optional)
    qs.append(when_hosted("traffic_start", "How much traffic do you expect? Please include the unit, e.g. '2,000 monthly active users', '50,000 requests per day'. \"Don't know\" is fine.", optional=True))
    qs.append(when_hosted("budget", "What's your monthly infrastructure budget?"))
    qs.append(when_hosted("uptime", "How much downtime could you tolerate if something broke?", "choice",
                          ["None (zero downtime)", "A few minutes", "An hour or more is fine", DONT_KNOW]))
    qs.append(when_hosted("region", "Where are most of your users located, and are there any data-residency or compliance requirements (e.g. GDPR)?", optional=True))
    llm_api = any(x for x in scan_result.get("third_party_services", []) if any(k in x for k in ("OpenAI", "Anthropic", "LangChain", "Gemini")))
    if llm_api:
        qs.append(when_hosted("ai_usage", "This calls an AI/LLM API -- roughly how many AI calls do you expect per user per month, and are they short exchanges or long documents?", optional=True))
    return qs


def build_questionnaire(scan_result):
    """Builds the adaptive, batched question set -- only asks what the scan
    genuinely couldn't determine from the repo itself. Still rule-based: which
    questions apply is decided by scan_result flags, not by LLM judgment."""
    questions = []
    kind = scan_result.get("repo_kind", "application")
    if kind == "library_or_tool":
        return _library_questions(scan_result)
    if kind in ("example_collection", "project_template", "no_application_code"):
        # nothing is deployed from this repo, so traffic / budget / uptime questions would be noise
        return [{"id": "focus", "question": "This repository looks like a %s rather than a deployable application. What would you like the review to focus on (for example release process, security, maintainability, or how people consume it)?" % kind.replace("_", " ")}]
    if kind == "infrastructure_only":
        return [
            {"id": "environments", "question": "This repo contains infrastructure code only. Which environments does it manage (dev / staging / production) and which cloud or cluster does it target?"},
            {"id": "deployment_status", "question": "Is this infrastructure already applied somewhere, or is it for a new deployment you haven't launched yet?"},
            {"id": "budget", "question": "What's your monthly infrastructure budget?"},
        ]

    # always ask -- these are business facts no amount of code reading can reveal
    questions.append(_q("deployed", "Is this already running somewhere, or not launched yet?", "choice",
                        [NOT_LAUNCHED, "Running in staging only", "Running in production"]))
    dep = {"id": "deployed", "not": NOT_LAUNCHED}
    questions.append(_q("where_running", "Where does it run today (cloud or provider, region, and how it is deployed)?", depends_on=dep))
    questions.append(_q("current_cost", "Roughly what does it cost per month today? (A rough number is fine.)", depends_on=dep))
    questions.append(_q("real_traffic", "What does your real traffic look like today, including the busiest hour? (Numbers from your monitoring are best.)", depends_on=dep))
    questions.append(_q("existing_infra_notes", "Anything else about the existing setup we should know? (What hurts today: outages, slow pages, high bills; what you tried.)", depends_on=dep, optional=True))
    questions.append(_q("traffic_start", "How much traffic do you have, or expect at launch? Please include the unit, e.g. '2,000 monthly active users', '50,000 requests per day' or '1 million requests per month'. \"Don't know\" is fine.", optional=True))
    questions.append(_q("growth", "Expected growth per month?", "choice",
                        ["Flat (0% per month)", "Slow (about 5% per month)", "Steady (about 10% per month)", "Fast (about 25% per month)", DONT_KNOW]))
    questions.append(_q("peak", "How much busier is your busiest hour than an average hour?", "choice",
                        ["About the same (1-2x)", "Busy hours (3-5x)", "Spiky (10x or more)", DONT_KNOW]))
    questions.append(_q("spikes", "Any big launch or campaign planned in the next 12 months, and how big? (Leave empty if none.)", optional=True))
    questions.append(_q("budget", "What's your monthly infrastructure budget?"))
    questions.append(_q("database", _database_question(scan_result)))
    questions.append(_q("uptime", "How much downtime could you tolerate if something broke?", "choice",
                        ["None (zero downtime)", "A few minutes", "An hour or more is fine", DONT_KNOW]))
    questions.append(_q("data_loss", "After a failure, how much recent data could you afford to lose?", "choice",
                        ["None", "A few minutes of data", "Up to an hour", "Up to a day (daily backup is enough)", DONT_KNOW]))
    questions.append(_q("team", "Who will run this day to day?", "choice",
                        ["Just me", "A small team (2-5 people)", "A dedicated ops team", DONT_KNOW]))
    questions.append(_q("region", "Where are most of your users located, and are there any data-residency or compliance requirements (e.g. GDPR)?"))

    # conditional -- only asked when the scan found a reason to ask
    if scan_result["gpu_signals"]["gpu_likely"]:
        questions.append({"id": "model_usage", "question": "What model(s) are you running, and roughly how many requests per day do you expect?"})

    if "payments" in scan_result["dependencies"]:
        questions.append({"id": "payment_compliance", "question": "Are you handling card data directly, or only through your payment provider's hosted checkout?"})

    services = (scan_result.get("services") or {})
    deployable = services.get("count") or 0
    if deployable > 1:
        questions.append({"id": "which_service", "kind": "text", "question": f"This looks like it has {deployable} separately deployable services -- analyze all of them, or focus on one?"})
    elif not services and scan_result["monorepo"]["is_monorepo"]:
        count = len(scan_result["monorepo"]["manifest_locations"])
        questions.append({"id": "which_service", "question": f"This looks like it has {count} separate services -- analyze all of them, or focus on one?"})

    details = scan_result.get("infra_details") or {}
    managed_db = [m for m in (scan_result.get("managed_services") or []) if m.get("category") in ("database", "cache")]
    if managed_db:
        names = ", ".join(m["name"] for m in managed_db)
        questions.append({"id": "managed_backend", "question": f"The app uses {names} as hosted data service(s). Which plan/tier are you on, and do you rely on its built-in backups and scaling?"})
    if details.get("paas_config"):
        questions.append({"id": "paas", "question": "This repo is configured for %s. Do you plan to stay on that platform, or move to your own cloud account?" % " / ".join(details["paas_config"])})
    ml = scan_result.get("ml_artifacts") or {}
    if ml.get("present") and not scan_result["gpu_signals"]["gpu_likely"]:
        questions.append({"id": "ml_serving", "question": "Model files or ML pipeline markers were found. Will you serve predictions online (needs a running service), run batch jobs, or only experiment locally?"})

    if not scan_result["infra_signals"]["has_cicd"]:
        questions.append({"id": "deploy_frequency", "question": "How often do you expect to deploy changes once this is live -- daily, weekly, rarely?"})

    llm_api = any(x for x in scan_result.get("third_party_services", [])
                  if any(k in x for k in ("OpenAI", "Anthropic", "LangChain", "Gemini"))) or \
        any(d in ("openai", "anthropic", "langchain", "langgraph", "llama-index", "@anthropic-ai/sdk")
            for d in scan_result["dependencies"].get("ai_ml", []))
    if llm_api and not scan_result["gpu_signals"]["gpu_likely"]:
        questions.append({
            "id": "ai_usage",
            "question": "This looks like it calls an AI/LLM API rather than running a model locally -- roughly how many AI calls do you expect per user per month, and are those calls usually short exchanges or long documents/reports?",
        })    

    return questions


if __name__ == "__main__":
    fake_scan = {
        "gpu_signals": {"gpu_likely": True, "frameworks_found": ["torch"]},
        "dependencies": {"payments": ["stripe"]},
        "monorepo": {"is_monorepo": False, "manifest_locations": ["."]},
        "infra_signals": {"has_cicd": False},
    }
    for q in build_questionnaire(fake_scan):
        print("-", q["question"])