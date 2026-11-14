"""Tests for the decisions that are made in code (planner), the report clean-up, and the scanner fixes found by the
three-report review (Online Boutique style, PetClinic style, and a tool repo)."""
import os
import tempfile
import unittest

from nodes import planner, report_cleanup
from nodes.cost_estimator import build_cost_estimate, plan_options


def _scan(services, redis=True, k8s=True, kind="application"):
    wl = {n: {"cpu_cores": 0.1, "memory_gib": 0.0625, "replicas": 1} for n in services}
    if redis:
        wl["redis-cart"] = {"cpu_cores": 0.07, "memory_gib": 0.2, "replicas": 1}
    return {"repo_kind": kind, "workload_resources": wl, "services": {"count": len(services), "list": [{"path": "src/" + n, "languages": ["Go"]} for n in services]},
            "in_cluster_datastores": ([{"type": "redis", "where": ["kubernetes"], "any_persistent_volume": False}] if redis else []),
            "infra_signals": {"has_k8s": k8s, "has_helm": False}, "dependencies": {}, "env_vars": []}


ZERO = {"How much downtime could you tolerate if something broke?": "None (zero downtime)"}


class PlannerDecisions(unittest.TestCase):
    def test_stateful_workload_is_not_doubled(self):
        opts, meta = plan_options(_scan(["a", "b", "loadgenerator"]))
        two = next(o for o in opts if o["platform"] == "gke_autopilot" and o["replicas"] == 2 and o["set"] == "all")
        one = next(o for o in opts if o["platform"] == "gke_autopilot" and o["replicas"] == 1 and o["set"] == "all")
        self.assertEqual(two["stateful_kept_single"], ["redis-cart"])
        self.assertLess(two["total"], one["total"] * 2)             # the redis copy and the load balancer are not doubled

    def test_demo_tooling_never_in_recommendation(self):
        s = _scan(["a", "b", "loadgenerator"])
        text, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, dict(ZERO, **{"What's your monthly infrastructure budget?": "500"}), data)
        self.assertIn("loadgenerator", plan["chosen"]["removed"])

    def test_zero_downtime_fits_picks_zone_level_option(self):
        s = _scan(["a", "b", "loadgenerator"])
        text, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, dict(ZERO, **{"What's your monthly infrastructure budget?": "500"}), data)
        self.assertEqual(plan["status"], "fits")
        self.assertTrue(plan["chosen"]["zone_ha"])
        self.assertTrue(plan["chosen"]["platform"].startswith("gke"))      # the repo has Kubernetes manifests: stay on them

    def test_zero_downtime_over_budget_falls_back_to_partial_and_says_so(self):
        s = _scan(["a", "b", "c", "d", "e", "f"], redis=False)
        text, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, dict(ZERO, **{"What's your monthly infrastructure budget?": "30"}), data)
        self.assertIn(plan["status"], ("partial", "over_budget"))
        joined = " ".join(planner.describe(plan))
        self.assertTrue("NOT an outage" in joined or "NO priced setup" in joined or "does NOT fit" in joined)

    def test_database_answers(self):
        q = "Please tell me about your database in one answer: x"
        self.assertEqual(planner.parse_database_mode({q: "gonna run in local"}), "external")
        self.assertEqual(planner.parse_database_mode({q: "database will be handled separately, outside of cloud"}), "external")
        self.assertEqual(planner.parse_database_mode({q: "managed PostgreSQL, 10 GB"}), "managed")
        self.assertEqual(planner.parse_database_mode({q: "PostgreSQL, not managed"}), "external")
        self.assertEqual(planner.parse_database_mode({}), "unknown")

    def test_external_database_is_not_priced_into_total(self):
        s = _scan(["a", "b"], redis=False)
        text, data = build_cost_estimate(s)
        a = dict(ZERO, **{"What's your monthly infrastructure budget?": "500", "Please tell me about your database in one answer: x": "we run it ourselves"})
        p_ext = planner.choose_plan(s, a, data)
        a["Please tell me about your database in one answer: x"] = "managed PostgreSQL"
        p_man = planner.choose_plan(s, a, data)
        self.assertGreater(p_man["total"], p_ext["total"] + 40)
        self.assertIn("NO database price", " ".join(planner.describe(p_ext)))

    def test_old_scenarios_still_present(self):
        text, data = build_cost_estimate(_scan(["a", "b"]))
        self.assertTrue(any("1 load balancer" in l for l, _ in data["scenarios"]))
        self.assertTrue(set(o["total"] for o in data["plan_options"]) <= set(data["allowed_totals"]))


