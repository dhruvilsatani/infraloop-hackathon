"""Regression tests for scanner mistakes found on real repositories (goreleaser, uptime-kuma, excalidraw, nocodb, meilisearch,
fastapi template, miniflux)."""
import unittest

from scanner.common import dockerfile_role
from scanner.layer1_signals import _is_dockerfile
from scanner.layer4_deep import _location_kind
from scanner.rules.secret_patterns import scan_text_for_secrets
from nodes.gap_identifier import _drop_non_services


class LaunchFixes(unittest.TestCase):
    def test_dockerfiles_in_test_fixture_and_ci_folders_are_not_app_images(self):
        self.assertEqual(dockerfile_role("internal/pipe/docker/testdata/Dockerfile"), "dev")
        self.assertEqual(dockerfile_role(".github/oss-scanner/Dockerfile"), "dev")
        self.assertEqual(dockerfile_role("Dockerfile"), "app")

    def test_lowercase_dockerfile_names_are_found(self):
        for name in ("dockerfile", "base.dockerfile", "Dockerfile", "Dockerfile.prod", "app.Dockerfile"):
            self.assertTrue(_is_dockerfile(name), name)
        self.assertFalse(_is_dockerfile("docker-compose.yml"))

    def test_public_search_keys_and_doc_examples_are_not_secrets(self):
        self.assertEqual(scan_text_for_secrets("algolia: {\n apiKey: 'lNKDTZdJrE76Sg8WEyeN9mXT29l1xq7Q'}"), [])
        self.assertEqual(scan_text_for_secrets('"```js\\nconst c = {apiKey: \'6436fc5237b0d6e0d64253fbaac21d135012ecf1\'}'), [])
        self.assertTrue(scan_text_for_secrets("const apiKey = 'lNKDTZdJrE76Sg8WEyeN9mXT29l1xq7Q'"))

    def test_commented_samples_and_azurite_key_are_downgraded(self):
        self.assertTrue(scan_text_for_secrets('//   "accessKeyId": "AKIA' + '3WNQJCXE2DYPAU7R"')[0]["in_comment"])
        self.assertNotIn("in_comment", scan_text_for_secrets('x = "AKIA' + '3WNQJCXE2DYPAU7R"')[0])
        self.assertEqual(scan_text_for_secrets("AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw=="), [])
        self.assertEqual(_location_kind("internal/configuration/test_resources/config.yml"), "test_or_example")

    def test_mock_and_perl_test_folders_are_test_locations(self):
        self.assertEqual(_location_kind("packages/x/mockResponses/initialize.ts"), "test_or_example")
        self.assertEqual(_location_kind("t/certs/ca.key"), "test_or_example")
        self.assertEqual(_location_kind("src/config.ts"), "source")

    def test_docs_extra_and_helper_root_are_not_services(self):
        svcs = [{"path": ".", "has_dockerfile": False, "entrypoints": ["prepare_release.py"]},
                {"path": "backend", "has_dockerfile": True, "entrypoints": ["main.py"]},
                {"path": "dev-docs", "has_dockerfile": False, "entrypoints": ["index.js"]},
                {"path": "extra/push", "has_dockerfile": True, "entrypoints": []}]
        self.assertEqual([x["path"] for x in _drop_non_services(svcs)], ["backend"])
        root_app = [{"path": ".", "has_dockerfile": False, "entrypoints": ["main.go"]}, {"path": "web", "has_dockerfile": True, "entrypoints": ["server.js"]}]
        self.assertEqual(len(_drop_non_services(root_app)), 2)


