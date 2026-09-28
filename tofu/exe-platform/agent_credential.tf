# The Claude OAuth token's container (plan Q20, S9). Only the container: the
# operator adds the value themselves --
#
#   claude setup-token | gcloud secrets versions add exe-claude-oauth-token --data-file=-
#
# -- so the token never passes through a chat, an agent tool, a tracked file or
# this stack's state. `ax-job` reads the latest version at run time on the
# operator's own credentials and hands it to the task as an `ax ssh` argument,
# which keeps it out of the cluster's database, a Task's env and every actor
# snapshot.
#
# No IAM here on purpose: the operator reads it through their project role, and
# no workload identity, node or build account may. tests/unit/
# test_exe_agent_credential.py fails on any secret version or secret grant
# declared in the exe stacks.

resource "google_secret_manager_secret" "claude_oauth_token" {
  project   = var.gcp_project_id
  secret_id = "${local.prefix}-claude-oauth-token"

  # One location, the stack's region: each replica bills per active version.
  replication {
    user_managed {
      replicas {
        location = local.region
      }
    }
  }

  labels     = local.common_labels
  depends_on = [google_project_service.enabled]
}
