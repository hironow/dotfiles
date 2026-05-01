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
  description   = "exe-coder workspace VM auto-join (managed by tofu)"
  reusable      = true
  ephemeral     = false
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

# --- AI agent key -----------------------------------------------------
#
# Reusable so the same key can bring up multiple agent sessions; ACL
# (next commit) restricts what tag:agent can reach, not how many devices
# carry it.

resource "tailscale_tailnet_key" "agent" {
  description   = "AI agent restricted-role key (managed by tofu)"
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

# --- ACL bind --------------------------------------------------------
#
# Wire exe/tailscale/acl.hujson into the live tailnet. Without this
# resource, tag:agent keys would be issued under whatever ACL is
# currently in the admin UI — which by default lets every member
# device reach every other device. codex review flagged this as a
# critical hole: the auth keys we issue declare scoped permissions,
# but only the ACL actually enforces them.
#
# Lockout precautions:
#   - overwrite_existing_content = true so the first apply does not
#     stall on a divergent admin-UI ACL; declare tofu state as the
#     truth.
#   - lifecycle.prevent_destroy = true so a careless `tofu destroy`
#     cannot wipe the ACL and lock the operator out of the tailnet
#     in one move (must be removed manually).
#   - Tailscale itself maintains a 24h grace period on ACL pushes;
#     during that window an admin can revert from the UI.

resource "tailscale_acl" "this" {
  acl                        = file("${path.module}/../../exe/tailscale/acl.hujson")
  overwrite_existing_content = true

  lifecycle {
    prevent_destroy = true
  }
}