class MonorepoCosting(unittest.TestCase):
    def test_big_monorepo_prices_only_folders_with_a_dockerfile(self):
        from nodes.cost_estimator import build_cost_estimate
        svcs = [{"path": f"apps/m{i}", "languages": ["Go"], "has_dockerfile": i < 2} for i in range(12)]
        scan = {"repo_kind": "application", "workload_resources": {}, "services": {"count": 12, "list": svcs},
                "in_cluster_datastores": [], "infra_signals": {"has_k8s": False}, "dependencies": {}, "env_vars": []}
        text, data = build_cost_estimate(scan)
        self.assertEqual(data["workloads"], 2)
        self.assertIn("only the 2 folders", text)
        self.assertIn("libraries or modules", text)

    def test_kustomize_params_yaml_is_not_an_ml_marker(self):
        from scanner.layer6_runtime import ML_MARKER_FILES
        self.assertNotIn("params.yaml", ML_MARKER_FILES)


class Round3(unittest.TestCase):
    def test_gitignored_files_are_not_part_of_the_repository(self):
        import os, shutil, subprocess, tempfile
        if not shutil.which("git"):
            self.skipTest("git not installed")
        from scanner.common import GitIgnore
        from scanner.layer4_deep import detect_sensitive_files
        d = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", d])
        open(d + "/.gitignore", "w").write(".env\nkeys/\n")
        os.makedirs(d + "/keys"); os.makedirs(d + "/certs")
        open(d + "/keys/a.key", "w").write("-----BEGIN PRIVATE KEY-----\nabc\n")
        open(d + "/certs/b.key", "w").write("-----BEGIN PRIVATE KEY-----\nabc\n")
        open(d + "/.env", "w").write("X=1\n")
        g = GitIgnore(d)
        self.assertTrue(g.active)
        self.assertIn("keys/a.key", g)
        self.assertNotIn("certs/b.key", g)
        found = detect_sensitive_files(d)
        self.assertEqual([x["file"] for x in found["sensitive_file_names"]], ["certs/b.key"])
        self.assertEqual(found["env_files"], [])

    def test_autopilot_cluster_fee_is_covered_by_the_free_credit(self):
        from nodes.cost_estimator import plan_options
        scan = {"repo_kind": "application", "workload_resources": {"a": {"cpu_cores": 0.25, "memory_gib": 0.5, "replicas": 1}},
                "services": {"count": 1, "list": [{"path": "a", "languages": ["Go"]}]}, "in_cluster_datastores": [],
                "infra_signals": {"has_k8s": True}, "dependencies": {}, "env_vars": []}
        opts, meta = plan_options(scan)
        self.assertEqual(meta["fee_autopilot"], 0.0)
        self.assertGreater(meta["fee_regional"], 60)
        self.assertEqual({o["platform"] for o in opts}, {"gke_autopilot", "cloud_run"})
        two = next(o for o in opts if o["platform"] == "gke_autopilot" and o["replicas"] == 2)
        self.assertTrue(two["zone_ha"])

    def test_zero_downtime_database_uses_a_dedicated_core_instance(self):
        from nodes import planner
        from nodes.cost_estimator import build_cost_estimate
        scan = {"repo_kind": "application", "workload_resources": {"a": {"cpu_cores": 0.25, "memory_gib": 0.5, "replicas": 1}},
                "services": {"count": 1, "list": [{"path": "a", "languages": ["Go"]}]}, "in_cluster_datastores": [],
                "infra_signals": {"has_k8s": True}, "dependencies": {}, "env_vars": []}
        text, data = build_cost_estimate(scan)
        ans = {"How much downtime could you tolerate if something broke?": "None (zero downtime)",
               "What's your monthly infrastructure budget?": "500", "Please tell me about your database in one answer: x": "managed Postgres"}
        plan = planner.choose_plan(scan, ans, data)
        self.assertTrue(any("dedicated 1 vCPU" in n for n in plan["notes"]))
        self.assertGreater(plan["meta"]["sql_dedicated_ha"], plan["meta"]["sql_ha"])

    def test_ingress_class_other_than_gce_is_reported(self):
        import os, tempfile
        from scanner.scan import scan_repo
        from nodes.gap_identifier import identify_gaps
        d = tempfile.mkdtemp(); os.makedirs(d + "/k8s")
        open(d + "/k8s/app.yaml", "w").write("apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web\nspec:\n  template:\n    spec:\n      containers:\n      - name: web\n        image: web:1\n"
                                               "---\napiVersion: networking.k8s.io/v1\nkind: Ingress\nmetadata:\n  name: web\n  annotations:\n    kubernetes.io/ingress.class: \"nginx\"\nspec:\n  rules: []\n")
        open(d + "/main.py", "w").write("print(1)\n")
        issues = [g["issue"] for g in identify_gaps(scan_repo(d))]
        self.assertIn("k8s_ingress_class_not_gke", issues)


