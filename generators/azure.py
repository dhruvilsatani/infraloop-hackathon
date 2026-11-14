"""Pack for the target 'one Azure server': Terraform for one Linux virtual machine, its network and firewall rules, docker-compose to run the app, Caddy in front.

Written from scan facts only. Rules this pack keeps (the same as the Hetzner pack):
  * no secret is ever written: you log in with the Azure CLI, and the app's variables are created as names only, to be filled on the server
  * SSH is closed unless the user lists their own address (admin_cidrs has no default); password login is switched off
  * Terraform state files are git-ignored in the folder
  * nothing is applied: the user runs terraform themselves"""
from .model import Artifact, HEADER
from .context import services
from .docker import _commented
from .hetzner import PORT, _CLOUD_INIT, _CADDY, _GITIGNORE, _compose

TF = "infra/azure"

_MAIN = '''terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
  }
}

# Credentials are NOT set here: log in with `az login` before you run terraform.
provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

resource "azurerm_resource_group" "app" {
  name     = "${var.name}-rg"
  location = var.location
}

resource "azurerm_virtual_network" "app" {
  name                = "${var.name}-vnet"
  address_space       = ["10.20.0.0/16"]
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
}

resource "azurerm_subnet" "app" {
  name                 = "${var.name}-subnet"
  resource_group_name  = azurerm_resource_group.app.name
  virtual_network_name = azurerm_virtual_network.app.name
  address_prefixes     = ["10.20.1.0/24"]
}

resource "azurerm_public_ip" "app" {
  name                = "${var.name}-ip"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name
  allocation_method   = "Static"
  sku                 = "Standard"
}

resource "azurerm_network_security_group" "app" {
  name                = "${var.name}-nsg"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name

  security_rule {
    name                       = "ssh-from-admin"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "22"
    source_address_prefixes    = var.admin_cidrs
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "http"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "80"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "https"
    priority                   = 120
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "443"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}

resource "azurerm_network_interface" "app" {
  name                = "${var.name}-nic"
  location            = azurerm_resource_group.app.location
  resource_group_name = azurerm_resource_group.app.name

  ip_configuration {
    name                          = "primary"
    subnet_id                     = azurerm_subnet.app.id
    private_ip_address_allocation = "Dynamic"
    public_ip_address_id          = azurerm_public_ip.app.id
  }
}

resource "azurerm_network_interface_security_group_association" "app" {
  network_interface_id      = azurerm_network_interface.app.id
  network_security_group_id = azurerm_network_security_group.app.id
}

resource "azurerm_linux_virtual_machine" "app" {
  name                = var.name
  resource_group_name = azurerm_resource_group.app.name
  location            = azurerm_resource_group.app.location
  size                = var.vm_size
  admin_username      = "azureuser"

  network_interface_ids           = [azurerm_network_interface.app.id]
  disable_password_authentication = true

  admin_ssh_key {
    username   = "azureuser"
    public_key = var.ssh_public_key
  }

  os_disk {
    caching              = "ReadWrite"
    storage_account_type = "StandardSSD_LRS"
    disk_size_gb         = var.disk_gb
  }

  source_image_reference {
    publisher = "Canonical"
    offer     = "ubuntu-24_04-lts"
    sku       = "server"
    version   = "latest"
  }

  custom_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
    repo_url     = var.repo_url
    branch       = var.branch
    site_address = var.domain == "" ? ":80" : var.domain
  }))

  tags = {
    managed-by = "terraform"
    app        = var.name
  }
}
'''

_VARIABLES = '''variable "subscription_id" {
  description = "Your Azure subscription id (not a secret). Find it with: az account show --query id -o tsv"
  type        = string
}

variable "ssh_public_key" {
  description = "The public key (the line from your .pub file) that may log in as azureuser. Password login is switched off."
  type        = string
}

variable "admin_cidrs" {
  description = "Addresses allowed to reach SSH, for example [\\"203.0.113.4/32\\"]. There is no default on purpose."
  type        = list(string)

  validation {
    condition     = length(var.admin_cidrs) > 0 && !contains(var.admin_cidrs, "0.0.0.0/0") && !contains(var.admin_cidrs, "*")
    error_message = "List at least one address and do not open SSH to the whole internet (0.0.0.0/0 or *)."
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
  description = "Name used for the resource group, server and network parts."
  type        = string
  default     = "app"
}

variable "vm_size" {
  description = "Azure virtual machine size. Check that it is offered in your region: az vm list-skus --location westeurope --size Standard_B --output table"
  type        = string
  default     = "@@TYPE@@"
}

variable "location" {
  description = "Azure region. The price in the report was read for West Europe (westeurope)."
  type        = string
  default     = "@@REGION@@"
}

variable "disk_gb" {
  description = "Size of the server's disk in GB. The price in the report assumes 32."
  type        = number
  default     = 32
}

variable "domain" {
  description = "Domain name pointing at the server, for automatic HTTPS. Leave empty to serve plain HTTP on the IP address."
  type        = string
  default     = ""
}
'''

