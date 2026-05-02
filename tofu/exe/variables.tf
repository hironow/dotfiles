# Inputs for the exe.hironow.dev stack.
#
# Defaults reflect the single-tenant decision (GCP project gen-ai-hironow,
# Tokyo region, Cloudflare zone hironow.dev). Override via terraform.tfvars
# (gitignored) or environment variables (TF_VAR_*) for sensitive values.

variable "gcp_project_id" {
  description = "GCP project hosting the Coder workspace VM and state bucket."
  type        = string
  default     = "gen-ai-hironow"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.gcp_project_id))
    error_message = "Must be a valid GCP project ID."
  }
}

variable "gcp_region" {
  description = "GCP region for the workspace VM."
  type        = string
  default     = "asia-northeast1"
}

variable "gcp_zone" {
  description = "GCP zone for the workspace VM (must be inside gcp_region)."
  type        = string
  default     = "asia-northeast1-a"
}

variable "domain" {
  description = "Apex hostname for the Coder UI / SSH gateway."
  type        = string
  default     = "exe.hironow.dev"
}

variable "sandbox_subdomain" {
  description = "Wildcard host used by agent-published sandbox apps. Reserved for the (P)ublic publish path; not yet provisioned."
  type        = string
  default     = "sandbox.hironow.dev"
}

variable "cf_zone_name" {
  description = "Cloudflare zone managing both domain and sandbox_subdomain."
  type        = string
  default     = "hironow.dev"
}

variable "cf_zone_id" {
  description = "Cloudflare zone ID for cf_zone_name. Discovered via `cf zones list` once and pinned to avoid runtime data-source variability."
  type        = string
}

variable "cf_account_id" {
  description = "Cloudflare account ID. Set via TF_VAR_cf_account_id; never committed."
  type        = string
  sensitive   = true
}

variable "tailnet" {
  description = "Tailscale tailnet identifier (e.g. <user>@github or <org>.ts.net)."
  type        = string
}

variable "owner_email" {
  description = "Email allowed by Cloudflare Access for the Coder UI."
  type        = string
  default     = "hironow365@gmail.com"
}

variable "machine_type" {
  description = "GCE machine type for the workspace VM."
  type        = string
  default     = "e2-small"
}

variable "preemptible" {
  description = "Run the workspace VM as preemptible (24h auto-stop, ~70% discount)."
  type        = bool
  default     = true
}

variable "vm_image" {
  description = "Boot image family for the workspace VM. Ubuntu 24.04 LTS (noble) — chosen over cos-stable because cos forbids host-side execution outside /var/lib/{google,docker,toolbox} and ships without gcloud, both of which the startup-script needs."
  type        = string
  default     = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2404-lts-amd64"
}

variable "boot_disk_size_gb" {
  description = "Boot disk size in GiB."
  type        = number
  default     = 30
  validation {
    condition     = var.boot_disk_size_gb >= 20 && var.boot_disk_size_gb <= 200
    error_message = "Disk must be between 20 and 200 GiB."
  }
}

# Coder server install — pinned per ADR 0007 (control-plane VM
# supply-chain hardening). Operator bumps the tag and the matching
# linux_amd64.tar.gz sha256 in lock-step. Sha256 is taken from the
# release's checksums.txt asset:
#   curl -fsSL https://github.com/coder/coder/releases/download/${ver}/coder_${ver#v}_checksums.txt
variable "coder_version" {
  description = "Coder server release tag (e.g. v2.31.11). Bump alongside coder_sha256."
  type        = string
  default     = "v2.31.11"
  validation {
    condition     = can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+$", var.coder_version))
    error_message = "coder_version must be a SemVer tag with leading 'v', e.g. v2.31.11."
  }
}

variable "coder_sha256" {
  description = "Sha256 of coder_<version>_linux_amd64.tar.gz; from the release's checksums.txt."
  type        = string
  default     = "32cf14eeecc96190dbc66b6965a3bdd563eaecc0d811a690e1e0b65828484979"
  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.coder_sha256))
    error_message = "coder_sha256 must be a lowercase 64-character hex sha256 digest."
  }
}