if __name__ == "__main__":
    unittest.main()


class UploadWithoutGit(unittest.TestCase):
    def test_gitignore_file_fallback_and_the_the(self):
        import tempfile
        from scanner.common import GitIgnore
        from nodes.report_cleanup import scrub_scanner_words
        d = tempfile.mkdtemp()
        with open(d + "/.gitignore", "w") as fh:
            fh.write(".env\nnode_modules/\n/build\n!keep\n")
        g = GitIgnore(d)
        self.assertIn(".env", g)
        self.assertIn("svc/.env", g)
        self.assertIn("web/node_modules/x.js", g)
        self.assertIn("build/o", g)
        self.assertNotIn("src/build/o", g)
        self.assertNotIn(".env.example", g)
        self.assertEqual(scrub_scanner_words("The the recommended setup"), "The recommended setup")


class DhParamAndInfraCi(unittest.TestCase):
    def test_dhparam_is_not_a_secret(self):
        import tempfile
        from scanner.layer4_deep import _looks_like_pem
        d = tempfile.mkdtemp()
        with open(d + "/dhparam.pem", "w") as fh:
            fh.write("-----BEGIN DH PARAMETERS-----\nabc\n")
        with open(d + "/k.pem", "w") as fh:
            fh.write("-----BEGIN RSA PRIVATE KEY-----\nabc\n")
        self.assertFalse(_looks_like_pem(d + "/dhparam.pem"))
        self.assertTrue(_looks_like_pem(d + "/k.pem"))


class MessyUploads(unittest.TestCase):
    def test_wrapper_folder_and_nested_gitignore(self):
        import tempfile, os
        from scanner.scan import scan_repo
        d = tempfile.mkdtemp()
        w = os.path.join(d, "repo-main")
        os.makedirs(os.path.join(w, "app"))
        os.makedirs(os.path.join(d, "__MACOSX"))
        with open(os.path.join(w, "README.md"), "w") as fh:
            fh.write("x")
        with open(os.path.join(w, "app", "Dockerfile"), "w") as fh:
            fh.write("FROM python:3.12\nCMD [\"python\",\"main.py\"]\n")
        with open(os.path.join(w, "app", "main.py"), "w") as fh:
            fh.write("print(1)\n")
        with open(os.path.join(w, "app", ".env"), "w") as fh:
            fh.write("A=1\n")
        with open(os.path.join(w, ".gitignore"), "w") as fh:
            fh.write(".env\n")
        s = scan_repo(d)
        self.assertEqual(s["dockerfiles"]["count"], 1)
        self.assertFalse(s["sensitive_files"].get("env_files"))

    def test_identifier_and_placeholder_keys(self):
        from scanner.rules.secret_patterns import scan_text_for_secrets as f
        self.assertEqual(f('api_key="edischarge1Today"'), [])
        self.assertEqual(f('DEFAULT_API_KEY = "sk-0000000000000000000"'), [])
        self.assertTrue(f('API_KEY = "k6QaiQmcTm2zfaNns5L1Z8duBtJmhDOW8JawlCC3"'))

    def test_lua_and_public_key(self):
        from scanner.layer6_runtime import LANGUAGE_BY_EXTENSION
        from scanner.layer4_deep import _location_kind
        self.assertEqual(LANGUAGE_BY_EXTENSION[".lua"], "Lua")
        self.assertEqual(_location_kind("backend/bdd/pebble/key.pem"), "test_or_example")


