## In your situation

This is a pre-launch microservices application with 12 services, and the recommended GKE Autopilot setup at 135.46 EUR/month fits your 150 EUR budget with 14.54 EUR to spare. The setup runs two copies of each service across multiple zones, designed to survive a zone failure. Your zero-downtime and zero-data-loss requirements are not fully met by the repo: no PodDisruptionBudget or autoscaler exists, and the in-cluster Redis has no persistent volume. The most important gaps are: tracing exists but there are no metrics or alerting to warn you of problems, 7 of 12 services have no tests, and the committed Terraform variable file may contain sensitive values.

_Written by an AI model from the report below; every number was checked against it._

## 1. What this project is

The scan found a deployable application with 12 services in Go, Python, C#, and JavaScript. Infrastructure tooling includes Helm, Kubernetes manifests, Kustomize, Skaffold, and Terraform. An in-cluster Redis instance is deployed by default.

Confidence: high on what the repository contains. The scan found its services, dependencies and deployment files directly.

## 2. What's missing for production

| # | Gap | Severity | Source | Risk and evidence |
| --- | --- | --- | --- | --- |
| 1 | Tracing without metrics or alerting | Medium | Checked in your repo by the scan | Tracing instrumentation was found, but no metrics library or alerting/monitoring config -- nothing in the repo would warn you before users notice a problem. |
| 2 | In-cluster redis has no persistent volume (data lost on restart) | Medium | Checked in your repo by the scan | A redis instance runs inside the cluster with no persistent volume (data lives only as long as the pod) -- a restart loses its data. Fine if it is only a cache; if it holds queues or sessions you cannot lose, add a volume or use a managed service. |
| 3 | Some services have no tests | Medium | Checked in your repo by the scan | 7 of 12 services have no test files: src/adservice, src/currencyservice, src/emailservice, src/loadgenerator, src/paymentservice, src/recommendationservice, src/shoppingassistantservice. |
| 4 | No PodDisruptionBudget or autoscaler | Medium | Checked in your repo by the scan | No PodDisruptionBudget or autoscaler found -- node upgrades can take all replicas down at once and traffic spikes are not absorbed automatically. |
| 5 | Terraform provider lock file missing | Low | Checked in your repo by the scan | No .terraform.lock.hcl is committed -- provider versions can change between runs. |
| 6 | Containers run as root | Low | Checked in your repo by the scan | most of the 12 analysed Dockerfiles never switch to a non-root USER (e.g. src/loadgenerator/Dockerfile, src/emailservice/Dockerfile, src/productcatalogservice/Dockerfile) -- Kubernetes manifests set runAsNonRoot for most workloads, which mitigates this when deployed there. |
| 7 | Base images are not pinned to a version | Low | Checked in your repo by the scan | some of the Dockerfiles use a base image without a version tag or digest (latest) (e.g. src/productcatalogservice/Dockerfile, src/frontend/Dockerfile, src/shippingservice/Dockerfile) -- builds are not reproducible and can break or change silently. |
| 8 | No .dockerignore | Low | Checked in your repo by the scan | Dockerfiles exist but there is no .dockerignore at the repository root (none found for src/adservice, src/emailservice, src/loadgenerator and more) -- build contexts may ship .git, local env files or large folders into images. |
| 9 | CI has no security scanning step | Low | Checked in your repo by the scan | No dependency, image, secret or code scanning step (e.g. CodeQL, Trivy, Snyk, gitleaks) was found in the CI pipelines. |

## 3. Recommended architecture and deployment

GKE Autopilot with 2 replicas per service spreads workloads across zones, designed to survive a zone outage without going fully down. The managed Redis with failover replaces the in-cluster Redis so cart and session data can survive a node failure. At 135.46 EUR/month it fits your 150 EUR budget. The loadgenerator is demo tooling and is excluded from the recommendation. A cheaper option at 97.54 EUR/month keeps the in-cluster Redis with a persistent volume, but that remains a single copy on one node. A load test is needed to confirm the pod sizes work for your actual services.

## 4. Estimated Monthly Cost (computed in code)

