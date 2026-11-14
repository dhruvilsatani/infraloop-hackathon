"""Plain-language profile of each 'where will it run?' option: what it is, why it costs what it does, what you give up, and how it changes the report.

Fixed text written for people who are not technical, and kept to things that are true of the KIND of setup (one machine, a managed container service, a managed
Kubernetes service), not to claims about a provider's current features or prices. Prices always come from the report's own price table."""

K8S_ONLY = ("k8s_no_security_context", "k8s_no_network_policies", "k8s_images_use_latest_tag", "k8s_ingress_class_not_gke",
            "k8s_no_disruption_or_autoscaling_config", "no_health_probes")

PROFILES = {
    "hetzner": {
        "plain": "You rent one small computer in a data centre and your app runs on it. It's like renting a flat yourself instead of staying in a hotel with staff.",
        "why_cheap": "You only pay for the machine. The pricier options also pay for spare copies of your app, for switching over when something fails, and for someone else keeping it all running. "
                     "Here none of that comes with it, so it costs less and that work lands on you.",
        "catch": "Only one machine: if it breaks, your app stays down until you fix it, and updates and backups are on you.",
        "good_for": ["A first launch, a side project or an internal tool", "Small, steady traffic", "A team that can log into a server and fix things"],
        "links": [("Hetzner Cloud: servers and prices", "https://www.hetzner.com/cloud/")],
        "benefits": ["Easy to understand: one machine runs your app, with no cluster or extra services to learn.",
                     "A simple bill: it is mostly the price of the one machine you rent.",
                     "Quick to set up: the download has what it takes to create the server and start your app.",
                     "No lock-in: your app runs in plain Docker, so you can move it to another provider later."],
        "give_up": ["If the machine breaks or restarts, your app is down until you sort it out. Nothing switches over by itself.",
                    "Updates and security patches are yours to install.",
                    "Backups are off unless you turn them on, and Hetzner charges extra for them.",
                    "It can't grow by itself: a sudden rush makes it slow, and a bigger project will outgrow one machine."],
        "avoid_if": ["You've promised customers almost no downtime", "Losing recent data would really hurt", "Nobody on the team is comfortable with a server",
                     "Traffic is big or hard to predict"],
        "before_launch": ["Turn on backups, then restore one to see that it works.", "Set up an uptime alert, so you hear about it when the site is down.",
                          "Pick a regular time to install updates.", "Keep the Terraform files: they can create the same machine again if you lose it (your data is separate)."],
        "gap_notes": {"no_observability": "Matters more on one machine, because nobody restarts it for you. Add an uptime alert before you launch.",
                      "no_iac": "Closed by the Terraform files in this download (`infra/hetzner`).",
                      "no_cloud_iac": "Closed by the Terraform files in this download (`infra/hetzner`).",
                      **{k: "Kubernetes only, so it doesn't apply to a single server (which uses docker-compose instead)." for k in K8S_ONLY}},
    },
    "aws_vm": {
        "plain": "You rent one virtual computer from Amazon, in their Frankfurt data centre, and your app runs on it. It is the same idea as the cheap single server, but on the biggest cloud, so AWS services are close by when you need them later.",
        "why_cheap": "You pay for one machine, a small disk and a fixed public address, billed by the hour. There are no spare copies of your app and no managed services in that price, "
                     "so anything you add later (a managed database, a load balancer, backups) is extra.",
        "catch": "Only one machine: if it breaks, your app stays down until you fix it. It is also more to set up than a plain server, and the bill has more parts, such as traffic out of AWS.",
        "good_for": ["Your team or company already uses AWS", "You may want AWS services next to the app later, like a managed database or file storage", "Small, steady traffic"],
        "links": [("Amazon EC2 (virtual servers)", "https://aws.amazon.com/ec2/"), ("EC2 on-demand prices", "https://aws.amazon.com/ec2/pricing/on-demand/")],
        "benefits": ["The biggest cloud: if you later need a managed database, file storage or more servers, they live in the same account.",
                     "The same simple idea as one server: one machine, with no cluster to learn.",
                     "The download creates the server, its firewall rules and a fixed IP address, and starts your app.",
                     "You pay by the hour, and one command removes everything again."],
        "give_up": ["If the machine breaks or restarts, your app is down until you sort it out. Nothing switches over by itself.",
                    "Updates and security patches are yours to install, and backups are not switched on.",
                    "More to set up than a plain server: an AWS account, access keys and a default network in your region.",
                    "The bill has more parts than one price: traffic out of AWS and backups cost extra, and long heavy CPU use costs extra on this kind of machine.",
                    "It can't grow by itself: a sudden rush makes it slow, and a bigger project will outgrow one machine."],
        "avoid_if": ["You've promised customers almost no downtime", "Nobody on the team is comfortable with a server", "Price is your main concern: compare it with the other single-server option in this list"],
        "before_launch": ["Set a billing alert in AWS, so a surprise charge reaches you.", "Use a separate AWS user or role for Terraform with only the permissions it needs, not your root account.",
                          "Turn on snapshots (backups) of the disk, then restore one to see that it works.", "Set up an uptime alert, so you hear about it when the site is down."],
        "gap_notes": {"no_observability": "Matters more on one machine, because nobody restarts it for you. Add an uptime alert before you launch.",
                      "no_iac": "Closed by the Terraform files in this download (`infra/aws`).",
                      "no_cloud_iac": "Closed by the Terraform files in this download (`infra/aws`).",
                      **{k: "Kubernetes only, so it doesn't apply to a single server (which uses docker-compose instead)." for k in K8S_ONLY}},
    },
    "azure_vm": {
        "plain": "You rent one virtual computer from Microsoft, in their West Europe data centre, and your app runs on it. It is the same idea as the cheap single server, but inside Azure, so Azure services are close by when you need them later.",
        "why_cheap": "You pay for one machine, a small disk and a fixed public address, billed by the hour. There are no spare copies of your app and no managed services in that price, "
                     "so anything you add later (a managed database, a load balancer, backups) is extra.",
        "catch": "Only one machine: if it breaks, your app stays down until you fix it. It is also more to set up than a plain server, and the bill has more parts, such as traffic out of Azure.",
        "good_for": ["Your team or company already uses Microsoft Azure or Microsoft 365", "You may want Azure services next to the app later, like a managed database or file storage", "Small, steady traffic"],
        "links": [("Azure Virtual Machines", "https://azure.microsoft.com/en-us/products/virtual-machines"),
                  ("Azure Linux VM prices", "https://azure.microsoft.com/en-us/pricing/details/virtual-machines/linux/")],
        "benefits": ["Fits well if your company already runs on Microsoft: the same account, sign-in and billing.",
                     "The same simple idea as one server: one machine, with no cluster to learn.",
                     "The download creates the server, its network, firewall rules and a fixed IP address, and starts your app. Password login is off.",
                     "You pay by the hour, and one command removes everything again."],
        "give_up": ["If the machine breaks or restarts, your app is down until you sort it out. Nothing switches over by itself.",
                    "Updates and security patches are yours to install, and backups are not switched on.",
                    "More to set up than a plain server: an Azure subscription, the Azure CLI login, and a machine size your subscription is allowed to create in that region.",
                    "The bill has more parts than one price: traffic out of Azure, disk operations and backups cost extra, and long heavy CPU use slows this kind of machine down.",
                    "It can't grow by itself: a sudden rush makes it slow, and a bigger project will outgrow one machine."],
        "avoid_if": ["You've promised customers almost no downtime", "Nobody on the team is comfortable with a server", "Price is your main concern: compare it with the other single-server option in this list"],
        "before_launch": ["Set a budget alert in Azure, so a surprise charge reaches you.", "Use a separate service principal for Terraform with only the permissions it needs.",
                          "Turn on backups for the server, then restore one to see that it works.", "Set up an uptime alert, so you hear about it when the site is down."],
        "gap_notes": {"no_observability": "Matters more on one machine, because nobody restarts it for you. Add an uptime alert before you launch.",
                      "no_iac": "Closed by the Terraform files in this download (`infra/azure`).",
                      "no_cloud_iac": "Closed by the Terraform files in this download (`infra/azure`).",
                      **{k: "Kubernetes only, so it doesn't apply to a single server (which uses docker-compose instead)." for k in K8S_ONLY}},
    },
    "gke_autopilot": {
        "plain": "Google runs the machines and keeps several copies of your app running, replacing any that fail. You describe what to run, using Kubernetes.",
        "why_cheap": "It costs more than one machine because you pay for several copies and for Google doing the operating work. The report's table shows the parts.",
        "catch": "More to learn and more to pay, and partly tied to Google.",
        "good_for": ["Several services that must keep running when one part fails", "Traffic that grows and shrinks", "A team that already knows Kubernetes, or wants to"],
        "links": [("Google Kubernetes Engine (GKE)", "https://cloud.google.com/kubernetes-engine"),
                  ("GKE pricing", "https://cloud.google.com/kubernetes-engine/pricing")],
        "benefits": ["If one copy of your app fails, Kubernetes starts a new one for you.",
                     "Google looks after the machines underneath, including their updates.",
                     "Can grow with your traffic once autoscaling is switched on.",
                     "A solid base if you add more services later."],
        "give_up": ["Someone needs to be comfortable with Kubernetes to deploy and fix things.",
                    "It costs more than a single machine, and part of the bill is fixed however little traffic you get.",
                    "It's partly tied to Google. Moving later is possible, but it takes work."],
        "avoid_if": ["Nobody on the team knows Kubernetes and nobody wants to", "It's a small project with steady, low traffic"],
        "before_launch": ["Set a budget alert in the cloud account.", "Try a deploy in a test project first.", "Make sure the app answers a health check, so Kubernetes can tell when it's ready."],
        "gap_notes": {**{k: "Applies directly: these are the settings your cluster will run with." for k in K8S_ONLY},
                      "no_iac": "Not covered by the download yet. Files for the cluster itself are the next step."},
    },
    "cloud_run": {
        "plain": "Google runs your container for you. There are no machines or clusters to look after.",
        "why_cheap": "It costs more than one machine because Google does the operating work, and the report prices copies that stay on all the time.",
        "catch": "The bill grows with traffic, and it's partly tied to Google.",
        "good_for": ["A web app or API that doesn't keep files on its own disk", "A team that wants no servers to look after", "Traffic that goes up and down"],
        "links": [("Google Cloud Run", "https://cloud.google.com/run"),
                  ("Cloud Run pricing", "https://cloud.google.com/run/pricing")],
        "benefits": ["No servers or clusters to look after: you hand over a container and it runs.",
                     "Adds and removes copies of your app as traffic goes up and down.",
                     "Deploying a new version is just handing over a new container."],
        "give_up": ["The bill follows your usage, and copies that stay on are paid for even when idle.",
                    "It works best if your app doesn't keep files on its own disk.",
                    "A database is a separate paid service, not in this price unless the report says so.",
                    "It's partly tied to Google. Moving later is possible, but it takes work."],
        "avoid_if": ["The app stores important files on its own disk", "You need long background jobs in the same container"],
        "before_launch": ["Set a budget alert in the cloud account.", "Check where the app writes files and move that elsewhere.", "Try a deploy in a test project first."],
        "gap_notes": {**{k: "Kubernetes only, so it doesn't apply to Cloud Run." for k in K8S_ONLY},
                      "no_iac": "Not covered by the download yet. Files for the service itself are the next step."},
    },
    "aws_fargate": {
        "plain": "Amazon runs your containers for you, so there are no machines to look after. A load balancer in front sends visitors to whichever copy is healthy.",
        "why_cheap": "It costs more than one machine because you pay for every copy of your app while it runs, plus a load balancer that has its own fixed fee every hour, "
                     "and a public address for each of them. The report's table shows the parts.",
        "catch": "More to set up than one server, the bill has several parts, and it is partly tied to AWS.",
        "good_for": ["Your team or company already uses AWS", "Several services that must keep running when one copy fails", "A team that wants no servers to patch"],
        "links": [("AWS Fargate", "https://aws.amazon.com/fargate/"), ("Amazon ECS", "https://aws.amazon.com/ecs/"),
                  ("Fargate pricing", "https://aws.amazon.com/fargate/pricing/")],
        "benefits": ["No servers to look after: you hand AWS a container image and it runs the copies.",
                     "If a copy fails, Amazon ECS starts a new one for you.",
                     "Other AWS services, like a managed database or secrets storage, sit in the same account.",
                     "You can add copies when traffic grows."],
        "give_up": ["More to set up than one server: a cluster, a service, a load balancer and network settings.",
                    "The load balancer costs money every hour, even when nobody visits.",
                    "A database or Redis is a separate paid service, not in this price unless the report says so.",
                    "It's partly tied to AWS. Moving later is possible, but it takes work."],
        "avoid_if": ["Nobody on the team has used AWS and nobody wants to", "It's a small project with steady, low traffic: one server costs much less"],
        "before_launch": ["Set a billing alert in AWS, so a surprise charge reaches you.", "Use a separate AWS user or role for deployments, not your root account.",
                          "Make sure the app answers a health check, so the load balancer can tell when a copy is ready.", "Try a deploy in a test account first."],
        "gap_notes": {**{k: "Kubernetes only, so it doesn't apply to ECS Fargate." for k in K8S_ONLY},
                      "no_iac": "Not covered by the download yet. Files for the service itself are the next step."},
    },
    "azure_container_apps": {
        "plain": "Microsoft runs your containers for you. There are no machines or clusters to look after, and it comes with its own web address and HTTPS.",
        "why_cheap": "It costs more than one machine because every copy of your app is paid for each second it runs. The report prices the copies at their full running rate; "
                     "Azure charges less while a copy is idle and gives a free allowance each month, so your real bill can be lower.",
        "catch": "The bill follows how long your copies run, and it is partly tied to Azure.",
        "good_for": ["Your team or company already uses Azure", "A web app or API that doesn't keep files on its own disk", "A team that wants no servers or clusters to look after"],
        "links": [("Azure Container Apps", "https://azure.microsoft.com/products/container-apps"),
                  ("Container Apps pricing", "https://azure.microsoft.com/en-us/pricing/details/container-apps/")],
        "benefits": ["No servers or clusters to look after: you hand over a container and it runs.",
                     "It comes with an HTTPS entry point, so there is no separate load balancer to pay for.",
                     "Can add and remove copies as traffic changes, once you set the scaling rules.",
                     "Other Azure services, like a managed database, sit in the same account."],
        "give_up": ["The report prices the copies at their full running rate. The real bill can be lower, but it follows your usage.",
                    "It works best if your app doesn't keep files on its own disk.",
                    "A database is a separate paid service, not in this price unless the report says so.",
                    "It's partly tied to Azure. Moving later is possible, but it takes work."],
        "avoid_if": ["The app stores important files on its own disk", "Nobody on the team has used Azure and nobody wants to"],
        "before_launch": ["Set a budget alert in Azure, so a surprise charge reaches you.", "Use a separate service principal for deployments with only the permissions it needs.",
                          "Check where the app writes files and move that elsewhere.", "Try a deploy in a test subscription first."],
        "gap_notes": {**{k: "Kubernetes only, so it doesn't apply to Container Apps." for k in K8S_ONLY},
                      "no_iac": "Not covered by the download yet. Files for the service itself are the next step."},
    },
    "other-cloud": {
        "plain": "You'll run it somewhere we don't have files for yet, like Fly.io, Kubernetes on AWS or Azure, or your own servers.",
        "why_cheap": "", "catch": "We don't write the hosting files for it yet, so that part is up to you. The basic files and the report still apply.",
        "good_for": ["You already have a provider, or your company has a standard"], "benefits": ["You keep the provider you already know."], "give_up": ["We don't generate hosting files for that provider yet."],
        "avoid_if": [], "before_launch": ["The report's cost table prices Google Cloud and Hetzner, so use it only as a rough comparison."], "gap_notes": {},
    },
    "not-yet": {
        "plain": "You haven't picked a place yet. You get the basic files (Dockerfile, CI and the rest), which work anywhere.",
        "why_cheap": "", "catch": "Nothing about hosting is generated until you choose.", "good_for": ["Still comparing options"], "benefits": ["You can decide later: the basic files fit any provider."], "give_up": [],
        "avoid_if": [], "before_launch": [], "gap_notes": {},
    },
}