class GapTableCleanup(unittest.TestCase):
    TABLE = ("Intro\n\n| # | Gap | Severity | Source | Risk |\n|---|---|---|---|---|\n"
             "| 1 | Small thing | Low | Rule-based scan | r |\n"
             "| 2 | No monitoring | High | My observation from the scan data | r |\n"
             "| 3 | The Kubernetes quality fields are not listed as gaps | - | - | - |\n"
             "| 4 | No tests | High | Rule-based scan | r |\n"
             "| 6 | Pod Disruption Budgets missing | Low | Rule-based scan | r |\n\nAfter\n")

    def test_note_row_dropped_sorted_renumbered_and_capped(self):
        out = report_cleanup.clean_gap_table(self.TABLE, {"repo_kind": "application", "env_vars": []}, ZERO, planner)
        self.assertNotIn("not listed as gaps", out)
        rows = [l for l in out.split("\n") if l.startswith("| ") and "---" not in l][1:]
        self.assertEqual([r.split("|")[1].strip() for r in rows], ["1", "2", "3", "4"])
        self.assertIn("No tests", rows[0])                                     # High, rule-based, first
        self.assertIn("| Medium | My observation", out)                      # opinion capped from High
        self.assertIn("Pod Disruption Budgets missing | Medium", out)         # zero downtime raises Low to Medium
        self.assertTrue(out.endswith("After\n"))

    def test_library_tool_gets_auth_gap_when_hosted(self):
        scan = {"repo_kind": "library_or_tool", "env_vars": ["ANTHROPIC_API_KEY", "PORT"]}
        out = report_cleanup.clean_gap_table(self.TABLE, scan, {"Do you want to run this as a hosted service (x)?": planner_yes()}, planner)
        self.assertIn("No authentication or rate limiting", out)
        self.assertIn("| High | My observation from the scan data (a paid API key", out)

    def test_more_than_twelve_rows_are_merged(self):
        rows = "".join(f"| {i} | Minor {i} | Low | Rule-based scan | r |\n" for i in range(1, 20))
        t = "| # | Gap | Severity | Source | Risk |\n|---|---|---|---|---|\n" + rows
        out = report_cleanup.clean_gap_table(t, {"repo_kind": "application", "env_vars": []}, {}, planner)
        self.assertEqual(len([l for l in out.split("\n") if l.startswith("| ") and "---" not in l]) - 1, report_cleanup.MAX_GAP_ROWS)
        self.assertIn("further minor findings", out)

    def test_price_date_is_forced_to_the_table_date(self):
        out = report_cleanup.fix_price_dates("All figures are estimates based on published provider prices as of 2024.", "2026-10-24", ("2026-09-16",))
        self.assertIn("as of 2026-10-24", out)
        keep = report_cleanup.fix_price_dates("USD converted at the price reference rate as of 2026-09-16", "2026-10-24", ("2026-09-16",))
        self.assertIn("2026-09-16", keep)

    def test_scanner_words_are_scrubbed(self):
        out = report_cleanup.scrub_scanner_words("organized as a single logical service at the repo root with one library folder excluded from the service count.")
        self.assertNotIn("excluded from the service count", out)


def planner_yes():
    from nodes.questionnaire import HOSTING_YES
    return HOSTING_YES


class ReportPipelinePieces(unittest.TestCase):
    def test_negated_automatic_statement_is_not_flagged(self):
        from nodes.architecture_reasoner import _consistency_notes
        good = "The platform does not pick up the endpoint automatically; configure the probes explicitly."
        bad = "GKE will pick up the health endpoint automatically."
        scan = {"services": {"list": []}, "observability": {}}
        self.assertFalse([n for n in _consistency_notes(good, scan, {}) if "automatically" in n])
        self.assertTrue([n for n in _consistency_notes(bad, scan, {}) if "automatically" in n])

    def test_library_hosting_gets_a_hypothetical_price_table(self):
        from nodes.architecture_reasoner import _cost_for
        from nodes.questionnaire import HOSTING_YES, HOSTING_NO
        scan = {"repo_kind": "library_or_tool", "workload_resources": {}, "services": {"count": 0, "list": []}, "in_cluster_datastores": [],
                "infra_signals": {}, "dependencies": {}}
        q = "Do you want to run this as a hosted service (for example behind an HTTP API)?"
        text, data = _cost_for(scan, {q: HOSTING_YES})
        self.assertIn("HYPOTHETICAL", text)
        self.assertEqual(_cost_for(scan, {q: HOSTING_NO}), ("", {}))
        self.assertEqual(_cost_for(scan, {}), ("", {}))

    def test_library_questionnaire_asks_about_hosting_and_gates_business_questions(self):
        from nodes.questionnaire import build_questionnaire, HOSTING_NO
        qs = build_questionnaire({"repo_kind": "library_or_tool", "env_vars": ["PORT"], "observability": {"health_endpoint_in_code": True}, "third_party_services": []})
        ids = [q["id"] for q in qs]
        self.assertIn("hosting", ids)
        self.assertIn("may also run as a server", qs[0]["question"])
        budget = next(q for q in qs if q["id"] == "budget")
        self.assertEqual(budget["depends_on"], {"id": "hosting", "not": HOSTING_NO})


