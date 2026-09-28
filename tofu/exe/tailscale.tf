# Tailscale — Pattern A permission model.
#
# Three roles, expressed as tags:
#   tag:owner      hironow's personal devices (laptop, phone, etc.)
#   tag:exe-coder  the workspace VM itself
#   tag:agent      AI agents executing inside the workspace
#
# Two reusable, expiring auth keys are issued and stashed in GCP Secret
# Manager. The VM startup-script and the agent runtime read them by
# secret name; the plaintext never touches the repo.
#
# Rotation: tofu apply re-issues keys when their expiry is < 7 days
# (driven by `time_rotating`). Old key versions remain in Secret
# Manager until manual destroy, so an in-flight session is not cut.

resource "time_rotating" "tailscale_keys" {
  rotation_days = 90
}

# --- workspace VM key -------------------------------------------------

resource "tailscale_tailnet_key" "exe_coder" {
  # Tailscale rejects '(', ')', ':' etc. in key descriptions with
  # 'description had invalid characters (400)'. Keep it alphanumeric
  # + spaces + hyphens only.
  description = "exe-coder workspace VM auto-join managed by tofu"
  reusable    = true
  # ephemeral = true: when the VM stops (preemptible 24h auto-stop, or
  # tofu destroy), Tailscale automatically removes the device from the
  # tailnet. Without this every boot leaves an 'exe-coder-N' stale
  # entry in the admin UI. MagicDNS (exe-coder.<tailnet>.ts.net) still
  # resolves to the active VM each boot, so the tradeoff (IP changes
  # per reboot) is invisible to consumers.
  ephemeral     = true
  preauthorized = true
  expiry        = 90 * 24 * 3600 # 90 days
  tags          = [local.tag_exe_coder]

  lifecycle {
    replace_triggered_by = [time_rotating.tailscale_keys.id]
  }
}

resource "google_secret_manager_secret" "exe_coder_authkey" {
  secret_id = "${local.prefix}-tailscale-coder-authkey"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "exe_coder_authkey" {
  secret      = google_secret_manager_secret.exe_coder_authkey.id
  secret_data = tailscale_tailnet_key.exe_coder.key
}

# --- workspace VM key -------------------------------------------------
#
# Auth key carrying tag:exe-workspace. Stamped on every Coder workspace
# VM so it can join the tailnet and reach exe-coder.<tailnet>:7080
# directly — no public CF Access edge hop. Reusable so a single key
# brings up many concurrent workspaces; ephemeral so torn-down ones
# auto-prune.

resource "tailscale_tailnet_key" "exe_workspace" {
  description   = "exe Coder workspace tailnet join key"
  reusable      = true
  ephemeral     = true
  preauthorized = true
  expiry        = 90 * 24 * 3600
  tags          = [local.tag_exe_workspace]

  lifecycle {
    replace_triggered_by = [time_rotating.tailscale_keys.id]
  }
}

resource "google_secret_manager_secret" "exe_workspace_authkey" {
  secret_id = "${local.prefix}-tailscale-workspace-authkey"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "exe_workspace_authkey" {
  secret      = google_secret_manager_secret.exe_workspace_authkey.id
  secret_data = tailscale_tailnet_key.exe_workspace.key
}

# --- AI agent key -----------------------------------------------------
#
# Reusable so the same key can bring up multiple agent sessions; ACL
# (next commit) restricts what tag:agent can reach, not how many devices
# carry it.

resource "tailscale_tailnet_key" "agent" {
  description   = "AI agent restricted-role key managed by tofu"
  reusable      = true
  ephemeral     = true # agents come and go; auto-prune from tailnet
  preauthorized = true
  expiry        = 90 * 24 * 3600
  tags          = [local.tag_agent]

  lifecycle {
    replace_triggered_by = [time_rotating.tailscale_keys.id]
  }
}

resource "google_secret_manager_secret" "agent_authkey" {
  secret_id = "${local.prefix}-tailscale-agent-authkey"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "agent_authkey" {
  secret      = google_secret_manager_secret.agent_authkey.id
  secret_data = tailscale_tailnet_key.agent.key
}

# --- ACL: handed over to tofu/tailnet ---------------------------------
#
# This stack is being retired (Phase 7). The tailnet's ACL outlives it:
# tofu/tailnet takes it over by import. Here it is dropped from state
# only -- destroy = false leaves the live policy exactly as it is, so
# the tailnet is never without one, and the stack's destroy no longer
# meets the ACL's prevent_destroy. Apply this before tofu/tailnet's
# first plan, so the ACL never has two owners.
removed {
  from = tailscale_acl.this

  lifecycle {
    destroy = false
  }
}