SERVER_PROFILES = {"hetzner-server": "hetzner", "aws-server": "aws_vm", "azure-server": "azure_vm"}


def profile_id(target_id, platform=""):
    if target_id in SERVER_PROFILES:
        return SERVER_PROFILES[target_id]
    if target_id in PROFILES:
        return target_id
    return platform if platform in PROFILES else "other-cloud"


def catch(pid):
    return PROFILES.get(pid, PROFILES["other-cloud"])["catch"]


def brief_markdown(target, scan=None, gaps=None, files=None):
    """The 'Your chosen setup' section, in plain language. files: paths the download holds for this choice (or None)."""
    pr = PROFILES.get(target.get("profile") or "other-cloud", PROFILES["other-cloud"])
    L = [f"## Your chosen setup: {target['label']}", "", f"**In plain words.** {pr['plain']}", ""]
    if target.get("monthly_eur") is not None:
        from knowledge import prices
        if target.get("price_note"):
            L += [f"**Cost.** About {target['monthly_eur']:.2f} EUR per month. {target['price_note']}", ""]
        else:
            L += [f"**Cost.** About {target['monthly_eur']:.2f} EUR per month, from the report's price table (prices read {prices.RETRIEVED}). "
                  "Taxes, traffic charges and anything the report doesn't list aren't included.", ""]
    if target.get("zone_ha") is True:
        L += ["**If a data centre has a problem:** this keeps running, because it has copies in more than one zone.", ""]
    elif target.get("zone_ha") is False:
        L += ["**If the machine or its data centre has a problem:** this stops until it's fixed or recreated, because everything runs in one place.", ""]
    if target.get("why"):
        L += ["**Why we recommend it:** " + " ".join(target["why"]), ""]
    if target.get("benefits"):
        L += ["**What you get**", ""] + [f"- {x}" for x in target["benefits"]] + [""]
    if pr["why_cheap"]:
        L += [f"**Why it costs what it does.** {pr['why_cheap']}", ""]
    if pr["give_up"]:
        L += ["**What you give up**", ""] + [f"- {x}" for x in pr["give_up"]] + [""]
    if pr["good_for"]:
        L += ["**A good fit if:**", ""] + [f"- {x}" for x in pr["good_for"]] + [""]
    if pr["avoid_if"]:
        L += ["**Think again if:**", ""] + [f"- {x}" for x in pr["avoid_if"]] + [""]
    if pr["before_launch"]:
        L += ["**Before you launch**", ""] + [f"- {x}" for x in pr["before_launch"]] + [""]
    notes = [(g["issue"], pr["gap_notes"][g["issue"]]) for g in (gaps or []) if g["issue"] in pr["gap_notes"]]
    if notes:
        L += ["**How this choice changes the gaps in your report**", ""] + [f"- `{i}`: {n}" for i, n in notes] + [""]
    if target.get("files") and files:
        L += ["**What the download adds for this choice**", ""] + [f"- `{p}`" for p in files] + [""]
    elif not target.get("files"):
        L += ["**What the download adds for this choice:** no infrastructure files exist for it yet, but you still get the basic files.", ""]
    links = pr.get("links") or []
    if links:
        L += ["**Links**", ""] + [f"- [{name}]({url})" for name, url in links] + [""]
    return "\n".join(L).rstrip() + "\n"
