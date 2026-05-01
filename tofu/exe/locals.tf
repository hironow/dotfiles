# Derived values. Keep computation centralised here so resource files
# stay declarative.

locals {
  # Resource naming — stable, lowercased, hyphenated.
  prefix = "exe"

  # Tailscale tags. tag:owner is for hironow's devices; tag:exe-coder
  # labels the Coder control-plane VM; tag:exe-workspace labels the
  # Coder workspace VMs (created from templates), which talk to
  # tag:exe-coder over the tailnet to fetch the agent binary; tag:agent
  # is the restricted role assigned to AI agents inside a workspace.
  tag_owner         = "tag:owner"
  tag_agent         = "tag:agent"
  tag_exe_coder     = "tag:exe-coder"
  tag_exe_workspace = "tag:exe-workspace"

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