class PublicMode(unittest.TestCase):
    def test_public_mode_only_github(self):
        import os
        from ingest import resolve_repo_path
        os.environ["INFRALOOP_PUBLIC"] = "1"
        try:
            for bad in ("/etc", "~", "file:///etc", "http://example.com/a/b", "https://github.com.evil.com/a/b", "https://github.com/a", "git@github.com:a/b.git"):
                with self.assertRaises(RuntimeError, msg=bad):
                    resolve_repo_path(bad)
        finally:
            del os.environ["INFRALOOP_PUBLIC"]

    def test_access_code_and_rate_limit(self):
        import os, importlib, base64
        try:
            import fastapi, httpx  # noqa: F401
        except ImportError:
            self.skipTest("fastapi/httpx not installed here")
        os.environ["INFRALOOP_ACCESS_CODE"] = "letmein"
        os.environ["INFRALOOP_PUBLIC"] = "1"
        os.environ["INFRALOOP_SCANS_PER_HOUR"] = "2"
        try:
            from fastapi.testclient import TestClient
            import web.api as api
            importlib.reload(api)
            c = TestClient(api.app)
            self.assertEqual(c.get("/").status_code, 401)
            good = {"Authorization": "Basic " + base64.b64encode(b"x:letmein").decode()}
            bad = {"Authorization": "Basic " + base64.b64encode(b"x:nope").decode()}
            self.assertEqual(c.get("/", headers=bad).status_code, 401)
            self.assertEqual(c.get("/", headers=good).status_code, 200)
            codes = [c.post("/scan", headers=good, json={"repo_path_or_url": ""}).status_code for _ in range(3)]
            self.assertEqual(codes[:2], [400, 400])
            self.assertEqual(codes[2], 429)
        finally:
            del os.environ["INFRALOOP_ACCESS_CODE"], os.environ["INFRALOOP_SCANS_PER_HOUR"], os.environ["INFRALOOP_PUBLIC"]
            import web.api as api
            importlib.reload(api)


class GithubUrlPath(unittest.TestCase):
    def test_url_clone_path_runs(self):
        """The clone branch must work (a stray local import once broke it). git is faked, no network."""
        import ingest, subprocess
        calls = []
        real = subprocess.run
        subprocess.run = lambda *a, **k: calls.append((a, k)) or None
        try:
            path, cleanup = ingest.resolve_repo_path("https://github.com/owner/repo")
        finally:
            subprocess.run = real
        self.assertTrue(cleanup)
        self.assertEqual(calls[0][1]["env"]["GIT_TERMINAL_PROMPT"], "0")
        import shutil
        shutil.rmtree(path, ignore_errors=True)


class ReportCleanupChain(unittest.TestCase):
    def test_every_cleanup_step_exists_and_chain_runs(self):
        """Every cleanup step used by reason_about_architecture must exist (a deleted helper once broke it unnoticed)."""
        from nodes import architecture_reasoner as ar
        import re, inspect
        src = inspect.getsource(ar._assemble)
        names = set(re.findall(r"\b(_[a-z0-9_]+)\(", src)) | set(re.findall(r"\b(claim_check|report_cleanup|planner)\.", src))
        self.assertIn("_ensure_confidence_line", names)
        for name in names:
            self.assertTrue(hasattr(ar, name), f"missing step {name}")
        sample = ("1. What this project appears to be\n\nA.\n\nB.\n\n2. What's missing for production\n\n| a |\n\n"
                  "3. Recommended architecture\n\nP1.\n\nP2.\n\nP3.\n\n4. Estimated Monthly Cost (computed in code)\n\nx\n\n5. Uncertainties\n\nThe database is unknown.\n\nThe database engine is unknown too.\n")
        out = ar._normalize_section_headings(ar._strip_capacity_claims(sample))
        out = ar._tidy_section5(ar._ensure_confidence_line(ar._tidy_section1(ar._cap_section3(out)), {"entrypoints": ["x"], "dependencies": {"a": 1}}))
        self.assertIn("## 3. Recommended architecture", out)
        self.assertNotIn("P3.", out)
        self.assertIn("Confidence: high", out)
        self.assertEqual(out.count("database"), 1)


