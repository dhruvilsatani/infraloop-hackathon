"""AWS ECS Fargate and Azure Container Apps are priced options, with their own load balancer, database, secrets and Redis prices.
Every expected number below is worked out here, by hand, from the provider prices written in knowledge/prices.py with their sources
(AWS Frankfurt price lists and Azure West Europe Retail Prices API, read 2026-11-14), so a changed price or a changed formula fails a test."""
import re
import unittest
from urllib.parse import urlparse

from knowledge import prices
from nodes import cost_estimator as ce, load_tiers, planner
from nodes.cost_estimator import build_cost_estimate, plan_options

USD = 1.1537          # USD per EUR, the table's own rate
H = 730               # hours per month
S = 730 * 3600        # seconds per month
BUDGET = "What's your monthly infrastructure budget?"
DOWNTIME = "How much downtime could you tolerate if something broke?"
DB = "Please tell me about your database in one answer: x"


def eur(usd):
    return usd / USD


def scan_one(redis=False, k8s=False):
    wl = {"web": {"cpu_cores": 0.25, "memory_gib": 0.5, "replicas": 1}}
    if redis:
        wl["redis"] = {"cpu_cores": 0.07, "memory_gib": 0.2, "replicas": 1}
    return {"repo_kind": "application", "workload_resources": wl,
            "services": {"count": 1, "list": [{"path": "web", "languages": ["Go"]}]},
            "in_cluster_datastores": ([{"type": "redis", "where": ["kubernetes"], "any_persistent_volume": False}] if redis else []),
            "infra_signals": {"has_k8s": k8s, "has_helm": False}, "dependencies": {}, "env_vars": []}


def only(platform, data):
    return dict(data, plan_options=[o for o in data["plan_options"] if o["platform"] == platform])


def option(opts, platform, replicas):
    return next(o for o in opts if o["platform"] == platform and o["replicas"] == replicas and o["set"] == "all")


class SourcedPrices(unittest.TestCase):
    KEYS = ("fargate_x86_vcpu_hour", "fargate_x86_gb_hour", "alb_per_hour", "alb_per_lcu_hour", "aws_public_ipv4_per_hour", "aws_secrets_manager_per_secret_month",
            "rds_pg_db_t4g_micro_single_az_hour", "rds_pg_db_t4g_medium_multi_az_hour", "rds_pg_gp3_gb_month_single_az", "rds_pg_gp3_gb_month_multi_az",
            "elasticache_redis_t4g_small_node_hour", "container_apps_vcpu_second_active", "container_apps_gib_second_active", "container_apps_per_million_requests",
            "azure_pg_flex_b1ms_hour", "azure_pg_flex_gp_2vcore_ddsv5_hour", "azure_pg_flex_storage_gb_month", "azure_key_vault_per_10k_operations")

    def test_every_new_price_has_a_value_a_scope_and_an_official_https_source(self):
        official = ("pricing.us-east-1.amazonaws.com", "aws.amazon.com", "prices.azure.com", "azure.microsoft.com", "learn.microsoft.com")
        for k in self.KEYS:
            value, scope, source = prices.PRICES_USD[k]
            self.assertGreater(value, 0, k)
            self.assertTrue(scope, k)
            self.assertEqual(urlparse(source).scheme, "https", k)
            self.assertIn(urlparse(source).hostname, official, k)

    def test_the_eu_prices_replaced_the_us_east_ones(self):
        for k in ("fargate_x86_vcpu_hour", "fargate_x86_gb_hour", "alb_per_hour", "alb_per_lcu_hour"):
            self.assertNotIn("NOT an EU price", prices.PRICES_USD[k][1], k)
            self.assertIn("Frankfurt", prices.PRICES_USD[k][1], k)

    def test_the_read_date_is_recorded(self):
        self.assertRegex(prices.RETRIEVED_PLATFORMS, r"^\d{4}-\d{2}-\d{2}$")

    def test_what_is_still_unreadable_is_named_and_what_was_found_is_not(self):
        joined = " ".join(prices.NOT_PRICED)
        self.assertNotIn("Hetzner load balancer", joined)
        self.assertNotIn("Amazon RDS (PostgreSQL) instances and storage", joined)
        self.assertNotIn("Amazon ElastiCache nodes", joined)
        self.assertIn("NAT gateways", joined)
        self.assertIn("Azure VMs for AKS nodes", joined)

    def test_hetzner_load_balancers_are_recorded_in_eur(self):
        self.assertEqual(dict(prices.HETZNER_LOAD_BALANCERS), {"LB11": 7.49, "LB21": 21.49, "LB31": 42.99})