- Recommended setup: GKE Autopilot, 2 replicas per service, 11 services + redis-cart (in-cluster, one copy) (without loadgenerator), 1 load balancer + managed Redis Standard with failover instead of the in-cluster Redis (Memorystore Iowa price; EU price not read) = 135.46 EUR/month.
- Against your budget of 150: 14.54 under budget.
- Availability: two or more copies of every service, spread over several zones of one region, so a pod, a node or a whole zone can fail without an outage. This is not multi-region: a full regional outage would still stop it. On GKE Autopilot the replicas are normally placed in different zones, but add a topologySpreadConstraints rule so this is guaranteed, not just likely.
- Database: no usable answer, so no database is in this total. A single small Cloud SQL instance would add 23.62 EUR/month and a two-zone high-availability one 47.24 EUR/month (PostgreSQL rate).
- Cheaper variant: keep the in-cluster Redis and give it a persistent volume = 97.54 EUR/month. It stays a single copy on one node, so cart/session data can still be lost if that node fails.
- Left out on purpose (demo/test tooling, not part of production): loadgenerator.

| Setup | €/month | Survives a zone outage |
|---|---|---|
| **Recommended:** GKE Autopilot, 2 replicas per service, 11 services + redis-cart (in-cluster, one copy) (without loadgenerator), 1 load balancer + managed Redis Standard with failover instead of the in-cluster Redis (Memorystore Iowa price; EU price not read) | **135.46** | yes |
| Cloud Run always-on, 2 instances per service, 11 services + redis-cart (in-cluster, one copy) (without loadgenerator), 1 load balancer + managed Redis Standard with failover instead of the in-cluster Redis (Memorystore Iowa price; EU price not read) | 172.79 | yes |

_Not included: egress, NAT, monitoring, persistent disks beyond boot disks, LLM tokens, and any database you run yourself._

## Load-based sizing (rule of thumb, not measured)

You said: "3,000 monthly active users and 10,000 requests per month". Converted: 10,000 requests per month as stated = about 333 requests/day on average; busiest hour x2 (you said about the same, 1-2x) = about **667 requests/day at peak** = **tier 1 of 10 (Tiny)**.
With the growth you gave, the peak after 12 months is about 1,197 requests/day = tier 1 (Tiny).

| Tier | Name | Peak requests/second | Copies per service | Pod size | EUR/month at the top of the tier | |
|---|---|---|---|---|---|---|
| 1 | Tiny | up to 0.5 | 2 | 0.1-0.2 vCPU | 135.46 | your load at launch |
| 2 | Small | up to 2 | 2 | 0.1-0.2 vCPU | 135.46 |  |
| 3 | Light | up to 5 | 2 | 0.1-0.2 vCPU | 135.46 |  |
| 4 | Moderate | up to 15 | 2 | 0.1-0.2 vCPU | 135.46 |  |
| 5 | Busy | up to 40 | 2-4 | 0.1-0.2 vCPU | 190.60 |  |
| 6 | High | up to 100 | 4 | 0.25 vCPU | 400.31 |  |
| 7 | Heavy | up to 250 | 3 | 1 vCPU | 1088.29 |  |
| 8 | Very heavy | up to 600 | 3 | 2 vCPU | 2120.26 |  |
| 9 | Large | up to 1500 | 8 | 2 vCPU | 5560.17 |  |
| 10 | Very large | above 1,500 | 15 | 2 vCPU | 10376.05 |  |

For your load at launch the plan is **135.46 EUR/month** (GKE Autopilot, same fixed parts and database/Redis choices as section 4). Section 4 prices the repo's own pod sizes; this section adjusts them to your load.
Against your budget of 150: 14.54 under budget.

How these figures were made (assumptions, not measurements): one monthly user = 20 requests/day; one vCPU handles about 100 requests/second at 70% CPU; every service is sized as if it sees the full rate (an upper bound, backends usually see less); pods keep the repo's own size up to 4 copies, then the smallest of 0.25 / 0.5 / 1 / 2 vCPU that needs 4 or fewer copies (memory 1 GiB per vCPU, never below the repo's own); at most 100 copies. A load test of your real services replaces these assumptions.

