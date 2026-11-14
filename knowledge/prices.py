"""Published cloud prices, copied from the providers' own pricing pages.

RULES FOR THIS FILE
- Every entry carries its source URL, the date it was read, and the region it applies to.
- If a price could not be read from an official page, it is NOT here. It goes in NOT_PRICED
  so the report says "no verified price" instead of guessing.
- Prices change. Re-check every entry when RETRIEVED is more than ~3 months old."""

RETRIEVED = "2026-10-24"
USD_PER_EUR = 1.1537          # Banca d'Italia/ECB reference rate
USD_PER_EUR_DATE = "2026-09-16"
HOURS_PER_MONTH = 730
SECONDS_PER_MONTH = HOURS_PER_MONTH * 3600

SRC_RUN = "https://cloud.google.com/run/pricing"
SRC_GKE = "https://cloud.google.com/kubernetes-engine/pricing"
SRC_SQL = "https://cloud.google.com/sql/pricing"
SRC_REDIS = "https://cloud.google.com/memorystore/docs/redis/pricing"
SRC_NET = "https://cloud.google.com/vpc/network-pricing"
SRC_SECRET = "https://cloud.google.com/secret-manager/pricing"
SRC_FARGATE = "https://aws.amazon.com/fargate/pricing/"
SRC_ALB = "https://aws.amazon.com/elasticloadbalancing/pricing/"
SRC_EKS = "https://aws.amazon.com/eks/pricing/"
SRC_HETZNER = "https://www.hetzner.com/cloud/regular-performance/"

# ---- USD prices ---------------------------------------------------------------------
PRICES_USD = {
    # Google Cloud Run, Tier 1 region (includes europe-west1)
    "cloud_run_cpu_per_vcpu_second_instance_based": (0.000018, "Cloud Run, Tier 1 (europe-west1)", SRC_RUN),
    "cloud_run_mem_per_gib_second_instance_based": (0.000002, "Cloud Run, Tier 1 (europe-west1)", SRC_RUN),
    "cloud_run_per_million_requests_request_based": (0.40, "Cloud Run, Tier 1 (europe-west1)", SRC_RUN),
    # GKE
    "gke_cluster_fee_per_hour": (0.10, "any region, Standard and Autopilot", SRC_GKE),
    "gke_free_credit_per_month": (74.40, "per billing account; covers ONE zonal cluster only", SRC_GKE),
    "gke_autopilot_vcpu_hour": (0.0445, "Autopilot container-optimized default (regional rates vary)", SRC_GKE),
    "gke_autopilot_gib_hour": (0.0049225, "Autopilot container-optimized default (regional rates vary)", SRC_GKE),
    # AWS
    "fargate_x86_vcpu_hour": (0.0404784, "US East (N. Virginia) -- NOT an EU price", SRC_FARGATE),
    "fargate_x86_gb_hour": (0.004446, "US East (N. Virginia) -- NOT an EU price", SRC_FARGATE),
    "eks_cluster_fee_per_hour": (0.10, "standard support", SRC_EKS),
    "alb_per_hour": (0.0225, "US East (N. Virginia) -- NOT an EU price", SRC_ALB),
    "alb_per_lcu_hour": (0.008, "US East (N. Virginia) -- NOT an EU price", SRC_ALB),
    # Google managed data stores (region not confirmed on the page)
    "cloud_sql_db_g1_small_hour": (0.035, "region not stated on page; shared-core, no SLA", SRC_SQL),
    "cloud_sql_db_g1_small_ha_hour": (0.07, "region not stated on page; shared-core, no SLA", SRC_SQL),
    # dedicated-core Enterprise instances, Iowa rates as shown on the page; high availability is exactly 2x (the page says so)
    "cloud_sql_dedicated_vcpu_hour": (0.0413, "Iowa (us-central1), Enterprise edition -- NOT an EU price", SRC_SQL),
    "cloud_sql_dedicated_gib_hour": (0.007, "Iowa (us-central1), Enterprise edition -- NOT an EU price", SRC_SQL),
    "cloud_sql_db_f1_micro_hour": (0.0105, "region not stated on page; shared-core, no SLA", SRC_SQL),
    "cloud_sql_ssd_gib_hour": (0.000232877, "region not stated on page", SRC_SQL),
    "cloud_sql_backup_gib_hour": (0.000109589, "region not stated on page", SRC_SQL),
    "memorystore_redis_basic_1_4gib_per_gib_hour": (0.049, "Iowa (us-central1) -- NOT an EU price", SRC_REDIS),
    "memorystore_redis_standard_1_4gib_per_gib_hour": (0.064, "Iowa (us-central1) -- NOT an EU price", SRC_REDIS),
    # Google networking / secrets
    "gcp_lb_forwarding_rule_hour_first5": (0.025, "per project", SRC_NET),
    "gcp_lb_data_processed_per_gib": (0.008, "regional load balancing", SRC_NET),
    "gcp_internet_egress_per_gib_to_europe_1_to_1024gib": (0.12, "Premium tier, destination Europe", SRC_NET),
    "secret_manager_per_version_month": (0.06, "first 6 versions free per billing account", SRC_SECRET),
    "secret_manager_per_10k_access": (0.03, "first 10,000 free per month", SRC_SECRET),
}

