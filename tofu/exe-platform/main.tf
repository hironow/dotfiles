# exe-platform — the GCP foundation for the ax / Agent Substrate stack.
#
# Scope (section 3.1 of docs/plan/exe-google-ax.md): everything below the
# cluster's own workloads. API enablement, VPC + NAT, dedicated service
# accounts, the GKE cluster and its node pool, the storage sinks, and the
# money stops (L3 daily forced stop, uptime + Scheduler alerts, JPY budget).
# What runs INSIDE the cluster belongs to tofu/exe-cluster, not here.
#
# The node pool's SIZE is deliberately not owned by this stack: it is owned by
# the lease-based auto-sleep. See gke.tf for how that is enforced and why it is
# an explicit, documented exception to the IaC drift policy.
#
# CONFIDENTIALITY: the target project is private and this repo is public. No
# variable here has a default, so a missing value fails loudly instead of
# quietly targeting the wrong project; every identifier arrives through
# terraform.tfvars and backend.hcl, both gitignored (see .gitignore).
#
# The project is SHARED with two unrelated OpenTofu stacks. Every name here is
# exe-prefixed, the state lives under its own prefix in its own bucket, and API
# enablement is never disabled on destroy (see apis.tf) so tearing this stack
# down cannot break a neighbour.

terraform {
  required_version = ">= 1.12.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.0"
    }
  }

  # Partial backend config: `tofu init -backend-config=backend.hcl`.
  # The bucket name embeds the project id, so it cannot be written here; the
  # prefix can, and pinning it in tracked config is what stops a typo from
  # silently starting a second, empty state. The bucket itself is created
  # out-of-band by scripts/exe_platform_bootstrap.sh — a stack cannot create
  # its own backend.
  backend "gcs" {
    prefix = "exe-platform"
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = local.region
  zone    = local.zone
}
