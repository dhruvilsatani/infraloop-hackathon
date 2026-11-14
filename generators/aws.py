"""Pack for the target 'one AWS server': Terraform for one EC2 server, its security group and a fixed public address, docker-compose to run the app, Caddy in front.

Written from scan facts only. Rules this pack keeps (the same as the Hetzner pack):
  * no secret is ever written: AWS credentials come from your own environment or profile, and the app's variables are created as names only, to be filled on the server
  * SSH is closed unless the user lists their own address (admin_cidrs has no default)
  * Terraform state files are git-ignored in the folder
  * nothing is applied: the user runs terraform themselves"""
from .model import Artifact, HEADER
from .context import services
from .docker import _commented
from .hetzner import PORT, _CLOUD_INIT, _CADDY, _GITIGNORE, _compose

TF = "infra/aws"

_MAIN = '''terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

# Credentials are NOT set here. Terraform reads them the way the AWS CLI does:
# AWS_PROFILE, or AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your shell.
provider "aws" {
  region = var.region
}

# The default network that every AWS account has in a region (unless someone deleted it).
data "aws_vpc" "default" {
  default = true
}

# Ubuntu 24.04 LTS, looked up from Canonical's public parameter so the image id is never written by hand.
data "aws_ssm_parameter" "ubuntu" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}

resource "aws_key_pair" "admin" {
  key_name   = "${var.name}-admin"
  public_key = var.ssh_public_key
}

resource "aws_security_group" "app" {
  name_prefix = "${var.name}-"
  description = "Web traffic for everyone, SSH only for the addresses in admin_cidrs"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH from your own address"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.admin_cidrs
  }

  ingress {
    description      = "HTTP"
    from_port        = 80
    to_port          = 80
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  ingress {
    description      = "HTTPS"
    from_port        = 443
    to_port          = 443
    protocol         = "tcp"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  egress {
    description = "Everything outbound (package downloads, git clone, image pulls)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.name}-web"
  }
}

resource "aws_instance" "app" {
  ami                    = nonsensitive(data.aws_ssm_parameter.ubuntu.value)
  instance_type          = var.instance_type
  key_name               = aws_key_pair.admin.key_name
  vpc_security_group_ids = [aws_security_group.app.id]

  user_data = templatefile("${path.module}/cloud-init.yaml", {
    repo_url     = var.repo_url
    branch       = var.branch
    site_address = var.domain == "" ? ":80" : var.domain
  })

  # Requires the newer, safer way for software on the server to read its own metadata (IMDSv2).
  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_size = var.disk_gb
    volume_type = "gp3"
    encrypted   = true
  }

  tags = {
    Name       = var.name
    managed-by = "terraform"
  }
}

# A fixed public address, so the IP does not change if the server is stopped and started.
resource "aws_eip" "app" {
  domain   = "vpc"
  instance = aws_instance.app.id

  tags = {
    Name = "${var.name}-ip"
  }
}
'''

_VARIABLES = '''variable "region" {
  description = "AWS region. The price in the report was read for Frankfurt (eu-central-1)."
  type        = string
  default     = "@@REGION@@"
}

variable "ssh_public_key" {
  description = "The public key (the line from your .pub file) that may log in as the ubuntu user."
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
  description = "Name used for the server, key and firewall rules."
  type        = string
  default     = "app"
}

variable "instance_type" {
  description = "EC2 instance type. Check that it is offered in your region: aws ec2 describe-instance-type-offerings --location-type region"
  type        = string
  default     = "@@TYPE@@"
}

variable "disk_gb" {
  description = "Size of the server's disk in GB. The price in the report assumes 20."
  type        = number
  default     = 20
}

variable "domain" {
  description = "Domain name pointing at the server, for automatic HTTPS. Leave empty to serve plain HTTP on the IP address."
  type        = string
  default     = ""
}
'''

_OUTPUTS = '''output "server_ip" {
  description = "Public IPv4 address of the server."
  value       = aws_eip.app.public_ip
}

output "url" {
  description = "Where the app will answer once it has started."
  value       = var.domain == "" ? "http://${aws_eip.app.public_ip}" : "https://${var.domain}"
}

output "ssh" {
  description = "How to log in (works from the addresses in admin_cidrs)."
  value       = "ssh ubuntu@${aws_eip.app.public_ip}"
}
'''

_TFVARS = '''# Copy to terraform.tfvars and fill in. terraform.tfvars is git-ignored: keep it that way.
# AWS credentials do NOT go here. Log in the way the AWS CLI does (for example: export AWS_PROFILE=...).
ssh_public_key = "ssh-ed25519 AAAA... you@example.com"
admin_cidrs    = ["203.0.113.4/32"]   # your own public address
repo_url       = "https://github.com/YOU/YOUR-REPO.git"
# branch      = "main"
# domain      = "app.example.com"
# region      = "eu-central-1"
'''