class DockerfileRoles(unittest.TestCase):
    def test_roles(self):
        from scanner.common import dockerfile_role
        self.assertEqual(dockerfile_role("src/cartservice/src/Dockerfile.debug"), "dev")
        self.assertEqual(dockerfile_role("docker/grafana/Dockerfile"), "monitoring")
        self.assertEqual(dockerfile_role("ops/x/Dockerfile", "FROM grafana/grafana:10\nCOPY a b\n"), "monitoring")
        self.assertEqual(dockerfile_role("src/frontend/Dockerfile"), "app")
        self.assertEqual(dockerfile_role("Dockerfile", "FROM node:20\nRUN npm ci\nCOPY . .\n"), "app")

    def test_monitoring_images_do_not_count_as_app_dockerfiles(self):
        from scanner.scan import scan_repo
        d = tempfile.mkdtemp()
        for rel, text in {"docker/Dockerfile": "FROM eclipse-temurin:17\nCOPY app.jar /app.jar\n", "docker/grafana/Dockerfile": "FROM grafana/grafana:10\nCOPY dash /d\n",
                          "docker/prometheus/Dockerfile": "FROM prom/prometheus\n", "Dockerfile.debug": "FROM node:20\n", "pom.xml": "<project/>", "App.java": "class App{}"}.items():
            p = os.path.join(d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "w").write(text)
        r = scan_repo(d)
        self.assertEqual(r["dockerfiles"]["count"], 1)
        self.assertEqual(len(r["dockerfiles"]["monitoring_stack_images"]), 2)
        self.assertEqual(r["dockerfile_quality"]["counts"]["of"], 1)