_OUTPUTS = '''output "server_ip" {
  description = "Public IPv4 address of the server."
  value       = azurerm_public_ip.app.ip_address
}

output "url" {
  description = "Where the app will answer once it has started."
  value       = var.domain == "" ? "http://${azurerm_public_ip.app.ip_address}" : "https://${var.domain}"
}

output "ssh" {
  description = "How to log in (works from the addresses in admin_cidrs)."
  value       = "ssh azureuser@${azurerm_public_ip.app.ip_address}"
}
'''

_TFVARS = '''# Copy to terraform.tfvars and fill in. terraform.tfvars is git-ignored: keep it that way.
# Azure credentials do NOT go here. Log in first with:  az login
subscription_id = "00000000-0000-0000-0000-000000000000"
ssh_public_key  = "ssh-ed25519 AAAA... you@example.com"
admin_cidrs     = ["203.0.113.4/32"]   # your own public address
repo_url        = "https://github.com/YOU/YOUR-REPO.git"
# branch       = "main"
# domain       = "app.example.com"
# location     = "westeurope"
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
    typ = srv.get("name") or "Standard_B1ms"
    region = srv.get("locations") or "westeurope"
    first = svcs[0]
    common_review = ["Nothing here was run against Azure: no server, container or Azure call was made. Run `terraform init && terraform validate && terraform plan` before `apply`.",
                     "Azure sells each VM size only in some regions and to some subscriptions (quotas). If `apply` is refused, pick another size or region in `terraform.tfvars`."]

    def art(path, content, title, assume=(), review=(), conf="medium"):
        return Artifact(path=path, content=content, gap=gap, title=title, confidence=conf, assumptions=list(assume), review=list(review))

    files = [
        art(f"{TF}/main.tf", _commented(HEADER) + _MAIN, "Terraform: server, network, public IP and firewall rules",
            ["Ubuntu 24.04 on one Linux virtual machine in a new resource group; ports 80 and 443 are open to everyone and SSH only to `admin_cidrs`.",
             "Password login is switched off: only your SSH key works.",
             "docker and docker-compose come from Ubuntu's own package repository."],
            common_review + ["Azure credentials come from `az login`. InfraLoop never asks for them and never stores them.",
                             "Terraform state (`terraform.tfstate`) is created on your machine and can contain sensitive values. It is git-ignored here: keep it that way or move it to a remote backend.",
                             "B-series servers are burstable: long periods of heavy CPU use run out of credits and the server slows down."]),
        art(f"{TF}/variables.tf", _commented(HEADER) + _VARIABLES.replace("@@TYPE@@", typ).replace("@@REGION@@", region), "Terraform: variables",
            [f"Server size {typ} was chosen by the price list for this provider and the report's CPU and memory estimate; it is not a measured size."],
            ["Load-test before you trust the size."]),
        art(f"{TF}/outputs.tf", _commented(HEADER) + _OUTPUTS, "Terraform: outputs", conf="high"),
        art(f"{TF}/cloud-init.yaml", "# " + HEADER + "\n" + _CLOUD_INIT.replace("@@ENV@@", env_lines), "Server start-up script (cloud-init)",
            ["The repository is public (or readable without a password) and has `docker-compose.prod.yml` on branch `main`.",
             "The app's environment variables are created as names only, in `/opt/app/.env` on the server."],
            ["Fill in the values by logging in: `ssh azureuser@<server_ip>`, then `sudo nano /opt/app/.env` and `cd /opt/app && sudo docker compose -f docker-compose.prod.yml up -d`.",
             "The app will not work until you do. This way no secret passes through Terraform state or Azure's custom-data field.",
             "Private repository: use a deploy key or build and push an image to a registry instead; this pack does neither."]),
        art(f"{TF}/terraform.tfvars.example", _TFVARS, "Terraform: example values", conf="high"),
        art(f"{TF}/.gitignore", _GITIGNORE, "Keeps Terraform state and your values out of git", conf="high"),
        art("docker-compose.prod.yml", _compose(svcs), "docker-compose file for the server",
            [f"Each service listens on its template port ({', '.join(f'{s.slug}: {PORT[s.kind]}' for s in svcs)}).",
             f"Only `{first.slug}` is reachable from outside, through Caddy."],
            ["Caddy gets a free HTTPS certificate only when `domain` is set and its DNS record points at the server's public IP.",
             "`caddy:2` follows the latest 2.x release: pin an exact version once it works.",
             "A database is not part of this file. Add one as another service with a volume, or use a managed database and put its address in `/opt/app/.env`."]
            + ([f"Only `{first.slug}` is exposed; the other services start but nothing routes to them."] if len(svcs) > 1 else [])),
        art("deploy/Caddyfile", _CADDY.replace("@@UPSTREAM@@", f"{first.slug}:{PORT[first.kind]}"), "Reverse proxy configuration", conf="medium"),
    ]
    return files, []