class Options(unittest.TestCase):
    def test_four_platforms_are_priced(self):
        opts, _ = plan_options(scan_one())
        self.assertEqual({o["platform"] for o in opts}, {"gke_autopilot", "cloud_run", "aws_fargate", "azure_container_apps"})

    def test_fargate_one_task_is_the_hand_worked_total(self):
        opts, _ = plan_options(scan_one())
        task = (0.25 * 0.04656 + 0.5 * 0.00511) * H
        alb = (0.027 + 2 * 0.005) * H                       # the fixed hourly fee, and the public address it holds in each of two zones
        expected = eur(task + alb + 1 * 0.005 * H)          # plus one public address for the one task
        o = option(opts, "aws_fargate", 1)
        self.assertAlmostEqual(o["total"], expected, places=2)
        self.assertFalse(o["zone_ha"])
        self.assertEqual(o["copies"], 1)

    def test_fargate_two_tasks_pay_for_two_public_addresses_and_one_load_balancer(self):
        opts, _ = plan_options(scan_one())
        task = (0.25 * 0.04656 + 0.5 * 0.00511) * H
        expected = eur(2 * task + (0.027 + 2 * 0.005) * H + 2 * 0.005 * H)
        o = option(opts, "aws_fargate", 2)
        self.assertAlmostEqual(o["total"], expected, places=2)
        self.assertTrue(o["zone_ha"])
        self.assertEqual(o["copies"], 2)
        self.assertIn("Application Load Balancer", o["label"])

    def test_container_apps_is_priced_at_the_active_rate_with_no_load_balancer(self):
        opts, _ = plan_options(scan_one())
        one = eur((0.25 * 0.000034 + 0.5 * 0.000004) * S)
        self.assertAlmostEqual(option(opts, "azure_container_apps", 1)["total"], one, places=2)
        self.assertAlmostEqual(option(opts, "azure_container_apps", 2)["total"], 2 * one, places=2)
        self.assertTrue(option(opts, "azure_container_apps", 2)["zone_ha"])
        self.assertIn("no separate load balancer", option(opts, "azure_container_apps", 2)["label"])

    def test_google_options_did_not_move(self):
        opts, meta = plan_options(scan_one())
        ap = (0.25 * 0.0445 + 0.5 * 0.0049225) * H
        lb = 0.025 * H
        self.assertAlmostEqual(option(opts, "gke_autopilot", 1)["total"], eur(ap + lb), places=2)       # the free credit covers the Autopilot cluster fee
        self.assertAlmostEqual(option(opts, "gke_autopilot", 2)["total"], eur(2 * ap + lb), places=2)
        self.assertEqual(meta["fee_autopilot"], 0.0)

    def test_a_stateful_service_is_one_copy_on_every_platform(self):
        opts, _ = plan_options(scan_one(redis=True))
        for plat in ("aws_fargate", "azure_container_apps"):
            o = option(opts, plat, 2)
            self.assertEqual(o["stateful_kept_single"], ["redis"], plat)
        self.assertEqual(option(opts, "aws_fargate", 2)["copies"], 3)      # two web tasks and one redis

    def test_report_totals_include_the_new_options(self):
        _, data = build_cost_estimate(scan_one())
        self.assertTrue({o["total"] for o in data["plan_options"]} <= set(data["allowed_totals"]))


