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
# AWS machine-readable price lists, region eu-central-1 (Frankfurt), read RETRIEVED_PLATFORMS (offer versions are in the URLs)
_AWS_OFFERS = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws"
SRC_AWS_ECS_LIST = f"{_AWS_OFFERS}/AmazonECS/20261111234623/eu-central-1/index.json"
SRC_AWS_ELB_LIST = f"{_AWS_OFFERS}/AWSELB/20261111153621/eu-central-1/index.json"
SRC_AWS_RDS_LIST = f"{_AWS_OFFERS}/AmazonRDS/20261113215233/eu-central-1/index.json"
SRC_AWS_CACHE_LIST = f"{_AWS_OFFERS}/AmazonElastiCache/20261113003443/eu-central-1/index.json"
SRC_AWS_SECRETS_LIST = f"{_AWS_OFFERS}/AWSSecretsManager/20261111195606/eu-central-1/index.json"
SRC_AWS_VPC_LIST = f"{_AWS_OFFERS}/AmazonVPC/20261105181945/eu-central-1/index.json"
# Azure's public Retail Prices API, armRegionName westeurope, priceType Consumption, requested in USD
SRC_AZURE_API_USD = "https://prices.azure.com/api/retail/prices?currencyCode='USD'"
SRC_AZURE_ACA_PAGE = "https://azure.microsoft.com/en-us/pricing/details/container-apps/"
SRC_AZURE_PG_HA = "https://learn.microsoft.com/en-us/azure/reliability/reliability-database-postgresql"
SRC_HETZNER_LB = "https://www.hetzner.com/cloud/load-balancer/"
RETRIEVED_PLATFORMS = "2026-11-14"

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
    # AWS, EU (Frankfurt) eu-central-1, on-demand, read RETRIEVED_PLATFORMS from AWS's own price lists (excl. VAT)
    "fargate_x86_vcpu_hour": (0.04656, "EU (Frankfurt), Linux/x86, on-demand", SRC_AWS_ECS_LIST),
    "fargate_x86_gb_hour": (0.00511, "EU (Frankfurt), Linux/x86, on-demand", SRC_AWS_ECS_LIST),
    "eks_cluster_fee_per_hour": (0.10, "standard support", SRC_EKS),
    "alb_per_hour": (0.027, "EU (Frankfurt), Application Load Balancer, fixed hourly part", SRC_AWS_ELB_LIST),
    "alb_per_lcu_hour": (0.008, "EU (Frankfurt), used LCU; depends on traffic, so it is NOT in the totals", SRC_AWS_ELB_LIST),
    "aws_public_ipv4_per_hour": (0.005, "EU (Frankfurt), per in-use public IPv4 address", SRC_AWS_VPC_LIST),
    "aws_secrets_manager_per_secret_month": (0.40, "EU (Frankfurt), per secret per month, before API calls", SRC_AWS_SECRETS_LIST),
    "rds_pg_db_t4g_micro_single_az_hour": (0.019, "EU (Frankfurt), RDS for PostgreSQL db.t4g.micro (2 vCPU, 1 GiB), Single-AZ", SRC_AWS_RDS_LIST),
    "rds_pg_db_t4g_medium_multi_az_hour": (0.149, "EU (Frankfurt), RDS for PostgreSQL db.t4g.medium (2 vCPU, 4 GiB), Multi-AZ", SRC_AWS_RDS_LIST),
    "rds_pg_gp3_gb_month_single_az": (0.137, "EU (Frankfurt), RDS for PostgreSQL gp3 storage, Single-AZ", SRC_AWS_RDS_LIST),
    "rds_pg_gp3_gb_month_multi_az": (0.274, "EU (Frankfurt), RDS for PostgreSQL gp3 storage, Multi-AZ", SRC_AWS_RDS_LIST),
    "elasticache_redis_t4g_small_node_hour": (0.036, "EU (Frankfurt), ElastiCache cache.t4g.small (1.37 GiB), Redis OSS, per node", SRC_AWS_CACHE_LIST),
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
    # Azure, West Europe, read RETRIEVED_PLATFORMS from Azure's Retail Prices API in USD (the EUR figure rounds the Container Apps rates to zero)
    "container_apps_vcpu_second_active": (0.000034, "West Europe, Consumption plan, ACTIVE rate (the idle rate is lower)", SRC_AZURE_API_USD),
    "container_apps_gib_second_active": (0.000004, "West Europe, Consumption plan, ACTIVE rate", SRC_AZURE_API_USD),
    "container_apps_per_million_requests": (0.56, "West Europe, Consumption plan; the first 2 million per month are free", SRC_AZURE_ACA_PAGE),
    "azure_pg_flex_b1ms_hour": (0.0199, "West Europe, Burstable B1ms (1 vCore, 2 GiB); no high availability on this tier", SRC_AZURE_API_USD),
    "azure_pg_flex_gp_2vcore_ddsv5_hour": (0.212, "West Europe, General Purpose Ddsv5 2 vCore (8 GiB)", SRC_AZURE_API_USD),
    "azure_pg_flex_storage_gb_month": (0.1369, "West Europe, provisioned storage", SRC_AZURE_API_USD),
    "azure_key_vault_per_10k_operations": (0.03, "Standard tier; there is no monthly fee per secret", SRC_AZURE_API_USD),
}

