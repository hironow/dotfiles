# Outputs for the just recipes and the spike. Anything that embeds an
# identifier is marked sensitive, as in exe-platform.

output "atespace" {
  description = "The Substrate atespace (and namespace) tasks run in. Task YAML names it as metadata.atespace."
  value       = local.atespace
}

output "ax_snapshots_location" {
  description = "Where AX tells Substrate to write every task's snapshots."
  value       = local.ax_snapshots_location
  sensitive   = true
}

output "gvisor_mirror_url" {
  description = "The private copy of the gVisor asset the SandboxConfig names."
  value       = local.gvisor_mirror_url
  sensitive   = true
}

output "worker_pool" {
  description = "The WorkerPool's namespace/name, or null until ateom_gvisor_image is set."
  value       = local.worker_pool_enabled ? "${local.atespace}/${local.worker_pool_name}" : null
}