class AddOns(unittest.TestCase):
    """The database, the secret store and the failover Redis are priced on the platform that was chosen, never with another provider's price."""

    def run_plan(self, platform, answers, **kw):
        s = scan_one(**kw)
        _, data = build_cost_estimate(s)
        return s, data, planner.choose_plan(s, answers, only(platform, data))

    def test_aws_single_database_and_secrets(self):
        s, data, plan = self.run_plan("aws_fargate", {BUDGET: "500", DOWNTIME: "A few minutes", DB: "managed Postgres"})
        base = option(data["plan_options"], "aws_fargate", 1)["total"]
        db = eur(0.019 * H + 0.137 * 20)
        secrets = eur(10 * 0.40)
        self.assertAlmostEqual(plan["total"], base + db + secrets, delta=0.02)
        self.assertTrue(any("Amazon RDS" in n and "db.t4g.micro" in n for n in plan["notes"]), plan["notes"])
        self.assertFalse(any("Cloud SQL" in n or "Secret Manager" in n for n in plan["notes"]), plan["notes"])

    def test_aws_zero_downtime_uses_a_multi_az_database(self):
        s, data, plan = self.run_plan("aws_fargate", {BUDGET: "500", DOWNTIME: "None (zero downtime)", DB: "managed Postgres"})
        base = option(data["plan_options"], "aws_fargate", 2)["total"]
        self.assertAlmostEqual(plan["total"], base + eur(0.149 * H + 0.274 * 20) + eur(10 * 0.40), delta=0.02)
        self.assertTrue(any("Multi-AZ" in n for n in plan["notes"]), plan["notes"])

    def test_azure_single_and_high_availability_database(self):
        _, data, one = self.run_plan("azure_container_apps", {BUDGET: "500", DOWNTIME: "A few minutes", DB: "managed Postgres"})
        self.assertAlmostEqual(one["total"], option(data["plan_options"], "azure_container_apps", 1)["total"]
                               + eur(0.0199 * H + 0.1369 * 32) + eur(0.03), delta=0.02)
        self.assertTrue(any("Azure Database for PostgreSQL" in n and "B1ms" in n and "Key Vault" in n for n in one["notes"]), one["notes"])
        _, data, ha = self.run_plan("azure_container_apps", {BUDGET: "900", DOWNTIME: "None (zero downtime)", DB: "managed Postgres"})
        self.assertAlmostEqual(ha["total"], option(data["plan_options"], "azure_container_apps", 2)["total"]
                               + eur(2 * (0.212 * H + 0.1369 * 32)) + eur(0.03), delta=0.02)
        self.assertTrue(any("high availability" in n and "standby is billed like the primary" in n for n in ha["notes"]), ha["notes"])

    def test_a_managed_redis_replaces_the_in_cluster_one_on_each_platform(self):
        ans = {BUDGET: "900", DOWNTIME: "None (zero downtime)"}
        for plat, ha_hour, fn in (("aws_fargate", None, lambda c, m: (c * 0.04656 + m * 0.00511) * H),
                                  ("azure_container_apps", None, lambda c, m: (c * 0.000034 + m * 0.000004) * S)):
            s, data, plan = self.run_plan(plat, ans, redis=True)
            base = option(data["plan_options"], plat, 2)["total"]
            managed = eur(2 * 0.036 * H) if plat == "aws_fargate" else 0.1214 * H
            self.assertAlmostEqual(plan["total"], base + managed - eur(fn(0.07, 0.2)), delta=0.05, msg=plat)
            self.assertTrue(any(("ElastiCache" in n) if plat == "aws_fargate" else ("Azure Cache for Redis" in n) for n in plan["notes"]), plan["notes"])

    def test_google_database_numbers_and_wording_are_unchanged(self):
        s = scan_one(k8s=True)
        _, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, {BUDGET: "500", DOWNTIME: "None (zero downtime)", DB: "managed Postgres"}, data)
        self.assertTrue(plan["chosen"]["platform"].startswith("gke"))
        self.assertTrue(any("dedicated 1 vCPU / 3.75 GiB" in n and "Secret Manager" in n for n in plan["notes"]), plan["notes"])
        self.assertAlmostEqual(plan["total"], plan["chosen"]["total"] + plan["meta"]["sql_dedicated_ha"] + plan["meta"]["secret_manager"], delta=0.02)

    def test_the_unknown_database_line_uses_the_chosen_platforms_own_numbers(self):
        _, _, plan = self.run_plan("aws_fargate", {BUDGET: "500", DOWNTIME: "A few minutes"})
        line = next(x for x in planner.describe(plan) if x.startswith("Database: no usable answer"))
        self.assertIn("Amazon RDS", line)
        self.assertNotIn("Cloud SQL", line)

    def test_every_add_on_figure_may_appear_in_the_text(self):
        _, _, plan = self.run_plan("azure_container_apps", {BUDGET: "500", DOWNTIME: "A few minutes"})
        allowed = planner.allowed_numbers(plan)
        for plat, ad in plan["meta"]["addons"].items():
            for k in ("db", "db_ha", "secrets"):
                self.assertIn(round(ad[k], 2), allowed, (plat, k))


