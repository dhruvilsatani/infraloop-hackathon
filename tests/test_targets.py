"""'Where will it run?': options come from the planner, files exist only where a pack exists, and the Hetzner pack stays safe."""
import io, os, shutil, subprocess, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from nodes.gap_identifier import identify_gaps
import generators
from generators import generate_files, build_targets, find_target, manifest
from generators.model import HEADER

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLAN = {"chosen": {"label": "GKE Autopilot, 1 replica per service", "platform": "gke_autopilot", "total": 24.42, "zone_ha": False}, "total": 24.42, "notes": [],
        "alternatives": [{"label": "Cloud Run always-on, 2 instances per service", "total": 40.88, "zone_ha": True, "notes": []}], "small_server": None}


def make_app(d, name="app"):
    app = os.path.join(d, name)
    os.makedirs(app)
    with open(os.path.join(app, "main.py"), "w") as fh:
        fh.write("import os\nfrom fastapi import FastAPI\napp = FastAPI()\nDB = os.environ['DATABASE_URL']\nKEY = os.environ.get('STRIPE_KEY')\n")
    with open(os.path.join(app, "requirements.txt"), "w") as fh:
        fh.write("fastapi\nuvicorn\n")
    return app


class Options(unittest.TestCase):
    def setUp(self):
        from scanner.scan import scan_repo
        self.tmp = tempfile.TemporaryDirectory()
        self.scan = scan_repo(make_app(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_always_has_the_escape_hatches_and_unique_ids(self):
        ts = build_targets(self.scan, None)
        ids = [t["id"] for t in ts]
        self.assertIn("other-cloud", ids)
        self.assertIn("not-yet", ids)
        self.assertEqual(len(ids), len(set(ids)))

    def test_every_option_explains_itself(self):
        for t in build_targets(self.scan, PLAN):
            self.assertTrue(t["label"].strip())
            self.assertTrue(t["note"].strip())

    def test_options_come_from_the_plan_with_its_prices(self):
        ts = build_targets(self.scan, PLAN)
        prices = {t["monthly_eur"] for t in ts if t["id"].startswith("plan-")}
        self.assertEqual(prices, {24.42, 40.88})

    def test_files_are_promised_only_where_a_pack_exists(self):
        for t in build_targets(self.scan, PLAN):
            if t["id"].startswith("plan-") or t["id"] == "other-cloud":
                self.assertFalse(t["files"], t["id"])
        self.assertTrue(find_target(build_targets(self.scan, PLAN), "hetzner-server")["files"])

    def test_exactly_one_recommended_and_it_is_first(self):
        ts = build_targets(self.scan, PLAN)
        self.assertEqual(sum(t["recommended"] for t in ts), 1)
        self.assertTrue(ts[0]["recommended"])
        self.assertEqual(ts[0]["id"], "plan-0")

    def test_the_small_server_is_recommended_when_the_planner_says_so(self):
        plan = dict(PLAN, small_server={"name": "CPX02", "total": 6.49})
        ts = build_targets(self.scan, plan)
        self.assertEqual(ts[0]["id"], "hetzner-server")
        self.assertEqual(sum(t["recommended"] for t in ts), 1)

    def test_unknown_id_is_not_found(self):
        self.assertIsNone(find_target(build_targets(self.scan, PLAN), "aws-yolo"))


class HetznerPack(unittest.TestCase):
    def setUp(self):
        from scanner.scan import scan_repo
        self.tmp = tempfile.TemporaryDirectory()
        self.scan = scan_repo(make_app(self.tmp.name))
        self.gaps = identify_gaps(self.scan)
        self.target = find_target(build_targets(self.scan, None), "hetzner-server")
        self.bundle = generate_files(self.scan, self.gaps, self.target)
        self.files = {f.path: f.content for f in self.bundle.files}

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_terraform_compose_proxy_and_the_basic_files(self):
        for p in ("infra/hetzner/main.tf", "infra/hetzner/variables.tf", "infra/hetzner/outputs.tf", "infra/hetzner/cloud-init.yaml",
                  "infra/hetzner/terraform.tfvars.example", "infra/hetzner/.gitignore", "docker-compose.prod.yml", "deploy/Caddyfile", "Dockerfile"):
            self.assertIn(p, self.files)

    def test_the_missing_iac_gap_is_now_closed_by_files(self):
        self.assertFalse(any(s.gap == "no_iac" for s in self.bundle.skipped))
        self.assertTrue(any(f.gap == "no_iac" for f in self.bundle.files))

    def test_no_token_or_secret_value_is_ever_written(self):
        everything = "\n".join(self.files.values())
        import re
        self.assertIsNone(re.search(r'hcloud_token\s*=\s*"', everything))      # no token value is set anywhere
        self.assertIsNone(re.search(r'[A-Za-z0-9]{64}', everything))           # nothing that looks like a 64-character API token
        v = self.files["infra/hetzner/variables.tf"]
        block = v[v.index('variable "hcloud_token"'):v.index('variable "ssh_public_key"')]
        self.assertIn("sensitive   = true", block)
        self.assertNotIn("default", block)

    def test_app_variables_are_created_as_names_only(self):
        env = yaml.safe_load(self.files["infra/hetzner/cloud-init.yaml"].replace("${site_address}", ":80").replace("${branch}", "main").replace("${repo_url}", "https://x/y.git"))
        content = env["write_files"][0]["content"]
        self.assertIn("DATABASE_URL=\n", content)
        self.assertIn("STRIPE_KEY=\n", content)
        self.assertEqual(env["write_files"][0]["permissions"], "0600")

    def test_ssh_has_no_default_and_is_never_open_to_everyone(self):
        v = self.files["infra/hetzner/variables.tf"]
        block = v[v.index('variable "admin_cidrs"'):v.index('variable "repo_url"')]
        import re
        self.assertIsNone(re.search(r'^\s*default\s*=', block, re.M))
        self.assertIn("0.0.0.0/0", block)                       # only inside the validation that rejects it
        m = self.files["infra/hetzner/main.tf"]
        ssh = m[m.index('port       = "22"'):m.index('port       = "22"') + 80]
        self.assertIn("var.admin_cidrs", ssh)

    def test_state_and_values_are_git_ignored(self):
        g = self.files["infra/hetzner/.gitignore"]
        for want in ("*.tfstate", "terraform.tfvars", ".terraform/"):
            self.assertIn(want, g)

    def test_compose_and_cloud_init_are_valid_yaml(self):
        c = yaml.safe_load(self.files["docker-compose.prod.yml"])
        self.assertEqual(set(c["services"]), {"app", "caddy"})
        self.assertEqual(c["services"]["app"]["expose"], ["8000"])
        ci = yaml.safe_load(self.files["infra/hetzner/cloud-init.yaml"].replace("${site_address}", ":80").replace("${branch}", "main").replace("${repo_url}", "https://x/y.git"))
        self.assertIn("runcmd", ci)

    def test_proxy_points_at_the_service_port(self):
        self.assertIn("reverse_proxy app:8000", self.files["deploy/Caddyfile"])

    def test_every_file_is_marked_as_generated_and_has_notes(self):
        for f in self.bundle.files:
            if f.path.endswith(".tf") or f.path in ("docker-compose.prod.yml", "Dockerfile"):
                self.assertIn(HEADER, f.content, f.path)
        for f in self.bundle.files:
            if f.path == "infra/hetzner/main.tf":
                self.assertTrue(any("Nothing here was run" in r for r in f.review))

    def test_manifest_records_the_choice_and_its_price(self):
        m = manifest(self.bundle)
        self.assertIn("**Your choice:**", m)
        self.assertIn("Hetzner", m)
        self.assertIn("6.49", m)

    def test_never_overwrites_an_existing_compose_file(self):
        # the pack writes docker-compose.prod.yml, never docker-compose.yml, so a developer's own compose file is never touched
        self.assertNotIn("docker-compose.yml", self.files)

    def test_unsupported_choice_gets_basic_files_and_says_so(self):
        t = find_target(build_targets(self.scan, PLAN), "plan-0")
        b = generate_files(self.scan, self.gaps, t)
        self.assertFalse([f.path for f in b.files if f.path.startswith("infra/")])
        self.assertIn("No infrastructure files exist for this choice yet", manifest(b))
        self.assertTrue(any(s.gap == "no_iac" for s in b.skipped))

    def test_not_yet_gives_only_the_basic_files(self):
        b = generate_files(self.scan, self.gaps, find_target(build_targets(self.scan, None), "not-yet"))
        self.assertFalse([f.path for f in b.files if f.path.startswith("infra/")])
        self.assertIn("Dockerfile", [f.path for f in b.files])

    def test_same_choice_same_files(self):
        again = generate_files(self.scan, self.gaps, self.target)
        self.assertEqual([(f.path, f.content) for f in again.files], [(f.path, f.content) for f in self.bundle.files])

    @unittest.skipUnless(os.environ.get("INFRALOOP_TF_VALIDATE") and shutil.which("terraform"), "set INFRALOOP_TF_VALIDATE=1 and put terraform on PATH (needs network to fetch the provider)")
    def test_terraform_validate_passes(self):
        with tempfile.TemporaryDirectory() as d:
            for p, text in self.files.items():
                if p.startswith("infra/hetzner/"):
                    os.makedirs(os.path.dirname(os.path.join(d, p)), exist_ok=True)
                    with open(os.path.join(d, p), "w") as fh:
                        fh.write(text)
            tf = os.path.join(d, "infra", "hetzner")
            subprocess.run(["terraform", "init", "-backend=false", "-input=false"], cwd=tf, check=True, capture_output=True)
            r = subprocess.run(["terraform", "validate"], cwd=tf, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class PlainLanguageChoices(unittest.TestCase):
    """Someone who is not technical must understand why the cheap option is cheap, and what the catch is."""

    def setUp(self):
        from scanner.scan import scan_repo
        self.tmp = tempfile.TemporaryDirectory()
        self.scan = scan_repo(make_app(self.tmp.name))
        self.gaps = identify_gaps(self.scan)
        self.ts = build_targets(self.scan, PLAN, self.gaps)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_option_states_its_catch_in_one_line(self):
        for t in self.ts:
            self.assertTrue(t["catch"].strip(), t["id"])
            self.assertLess(len(t["catch"]), 200, t["id"])

    def test_the_page_gets_a_short_list_of_drawbacks_and_a_short_name(self):
        hz = find_target(self.ts, "hetzner-server")
        self.assertEqual(hz["short"], "one Hetzner server")
        self.assertTrue(3 <= len(hz["drawbacks"]) <= 6)
        for d in hz["drawbacks"]:
            self.assertLess(len(d), 160)
        self.assertEqual(find_target(self.ts, "plan-0")["short"], "GKE Autopilot")
        self.assertEqual(find_target(self.ts, "not-yet")["drawbacks"], [])

    def test_wording_is_plain_not_jargon(self):
        for t in self.ts:
            for d in t["drawbacks"] + [t["catch"]]:
                for jargon in ("SPOF", "single point of failure", "RTO", "RPO", "SLA"):
                    self.assertNotIn(jargon, d)

    def test_every_option_has_a_brief_with_plain_words(self):
        for t in self.ts:
            self.assertIn("In plain words", t["brief"], t["id"])
            self.assertIn(t["label"], t["brief"])

    def test_the_cheap_option_explains_why_it_is_cheap_and_what_you_give_up(self):
        b = find_target(self.ts, "hetzner-server")["brief"]
        self.assertIn("Why it costs what it does", b)
        for must in ("breaks or restarts", "security patches are yours", "Backups are off", "outgrow one machine"):
            self.assertIn(must, b)
        self.assertIn("Think again if", b)

    def test_the_price_in_the_brief_is_the_price_in_the_option(self):
        for t in self.ts:
            if t["monthly_eur"] is not None:
                self.assertIn(f"{t['monthly_eur']:.2f} EUR", t["brief"], t["id"])

    def test_it_says_whether_a_zone_outage_is_survived(self):
        self.assertIn("this stops until", find_target(self.ts, "hetzner-server")["brief"])
        self.assertIn("this keeps running", find_target(self.ts, "plan-1")["brief"])     # the 2-instance Cloud Run option

    def test_gap_notes_appear_only_for_gaps_this_repo_really_has(self):
        b = find_target(self.ts, "hetzner-server")["brief"]
        self.assertIn("`no_iac`", b)
        self.assertNotIn("`k8s_no_security_context`", b)          # this repo has no Kubernetes gaps

    def test_unsupported_choice_says_no_files_yet(self):
        self.assertIn("no infrastructure files exist for it yet", find_target(self.ts, "plan-0")["brief"])

    def test_no_promise_of_availability_or_security(self):
        for t in self.ts:
            low = t["brief"].lower()
            for banned in ("guarantee", "100% uptime", "unhackable", "fully secure"):
                self.assertNotIn(banned, low, t["id"])

    def test_setup_md_is_in_the_zip_only_when_a_choice_was_made(self):
        import zipfile
        from generators import to_zip_bytes
        with_choice = generate_files(self.scan, self.gaps, find_target(self.ts, "hetzner-server"))
        self.assertIn("infraloop-generated/SETUP.md", zipfile.ZipFile(io.BytesIO(to_zip_bytes(with_choice))).namelist())
        self.assertIn("SETUP.md", manifest(with_choice))
        without = generate_files(self.scan, self.gaps)
        self.assertNotIn("infraloop-generated/SETUP.md", zipfile.ZipFile(io.BytesIO(to_zip_bytes(without))).namelist())


class BenefitsAndWhy(unittest.TestCase):
    def setUp(self):
        from scanner.scan import scan_repo
        self.tmp = tempfile.TemporaryDirectory()
        self.scan = scan_repo(make_app(self.tmp.name))
        self.gaps = identify_gaps(self.scan)
        self.plan = {"chosen": {"label": "GKE Autopilot, 2 replicas per service", "platform": "gke_autopilot", "total": 33.01, "zone_ha": True},
                     "total": 33.01, "notes": [], "budget": 50.0, "uptime": "zero", "status": "fits",
                     "alternatives": [{"label": "Cloud Run always-on, 2 instances per service", "total": 40.88, "zone_ha": True, "notes": []}],
                     "small_server": None}
        self.ts = generators.build_targets(self.scan, self.plan, self.gaps)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_real_option_lists_what_you_get(self):
        for t in self.ts:
            if t["id"] != "not-yet":
                self.assertTrue(t["benefits"], t["id"])

    def test_recommended_option_has_more_benefits_than_drawbacks(self):
        rec = self.ts[0]
        self.assertTrue(rec["recommended"])
        self.assertGreater(len(rec["benefits"]), len(rec["drawbacks"]))

    def test_why_is_only_on_the_recommended_option_and_uses_plan_numbers(self):
        self.assertTrue(self.ts[0]["why"])
        self.assertIn("50", " ".join(self.ts[0]["why"]))
        for t in self.ts[1:]:
            self.assertEqual(t["why"], [])

    def test_no_budget_claim_when_the_plan_does_not_fit(self):
        plan = dict(self.plan, status="over_budget", budget=10.0)
        ts = generators.build_targets(self.scan, plan, self.gaps)
        self.assertNotIn("It fits your budget", " ".join(ts[0]["why"]))

    def test_zone_benefit_only_when_the_option_really_survives_a_zone_outage(self):
        for t in self.ts:
            text = " ".join(t["benefits"])
            if "one zone" in text:
                self.assertTrue(t["zone_ha"])

    def test_lowest_price_claim_is_only_on_the_cheapest(self):
        priced = [t for t in self.ts if t["monthly_eur"] is not None]
        cheapest = min(t["monthly_eur"] for t in priced)
        for t in priced:
            has = any("lowest price" in b for b in t["benefits"])
            self.assertEqual(has, t["monthly_eur"] == cheapest, t["id"])

    def test_the_download_note_carries_the_benefits_and_the_reason(self):
        rec = self.ts[0]
        md = rec["brief"]
        self.assertIn("What you get", md)
        self.assertIn("Why we recommend it", md)
        self.assertLess(md.index("What you get"), md.index("What you give up"))

    def test_no_promise_words_in_benefits(self):
        import re
        for t in self.ts:
            self.assertIsNone(re.search(r"guarantee|never goes down|100%|unhackable|secure by", " ".join(t["benefits"] + t["why"]), re.I), t["id"])


class ProviderLinks(unittest.TestCase):
    def setUp(self):
        from scanner.scan import scan_repo
        self.tmp = tempfile.TemporaryDirectory()
        sc = scan_repo(make_app(self.tmp.name))
        self.ts = build_targets(sc, PLAN, identify_gaps(sc))

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_real_provider_has_https_links_on_its_own_site(self):
        from urllib.parse import urlparse
        ok = ("www.hetzner.com", "cloud.google.com", "aws.amazon.com", "azure.microsoft.com")
        for t in self.ts:
            for l in t["links"]:
                u = urlparse(l["url"])
                self.assertEqual(u.scheme, "https", l)
                self.assertIn(u.hostname, ok, l)
                self.assertTrue(l["label"])

    def test_hetzner_and_google_options_have_links_and_the_escape_hatches_do_not(self):
        by = {t["id"]: t for t in self.ts}
        self.assertTrue(by["hetzner-server"]["links"])
        self.assertTrue(by["plan-0"]["links"])
        self.assertTrue(by["aws-server"]["links"])
        self.assertTrue(by["azure-server"]["links"])
        self.assertEqual(by["other-cloud"]["links"], [])
        self.assertEqual(by["not-yet"]["links"], [])

    def test_links_are_in_the_setup_notes_too(self):
        by = {t["id"]: t for t in self.ts}
        self.assertIn("https://www.hetzner.com/cloud/", by["hetzner-server"]["brief"])


class CloudServerOptions(unittest.TestCase):
    """One server on AWS and on Azure: priced from each provider's own list, with its own Terraform pack."""
    def setUp(self):
        from scanner.scan import scan_repo
        self.tmp = tempfile.TemporaryDirectory()
        self.scan = scan_repo(make_app(self.tmp.name))
        self.gaps = identify_gaps(self.scan)
        self.ts = build_targets(self.scan, PLAN, self.gaps)

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self, tid):
        return generate_files(self.scan, self.gaps, find_target(self.ts, tid))

    def test_both_options_are_offered_with_files_and_no_recommendation(self):
        for tid in ("aws-server", "azure-server"):
            t = find_target(self.ts, tid)
            self.assertIsNotNone(t, tid)
            self.assertTrue(t["files"])
            self.assertIs(t["zone_ha"], False)
            self.assertFalse(t["recommended"])

    def test_the_price_is_the_providers_own_numbers_added_up(self):
        from knowledge import prices as P
        aws = find_target(self.ts, "aws-server")
        row = next(r for r in P.AWS_SERVERS if r[0] == aws["server"]["name"])
        vcpu, ram, hour = P.AWS_EC2_LINUX_USD_PER_HOUR[row[0]]
        usd = hour * 730 + P.AWS_GP3_USD_PER_GB_MONTH * P.AWS_DISK_GB + P.AWS_PUBLIC_IPV4_USD_PER_HOUR * 730
        self.assertAlmostEqual(aws["monthly_eur"], round(usd / P.USD_PER_EUR, 2), places=2)
        az = find_target(self.ts, "azure-server")
        vcpu, ram, hour = P.AZURE_VM_LINUX_EUR_PER_HOUR[az["server"]["name"]]
        self.assertAlmostEqual(az["monthly_eur"], round(hour * 730 + P.AZURE_SSD_E4_EUR_PER_MONTH + P.AZURE_PUBLIC_IP_EUR_PER_HOUR * 730, 2), places=2)

    def test_every_price_row_has_a_source_and_a_date(self):
        from knowledge import prices as P
        self.assertRegex(P.RETRIEVED_VM, r"^\d{4}-\d{2}-\d{2}$")
        for src in (P.SRC_EC2_LIST, P.SRC_VPC_LIST, P.SRC_EC2_PAGE, P.SRC_AZURE_VM_PAGE):
            self.assertTrue(src.startswith("https://"))
        # cheapest first, as the picker assumes
        for rows in (P.AWS_SERVERS, P.AZURE_SERVERS):
            self.assertEqual([r[4] for r in rows], sorted(r[4] for r in rows))

    def test_the_cost_line_says_where_the_price_came_from_and_what_is_left_out(self):
        for tid, who in (("aws-server", "AWS"), ("azure-server", "Azure")):
            b = self.bundle(tid).brief
            self.assertIn("own price list", b)
            self.assertIn("2026-11-14", b)
            self.assertIn("excluding VAT", b)
            self.assertIn(f"Traffic out of {who}", b)

    def test_each_pack_writes_its_own_folder_only(self):
        for tid, mine, other in (("aws-server", "infra/aws/", "infra/azure/"), ("azure-server", "infra/azure/", "infra/aws/")):
            paths = [f.path for f in self.bundle(tid).files]
            self.assertTrue(any(p.startswith(mine) for p in paths))
            self.assertFalse(any(p.startswith(other) or p.startswith("infra/hetzner/") for p in paths))
            self.assertIn("docker-compose.prod.yml", paths)
            self.assertIn("deploy/Caddyfile", paths)

    def test_no_credential_is_ever_written(self):
        import re
        for tid in ("aws-server", "azure-server"):
            for f in self.bundle(tid).files:
                self.assertIsNone(re.search(r"AKIA[0-9A-Z]{12}|aws_secret_access_key|access_key\s*=|client_secret\s*=|password\s*=\s*\"", f.content), (tid, f.path))

    def test_ssh_is_closed_to_the_world_and_has_no_default(self):
        for tid, d in (("aws-server", "infra/aws"), ("azure-server", "infra/azure")):
            files = {f.path: f.content for f in self.bundle(tid).files}
            v = files[f"{d}/variables.tf"]
            block = v[v.index('variable "admin_cidrs"'):]
            block = block[:block.index("\n}\n")]
            self.assertNotRegex(block, r"\n\s+default\s*=")
            self.assertIn("0.0.0.0/0", block)       # the validation that rejects it
            self.assertIn("!contains(var.admin_cidrs", block)

    def test_server_hardening_defaults(self):
        aws = {f.path: f.content for f in self.bundle("aws-server").files}["infra/aws/main.tf"]
        self.assertIn('http_tokens   = "required"', aws)
        self.assertIn("encrypted   = true", aws)
        az = {f.path: f.content for f in self.bundle("azure-server").files}["infra/azure/main.tf"]
        self.assertIn("disable_password_authentication = true", az)

    def test_app_variables_are_names_only_in_cloud_init(self):
        for tid, d in (("aws-server", "infra/aws"), ("azure-server", "infra/azure")):
            ci = {f.path: f.content for f in self.bundle(tid).files}[f"{d}/cloud-init.yaml"]
            self.assertIn("DATABASE_URL=\n", ci)
            self.assertIn("STRIPE_KEY=\n", ci)
            self.assertTrue(yaml.safe_load(ci.replace("${site_address}", ":80")))

    def test_every_file_is_marked_as_generated_and_has_notes(self):
        for tid in ("aws-server", "azure-server"):
            for f in self.bundle(tid).files:
                if f.path.startswith("infra/") and f.path.endswith((".tf", ".yaml")):
                    self.assertIn("Generated by InfraLoop", f.content, f.path)
                if f.path.endswith("main.tf"):
                    self.assertTrue(f.assumptions and f.review, f.path)

    def test_the_escape_hatch_no_longer_lists_aws_and_azure_as_missing(self):
        other = find_target(self.ts, "other-cloud")
        self.assertNotIn("(AWS, Azure,", other["label"])
        self.assertIn("Kubernetes on AWS or Azure", other["label"])      # AWS Fargate and Azure Container Apps are priced options now

    @unittest.skipUnless(os.environ.get("INFRALOOP_TF_VALIDATE") and shutil.which("terraform"), "set INFRALOOP_TF_VALIDATE=1 and install terraform")
    def test_terraform_validate_and_fmt_pass(self):
        for tid, d in (("aws-server", "infra/aws"), ("azure-server", "infra/azure")):
            with tempfile.TemporaryDirectory() as t:
                for f in self.bundle(tid).files:
                    if f.path.startswith(d + "/"):
                        os.makedirs(os.path.dirname(os.path.join(t, f.path)), exist_ok=True)
                        with open(os.path.join(t, f.path), "w") as fh:
                            fh.write(f.content)
                tf = os.path.join(t, d)
                subprocess.run(["terraform", "init", "-backend=false", "-input=false"], cwd=tf, check=True, capture_output=True)
                r = subprocess.run(["terraform", "validate"], cwd=tf, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, tid + r.stdout + r.stderr)
                r = subprocess.run(["terraform", "fmt", "-check", "-diff"], cwd=tf, capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, tid + r.stdout + r.stderr)


class ImplementationGuide(unittest.TestCase):
    def setUp(self):
        from scanner.scan import scan_repo
        self.tmp = tempfile.TemporaryDirectory()
        self.scan = scan_repo(make_app(self.tmp.name))
        self.gaps = identify_gaps(self.scan)
        self.ts = build_targets(self.scan, PLAN, self.gaps)

    def tearDown(self):
        self.tmp.cleanup()

    def guide(self, tid=None):
        t = find_target(self.ts, tid) if tid else None
        return generate_files(self.scan, self.gaps, t).implementation

    def test_every_download_has_the_guide_in_the_zip_and_in_a_folder(self):
        import zipfile
        for tid in (None, "not-yet", "other-cloud", "hetzner-server", "aws-server", "azure-server", "plan-0"):
            b = generate_files(self.scan, self.gaps, find_target(self.ts, tid) if tid else None)
            self.assertTrue(b.implementation.startswith("# How to put this into practice"), tid)
            self.assertIn("infraloop-generated/IMPLEMENTATION.md", zipfile.ZipFile(io.BytesIO(generators.to_zip_bytes(b))).namelist(), tid)
            with tempfile.TemporaryDirectory() as d:
                out = os.path.join(d, "out")
                generators.write_to_dir(b, out)
                self.assertTrue(os.path.isfile(os.path.join(out, "IMPLEMENTATION.md")), tid)

    def test_manifest_points_to_the_guide(self):
        self.assertIn("IMPLEMENTATION.md", manifest(generate_files(self.scan, self.gaps, None)))
        self.assertIn("IMPLEMENTATION.md", manifest(generate_files(self.scan, self.gaps, find_target(self.ts, "hetzner-server"))))

    def test_it_says_it_was_not_run_and_promises_nothing(self):
        import re
        for tid in (None, "hetzner-server", "aws-server", "azure-server"):
            g = self.guide(tid)
            self.assertIn("Nothing here was run", g)
            self.assertIsNone(re.search(r"guarantee|always works|100%|will not fail", g, re.I), tid)

    def test_it_uses_the_projects_own_names(self):
        g = self.guide("hetzner-server")
        self.assertIn("docker build -t", g)
        self.assertIn("DATABASE_URL", g)
        self.assertIn("8000", g)

    def test_the_number_of_things_terraform_creates_matches_the_files(self):
        import re
        for tid, d in (("hetzner-server", "infra/hetzner"), ("aws-server", "infra/aws"), ("azure-server", "infra/azure")):
            b = generate_files(self.scan, self.gaps, find_target(self.ts, tid))
            n = {f.path: f.content for f in b.files}[f"{d}/main.tf"].count('\nresource "')
            self.assertGreater(n, 0)
            self.assertIn(f"about {n} things", b.implementation, tid)

    def test_each_cloud_gets_its_own_login_and_ssh_user(self):
        self.assertIn("TF_VAR_hcloud_token", self.guide("hetzner-server"))
        self.assertIn("ssh root@", self.guide("hetzner-server"))
        a = self.guide("aws-server")
        self.assertIn("aws sts get-caller-identity", a)
        self.assertIn("ssh ubuntu@", a)
        z = self.guide("azure-server")
        self.assertIn("az login", z)
        self.assertIn("ssh azureuser@", z)
        self.assertIn("subscription_id", z)

    def test_no_secret_is_pasted_into_a_file_by_the_guide(self):
        for tid in ("hetzner-server", "aws-server", "azure-server"):
            g = self.guide(tid)
            self.assertIn("never written to a file", g) if tid == "hetzner-server" else None
            self.assertNotRegex(g, r"AKIA[0-9A-Z]{12}")

    def test_without_a_hosting_choice_it_has_no_terraform_steps(self):
        for tid in (None, "not-yet", "other-cloud", "plan-0"):
            g = self.guide(tid)
            self.assertNotIn("terraform apply", g, tid)
            self.assertIn("Choose where it runs", g, tid)

    def test_a_report_only_option_gets_its_provider_links(self):
        g = self.guide("plan-0")
        self.assertIn("https://cloud.google.com/kubernetes-engine", g)

    def test_dns_advice_does_not_tell_people_to_change_terraform_after_the_first_apply(self):
        g = self.guide("hetzner-server")
        self.assertIn("SITE_ADDRESS=", g)
        self.assertIn("Do not change `domain`", g)

    def test_same_scan_same_guide(self):
        self.assertEqual(self.guide("aws-server"), self.guide("aws-server"))


class CliTarget(unittest.TestCase):
    def test_target_flag_adds_the_infrastructure_files(self):
        with tempfile.TemporaryDirectory() as d:
            app = make_app(d)
            out = os.path.join(d, "out")
            r = subprocess.run([sys.executable, os.path.join(ROOT, "infraloop.py"), "generate", app, "--out", out, "--target", "hetzner-server"], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(out, "infra", "hetzner", "main.tf")))
            self.assertIn("Your choice", open(os.path.join(out, "MANIFEST.md")).read())


try:
    from fastapi.testclient import TestClient
    from web import api
    HAVE_API = True
except Exception:
    HAVE_API = False


@unittest.skipUnless(HAVE_API, "fastapi is not installed")
class Api(unittest.TestCase):
    def setUp(self):
        from scanner.scan import scan_repo
        self.tmp = tempfile.TemporaryDirectory()
        sc = scan_repo(make_app(self.tmp.name))
        self.sid = "test-targets-session-1"
        api.SESSIONS[self.sid] = {"scan_result": sc, "gaps": identify_gaps(sc), "answers": {}, "asked": [], "notes": ""}
        self.client = TestClient(api.app)

    def tearDown(self):
        api.SESSIONS.pop(self.sid, None)
        self.tmp.cleanup()

    def test_targets_lists_options_and_the_escape_hatches(self):
        r = self.client.post("/targets", json={"session_id": self.sid})
        self.assertEqual(r.status_code, 200)
        ids = [t["id"] for t in r.json()["targets"]]
        self.assertIn("not-yet", ids)
        self.assertIn("other-cloud", ids)

    def test_generate_with_a_choice_returns_its_files(self):
        import zipfile
        r = self.client.post("/generate", json={"session_id": self.sid, "target": "hetzner-server"})
        self.assertEqual(r.status_code, 200)
        names = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        self.assertIn("infraloop-generated/infra/hetzner/main.tf", names)

    def test_generate_without_a_choice_still_works(self):
        r = self.client.post("/generate", json={"session_id": self.sid})
        self.assertEqual(r.status_code, 200)

    def test_preview_lists_the_real_files_with_their_content(self):
        r = self.client.post("/preview", json={"session_id": self.sid, "target": "hetzner-server"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        paths = [f["path"] for f in d["files"]]
        self.assertIn("infra/hetzner/main.tf", paths)
        self.assertTrue(any(p.endswith("Dockerfile") for p in paths))
        self.assertEqual([x["path"] for x in d["docs"]], ["SETUP.md", "IMPLEMENTATION.md", "MANIFEST.md"])
        for f in d["files"]:
            self.assertTrue(f["content"].strip(), f["path"])
            self.assertIn(f["group"], ("cloud", "basic"))
        groups = {f["path"]: f["group"] for f in d["files"]}
        self.assertEqual(groups["infra/hetzner/main.tf"], "cloud")
        self.assertTrue(any(g == "basic" for g in groups.values()))

    def test_preview_matches_what_the_zip_contains(self):
        import zipfile
        pv = self.client.post("/preview", json={"session_id": self.sid, "target": "hetzner-server"}).json()
        z = self.client.post("/generate", json={"session_id": self.sid, "target": "hetzner-server"})
        names = {n.split("/", 1)[1] for n in zipfile.ZipFile(io.BytesIO(z.content)).namelist() if "/" in n}
        shown = {f["path"] for f in pv["files"]} | {d["path"] for d in pv["docs"]}
        self.assertEqual(shown, names)

    def test_preview_without_a_choice_has_no_setup_doc(self):
        d = self.client.post("/preview", json={"session_id": self.sid}).json()
        self.assertEqual([x["path"] for x in d["docs"]], ["IMPLEMENTATION.md", "MANIFEST.md"])
        self.assertFalse(any(f["group"] == "cloud" for f in d["files"]))

    def test_preview_rejects_invented_choice_and_lost_session(self):
        self.assertEqual(self.client.post("/preview", json={"session_id": self.sid, "target": "aws-yolo"}).status_code, 422)
        self.assertEqual(self.client.post("/preview", json={"session_id": "nope-nope-nope"}).status_code, 404)

    def test_targets_carry_benefits_and_the_reason(self):
        ts = self.client.post("/targets", json={"session_id": self.sid}).json()["targets"]
        self.assertTrue(all("benefits" in t and "why" in t for t in ts))

    def test_an_invented_choice_is_rejected(self):
        r = self.client.post("/generate", json={"session_id": self.sid, "target": "aws-yolo"})
        self.assertEqual(r.status_code, 422)

    def test_lost_session_is_a_clear_404(self):
        self.assertEqual(self.client.post("/targets", json={"session_id": "nope-nope-nope"}).status_code, 404)
        self.assertEqual(self.client.post("/generate", json={"session_id": "nope-nope-nope", "target": "not-yet"}).status_code, 404)


    def test_answer_returns_the_reports_own_gap_rows_the_budget_and_whether_ai_wrote_it(self):
        budget_q = "What's your monthly infrastructure budget?"
        from nodes import questionnaire
        asked = questionnaire.build_questions(api.SESSIONS[self.sid]["scan_result"], api.SESSIONS[self.sid]["gaps"]) if hasattr(questionnaire, "build_questions") else []
        budget_q = next((q["question"] for q in asked if isinstance(q, dict) and "budget" in q["question"].lower()), budget_q)
        api.SESSIONS[self.sid]["asked"] = [{"question": budget_q}]
        r = self.client.post("/answer", json={"session_id": self.sid, "answers": {budget_q: "200"}, "mode": "offline"})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertEqual(d["status"], "done")
        self.assertFalse(d["ai_written"])
        self.assertIsNone(d["ai_polish_error"])
        self.assertEqual(d["gaps"], api.report_gaps(d["report"]))
        for g in d["gaps"]:
            self.assertIn(g["name"], d["report"])
            self.assertIn(g["severity"], ("Critical", "High", "Medium", "Low"))
        self.assertIn("monthly_eur", d["budget"])
        self.assertEqual(d["budget"], {"monthly_eur": 200, "status": "fits"})

    def test_report_gaps_reads_the_table_and_ignores_a_report_without_one(self):
        rep = ("## 2. Gaps\n\n| # | Gap | Group | Severity | Source | Risk and evidence |\n|---|---|---|---|---|---|\n"
               "| 1 | No CI | Recommended | High | Checked in your repo by the scan | no workflow file |\n\n## 3. Next\n")
        self.assertEqual(api.report_gaps(rep), [{"name": "No CI", "severity": "High", "group": "Recommended",
                                                 "source": "Checked in your repo by the scan", "evidence": ["no workflow file"]}])
        self.assertEqual(api.report_gaps("# nothing here"), [])


if __name__ == "__main__":
    unittest.main()
