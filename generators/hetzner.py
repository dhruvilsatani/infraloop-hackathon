"""Pack for the target 'one Hetzner Cloud server': Terraform for the server and firewall, docker-compose to run the app, Caddy in front.

Written from scan facts only. Rules this pack keeps:
  * no secret is ever written: the tool asks for no token, and the app's variables are created as names only, to be filled on the server
  * SSH is closed unless the user lists their own address (admin_cidrs has no default)
  * Terraform state files are git-ignored in the folder
  * nothing is applied: the user runs terraform themselves"""
from .model import Artifact, HEADER
from .context import services, join
from .docker import _commented

PORT = {"python": 8000, "node": 3000, "go": 8080}


def port_of(s):
    """The port the repo's own Dockerfile EXPOSEs, else the template default for the language."""
    return s.port or PORT[s.kind]
TF = "infra/hetzner"

_MAIN = '''terraform {
  required_version = ">= 1.5"
  required_providers {
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.48"
    }
  }
}

provider "hcloud" {
  token = var.hcloud_token
}

resource "hcloud_ssh_key" "admin" {
  name       = "${var.name}-admin"
  public_key = var.ssh_public_key
}

resource "hcloud_firewall" "app" {
  name = "${var.name}-firewall"

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.admin_cidrs
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }
}

resource "hcloud_server" "app" {
  name         = var.name
  server_type  = var.server_type
  image        = "ubuntu-24.04"
  location     = var.location
  ssh_keys     = [hcloud_ssh_key.admin.id]
  firewall_ids = [hcloud_firewall.app.id]
  backups      = var.backups

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    repo_url     = var.repo_url
    branch       = var.branch
    site_address = var.domain == "" ? ":80" : var.domain
  })

  labels = {
    managed-by = "terraform"
    app        = var.name
  }
}
'''

_VARIABLES = '''variable "hcloud_token" {
  description = "Hetzner Cloud API token (read and write). Pass it as TF_VAR_hcloud_token; never write it into a file."
  type        = string
  sensitive   = true
}

variable "ssh_public_key" {
  description = "The public key (the line from your .pub file) that may log in as root."
  type        = string
}

variable "admin_cidrs" {
  description = "Addresses allowed to reach SSH, for example [\\"203.0.113.4/32\\"]. There is no default on purpose."
  type        = list(string)

  validation {
    condition     = length(var.admin_cidrs) > 0 && !contains(var.admin_cidrs, "0.0.0.0/0")
    error_message = "List at least one address and do not open SSH to the whole internet (0.0.0.0/0)."
  }
}

variable "repo_url" {
  description = "HTTPS URL of the git repository the server clones and builds. It must be readable without a password (public), or see the notes in MANIFEST.md."
  type        = string
}

variable "branch" {
  description = "Branch to deploy."
  type        = string
  default     = "main"
}

variable "name" {
  description = "Name used for the server, firewall and key."
  type        = string
  default     = "app"
}

variable "server_type" {
  description = "Hetzner server type (lower case). Check the current names with: hcloud server-type list"
  type        = string
  default     = "@@TYPE@@"
}

variable "location" {
  description = "Hetzner location. Not every server type is sold in every location."
  type        = string
  default     = "@@LOCATION@@"
}

variable "domain" {
  description = "Domain name pointing at the server, for automatic HTTPS. Leave empty to serve plain HTTP on the IP address."
  type        = string
  default     = ""
}

variable "backups" {
  description = "Hetzner server backups (an extra charge: check Hetzner's price page). Turn this on if losing the server's disk would hurt."
  type        = bool
  default     = false
}
'''

_OUTPUTS = '''output "server_ip" {
  description = "Public IPv4 address of the server."
  value       = hcloud_server.app.ipv4_address
}

output "url" {
  description = "Where the app will answer once it has started."
  value       = var.domain == "" ? "http://${hcloud_server.app.ipv4_address}" : "https://${var.domain}"
}
'''

_CLOUD_INIT = '''#cloud-config
package_update: true
packages:
  - docker.io
  - docker-compose-v2
  - git
write_files:
  - path: /root/app.env
    permissions: "0600"
    content: |
@@ENV@@      SITE_ADDRESS=${site_address}
runcmd:
  - systemctl enable --now docker
  - git clone --branch ${branch} ${repo_url} /opt/app
  - sh -c 'cd /opt/app && { [ -f .env ] || cp /root/app.env .env; }'
  - sh -c 'cd /opt/app && docker compose -f docker-compose.prod.yml up -d --build'
'''

_TFVARS = '''# Copy to terraform.tfvars and fill in. terraform.tfvars is git-ignored: keep it that way.
# The API token does NOT go here. Export it instead:  export TF_VAR_hcloud_token=...
ssh_public_key = "ssh-ed25519 AAAA... you@example.com"
admin_cidrs    = ["203.0.113.4/32"]   # your own public address
repo_url       = "https://github.com/YOU/YOUR-REPO.git"
# branch      = "main"
# domain      = "app.example.com"
# backups     = true
'''

_GITIGNORE = '''.terraform/
*.tfstate
*.tfstate.*
terraform.tfvars
crash.log
'''

_CADDY = '''# {$SITE_ADDRESS::80} means: use the SITE_ADDRESS variable, or ":80" (plain HTTP on any host name) when it is not set.
{$SITE_ADDRESS::80} {
	reverse_proxy @@UPSTREAM@@
}
'''


