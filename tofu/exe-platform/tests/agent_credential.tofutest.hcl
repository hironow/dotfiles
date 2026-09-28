# What this file pins: the Secret Manager secret that holds the Claude OAuth
# token (plan Q20 / S9), and that nothing but the operator can read it.
#
# Q20: the token lives in the private project's Secret Manager and is handed to
# a task per run by `ax-job` (on the operator's own credentials) as an `ax ssh`
# argument, so it is never stored in the cluster's database, a Task's env, or an
# actor snapshot. This stack creates only the container: the value is added by
# the operator (`claude setup-token` piped into `gcloud secrets versions add`),
# never through a chat, an agent tool, a tracked file or state.
#
#   - no version resource, and no secret_data anywhere in this stack: a version
#     created here would put the token in state and in every saved plan;
#   - one replica, in the stack's region: one location billed per version;
#   - no IAM on the secret at all: the operator reads it through their project
#     role, and no workload identity, node or build account is ever granted it.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "the_claude_token_secret_is_an_empty_regional_container" {
  command = plan

  assert {
    condition     = google_secret_manager_secret.claude_oauth_token.secret_id == "exe-claude-oauth-token"
    error_message = "the Claude token secret must be named exe-claude-oauth-token: ax-job and the operator's `gcloud secrets versions add` both address it by that name."
  }

  assert {
    condition     = one(one(google_secret_manager_secret.claude_oauth_token.replication).user_managed).replicas[0].location == "asia-northeast1" && length(one(one(google_secret_manager_secret.claude_oauth_token.replication).user_managed).replicas) == 1
    error_message = "the secret must be replicated to exactly one location, the stack's region: each extra replica bills per version, and the token has no reason to leave the region."
  }
}
