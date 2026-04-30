# Derived values. Keep computation centralised here so resource files
# stay declarative.

locals {
  # Resource naming — stable, lowercased, hyphenated.
  prefix = "exe"

  # Tailscale tags. tag:owner is for hironow's devices; tag:agent is the
  # restricted role assigned to AI agents; tag:exe-coder labels the
  # workspace VM itself so ACL rules can target it.
  tag_owner     = "tag:owner"
  tag_agent     = "tag:agent"
  tag_exe_coder = "tag:exe-coder"

  # Subdomains.
  coder_host   = var.domain                   # exe.hironow.dev
  sandbox_host = "*.${var.sandbox_subdomain}" # *.sandbox.hironow.dev

  # GCS state bucket name (already created by bootstrap.sh; referenced for
  # outputs and consistency checks).
  state_bucket = "${var.gcp_project_id}-tofu-state"

  # Common labels applied to every GCP resource for cost allocation and
  # cleanup. GCP labels must be lowercase letters/digits/hyphens.
  common_labels = {
    stack       = local.prefix
    managed-by  = "opentofu"
    environment = "personal"
  }
}