def _compose(svcs):
    L = [_commented(HEADER).rstrip("\n"), "services:"]
    for s in svcs:
        L += [f"  {s.slug}:", f"    build: {'.' if s.path in ('', '.') else './' + s.path}", "    restart: unless-stopped", "    env_file: .env",
              f"    expose: [\"{port_of(s)}\"]"]
    first = svcs[0]
    L += ["  caddy:", "    image: caddy:2", "    restart: unless-stopped", "    ports: [\"80:80\", \"443:443\"]",
          "    environment:", "      SITE_ADDRESS: ${SITE_ADDRESS:-:80}",
          "    volumes:", "      - ./deploy/Caddyfile:/etc/caddy/Caddyfile:ro", "      - caddy_data:/data", "      - caddy_config:/config",
          f"    depends_on: [{first.slug}]", "volumes:", "  caddy_data:", "  caddy_config:", ""]
    return "\n".join(L)


def pack(scan, gaps, target):
    svcs, _ = services(scan)
    if not svcs:
        return [], ["The scan found no service this pack has a template for."]
    srv = (target or {}).get("server") or {}
    issues = {g["issue"] for g in gaps}
    gap = "no_iac" if "no_iac" in issues else ("no_cloud_iac" if "no_cloud_iac" in issues else "")
    names = list(dict.fromkeys(scan.get("env_vars") or []))
    env_lines = "".join(f"      {n}=\n" for n in names)
    typ = (srv.get("name") or "cpx22").lower()
    loc = (srv.get("locations") or "FSN1").split("/")[0].lower()
    first = svcs[0]
    common_review = ["Nothing here was run: no `terraform validate`, no server and no container was started. Run `terraform init && terraform validate && terraform plan` before `apply`.",
                     "Hetzner changes server type names and locations over time: check `hcloud server-type list` and edit `server_type` and `location` if needed."]

    def art(path, content, title, assume=(), review=(), conf="medium"):
        return Artifact(path=path, content=content, gap=gap, title=title, confidence=conf, assumptions=list(assume), review=list(review))

    files = [
        art(f"{TF}/main.tf", _commented(HEADER) + _MAIN, "Terraform: server, SSH key and firewall",
            ["Ubuntu 24.04 on one server; the firewall opens ports 80 and 443 to everyone and SSH only to `admin_cidrs`.",
             "The server is created with docker and docker-compose from Ubuntu's own package repository."],
            common_review + ["The Hetzner API token is read from `TF_VAR_hcloud_token`. InfraLoop never asks for it and never stores it.",
                             "Terraform state (`terraform.tfstate`) is created on your machine and can contain sensitive values. It is git-ignored here: keep it that way or move it to a remote backend."]),
        art(f"{TF}/variables.tf", _commented(HEADER) + _VARIABLES.replace("@@TYPE@@", typ).replace("@@LOCATION@@", loc), "Terraform: variables",
            [f"Server size {srv.get('name', typ.upper())} was chosen by the cost estimate in the report; it is not a measured size."],
            ["Load-test before you trust the size. The report priced it from the repository's own CPU and memory requests."]),
        art(f"{TF}/outputs.tf", _commented(HEADER) + _OUTPUTS, "Terraform: outputs", conf="high"),
        art(f"{TF}/cloud-init.yaml", "# " + HEADER + "\n" + _CLOUD_INIT.replace("@@ENV@@", env_lines), "Server start-up script (cloud-init)",
            [f"The repository is public (or readable without a password) and has `docker-compose.prod.yml` on branch `{{branch}}`.".replace("{branch}", "main"),
             "The app's environment variables are created as names only, in `/opt/app/.env` on the server."],
            ["Fill in the values by logging in: `ssh root@<server_ip>`, edit `/opt/app/.env`, then `cd /opt/app && docker compose -f docker-compose.prod.yml up -d`.",
             "The app will not work until you do. This way no secret passes through Terraform state or Hetzner's metadata service.",
             "Private repository: use a deploy key or build and push an image to a registry instead; this pack does neither."]),
        art(f"{TF}/terraform.tfvars.example", _TFVARS, "Terraform: example values", conf="high"),
        art(f"{TF}/.gitignore", _GITIGNORE, "Keeps Terraform state and your values out of git", conf="high"),
        art("docker-compose.prod.yml", _compose(svcs), "docker-compose file for the server",
            [f"Each service listens on port ({', '.join(f'{s.slug}: {port_of(s)}' for s in svcs)}).",
             f"Only `{first.slug}` is reachable from outside, through Caddy."],
            ["If your own Dockerfile listens on a different port than the one above, change `expose` here and the upstream in `deploy/Caddyfile`; the pack cannot read the port from your Dockerfile.",
             "Caddy gets a free HTTPS certificate only when `domain` is set and its DNS record points at the server.",
             "`caddy:2` follows the latest 2.x release: pin an exact version once it works.",
             "A database is not part of this file. Add one as another service with a volume, or use a managed database and put its address in `/opt/app/.env`."]
            + ([f"Only `{first.slug}` is exposed; the other services start but nothing routes to them."] if len(svcs) > 1 else [])),
        art("deploy/Caddyfile", _CADDY.replace("@@UPSTREAM@@", f"{first.slug}:{port_of(first)}"), "Reverse proxy configuration", conf="medium"),
    ]
    return files, []