class ClaimCheck(unittest.TestCase):
    def setUp(self):
        from nodes import claim_check
        self.cc = claim_check
        self.allowed = claim_check.build_allowed("12 services. 1.67 vCPU. 135.46 EUR. 3,000 to 10,000 users. growth 5%. src/adservice 0.07 vCPU 5,360")

    def _run(self, body):
        return self.cc.verify("## 3. Recommended architecture\n\n" + body + "\n\n## 4. Estimated Monthly Cost\n\nTotal 999 EUR.\n", self.allowed)

    def test_invented_percentage_removed(self):
        out, rem = self._run("The setup costs 135.46 EUR. Traffic rises about 22% in six months.")
        self.assertIn("135.46", out)
        self.assertNotIn("22%", out)
        self.assertEqual(len(rem), 1)

    def test_numbers_from_facts_kept(self):
        out, rem = self._run("There are 12 services using 1.67 vCPU, with 5% monthly growth and 3,000 to 10,000 users.")
        self.assertEqual(rem, [])

    def test_made_up_number_and_question_removed(self):
        out, rem = self._run("Month 12 will have 29,104 users. Is the database managed? Two replicas are used.")
        self.assertNotIn("29,104", out)
        self.assertNotIn("Is the database", out)
        self.assertIn("Two replicas", out)

    def test_unit_conversion_allowed(self):
        out, rem = self._run("The cache is sized at 70 millicores.")
        self.assertEqual(rem, [])

    def test_unknown_path_removed_known_kept(self):
        out, rem = self._run("See src/adservice for details. Also check src/ghostservice/main.go now.")
        self.assertIn("src/adservice", out)
        self.assertNotIn("ghostservice", out)

    def test_code_written_section_untouched(self):
        out, rem = self._run("Fine.")
        self.assertIn("999 EUR", out)

    def test_only_option_claims_and_guesses(self):
        out, rem = self._run("This is the only setup in the table that fits. Managed Redis replaces the in-cluster one - this is the only way to meet the goal. A relational database is likely needed. Two replicas are used.")
        self.assertNotIn("only setup", out)
        self.assertNotIn("only way", out)
        self.assertIn("Managed Redis replaces the in-cluster one", out)
        self.assertNotIn("likely needed", out)
        self.assertIn("Two replicas", out)


class OfflineMode(unittest.TestCase):
    def test_offline_report_needs_no_model(self):
        import os, tempfile, subprocess
        from nodes import architecture_reasoner as ar
        d = tempfile.mkdtemp()
        open(os.path.join(d, "app.py"), "w").write("print('hi')\n")
        subprocess.run(["git", "init", "-q", d], check=False)
        from scanner.scan import scan_repo
        from nodes.gap_identifier import identify_gaps
        old = (os.environ.get("INFRALOOP_MODE"), os.environ.get("OMNIROUTE_BASE_URL"))
        os.environ["INFRALOOP_MODE"] = "offline"
        os.environ["OMNIROUTE_BASE_URL"] = "http://127.0.0.1:9"
        try:
            s = scan_repo(d)
            r = ar.reason_about_architecture(s, {"Budget?": "100 EUR"}, identify_gaps(s))
        finally:
            for k, v in zip(("INFRALOOP_MODE", "OMNIROUTE_BASE_URL"), old):
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v
        for n in range(1, 6):
            self.assertIn(f"## {n}.", r)
        self.assertIn("What's missing for production", r)


class CommandLine(unittest.TestCase):
    def test_cli_writes_report_without_model(self):
        import os, tempfile, subprocess, sys
        d = tempfile.mkdtemp()
        open(os.path.join(d, "app.py"), "w").write("print('hi')\n")
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        env = dict(os.environ, OMNIROUTE_BASE_URL="http://127.0.0.1:9")
        r = subprocess.run([sys.executable, os.path.join(here, "infraloop.py"), "scan", d], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("## 1."))


