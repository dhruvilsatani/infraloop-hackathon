"""IMPLEMENTATION.md: one file that says, in order, what to do with the downloaded files.

Fixed text with the project's own names filled in (file paths, ports, variable names, the number of things Terraform will create).
Nothing here is written by an AI model, and nothing was run against the user's project or cloud account: the file says so."""
from .context import services, join
from .docker import _commented  # noqa: F401  (kept so every generator module imports the same helpers)

# Provider-specific facts for the three packs that exist. Everything else is generic.
_CLOUDS = {
    "hetzner-server": {
        "name": "Hetzner Cloud", "dir": "infra/hetzner", "user": "root",
        "need": ["A Hetzner Cloud account (https://www.hetzner.com/cloud/) and a project in it.",
                 "Terraform 1.5 or newer (https://developer.hashicorp.com/terraform/install)."],
        "login": ["In the Hetzner Cloud console open your project, then Security, then API tokens, and create a token with **Read & Write** access. Copy it once: it is not shown again.",
                  "In the terminal where you will run Terraform, set it as a variable (it stays in that terminal and is never written to a file):",
                  "```\nexport TF_VAR_hcloud_token='paste-the-token-here'\n```"],
        "extra_tfvars": "",
        "shows": "an SSH key, a firewall and the server",
    },
    "aws-server": {
        "name": "AWS", "dir": "infra/aws", "user": "ubuntu",
        "need": ["An AWS account, and an IAM user or role for Terraform with permission to create servers (EC2), security groups and addresses. Do not use the root account.",
                 "The AWS command line tool (https://aws.amazon.com/cli/) and Terraform 1.5 or newer (https://developer.hashicorp.com/terraform/install).",
                 "A default network (VPC) in the region. Check with: `aws ec2 describe-vpcs --filters Name=isDefault,Values=true --region eu-central-1`"],
        "login": ["Log in the way the AWS command line tool does, for example with a named profile:",
                  "```\nexport AWS_PROFILE=your-profile\naws sts get-caller-identity\n```",
                  "The second command must print your account id. If it does not, Terraform cannot log in either."],
        "extra_tfvars": "",
        "shows": "a key pair, a security group, the server and a fixed IP address",
    },
    "azure-server": {
        "name": "Azure", "dir": "infra/azure", "user": "azureuser",
        "need": ["An Azure subscription that is allowed to create virtual machines.",
                 "The Azure command line tool (https://learn.microsoft.com/cli/azure/install-azure-cli) and Terraform 1.5 or newer (https://developer.hashicorp.com/terraform/install)."],
        "login": ["Log in and find your subscription id (it is not a secret):",
                  "```\naz login\naz account show --query id -o tsv\n```",
                  "Check that the server size exists in your region: `az vm list-skus --location westeurope --size Standard_B --output table`"],
        "extra_tfvars": "`subscription_id` (the id from the command above), ",
        "shows": "a resource group, a network, a public IP, firewall rules and the server",
    },
}


def _steps(items, start=1):
    return [f"{i}. {x}" if not x.startswith("```") else x for i, x in enumerate(items, start)]


def _numbered(blocks):
    """blocks: list of (text, [following code or note lines]). Numbers the texts, keeps their code blocks under them."""
    L, n = [], 0
    for text, extra in blocks:
        n += 1
        L.append(f"{n}. {text}")
        for e in extra:
            L += ["", *(("   " + ln) if ln else "" for ln in e.split("\n"))]
        L.append("")
    return L


def _count_resources(bundle, folder):
    f = next((x for x in bundle.files if x.path == f"{folder}/main.tf"), None)
    return f.content.count('\nresource "') if f else 0


