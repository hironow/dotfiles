# Outputs are filled in by subsequent commits as resources are added.
# Declared here so the file exists from the start and downstream
# references (smoke.sh, runbook) have a single source of truth.

output "coder_url" {
  description = "Public URL for the Coder UI (behind Cloudflare Access)."
  value       = "https://${local.coder_host}"
}

output "sandbox_wildcard" {
  description = "Wildcard hostname reserved for agent-published apps (P-mode, not yet provisioned)."
  value       = local.sandbox_host
}

output "state_bucket" {
  description = "GCS bucket holding the encrypted tofu state."
  value       = local.state_bucket
}

output "tailscale_secret_coder" {
  description = "Secret Manager resource name for the workspace VM Tailscale auth key."
  value       = google_secret_manager_secret.exe_coder_authkey.name
}

output "tailscale_secret_agent" {
  description = "Secret Manager resource name for the AI agent Tailscale auth key."
  value       = google_secret_manager_secret.agent_authkey.name
}

output "tailscale_keys_rotated_at" {
  description = "Timestamp of the most recent Tailscale auth-key rotation (driven by time_rotating)."
  value       = time_rotating.tailscale_keys.rfc3339
}