# ---- Azure, EUR, West Europe -- from Azure's own public Retail Prices API -------------
SRC_AZURE_API = "https://prices.azure.com/api/retail/prices"
PRICES_EUR_AZURE = {
    "aks_standard_uptime_sla_cluster_fee_per_hour": (0.088, "West Europe, paid tier with SLA", SRC_AZURE_API),
    "aks_free_tier_cluster_fee_per_hour": (0.0, "Free tier: no SLA, you pay only for node VMs", "https://azure.microsoft.com/en-us/pricing/details/kubernetes-service/"),
    "azure_redis_basic_c1_1gb_per_hour": (0.0484, "West Europe, single node, no SLA", SRC_AZURE_API),
    "azure_redis_standard_c1_1gb_per_hour": (0.1214, "West Europe, replicated pair; the API also lists a 0.0607 'instance' row, 0.1214 is taken as the pair total", SRC_AZURE_API),
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
# Hetzner Cloud load balancers (EUR/month excl. VAT), read RETRIEVED_PLATFORMS from SRC_HETZNER_LB. A single Hetzner server does not need one.
HETZNER_LOAD_BALANCERS = [("LB11", 7.49), ("LB21", 21.49), ("LB31", 42.99)]
HETZNER_NOTE = "EUR, excluding VAT (German VAT must be added). 20 TB traffic included on EU locations."

# ---- One server on AWS or Azure (EU) -------------------------------------------------
# Read on RETRIEVED_VM from each provider's own machine-readable price list, not from a web page:
#   AWS:   the Price List offer files, region eu-central-1 (Frankfurt), on-demand, Linux, shared tenancy
#          EC2 offer version 20261114012926 (published 2026-11-14), VPC offer version 20261105181945 (published 2026-11-05)
#   Azure: the public Retail Prices API, armRegionName westeurope, priceType Consumption, currency EUR
# AWS prices are in USD and converted at USD_PER_EUR above (same rule as every other USD price in this file). Excluding VAT.
RETRIEVED_VM = "2026-11-14"
SRC_EC2_LIST = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonEC2/20261114012926/eu-central-1/index.json"
SRC_VPC_LIST = "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonVPC/20261105181945/eu-central-1/index.json"
SRC_EC2_PAGE = "https://aws.amazon.com/ec2/pricing/on-demand/"
SRC_AZURE_VM_PAGE = "https://azure.microsoft.com/en-us/pricing/details/virtual-machines/linux/"

# name -> (vCPU, RAM GiB, USD per hour). T3 is a burstable family.
AWS_EC2_LINUX_USD_PER_HOUR = {
    "t3.micro": (2, 1, 0.012),
    "t3.small": (2, 2, 0.024),
    "t3.medium": (2, 4, 0.048),
    "t3.large": (2, 8, 0.096),
    "t3.xlarge": (4, 16, 0.192),
}
AWS_GP3_USD_PER_GB_MONTH = 0.0952        # EBS General Purpose (gp3) storage, Frankfurt
AWS_PUBLIC_IPV4_USD_PER_HOUR = 0.005     # in-use public IPv4 address, Frankfurt
AWS_DISK_GB = 20

# size -> (vCPU, RAM GiB, EUR per hour). B-series is burstable.
AZURE_VM_LINUX_EUR_PER_HOUR = {
    "Standard_B1s": (1, 1, 0.0108),
    "Standard_B1ms": (1, 2, 0.0215),
    "Standard_B2s": (2, 4, 0.0431),
    "Standard_B2ms": (2, 8, 0.0862),
    "Standard_B4ms": (4, 16, 0.1724),
}
AZURE_SSD_E4_EUR_PER_MONTH = 2.1545      # Standard SSD E4 LRS, 32 GiB (disk operations are billed separately and not included)
AZURE_PUBLIC_IP_EUR_PER_HOUR = 0.0045    # Standard IPv4 static public IP
AZURE_DISK_GB = 32


def _aws_servers():
    """Same row shape as HETZNER_SERVERS: (name, vCPU, RAM GiB, disk GB, EUR/month excl. VAT, region, line). The price is the server, a 20 GB gp3 disk and one public IPv4 address."""
    out = []
    for name, (vcpu, ram, hour) in AWS_EC2_LINUX_USD_PER_HOUR.items():
        usd = hour * HOURS_PER_MONTH + AWS_GP3_USD_PER_GB_MONTH * AWS_DISK_GB + AWS_PUBLIC_IPV4_USD_PER_HOUR * HOURS_PER_MONTH
        out.append((name, vcpu, ram, AWS_DISK_GB, round(usd / USD_PER_EUR, 2), "eu-central-1", "EC2 T3 (burstable), Linux, on-demand"))
    return out


def _azure_servers():
    out = []
    for name, (vcpu, ram, hour) in AZURE_VM_LINUX_EUR_PER_HOUR.items():
        eur = hour * HOURS_PER_MONTH + AZURE_SSD_E4_EUR_PER_MONTH + AZURE_PUBLIC_IP_EUR_PER_HOUR * HOURS_PER_MONTH
        out.append((name, vcpu, ram, AZURE_DISK_GB, round(eur, 2), "westeurope", "B-series (burstable), Linux, pay-as-you-go"))
    return out


AWS_SERVERS = _aws_servers()
AZURE_SERVERS = _azure_servers()
AWS_NOTE = ("EUR (converted from USD), excluding VAT. The price is one server, a 20 GB gp3 disk and one public IPv4 address, all on-demand. Not included: traffic out of AWS "
            "beyond the free allowance, backups, load balancers, databases. T3 servers are burstable: sustained heavy CPU use can add charges.")
AZURE_NOTE = ("EUR, excluding VAT. The price is one server, a 32 GiB Standard SSD disk and one static public IPv4 address, pay-as-you-go. Not included: traffic out of Azure beyond "
              "the free allowance, disk operations, backups, load balancers, databases. B-series servers are burstable.")

# ---- Things we could NOT read from an official page. Never estimate these silently. ----
NOT_PRICED = [
    "Azure VMs for AKS nodes, and the worker nodes of AKS and EKS (node-based Kubernetes on AWS and Azure is not priced; the AWS and Azure setups priced here are ECS Fargate and Container Apps)",
    "GKE Standard node VMs (Compute Engine e2 hourly prices did not load)",
    "NAT gateways (Google Cloud NAT and AWS): the AWS Fargate setup is priced with tasks in public subnets, each with its own public IPv4 address, so no NAT gateway is in the totals",
    "Azure load balancers: Container Apps has its own HTTPS entry point, so no separate Azure load balancer is in the totals",
    "Azure Container Apps request charges and the monthly free grants (traffic is unknown; the compute is priced at the full active rate, so it is an upper bound)",
    "AWS load balancer capacity units (LCU) and Azure PostgreSQL / RDS / ElastiCache sizes other than the ones named in the tables (your real size depends on your data and load)",
    "Memorystore and Cloud SQL prices for EU regions (only Iowa or region-not-stated rows were readable)",
    "Internet egress for your real traffic (rate is listed, volume is unknown)",
    "Any LLM API token costs (depend on the model and your usage)",
]