# ---- Azure, EUR, West Europe -- from Azure's own public Retail Prices API -------------
SRC_AZURE_API = "https://prices.azure.com/api/retail/prices"
PRICES_EUR_AZURE = {
    "aks_standard_uptime_sla_cluster_fee_per_hour": (0.088, "West Europe, paid tier with SLA", SRC_AZURE_API),
    "aks_free_tier_cluster_fee_per_hour": (0.0, "Free tier: no SLA, you pay only for node VMs", "https://azure.microsoft.com/en-us/pricing/details/kubernetes-service/"),
    "azure_redis_basic_c1_1gb_per_hour": (0.0484, "West Europe, single node, no SLA", SRC_AZURE_API),
    "azure_redis_standard_c1_1gb_per_hour": (0.1214, "West Europe, replicated pair; the API also lists a 0.0607 'instance' row, 0.1214 is taken as the pair total", SRC_AZURE_API),
    "container_apps_requests_per_million": (0.4928, "West Europe, Consumption plan", SRC_AZURE_API),
    "container_apps_dedicated_vcpu_hour": (0.0712, "West Europe, Dedicated plan", SRC_AZURE_API),
    "container_apps_dedicated_gib_hour": (0.0058, "West Europe, Dedicated plan", SRC_AZURE_API),
    "container_apps_dedicated_plan_management_hour": (0.088, "West Europe, Dedicated plan", SRC_AZURE_API),
}

# ---- Hetzner (EUR, EXCLUDING VAT) ----------------------------------------------------
# (name, vCPU, RAM GB, SSD GB, EUR/month excl. VAT, EU locations, line)
HETZNER_SERVERS = [
    ("CPX02", 1, 1, 20, 6.49, "FSN1/NBG1/HEL1", "Regular Performance"),
    ("CPX12", 1, 2, 40, 11.99, "FSN1/NBG1/HEL1", "Regular Performance"),
    ("CPX22", 2, 4, 80, 19.99, "NBG1/HEL1", "Regular Performance"),
    ("CPX32", 4, 8, 160, 35.99, "NBG1/HEL1", "Regular Performance"),
    ("CPX42", 8, 16, 320, 69.99, "NBG1/HEL1", "Regular Performance"),
    ("CPX52", 12, 24, 480, 100.99, "NBG1/HEL1", "Regular Performance"),
    ("CPX62", 16, 32, 640, 130.49, "NBG1/HEL1", "Regular Performance"),
    ("CCX13", 2, 8, 80, 43.49, "FSN1/NBG1/HEL1", "General Purpose (dedicated vCPU)"),
    ("CCX23", 4, 16, 160, 86.49, "FSN1/NBG1/HEL1", "General Purpose (dedicated vCPU)"),
    ("CCX33", 8, 32, 240, 138.99, "FSN1/NBG1/HEL1", "General Purpose (dedicated vCPU)"),
]
HETZNER_SOURCES = [SRC_HETZNER, "https://www.hetzner.com/cloud/general-purpose/"]
HETZNER_NOTE = "EUR, excluding VAT (German VAT must be added). 20 TB traffic included on EU locations."

# ---- Things we could NOT read from an official page. Never estimate these silently. ----
NOT_PRICED = [
    "Azure Container Apps Consumption-plan vCPU/memory rates (the price API rounds them to 0.0000)",
    "Azure VMs for AKS nodes, Azure Database for PostgreSQL, Azure load balancers",
    "GKE Standard node VMs (Compute Engine e2 hourly prices did not load)",
    "Amazon RDS (PostgreSQL) instances and storage",
    "Amazon ElastiCache nodes",
    "NAT gateways (Google Cloud NAT and AWS)",
    "Hetzner load balancer",
    "Memorystore and Fargate prices for EU regions (only Iowa / US East were readable)",
    "Internet egress for your real traffic (rate is listed, volume is unknown)",
    "Any LLM API token costs (depend on the model and your usage)",
]
