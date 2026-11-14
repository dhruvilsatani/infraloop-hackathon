"""Reviewer feedback: grouping of gaps, small-project severity, 'not found in the repository' wording, small-project note, provider-neutral section 3."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodes.gap_identifier import identify_gaps, gap_group
from nodes import planner, report_cleanup, offline_report


def scan(**kw):
    s = {"repo_kind": "application",
         "infra_signals": {"has_cicd": False, "has_tests": False, "has_dockerfile": True, "has_terraform": False, "has_k8s": False,
                           "has_helm": False, "has_monitoring_manifests": False},
         "secrets_findings": [], "services": {"count": 1, "list": [{"path": ".", "has_tests": False}]}, "entrypoints_total": 1}
    s.update(kw)
    return s


def by_issue(gaps):
    return {g["issue"]: g for g in gaps}


class SmallProjectSeverity(unittest.TestCase):
    def test_small_project_ci_and_tests_are_not_high(self):
        g = by_issue(identify_gaps(scan()))
        self.assertEqual(g["no_cicd"]["severity"], "low")
        self.assertEqual(g["no_tests"]["severity"], "medium")

    def test_cloud_deployed_project_keeps_high(self):
        s = scan()
        s["infra_signals"]["has_k8s"] = True
        g = by_issue(identify_gaps(s))
        self.assertEqual(g["no_cicd"]["severity"], "high")
        self.assertEqual(g["no_tests"]["severity"], "high")

    def test_multi_service_project_keeps_high(self):
        s = scan(services={"count": 2, "list": [{"path": "a"}, {"path": "b"}]})
        self.assertEqual(by_issue(identify_gaps(s))["no_cicd"]["severity"], "high")

    def test_wording_says_not_found_in_the_repository(self):
        g = by_issue(identify_gaps(scan()))
        self.assertIn("in the repository", g["no_cicd"]["detail"])
        self.assertIn("outside the repository", g["no_cicd"]["detail"])
        self.assertNotIn("No CI/CD config found --", g["no_cicd"]["detail"])


class Groups(unittest.TestCase):
    def test_every_gap_has_a_group(self):
        s = scan(secrets_findings=[{"pattern_type": "aws_key", "file": "a.py", "location_kind": "source"}])
        gaps = identify_gaps(s)
        self.assertTrue(gaps and all(g["group"] in ("required", "recommended", "optional") for g in gaps))
        self.assertEqual(by_issue(gaps)["possible_hardcoded_secrets"]["group"], "required")
        self.assertEqual(by_issue(gaps)["no_cicd"]["group"], "recommended")
        self.assertEqual(by_issue(gaps)["no_dependency_update_bot"]["group"], "optional")

    def test_data_loss_in_cluster_is_required_but_cache_is_not(self):
        self.assertEqual(gap_group({"issue": "in_cluster_postgres_without_persistent_volume", "severity": "high"}), "required")
        self.assertEqual(gap_group({"issue": "in_cluster_redis_without_persistent_volume", "severity": "medium"}), "recommended")

    def test_nothing_recognisable_to_run(self):
        s = scan(entrypoints_total=0, dependencies={}, infra_signals=dict(scan()["infra_signals"], has_dockerfile=False))
        self.assertIn("no_run_files_found", by_issue(identify_gaps(s)))
        self.assertNotIn("no_run_files_found", by_issue(identify_gaps(scan())))

    def test_table_has_group_column_and_required_comes_first(self):
        s = scan(secrets_findings=[{"pattern_type": "aws_key", "file": "a.py", "location_kind": "source"}])
        gaps = identify_gaps(s)
        rep = "| Gap | Severity | Source | Risk |\n|---|---|---|---|\n| x | Low | y | z |\n"
        out = report_cleanup.rebuild_gap_table(rep, s, {}, planner, gaps)
        rows = [l for l in out.split("\n") if l.startswith("| ") and "---" not in l]
        self.assertIn("Group", rows[0])
        self.assertIn("Needed to run safely", rows[1])          # the secret comes first although CI etc. exist
        self.assertIn("Optional", rows[-1])


class SmallProjectNote(unittest.TestCase):
    PLAN = {"uptime": "hours"}
    TINY = {"Expected real traffic, include the unit?": "200 users per month"}
    BIG = {"Expected real traffic, include the unit?": "5 million users per month"}

    def test_note_for_tiny_load(self):
        note = planner.small_project_note(self.PLAN, self.TINY, scan())
        self.assertIn("Small project?", note)
        self.assertIn("no verified free-tier prices", note)
        self.assertIn("Hetzner", note)

    def test_no_note_for_big_load_zero_downtime_or_no_load(self):
        self.assertEqual(planner.small_project_note(self.PLAN, self.BIG, scan()), "")
        self.assertEqual(planner.small_project_note({"uptime": "zero"}, self.TINY, scan()), "")
        self.assertEqual(planner.small_project_note(self.PLAN, {}, scan()), "")
        self.assertEqual(planner.small_project_note(None, self.TINY, scan()), "")


class ProviderNeutral(unittest.TestCase):
    def test_section3_names_needs_before_platform(self):
        plan = {"chosen": {"platform": "gke_autopilot", "replicas": 1, "stateless_services": 1}, "total": 20.0, "budget": None}
        out = offline_report._section3(scan(), plan, None)
        self.assertLess(out.index("on any provider"), out.index("Platform:"))
        self.assertIn("not a requirement", out)


class SmallServerHeadline(unittest.TestCase):
    """End to end (offline report): a tiny load that needs no zero downtime is recommended the cheapest single server."""
    def _report(self, answers):
        import shutil, tempfile
        from scanner.scan import scan_repo
        from nodes import architecture_reasoner as ar
        d = tempfile.mkdtemp()
        try:
            open(os.path.join(d, "app.py"), "w").write("print('hi')\n")
            open(os.path.join(d, "requirements.txt"), "w").write("flask==3.0.0\n")
            open(os.path.join(d, "Dockerfile"), "w").write("FROM python:3.12-slim\nCOPY . .\nUSER 1000\nCMD [\"python\",\"app.py\"]\n")
            old = os.environ.get("INFRALOOP_MODE")
            os.environ["INFRALOOP_MODE"] = "offline"
            try:
                s = scan_repo(d)
                return ar.reason_about_architecture(s, answers, identify_gaps(s))
            finally:
                if old is None: os.environ.pop("INFRALOOP_MODE", None)
                else: os.environ["INFRALOOP_MODE"] = old
        finally:
            shutil.rmtree(d, ignore_errors=True)

    LOAD = "Expected real traffic, include the unit?"

    def test_tiny_load_gets_the_server_as_headline(self):
        r = self._report({self.LOAD: "200 users per month", "Monthly budget in EUR?": "20", "How much downtime is acceptable?": "a few hours"})
        self.assertIn("Recommended for your small load", r)
        self.assertIn("6.49", r)
        self.assertIn("under budget", r)

    def test_zero_downtime_never_gets_the_single_server_headline(self):
        r = self._report({self.LOAD: "200 users per month", "Monthly budget in EUR?": "200", "How much downtime is acceptable?": "none"})
        self.assertNotIn("Recommended for your small load", r)

    def test_big_load_never_gets_the_single_server_headline(self):
        r = self._report({self.LOAD: "5 million users per month", "Monthly budget in EUR?": "2000", "How much downtime is acceptable?": "a few hours"})
        self.assertNotIn("Recommended for your small load", r)

    def test_budget_below_the_server_price_keeps_the_old_behaviour(self):
        r = self._report({self.LOAD: "200 users per month", "Monthly budget in EUR?": "3", "How much downtime is acceptable?": "a few hours"})
        self.assertNotIn("Recommended for your small load", r)


if __name__ == "__main__":
    unittest.main()