def implementation_md(bundle, scan):
    t = bundle.target or {}
    tid = t.get("id")
    cloud = _CLOUDS.get(tid)
    svcs, _ = services(scan)
    env_names = list(dict.fromkeys(scan.get("env_vars") or []))
    files = [f for f in bundle.files]
    cloud_dir = cloud["dir"] if cloud else None

    L = ["# How to put this into practice", ""]
    L += [f"For your choice: **{t['label']}**." if t else "For your choice: **not decided yet** (the basic files only).", ""]
    L += ["These steps were written from a fixed template, with the names from the scan of your project filled in. **Nothing here was run against your project or your cloud account.** "
          "Do the steps in order and check that each one worked before you start the next.", ""]

    # ---------- before you start
    L += ["## Before you start", "",
          "- Your project is in a git repository that you can push to (GitHub, for example).",
          "- Docker is installed on your computer, so you can test the image before it goes anywhere."]
    if cloud:
        L += [f"- {x}" for x in cloud["need"]]
    L += [""]

    # ---------- step 1: copy
    n = 1
    L += [f"## Step {n}: Copy the files into your project", "",
          "Work on a new branch so nothing can break your main one:", "", "```\ngit switch -c add-infraloop-files\n```", "",
          "Copy the files from this download into your project. They are laid out like your project, so keep the folders as they are.", ""]
    if files:
        L += [f"- `{f.path}`: {f.title}" for f in files]
        L += [""]
        if any(x.split("/")[-1].startswith(".") or any(p.startswith(".") for p in x.split("/")) for x in (f.path for f in files)):
            L += ["On a Mac, Finder hides names that start with a dot (`.github`, `.dockerignore`, `.env.example`). Press `Cmd + Shift + .` in Finder to show them, "
                  "or copy with your code editor or the terminal.", ""]
    else:
        L += ["This download has no new files for your project. See `MANIFEST.md` for why.", ""]
    L += ["If a file with the same name already exists in your project, **do not overwrite it**. Open both, compare them, and keep what you need. "
          "InfraLoop never edits files you already have." + (f" `MANIFEST.md` also lists {len(bundle.advice)} {'fix' if len(bundle.advice) == 1 else 'fixes'} for files you already have, to make by hand." if bundle.advice else ""), ""]

    # ---------- step 2: build locally
    n += 1
    dockerfiles = [(s, join(s.path, "Dockerfile")) for s in svcs]
    PORT = {"python": 8000, "node": 3000, "go": 8080}
    L += [f"## Step {n}: Check that the image builds on your computer", ""]
    if dockerfiles:
        L += ["For each service, build the image and start it. A service that fails here would fail on a server too, so fix it now:", ""]
        for s, df in dockerfiles:
            folder = "." if s.path in ("", ".") else s.path
            port = PORT[s.kind]
            L += [f"**{s.slug}** (`{df}`):", "", "```", *([f"cd {folder}"] if folder != "." else []), f"docker build -t {s.slug} .", f"docker run --rm -p {port}:{port} {'--env-file .env ' if env_names else ''}{s.slug}", "```", ""]
        if env_names:
            L += [f"The app reads these variables: {', '.join('`' + v + '`' for v in env_names[:12])}{' and more' if len(env_names) > 12 else ''}. "
                  "`.env.example` lists the names. Copy it to `.env`, fill in test values, and keep `.env` out of git (it is in the generated `.dockerignore`; add it to `.gitignore` too).", ""]
        ports = " or ".join(f"`http://localhost:{PORT[s.kind]}`" for s, _ in dockerfiles)
        L += [f"Then open {ports} in a browser (the port is the one the template assumed: change it if your app listens on another). If it does not answer, read the output of `docker run`: it usually says what is missing.", ""]
    else:
        L += ["The scan found no service the templates cover, so there is no image to build yet. Add a Dockerfile for your app first.", ""]

    # ---------- step 3: CI
    n += 1
    L += [f"## Step {n}: Turn on the checks", "",
          "Commit the files and push the branch:", "", "```\ngit add -A\ngit commit -m \"Add Dockerfile, CI and deployment files\"\ngit push -u origin add-infraloop-files\n```", ""]
    if any(f.path.startswith(".github/workflows") for f in files):
        L += ["Open your repository on GitHub and look at the **Actions** tab. The workflow builds and tests your code and builds the image. "
              "It does not deploy anything. If it fails, the log says which step; the most common causes are a wrong branch name in the file or a missing test command.", ""]
    else:
        L += ["Your project already has CI files, so check that the new commit still passes your own checks.", ""]
    L += ["Open a pull request, let the checks pass, then merge it.", ""]

    # ---------- step 4: hosting
    n += 1
    if cloud:
        d = cloud["dir"]
        user = cloud["user"]
        k = _count_resources(bundle, d)
        L += [f"## Step {n}: Create the server on {cloud['name']}", ""]
        L += ["### 4a. Get ready", ""] + [x if x.startswith("```") else x for x in cloud["login"]] + [""]
        L += ["### 4b. Make an SSH key (skip this if you already have one)", "",
              "```\nssh-keygen -t ed25519 -C \"you@example.com\"\ncat ~/.ssh/id_ed25519.pub\n```", "",
              "The last command prints one line (the public key). You will paste it into the next step. Never share the other file, `id_ed25519`.", ""]
        L += ["### 4c. Make sure the server can download your project", "",
              "The new server fetches your project from git, so the files from steps 1 to 3 must already be on the branch it downloads (`main` unless you change `branch`), "
              "and the repository must be public or readable without a password. For a private repository this pack does not work as it is: see the notes in `MANIFEST.md`.", ""]
        L += ["### 4d. Fill in your values", "",
              f"```\ncd {d}\ncp terraform.tfvars.example terraform.tfvars\n```", "",
              f"Open `terraform.tfvars` and set {cloud['extra_tfvars']}`ssh_public_key` (the line you printed), `admin_cidrs` (your own public address followed by `/32`, "
              "for example `[\"203.0.113.4/32\"]`; find it with `curl -s https://ifconfig.me`) and `repo_url` (the HTTPS address of your repository). "
              "That file is git-ignored on purpose. SSH stays closed to everyone else.", ""]
        L += ["### 4e. Create it", "",
              "```\nterraform init\nterraform validate\nterraform plan\n```", "",
              f"Read the plan. It should create about {k} things ({cloud['shows']}) and change nothing else. If it wants to change or destroy something you did not expect, stop and ask before going on. Then:", "",
              "```\nterraform apply\n```", "",
              "Type `yes` when it asks. When it finishes it prints `server_ip` and `url`.", ""]
        L += ["### 4f. Wait, then look", "",
              "The first start takes a few minutes: the server installs Docker, downloads your project and builds the image. Then open the address:", "",
              "```\nterraform output url\n```", "",
              "You will see your app, or an error page from the reverse proxy if the app is still starting or is missing its settings (next step).", ""]
        L += ["### 4g. Give the app its settings", "",
              f"The settings are created as empty names so that no secret passes through Terraform or {cloud['name']}'s start-up data. Log in and fill them in:", "",
              f"```\nssh {user}@<server_ip>\nsudo nano /opt/app/.env\ncd /opt/app && sudo docker compose -f docker-compose.prod.yml up -d\n```", ""]
        if env_names:
            L += [f"Names to fill in: {', '.join('`' + v + '`' for v in env_names)}.", ""]
        L += ["### 4h. If something is wrong", "",
              f"```\nssh {user}@<server_ip>\nsudo cloud-init status\nsudo tail -n 60 /var/log/cloud-init-output.log\nsudo docker compose -f /opt/app/docker-compose.prod.yml logs --tail 60\n```", "",
              "The first command says whether the first start finished. The second shows what the start-up script did. The third shows what your app printed.", ""]
        L += ["### 4i. Your own domain and HTTPS (optional)", "",
              "1. In your domain's DNS settings, create an **A record** that points at `server_ip`.",
              "2. Wait until it resolves (`nslookup app.example.com`).",
              "3. On the server, set `SITE_ADDRESS=app.example.com` in `/opt/app/.env`, then run `cd /opt/app && sudo docker compose -f docker-compose.prod.yml up -d`. The proxy gets a free certificate by itself.", "",
              "Do not change `domain` in `terraform.tfvars` after the first `apply` just for this: it changes the start-up script, and Terraform will then want to restart or replace the server. "
              "Read `terraform plan` before you agree to anything like that.", ""]
    else:
        L += [f"## Step {n}: Choose where it runs and put the image there", ""]
        if t and t.get("id", "").startswith("plan-"):
            L += [f"You picked **{t['label']}**. No infrastructure files exist for it yet, so this part is manual. The report has the details; in short:", ""]
        elif t and t.get("id") == "other-cloud":
            L += ["You picked another cloud or platform. No infrastructure files exist for it yet, so this part is manual. The basic files and the report still apply:", ""]
        else:
            L += ["You have not chosen where it runs yet. Come back to this step after you have. The general order is the same everywhere:", ""]
        L += ["1. Make sure the image from step 2 builds and starts on your computer.",
              "2. Put the image in a registry your provider can read from (the provider's own registry is the usual choice).",
              "3. Create the service on the provider and point it at that image.",
              "4. Set the app's variables on the provider (not in the image, not in git)" + (f": {', '.join('`' + v + '`' for v in env_names[:12])}." if env_names else "."),
              "5. Open the address the provider gives you and check the logs.",
              "6. Point your domain at it once it works.", ""]
        links = (t or {}).get("links") or []
        if links:
            L += ["Where to start:", ""] + [f"- [{l['label']}]({l['url']})" for l in links] + [""]
        L += ["Or choose one of the server options in the page (Hetzner, AWS or Azure): they come with Terraform files and a longer version of this step.", ""]

    # ---------- after it runs
    n += 1
    L += [f"## Step {n}: Before you call it done", "",
          "- Open the address from a different network (your phone, off Wi-Fi) to check it is reachable from outside.",
          "- Set an uptime alert, so you hear when the site is down.",
          "- Turn on backups and **restore one** to see that it works.",
          "- Set a budget alert with your provider, so a surprise cost reaches you.",
          "- Keep `MANIFEST.md` somewhere your team can find it: it lists what each file assumed and what to check.", ""]
    if cloud:
        L += ["## Taking it down again", "",
              "Everything Terraform created can be removed with one command. It destroys the server and its data, so copy anything you need first:", "",
              f"```\ncd {cloud['dir']}\nterraform destroy\n```", ""]
    L += ["## If you get stuck", "",
          "Check `MANIFEST.md`: every file has a \"Check before you use it\" list, and the most common problems are on it. "
          "Prices and server names change over time, so check the provider's own page before you rely on a number."]
    return "\n".join(L).rstrip() + "\n"