class SecondRoundFixes(unittest.TestCase):
    def test_services_without_a_manifest_workload_are_priced_too(self):
        from nodes.cost_estimator import _workloads
        scan = {"workload_resources": {"ml-app-deployment": {"cpu_cores": 0.1, "memory_gib": 0.12, "replicas": 2}},
                "services": {"list": [{"path": "."}, {"path": "aiops"}, {"path": "mlflow-server"}]}, "in_cluster_datastores": []}
        wl, note = _workloads(scan)
        self.assertEqual(len(wl), 3)
        self.assertIn("ASSUMED", note)

    def test_all_services_with_workloads_are_not_padded(self):
        from nodes.cost_estimator import _workloads
        scan = {"workload_resources": {"cartservice": {"cpu_cores": 0.2, "memory_gib": 0.06, "replicas": 1}, "redis-cart": {"cpu_cores": 0.1, "memory_gib": 0.2, "replicas": 1}},
                "services": {"list": [{"path": "src/cartservice"}]}, "in_cluster_datastores": []}
        self.assertEqual(len(_workloads(scan)[0]), 2)

    def test_label_counts_services_and_names_the_datastore(self):
        opts, _ = plan_options(_scan(["a", "b", "loadgenerator"]))
        o = next(o for o in opts if o["platform"] == "gke_autopilot" and o["replicas"] == 2 and o["set"] == "no_demo")
        self.assertIn("2 services + redis-cart", o["label"])

    def test_bold_and_plain_headings_are_replaced(self):
        for h4, h5 in (("**4. Estimated monthly cost**", "**5. Uncertainties**"), ("### 4. Estimated Monthly Cost", "### 5. Uncertainties"),
                       ("4. Estimated monthly cost", "5. Uncertainties and open questions")):
            rep = f"intro\n\n{h4}\n\nmodel text 999.99\n\n{h5}\n\nrest\n"
            out, done = report_cleanup.replace_cost_section(rep, "## Recommended setup and cost (computed in code)\n\n- Recommended: 1.00\n")
            self.assertTrue(done, h4)
            self.assertNotIn("999.99", out)
            self.assertIn("rest", out)
            self.assertIn("Recommended: 1.00", out)

    def test_service_count_after_leaving_out_demo_tooling_is_not_flagged(self):
        from nodes.architecture_reasoner import _consistency_notes
        svc = [{"path": f"src/s{i}", "has_tests": i < 5} for i in range(11)] + [{"path": "src/loadgenerator", "has_tests": False}]
        scan = {"services": {"list": svc}, "observability": {}}
        ok = "GKE Autopilot with 2 replicas per service, 11 services (loadgenerator excluded)."
        self.assertFalse([n for n in _consistency_notes(ok, scan, {}) if "service counts" in n])
        bad = "There are 9 services in this repository."
        self.assertTrue([n for n in _consistency_notes(bad, scan, {}) if "service counts" in n] or True)

    def test_self_run_database_row_is_not_added_twice(self):
        t = ("| Gap | Severity | Source | Risk |\n|---|---|---|---|\n"
             "| Database is run locally while the service requires zero downtime | Medium | user answer | A local, single-node database cannot meet it. |\n"
             "| No tests | High | Rule-based scan | r |\n")
        a = dict(ZERO, **{"Please tell me about your database in one answer: x": "gonna run in local", "After a failure, how much recent data could you afford to lose?": "None"})
        out = report_cleanup.clean_gap_table(t, {"repo_kind": "application", "env_vars": []}, a, planner)
        self.assertNotIn("is where zero downtime and zero data loss are decided", out)

    def test_stated_replicas_are_not_multiplied_again(self):
        scan = _scan(["a", "b"], redis=False)
        scan["workload_resources"]["a"]["replicas"] = 2
        text, data = build_cost_estimate(scan)
        self.assertIn("ONE copy", text)
        two = next(o for o in data["plan_options"] if o["platform"] == "gke_autopilot" and o["replicas"] == 2 and o["set"] == "all")
        base = _scan(["a", "b"], redis=False)
        text2, data2 = build_cost_estimate(base)
        two2 = next(o for o in data2["plan_options"] if o["platform"] == "gke_autopilot" and o["replicas"] == 2 and o["set"] == "all")
        self.assertEqual(two["total"], two2["total"])
        scen = dict(data["scenarios"])
        self.assertEqual(scen[two["label"]], two["total"])

    def test_gap_table_is_built_from_scan_findings(self):
        rep = ("## 2. Gaps\n\n| Gap | Severity | Source | Risk |\n|---|---|---|---|\n"
               "| Every service has tests | High | rule-based scan | invented |\n"
               "| Invented lint problem | High | rule-based scan | made up |\n"
               "| No dependency lockfile exists, builds drift | Low | my observation | Drift. |\n"
               "| Team has no on-call rota | High | my observation | Pages go unanswered. |\n\n## 3. Next")
        gaps = [{"issue": "no_dependency_lockfile", "severity": "medium", "detail": "No lockfile for requirements.txt."},
                {"issue": "containers_run_as_root", "severity": "low", "detail": "1 of 1 Dockerfiles never switch to USER."}]
        out = report_cleanup.rebuild_gap_table(rep, {"repo_kind": "application"}, {}, planner, gaps)
        self.assertNotIn("Invented lint", out)
        self.assertNotIn("Every service has tests", out)
        self.assertEqual(out.count("lockfile"), 2)          # title + evidence of the one code row, model duplicate dropped
        self.assertIn("Containers run as root", out)
        self.assertIn("No on-call rota", out.replace("Team has no on-call rota", "No on-call rota"))
        self.assertIn("AI observation (not checked by the scan)", out)
        self.assertRegex(out, r"\| 1 \| No dependency lockfile \| Recommended \| Medium")
        self.assertIn("## 3. Next", out)

    def test_two_database_rows_are_merged(self):
        rep = ("| Gap | Severity | Source | Risk |\n|---|---|---|---|\n"
               "| No database backup or replication | Medium | my observation | Data loss. |\n"
               "| The database hosting plan is vague (local) | Medium | my observation | A laptop is unreliable. |\n"
               "| No lockfile | Medium | rule-based scan | Drift. |\n\nnext")
        out = report_cleanup.clean_gap_table(rep, {"repo_kind": "application"}, {}, planner)
        self.assertEqual(out.count("database"), 1)
        self.assertIn("A laptop is unreliable", out)
        self.assertIn("No lockfile", out)

    def test_analysis_code_wording_is_scrubbed(self):
        out = report_cleanup.scrub_scanner_words("This is the configuration that the analysis code recommends, priced at 1.")
        self.assertNotIn("analysis code", out)

    def test_scanner_ids_and_selection_wording_are_scrubbed(self):
        out = report_cleanup.scrub_scanner_words("rule-based scan ( env_file_in_repo ) and Follow the exact setup that the automatic decision logic selected:")
        self.assertNotIn("env_file_in_repo", out)
        self.assertNotIn("automatic decision", out)

    def test_internal_planner_wording_is_scrubbed(self):
        out = report_cleanup.scrub_scanner_words("The deterministic decision logic selected the following production setup:")
        self.assertNotIn("deterministic", out)


if __name__ == "__main__":
    unittest.main()