def pack(scan, gaps, target):
    svcs, _ = services(scan)
    if not svcs:
        return [], ["The scan found no service this pack has a template for."]
    srv = (target or {}).get("server") or {}
    issues = {g["issue"] for g in gaps}
    gap = "no_iac" if "no_iac" in issues else ("no_cloud_iac" if "no_cloud_iac" in issues else "")
    names = list(dict.fromkeys(scan.get("env_vars") or []))
    env_lines = "".join(f"      {n}=\n" for n in names)
    typ = srv.get("name") or "t3.small"
    region = srv.get("locations") or "eu-central-1"
    first = svcs[0]
    common_review = ["Nothing here was run against AWS: no server, container or AWS call was made. Run `terraform init && terraform validate && terraform plan` before `apply`.",
                     "The server is created in your account's default network (VPC). If your account has none, `terraform plan` will say so: create one or point the file at your own network."]

    def art(path, content, title, assume=(), review=(), conf="medium"):
        return Artifact(path=path, content=content, gap=gap, title=title, confidence=conf, assumptions=list(assume), review=list(review))

    files = [
        art(f"{TF}/main.tf", _commented(HEADER) + _MAIN, "Terraform: server, SSH key, security group and fixed IP",
            ["Ubuntu 24.04 on one EC2 server in the default network; ports 80 and 443 are open to everyone and SSH only to `admin_cidrs`.",
             "The server disk is encrypted and the server requires the safer metadata mode (IMDSv2).",
             "docker and docker-compose come from Ubuntu's own package repository."],
            common_review + ["AWS credentials are read from your own environment or profile. InfraLoop never asks for them and never stores them.",
                             "Terraform state (`terraform.tfstate`) is created on your machine and can contain sensitive values. It is git-ignored here: keep it that way or move it to a remote backend.",
                             "T3 servers are burstable. If the app uses a lot of CPU for long periods, AWS bills extra for it: watch the CPU credit metrics in CloudWatch."]),
        art(f"{TF}/variables.tf", _commented(HEADER) + _VARIABLES.replace("@@TYPE@@", typ).replace("@@REGION@@", region), "Terraform: variables",
            [f"Server size {typ} was chosen by the price list for this provider and the report's CPU and memory estimate; it is not a measured size."],
            ["Load-test before you trust the size. AWS changes instance offerings over time: check that the type exists in your region."]),
        art(f"{TF}/outputs.tf", _commented(HEADER) + _OUTPUTS, "Terraform: outputs", conf="high"),
        art(f"{TF}/cloud-init.yaml", "# " + HEADER + "\n" + _CLOUD_INIT.replace("@@ENV@@", env_lines), "Server start-up script (cloud-init)",
            ["The repository is public (or readable without a password) and has `docker-compose.prod.yml` on branch `main`.",
             "The app's environment variables are created as names only, in `/opt/app/.env` on the server."],
            ["Fill in the values by logging in: `ssh ubuntu@<server_ip>`, then `sudo nano /opt/app/.env` and `cd /opt/app && sudo docker compose -f docker-compose.prod.yml up -d`.",
             "The app will not work until you do. This way no secret passes through Terraform state or the AWS user-data field.",
             "Private repository: use a deploy key or build and push an image to a registry instead; this pack does neither."]),
        art(f"{TF}/terraform.tfvars.example", _TFVARS, "Terraform: example values", conf="high"),
        art(f"{TF}/.gitignore", _GITIGNORE, "Keeps Terraform state and your values out of git", conf="high"),
        art("docker-compose.prod.yml", _compose(svcs), "docker-compose file for the server",
            [f"Each service listens on its template port ({', '.join(f'{s.slug}: {PORT[s.kind]}' for s in svcs)}).",
             f"Only `{first.slug}` is reachable from outside, through Caddy."],
            ["Caddy gets a free HTTPS certificate only when `domain` is set and its DNS record points at the server's fixed IP.",
             "`caddy:2` follows the latest 2.x release: pin an exact version once it works.",
             "A database is not part of this file. Add one as another service with a volume, or use a managed database and put its address in `/opt/app/.env`."]
            + ([f"Only `{first.slug}` is exposed; the other services start but nothing routes to them."] if len(svcs) > 1 else [])),
        art("deploy/Caddyfile", _CADDY.replace("@@UPSTREAM@@", f"{first.slug}:{PORT[first.kind]}"), "Reverse proxy configuration", conf="medium"),
    ]
    return files, []