class LoadTiers(unittest.TestCase):
    A = "How much traffic do you have, or expect at launch? Please include the unit"

    def test_parse_units(self):
        from nodes import load_tiers as lt
        self.assertAlmostEqual(lt.parse_load({self.A: "10 requests per second"})["per_month"], 10 * 2592000)
        self.assertAlmostEqual(lt.parse_load({self.A: "50,000 requests per day"})["per_month"], 50000 * 30)
        self.assertAlmostEqual(lt.parse_load({self.A: "2,000 monthly active users"})["per_month"], 2000 * 600)
        self.assertIsNone(lt.parse_load({self.A: "Don't know"}))
        self.assertIsNone(lt.parse_load({self.A: "lots"}))

    def test_tiers_are_ordered_and_cover_everything(self):
        from nodes import load_tiers as lt
        self.assertEqual(len(lt.TIERS), 10)
        self.assertEqual(lt.tier_of(0.1)[0], 1)
        self.assertEqual(lt.tier_of(100)[0], 6)
        self.assertEqual(lt.tier_of(100000)[0], 10)

    def test_price_never_decreases_with_load(self):
        import os
        from scanner.scan import scan_repo
        from nodes import architecture_reasoner as ar, load_tiers as lt, cost_estimator as ce
        repo = os.environ.get("INFRALOOP_TEST_REPO", "")
        if not repo or not os.path.isdir(repo):
            self.skipTest("set INFRALOOP_TEST_REPO to a multi-service repo to run this")
        s = scan_repo(repo)
        ans = {self.A: "50,000 requests per day", "What's your monthly infrastructure budget?": "300"}
        _, cd = ar._cost_for(s, ans)
        plan = ar._plan_for(s, ans, cd)
        wl = ce._workloads(s)[0]
        prev = 0
        for _, _, _, rep in lt.TIERS:
            total = lt.price_tier(rep, plan, wl, ce)[0]
            self.assertGreaterEqual(total + 1e-6, prev)
            prev = total


