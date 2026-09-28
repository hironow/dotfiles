# Outputs.
#
# These are how the just recipes learn the private identifiers without any of
# them being written into a tracked file: `just exe-ctx` reads project_id and
# zone from here rather than from a constant in the justfile.
#
# Outputs land in state (a private, UBLA + PAP bucket), never in the repo. The
# ones that carry an identifier are marked sensitive so a stray `tofu output`
# with no argument cannot print them into a terminal transcript.

output "project_id" {
  description = "The private project. Consumed by just recipes via `tofu output -raw`."
  value       = var.gcp_project_id
  sensitive   = true
}

output "zone" {
  description = "Cluster zone (not an identifier)."
  value       = local.zone
}

output "region" {
  description = "Cluster region (not an identifier)."
  value       = local.region
}

output "cluster_name" {
  description = "GKE cluster name."
  value       = google_container_cluster.exe.name
}

output "node_pool_name" {
  description = "The single node pool whose size the auto-sleep owns."
  value       = google_container_node_pool.main.name
}

output "cluster_dns_endpoint" {
  description = <<-EOT
    The IAM-guarded DNS control-plane endpoint. There is no IP endpoint; this is
    the only way in, and it authenticates every request with Google IAM.
  EOT
  value       = google_container_cluster.exe.control_plane_endpoints_config[0].dns_endpoint_config[0].endpoint
  sensitive   = true
}

output "node_pool_set_size_uri" {
  description = "The setSize URI L3 posts to. Exposed so a manual stop uses the same target, not a retyped one."
  value       = local.node_pool_set_size_uri
  sensitive   = true
}

output "l3_scheduler_job" {
  description = "Name of the L3 job, for `gcloud scheduler jobs run`."
  value       = google_cloud_scheduler_job.l3_daily_stop.name
}

output "l2_scheduler_job" {
  description = "Name of the L2 tick, for `gcloud scheduler jobs run` — the way to force an enforcement pass without waiting for the cadence. Null while L2 is not deployed (no enforcer_image)."
  value       = one(google_cloud_scheduler_job.l2_tick[*].name)
}

output "l2_enforcer_job" {
  description = <<-EOT
    Name of the L2 Cloud Run job. Exposed so a recipe reads the name instead of
    retyping it: `gcloud run jobs execute` bypasses the tick, which is what the
    Phase 3 e2e needs, and `gcloud run jobs executions list` is where a failed
    enforcement pass is actually visible (the tick reports success as soon as the
    execution is created, not when it succeeds). Null while L2 is not deployed
    (no enforcer_image).
  EOT
  value       = one(google_cloud_run_v2_job.l2_enforcer[*].name)
}

output "bucket_snapshots" {
  description = "Actor snapshot bucket (AX_SNAPSHOTS_BUCKET)."
  value       = google_storage_bucket.snapshots.name
  sensitive   = true
}

output "bucket_ops" {
  description = "Lease / drain / enforce object bucket."
  value       = google_storage_bucket.ops.name
  sensitive   = true
}

output "bucket_build" {
  description = "Bounded Cloud Build staging bucket."
  value       = google_storage_bucket.build.name
  sensitive   = true
}

output "ar_platform_repo" {
  description = "Artifact Registry repository for platform images (KO_DOCKER_REPO base)."
  value       = "${local.region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.platform.repository_id}"
  sensitive   = true
}

output "ar_task_repo" {
  description = "Artifact Registry repository for task images."
  value       = "${local.region}-docker.pkg.dev/${var.gcp_project_id}/${google_artifact_registry_repository.task.repository_id}"
  sensitive   = true
}

output "ar_task_repository" {
  description = <<-EOT
    The exe-task repository's resource name (projects/P/locations/L/repositories/R):
    what exe-reap is told to protect (EXE_AR_REPOS), and compares with the
    repository parsed out of each task's image reference.
  EOT
  value       = "projects/${var.gcp_project_id}/locations/${local.region}/repositories/${google_artifact_registry_repository.task.repository_id}"
  sensitive   = true
}

output "service_account_emails" {
  description = "The five dedicated identities, by role."
  value = {
    node      = google_service_account.node.email
    build     = google_service_account.build.email
    reaper    = google_service_account.reaper.email
    enforcer  = google_service_account.enforcer.email
    scheduler = google_service_account.scheduler.email
  }
  sensitive = true
}

output "workload_identity_principals" {
  description = <<-EOT
    The principal:// members this stack binds. Exposed because the cluster stack
    has to create KSAs with exactly these names, and a mismatch shows up only as
    a 403 at first use.
  EOT
  value = {
    atelet      = local.wi_atelet
    api_server  = local.wi_api_server
    reaper      = local.wi_reaper
    snapshot_gc = local.wi_snapshot_gc
  }
  sensitive = true
}

output "state_kms_key" {
  description = <<-EOT
    The KMS key tofu/exe-cluster encrypts its state with (kms.tf). Its id embeds
    the project id, so it reaches that stack through its gitignored tfvars, not
    through a tracked file.
  EOT
  value       = google_kms_crypto_key.state.id
  sensitive   = true
}

output "claude_token_secret" {
  description = "The Secret Manager secret holding the Claude OAuth token (plan Q20). ax-job reads its latest version; the operator adds versions."
  value       = google_secret_manager_secret.claude_oauth_token.secret_id
}