## 5. What this report cannot tell you

- No usable database answer was given, so no database is included in the cost; a small Cloud SQL instance would add 23.62 EUR/month.
- Some managed-service prices are US prices because the EU price could not be read; actual EU pricing may differ.
- The report covers only what the scanner found in the repository; runtime behaviour, real load, and cloud account settings are not checked.
- The committed Terraform variable file was flagged but its contents were not read; check whether it contains credentials or project IDs.

## Appendix: price table (calculated from published prices, not estimated by the AI)

### Per-service compute price (always-on, 13 workloads)
_Sizing: CPU/memory requests read from the repo's Kubernetes manifests. Prices read from the providers' pages on 2026-10-24; USD converted to EUR at 1.1537 USD per EUR (2026-09-16 reference rate)._

| Service | vCPU | Memory GiB | GKE Autopilot €/mo | Cloud Run (always-on) €/mo | AWS Fargate* €/mo |
|---|---|---|---|---|---|
| adservice | 0.2 | 0.18 | 6.18 | 9.00 | 5.62 |
| cartservice | 0.2 | 0.06 | 5.83 | 8.49 | 5.30 |
| checkoutservice | 0.1 | 0.06 | 3.01 | 4.38 | 2.74 |
| currencyservice | 0.1 | 0.06 | 3.01 | 4.38 | 2.74 |
| emailservice | 0.1 | 0.06 | 3.01 | 4.38 | 2.74 |
| frontend | 0.1 | 0.06 | 3.01 | 4.38 | 2.74 |
| loadgenerator | 0.3 | 0.25 | 9.23 | 13.44 | 8.39 |
| paymentservice | 0.1 | 0.06 | 3.01 | 4.38 | 2.74 |
| productcatalogservice | 0.1 | 0.06 | 3.01 | 4.38 | 2.74 |
| recommendationservice | 0.1 | 0.21 | 3.48 | 5.08 | 3.17 |
| redis-cart | 0.07 | 0.20 | 2.58 | 3.76 | 2.34 |
| shippingservice | 0.1 | 0.06 | 3.01 | 4.38 | 2.74 |
| shoppingassistantservice | 0.1 | 0.06 | 3.01 | 4.38 | 2.74 |
| **Total** | **1.67** | **1.40** | **51.38** | **74.84** | **46.71** |

*Fargate uses US East prices (no EU price was readable). Autopilot, Cloud Run and Fargate round small requests up to their own minimum sizes, which is not modelled -- treat these as lower bounds.

### Fixed and add-on items
| Item | €/month | Basis |
|---|---|---|
| GKE Autopilot cluster fee (Autopilot is regional by design) | 0.00 | $0.10/h; the $74.40 monthly free credit covers one Autopilot or zonal cluster per billing account; add 63.27 if the credit is already used by another cluster |
| GKE Standard regional cluster fee | 63.27 | $0.10/h, the free credit does not apply to regional Standard clusters (node VMs not priced) |
| AKS cluster fee, Standard tier with SLA (West Europe, already in EUR) | 64.24 | €0.088/h |
| AKS cluster fee, Free tier | 0.00 | no SLA; you pay only for node VMs (not priced) |
| EKS cluster fee | 63.27 | $0.10/h |
| Google HTTPS load balancer (1 forwarding rule) | 15.82 | $0.025/h + $0.008/GiB processed (traffic unknown) |
| Managed Redis, Basic 1 GiB (replaces in-cluster Redis) | 31.00 | Memorystore Iowa price -- EU price not read |
| Managed Redis, Standard 1 GiB (with failover) | 40.50 | Memorystore Iowa price -- EU price not read |
| Azure Cache for Redis Basic C1 1 GB (West Europe) | 35.33 | single node, no SLA; Azure announced retirement in 2028 |
| Azure Cache for Redis Standard C1 1 GB (West Europe) | 88.62 | replicated pair |
| Cloud SQL PostgreSQL db-g1-small + 10 GiB SSD (OPTIONAL -- only if the app needs a relational DB) | 23.62 | shared-core, no SLA |
| Same, high availability (two zones) | 47.24 | shared-core, no SLA |
| Cloud SQL PostgreSQL dedicated-core 1 vCPU / 3.75 GiB + 10 GiB SSD (has an SLA; needed for production data) | 44.22 | Iowa rate, EU price not read |
| Same, high availability (two zones) | 88.43 | Iowa rate, EU price not read |
| Secret Manager, 10 secrets, light use | 0.21 | first 6 versions free |