class PlannerChoice(unittest.TestCase):
    def test_the_cheapest_single_copy_option_wins_when_there_is_no_kubernetes_in_the_repo(self):
        s = scan_one()
        _, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, {BUDGET: "500", DOWNTIME: "A few minutes"}, data)
        cheapest = min(o["total"] for o in data["plan_options"] if o["replicas"] == 1 and o["set"] == "all")
        self.assertAlmostEqual(plan["total"], cheapest, places=2)

    def test_a_repo_with_kubernetes_manifests_stays_on_google_kubernetes(self):
        s = scan_one(k8s=True)
        _, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, {BUDGET: "500", DOWNTIME: "A few minutes"}, data)
        self.assertTrue(plan["chosen"]["platform"].startswith("gke"))

    def test_aws_and_azure_options_show_up_as_alternatives(self):
        s = scan_one(k8s=True)
        _, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, {BUDGET: "500", DOWNTIME: "None (zero downtime)"}, data)
        labels = " | ".join(a["label"] for a in plan["alternatives"])
        self.assertTrue("AWS ECS Fargate" in labels or "Azure Container Apps" in labels, labels)

    def test_the_words_about_what_is_included_have_no_prices_in_them(self):
        for plat in ("aws_fargate", "azure_container_apps"):
            for r in (1, 2):
                lines = planner._platform_lines({"platform": plat, "zone_ha": r == 2})
                self.assertTrue(lines, plat)
                for line in lines:
                    self.assertNotRegex(line, r"\d+\.\d\d", line)
        self.assertEqual(planner._platform_lines({"platform": "gke_autopilot", "zone_ha": True}), [])

    def test_zone_placement_advice_only_when_the_option_is_zone_level(self):
        self.assertEqual(len(planner._platform_lines({"platform": "aws_fargate", "zone_ha": False})), 1)
        two = planner._platform_lines({"platform": "aws_fargate", "zone_ha": True})
        self.assertEqual(len(two), 2)
        self.assertIn("availability zones", two[1])
        az = planner._platform_lines({"platform": "azure_container_apps", "zone_ha": True})
        self.assertIn("zone redundancy", az[1])

    def test_the_decision_text_for_azure_says_the_price_is_the_full_active_rate(self):
        s = scan_one()
        _, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, {BUDGET: "500", DOWNTIME: "A few minutes"}, only("azure_container_apps", data))
        text = " ".join(planner.describe(plan))
        self.assertIn("full active rate", text)
        self.assertIn("free grant", text)