class HygieneChecks(unittest.TestCase):
    def _scan(self, files):
        import os, tempfile
        from scanner.scan import scan_repo
        d = tempfile.mkdtemp()
        for rel, body in files.items():
            p = os.path.join(d, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w").write(body)
        return scan_repo(d)

    def test_renovate_json5_in_github_folder_counts(self):
        s = self._scan({"app.py": "x=1\n", ".github/renovate.json5": "{}"})
        self.assertTrue(s["repo_hygiene"]["dependency_update_bot"])

    def test_dockerignore_next_to_each_dockerfile_is_enough(self):
        from nodes.gap_identifier import identify_gaps
        s = self._scan({"svc/app.py": "x=1\n", "svc/Dockerfile": "FROM python:3.12\nCMD [\"python\",\"app.py\"]\n", "svc/.dockerignore": ".git\n"})
        self.assertNotIn("no_dockerignore", {g["issue"] for g in identify_gaps(s)})

    def test_dockerignore_missing_is_named(self):
        from nodes.gap_identifier import identify_gaps
        s = self._scan({"a/app.py": "x=1\n", "a/Dockerfile": "FROM python:3.12\n", "a/.dockerignore": "x\n",
                        "b/app.py": "x=1\n", "b/Dockerfile": "FROM python:3.12\n"})
        g = [x for x in identify_gaps(s) if x["issue"] == "no_dockerignore"]
        self.assertTrue(g and "b" in g[0]["detail"])

    def test_sonar_counts_as_security_scanning(self):
        s = self._scan({"app.py": "x=1\n", ".github/workflows/ci.yml": "jobs:\n  s:\n    steps:\n      - run: mvn sonar:sonar\n"})
        self.assertTrue(s["ci_quality"]["security_scanning"])


class ReportReviewFixes(unittest.TestCase):
    A = "How much traffic do you have, or expect at launch? Please include the unit"

    def test_request_figure_wins_over_user_figure(self):
        from nodes import load_tiers as lt
        r = lt.parse_load({self.A: "3000 user and 10000 request per month"})
        self.assertAlmostEqual(r["per_month"], 10000)

    def test_tiny_rates_are_shown_per_day(self):
        from nodes import load_tiers as lt
        self.assertIn("per day" if False else "requests/day", lt.rate_text(0.004))

    def test_zero_data_loss_guarantee_sentence_is_removed(self):
        from nodes import claim_check
        a = claim_check.build_allowed("x")
        self.assertTrue(claim_check.check_sentence("The managed Redis provides failover, meeting your zero-data-loss requirement for cart data.", a))

    def test_unnumbered_headings_get_numbers(self):
        from nodes import architecture_reasoner as ar
        out = ar._normalize_section_headings("## What this project is\nx\n## Gaps for production\n## Recommended architecture\n## Estimated monthly cost\n## What you're uncertain about")
        for n in "12345":
            self.assertIn(f"## {n}.", out)

    def test_model_monitoring_row_dropped_when_scanner_has_one(self):
        from nodes import report_cleanup
        self.assertTrue(report_cleanup._same_topic("No monitoring/alerting manifests Prometheus rules", "Tracing without metrics or alerting"))
        self.assertFalse(report_cleanup._same_topic("No backups of the database", "Tracing without metrics or alerting"))


class PolishOnBase(unittest.TestCase):
    BASE = ("## 1. What this project is\n\nA shop with 12 services.\n\nConfidence: high.\n\n## 2. What's missing\n\n| a |\n\n"
            "## 3. Recommended architecture\n\nOld text.\n\n## 4. Estimated Monthly Cost\n\nTotal 135.46 EUR.\n\n## 5. What this report cannot tell you\n\n- Old.\n")

    def _run(self, answer):
        from nodes import polish, architecture_reasoner as ar
        return polish.polish(self.BASE, '{"services": 12}', '{"budget": "200"}', "", lambda p: answer, ar)

    def test_good_blocks_replace_code_text_and_summary_is_added(self):
        out, removed = self._run("[[SUMMARY]]\nYou asked for 200 and the total is 135.46 EUR.\n[[S1]]\nA shop with 12 services.\n[[S3]]\nThe setup suits you.\n[[S5]]\n- Load is not measured.\n")
        self.assertIn("## In your situation", out)
        self.assertIn("The setup suits you.", out)
        self.assertNotIn("Old text.", out)
        self.assertIn("Total 135.46 EUR.", out)           # the cost section is never touched
        self.assertEqual(removed, [])

    def test_invented_number_drops_the_block(self):
        out, removed = self._run("[[S3]]\nThis costs 999 EUR. It is fine.\n")
        self.assertIn("Old text.", out)
        self.assertTrue(removed)

    def test_unreadable_answer_raises_so_the_caller_can_fall_back(self):
        with self.assertRaises(ValueError):
            self._run("no blocks here")

    def test_unit_conversion_needs_a_unit(self):
        from nodes import claim_check
        a = claim_check.build_allowed("cpu 0.07 and cost 9.00")
        self.assertTrue(claim_check.check_sentence("It costs 9000 per month.", a))
        self.assertFalse(claim_check.check_sentence("It asks for 70 millicores.", a))


class PolishWording(unittest.TestCase):
    def test_sufficiency_judgement_is_removed(self):
        from nodes import claim_check
        a = claim_check.build_allowed("tier 1")
        self.assertTrue(claim_check.check_sentence("For your traffic the Tiny tier sizing is appropriate.", a))
        self.assertFalse(claim_check.check_sentence("A load test is needed to confirm the pod sizes.", a))

    def test_confidence_sentence_not_repeated_in_section_1(self):
        from nodes import polish, architecture_reasoner as ar
        base = "## 1. What this project is\n\nOld.\n\nConfidence: high.\n\n## 3. Recommended architecture\n\nx\n"
        out, _ = polish.polish(base, "{}", "{}", "", lambda p: "[[S1]]\nA shop. We have high confidence in this.\n", ar)
        self.assertEqual(out.lower().count("confiden"), 1)
