# What this file pins: every Workload Identity binding names the pool the cluster
# creates, and is planned AFTER that cluster.
#
# The pool, <project>.svc.id.goog, comes into existence with the first cluster
# that enables Workload Identity. A binding sent before it fails with "Identity
# Pool does not exist": all seven did on the first apply, because nothing tied
# their creation to the cluster's.
#
# Two kinds of assertion, because they catch different mistakes:
#
#   VALUE. Each member is exactly the principal for its Kubernetes service
#   account in the pool the cluster declares, with the project NUMBER in the
#   path. The pool is NAMED by project id and ADDRESSED by project number; mixing
#   the two up yields a binding that matches nothing, and a 403 at first use.
#
#   ORDER. A plan TARGETED at one binding contains everything that binding
#   depends on. If the cluster is among them, the binding cannot be created
#   before it. Each run below targets one binding and reads the cluster's name:
#   when the binding does not depend on the cluster, the cluster is not in the
#   targeted plan, its name is unknown, and the run fails with "Unknown
#   condition". In THIS file that error means "this binding can be created
#   before its pool exists". A value comparison alone cannot show it: the member
#   reads the same whether its pool segment came from the cluster or from
#   var.gcp_project_id, and OpenTofu refuses to override a configured attribute
#   such as workload_pool to tell the two apart.
#
# Every ORDER run prints OpenTofu's "Resource targeting is in effect" warning.
# Here targeting is the instrument, not an accident.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "every_member_names_its_ksa_in_the_pool_the_cluster_creates" {
  command = plan

  assert {
    condition     = google_storage_bucket_iam_member.atelet_snapshots_object_admin.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/ate-system/sa/atelet"
    error_message = "atelet_snapshots_object_admin must bind ate-system/atelet in the cluster's own Workload Identity pool, addressed by project number. Anything else is a grant nobody holds: the first actor suspend fails with a 403."
  }

  assert {
    condition     = google_storage_bucket_iam_member.atelet_snapshots_bucket_viewer.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/ate-system/sa/atelet"
    error_message = "atelet_snapshots_bucket_viewer must bind ate-system/atelet in the cluster's own Workload Identity pool, addressed by project number."
  }

  assert {
    condition     = google_storage_bucket_iam_member.api_server_snapshots_object_admin.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/ate-system/sa/ate-api-server"
    error_message = "api_server_snapshots_object_admin must bind ate-system/ate-api-server in the cluster's own Workload Identity pool, addressed by project number. Losing it silently breaks snapshot GC and tag copying."
  }

  assert {
    condition     = google_storage_bucket_iam_member.api_server_snapshots_bucket_viewer.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/ate-system/sa/ate-api-server"
    error_message = "api_server_snapshots_bucket_viewer must bind ate-system/ate-api-server in the cluster's own Workload Identity pool, addressed by project number."
  }

  assert {
    condition     = google_storage_bucket_iam_member.reaper_ops.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-reaper"
    error_message = "reaper_ops must bind exe-ops/exe-reaper in the cluster's own Workload Identity pool, addressed by project number: it is how L1 reads the lease."
  }

  assert {
    condition     = google_storage_bucket_iam_member.reaper_ops_write.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-reaper"
    error_message = "reaper_ops_write must bind exe-ops/exe-reaper in the cluster's own Workload Identity pool, addressed by project number: it is how L1 writes drain.json."
  }

  assert {
    condition     = google_artifact_registry_repository_iam_member.atelet_task_reader.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/ate-system/sa/atelet"
    error_message = "atelet_task_reader must bind ate-system/atelet in the cluster's own Workload Identity pool, addressed by project number: atelet pulls actor images itself."
  }

  assert {
    condition     = google_artifact_registry_repository_iam_member.reaper_task_tags.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-reaper"
    error_message = "reaper_task_tags must bind exe-ops/exe-reaper in the cluster's own Workload Identity pool, addressed by project number: the reaper moves inuse- tags."
  }

  assert {
    condition     = google_artifact_registry_repository_iam_member.reaper_platform_tags.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-reaper"
    error_message = "reaper_platform_tags must bind exe-ops/exe-reaper in the cluster's own Workload Identity pool, addressed by project number: the reaper moves inuse- tags on platform images too."
  }

  assert {
    condition     = google_storage_bucket_iam_member.snapshot_gc_list.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-snapshot-gc"
    error_message = "snapshot_gc_list must bind exe-ops/exe-snapshot-gc in the cluster's own Workload Identity pool, addressed by project number: the GC lists the snapshot bucket."
  }

  assert {
    condition     = google_storage_bucket_iam_member.snapshot_gc_delete.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-snapshot-gc"
    error_message = "snapshot_gc_delete must bind exe-ops/exe-snapshot-gc in the cluster's own Workload Identity pool, addressed by project number: the GC deletes orphaned actor snapshots."
  }
}

# --- ORDER: one targeted plan per binding ------------------------------------

run "atelet_snapshots_object_admin_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.atelet_snapshots_object_admin]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with atelet_snapshots_object_admin: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "atelet_snapshots_bucket_viewer_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.atelet_snapshots_bucket_viewer]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with atelet_snapshots_bucket_viewer: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "api_server_snapshots_object_admin_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.api_server_snapshots_object_admin]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with api_server_snapshots_object_admin: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "api_server_snapshots_bucket_viewer_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.api_server_snapshots_bucket_viewer]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with api_server_snapshots_bucket_viewer: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "reaper_ops_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.reaper_ops]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with reaper_ops: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "reaper_ops_write_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.reaper_ops_write]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with reaper_ops_write: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "atelet_task_reader_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_artifact_registry_repository_iam_member.atelet_task_reader]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with atelet_task_reader: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "reaper_task_tags_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_artifact_registry_repository_iam_member.reaper_task_tags]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with reaper_task_tags: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "reaper_platform_tags_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_artifact_registry_repository_iam_member.reaper_platform_tags]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with reaper_platform_tags: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "snapshot_gc_list_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.snapshot_gc_list]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with snapshot_gc_list: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}

run "snapshot_gc_delete_waits_for_the_cluster" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.snapshot_gc_delete]
  }

  assert {
    condition     = google_container_cluster.exe.name != ""
    error_message = "the cluster must be planned with snapshot_gc_delete: the binding names the cluster's Workload Identity pool and has to be created after it."
  }
}