class ReportTables(unittest.TestCase):
    def setUp(self):
        self.text, self.data = build_cost_estimate(scan_one(redis=True))

    def test_the_per_service_table_has_frankfurt_and_west_europe_columns_and_no_us_east(self):
        self.assertIn("AWS Fargate (Frankfurt)", self.text)
        self.assertIn("Azure Container Apps (West Europe)", self.text)
        self.assertNotIn("US East", self.text)
        self.assertNotIn("AWS Fargate*", self.text)

    def test_the_total_row_adds_up(self):
        row = next(l for l in self.text.splitlines() if l.startswith("| **Total**"))
        cells = [c.strip().strip("*") for c in row.strip("|").split("|")]
        fargate = eur(((0.25 + 0.07) * 0.04656 + (0.5 + 0.2) * 0.00511) * H)
        aca = eur(((0.25 + 0.07) * 0.000034 + (0.5 + 0.2) * 0.000004) * S)
        self.assertAlmostEqual(float(cells[5]), fargate, places=2)
        self.assertAlmostEqual(float(cells[6]), aca, places=2)

    def test_the_active_rate_caveat_is_in_the_report(self):
        self.assertIn("full ACTIVE rate", self.text)
        self.assertIn("neither is subtracted", self.text)

    def test_new_fixed_rows_carry_the_provider_figures(self):
        rows = {l.split("|")[1].strip(): l.split("|")[2].strip() for l in self.text.splitlines() if l.startswith("| ") and l.count("|") >= 4}
        def row(start):
            return next(v for k, v in rows.items() if k.startswith(start))
        self.assertEqual(row("AWS Application Load Balancer"), f"{eur(0.027 * H):.2f}")
        self.assertEqual(row("AWS public IPv4 address"), f"{eur(0.005 * H):.2f}")
        self.assertEqual(row("Amazon RDS for PostgreSQL db.t4g.micro"), f"{eur(0.019 * H + 0.137 * 20):.2f}")
        self.assertEqual(row("Amazon RDS for PostgreSQL db.t4g.medium Multi-AZ"), f"{eur(0.149 * H + 0.274 * 20):.2f}")
        self.assertEqual(row("AWS Secrets Manager"), f"{eur(4.0):.2f}")
        self.assertEqual(row("Amazon ElastiCache Redis"), f"{eur(2 * 0.036 * H):.2f}")
        self.assertEqual(row("Azure Database for PostgreSQL Burstable B1ms"), f"{eur(0.0199 * H + 0.1369 * 32):.2f}")
        self.assertEqual(row("Azure Database for PostgreSQL General Purpose 2 vCore"), f"{eur(2 * (0.212 * H + 0.1369 * 32)):.2f}")
        self.assertEqual(row("Hetzner load balancer LB11"), "7.49")

    def test_ready_made_totals_list_the_aws_and_azure_setups(self):
        labels = [l for l, _ in self.data["scenarios"]]
        self.assertTrue(any(l.startswith("AWS ECS Fargate, 1 task per service") for l in labels))
        self.assertTrue(any(l.startswith("Azure Container Apps, 2 replicas per service") for l in labels))


class LoadTiers(unittest.TestCase):
    def test_tier_prices_start_at_the_plans_total_and_never_fall_on_every_platform(self):
        s = scan_one()
        _, data = build_cost_estimate(s)
        workloads = ce._workloads(s)[0]
        for plat in ("gke_autopilot", "cloud_run", "aws_fargate", "azure_container_apps"):
            plan = planner.choose_plan(s, {BUDGET: "5000", DOWNTIME: "None (zero downtime)"}, only(plat, data))
            totals = [load_tiers.price_tier(rep, plan, workloads, ce)[0] for _, _, _, rep in load_tiers.TIERS]
            self.assertAlmostEqual(totals[0], plan["total"], places=1, msg=plat)
            self.assertEqual(totals, sorted(totals), plat)
            self.assertGreater(totals[-1], totals[0], plat)

    def test_aws_charges_for_the_extra_public_addresses_of_a_bigger_tier(self):
        s = scan_one()
        _, data = build_cost_estimate(s)
        workloads = ce._workloads(s)[0]
        plan = planner.choose_plan(s, {BUDGET: "5000", DOWNTIME: "None (zero downtime)"}, only("aws_fargate", data))
        top = load_tiers.TIERS[-1][3]
        total, pods, _ = load_tiers.price_tier(top, plan, workloads, ce)
        cpu, mem, r = pods["web"]
        compute = eur((cpu * 0.04656 + mem * 0.00511) * H * r)
        fixed = eur((0.027 + 2 * 0.005) * H + r * 0.005 * H)
        self.assertAlmostEqual(total, compute + fixed, places=1)


