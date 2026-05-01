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

output "tailscale_secret_workspace" {
  description = "Secret Manager resource name for the Coder workspace Tailscale auth key."
  value       = google_secret_manager_secret.exe_workspace_authkey.name
}

output "tailscale_secret_workspace_id" {
  description = "Bare secret_id (no project prefix) for use in template variables."
  value       = google_secret_manager_secret.exe_workspace_authkey.secret_id
}

output "tailscale_keys_rotated_at" {
  description = "Timestamp of the most recent Tailscale auth-key rotation (driven by time_rotating)."
  value       = time_rotating.tailscale_keys.rfc3339
}

output "tailscale_acl_id" {
  description = "ID of the tailscale_acl resource (proves the live ACL has been bound to acl.hujson)."
  value       = tailscale_acl.this.id
}

output "vm_name" {
  description = "GCE instance name of the workspace VM (also its Tailscale hostname)."
  value       = google_compute_instance.exe_coder.name
}

output "vm_zone" {
  description = "GCE zone hosting the workspace VM."
  value       = google_compute_instance.exe_coder.zone
}

output "vm_external_ip" {
  description = "Ephemeral external IP of the workspace VM (egress + NAT only; no ingress allowed)."
  value       = google_compute_instance.exe_coder.network_interface[0].access_config[0].nat_ip
}

output "vm_service_account_email" {
  description = "Service account email the VM runs as."
  value       = google_service_account.exe_coder.email
}

output "exe_workspace_sa_email" {
  description = <<-EOF
Service account email stamped on Coder workspace VMs by the
dotfiles-devcontainer template. Pass this to
`cdr templates push --variable workspace_sa_email=...`.
EOF
  value       = google_service_account.exe_workspace.email
}

output "coder_internal_url" {
  description = <<-EOF
URL the Coder agent binary is downloaded from inside the workspace
VM. Resolves over MagicDNS on the tailnet (the workspace VM joins
with tag:exe-workspace at boot, then `exe-coder` resolves to the
control-plane VM's tailnet IP automatically). Public CF Access edge
is bypassed for this path. Pass to
`cdr templates push --variable coder_internal_url=...`.
EOF
  value       = "http://${google_compute_instance.exe_coder.name}:7080"
}

output "cloudflare_tunnel_id" {
  description = "Argo Tunnel ID (also the CNAME target as <id>.cfargotunnel.com)."
  value       = cloudflare_zero_trust_tunnel_cloudflared.exe.id
}

output "cloudflare_tunnel_cname" {
  description = "CNAME target the DNS records point at."
  value       = "${cloudflare_zero_trust_tunnel_cloudflared.exe.id}.cfargotunnel.com"
}

output "access_application_id" {
  description = "Cloudflare Access Application ID protecting the Coder UI."
  value       = cloudflare_zero_trust_access_application.coder.id
}

output "coder_cli_secret_client_id" {
  description = "Secret Manager resource name for the Coder CLI Cloudflare Access client_id."
  value       = google_secret_manager_secret.coder_cli_client_id.name
}

output "coder_cli_secret_client_secret" {
  description = "Secret Manager resource name for the Coder CLI Cloudflare Access client_secret."
  value       = google_secret_manager_secret.coder_cli_client_secret.name
}