### Cheapest self-managed alternative (one Hetzner server running k3s/Docker)
Total requests are 1.67 vCPU and 1.40 GiB as requested in the repo, but about 3.8 GiB once each service gets a realistic minimum (ASSUMPTION, not measured: at least 0.25 GiB per service (0.5 GiB for Java/.NET) plus about 0.25-2 GiB per in-cluster datastore). With ~30% headroom that fits **CPX32** (4 vCPU, 8 GB RAM): **€35.99/month excl. VAT**. EUR, excluding VAT (German VAT must be added). 20 TB traffic included on EU locations. A single server has no failover: it cannot meet a true zero-downtime requirement.

### Ready-made monthly totals (computed in code)
| Setup | €/month |
|---|---|
| GKE Autopilot (cluster fee covered by the free credit), 1 load balancer | 67.20 |
| GKE Autopilot + managed Redis Basic (replaces in-cluster Redis) (Memorystore Iowa price; EU price not read) | 95.62 |
| GKE Autopilot + managed Redis Standard (replaces in-cluster Redis) (Memorystore Iowa price; EU price not read) | 105.11 |
| GKE Autopilot, 2 replicas per service + managed Redis Standard with failover (replaces in-cluster Redis) + 1 load balancer (Memorystore Iowa price; EU price not read) | 153.91 |
| GKE Autopilot, 2 replicas per service WITHOUT the load generator + managed Redis Standard with failover + 1 load balancer (Memorystore Iowa price; EU price not read) | 135.46 |
| Saving from removing the load generator at 2 replicas per service on GKE Autopilot | 18.45 |
| Cloud Run always-on, 1 load balancer, no cluster fee | 90.66 |
| GKE Autopilot, 2 replicas per service, 1 load balancer | 118.58 |
| Cloud Run always-on, 2 instances per service, 1 load balancer | 165.51 |
| GKE Autopilot, 1 replica per service without demo/test tooling (loadgenerator; 12 services), 1 load balancer | 57.97 |
| GKE Autopilot, 2 replicas per service without demo/test tooling (loadgenerator; 12 services), 1 load balancer | 100.12 |
| Hetzner CPX32 single server (excl. VAT, no failover) | 35.99 |
| Hetzner CPX32 single server (excl. VAT, no failover) + managed Redis Basic (Memorystore Iowa price; EU price not read) + Secret Manager (mixed providers) | 67.20 |
| Saving from removing loadgenerator on GKE Autopilot | 9.23 |

These totals contain compute, cluster fee, load balancer and the stated Redis/Cloud SQL option only. Persistent disks, egress, NAT, monitoring, databases and LLM tokens are not included.

### Not priced (no verified price available)
- Azure Container Apps Consumption-plan vCPU/memory rates (the price API rounds them to 0.0000)
- Azure VMs for AKS nodes, Azure Database for PostgreSQL, Azure load balancers
- GKE Standard node VMs (Compute Engine e2 hourly prices did not load)
- Amazon RDS (PostgreSQL) instances and storage
- Amazon ElastiCache nodes
- NAT gateways (Google Cloud NAT and AWS)
- Hetzner load balancer
- Memorystore and Fargate prices for EU regions (only Iowa / US East were readable)
- Internet egress for your real traffic (rate is listed, volume is unknown)
- Any LLM API token costs (depend on the model and your usage)
- Cloud SQL instance sizes other than db-g1-small and the 1 vCPU / 3.75 GiB dedicated instance (larger machines are priced by vCPU and GiB; your real size depends on your data and load)
- Read replicas, cross-region replicas and Cloud SQL backups beyond the included amount
- Cost of more than two replicas per service, and any other replica count (only 1 and 2 replicas are in the totals)