class Cards(unittest.TestCase):
    def setUp(self):
        import tempfile
        from scanner.scan import scan_repo
        from nodes.gap_identifier import identify_gaps
        from generators import build_targets
        from test_targets import make_app
        self.tmp = tempfile.TemporaryDirectory()
        self.scan = scan_repo(make_app(self.tmp.name))
        plan = {"chosen": {"label": "Azure Container Apps, 2 replicas per service, 1 service, no separate load balancer", "platform": "azure_container_apps",
                           "total": 52.0, "zone_ha": True},
                "total": 52.0, "notes": [], "budget": 100.0, "uptime": "zero", "status": "fits", "small_server": None,
                "alternatives": [{"label": "AWS ECS Fargate, 2 tasks per service, 1 service, 1 Application Load Balancer", "total": 61.0, "zone_ha": True, "notes": []},
                                 {"label": "GKE Autopilot, 2 replicas per service, 1 service, 1 load balancer", "total": 40.0, "zone_ha": True, "notes": []}]}
        self.ts = {t["id"]: t for t in build_targets(self.scan, plan, identify_gaps(self.scan))}

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_new_option_has_its_own_profile_provider_and_price_note(self):
        az, aws, gke = self.ts["plan-0"], self.ts["plan-1"], self.ts["plan-2"]
        self.assertEqual((az["profile"], az["provider"]), ("azure_container_apps", "Azure"))
        self.assertEqual((aws["profile"], aws["provider"]), ("aws_fargate", "AWS"))
        self.assertEqual(gke["profile"], "gke_autopilot")
        self.assertIn("West Europe", az["price_note"])
        self.assertIn("Frankfurt", aws["price_note"])
        self.assertNotIn("price_note", gke)
        self.assertIn(prices.RETRIEVED_PLATFORMS, az["price_note"])

    def test_cards_have_benefits_drawbacks_and_links_on_the_providers_own_sites(self):
        for tid, host in (("plan-0", "azure.microsoft.com"), ("plan-1", "aws.amazon.com")):
            t = self.ts[tid]
            self.assertTrue(t["benefits"] and t["drawbacks"] and t["links"], tid)
            for l in t["links"]:
                u = urlparse(l["url"])
                self.assertEqual((u.scheme, u.hostname), ("https", host), l)
            self.assertFalse(t["files"])                         # no infrastructure files for them yet, and the card says so
            self.assertIn("No infrastructure files", t["note"])
            self.assertTrue(any("one zone" in b for b in t["benefits"]), t["benefits"])

    def test_the_brief_for_the_choice_states_the_cost_basis(self):
        brief = self.ts["plan-0"]["brief"]
        self.assertIn("52.00 EUR per month", brief)
        self.assertIn("full running rate", brief)
        self.assertIn("Container Apps pricing", brief)

    def test_other_cloud_is_still_there_for_everything_else(self):
        self.assertIn("other-cloud", self.ts)
        self.assertEqual(self.ts["other-cloud"]["profile"], "other-cloud")



class Comparison(unittest.TestCase):
    def test_the_alternatives_show_the_cheapest_setup_of_every_platform(self):
        s = scan_one(k8s=True)
        _, data = build_cost_estimate(s)
        plan = planner.choose_plan(s, {BUDGET: "500", DOWNTIME: "A few minutes"}, data)
        platforms = {plan["chosen"]["platform"]} | {a["platform"] for a in plan["alternatives"]}
        self.assertEqual(platforms, {"gke_autopilot", "cloud_run", "aws_fargate", "azure_container_apps"})
        self.assertLessEqual(len(plan["alternatives"]), 4)
        self.assertEqual([a["total"] for a in plan["alternatives"]], sorted(a["total"] for a in plan["alternatives"]))


if __name__ == "__main__":
    unittest.main()
