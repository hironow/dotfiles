# What this file pins: the orphan-snapshot GC's authority (Phase 6 plan D11,
# option B in manager-loop inbox M35).
#
# The GC is operator-triggered (`just exe-snapshot-gc`) and runs as its own
# KSA, exe-ops/exe-snapshot-gc, only inside that one-off Job. It lists the
# snapshot bucket and deletes objects under exactly two prefixes: the actors of
# the task atespace and of Substrate's golden atespace. The gVisor mirror every
# actor boots from (mirror/) and a Tag's snapshot (atespaces/<a>/tags/) stay out
# of reach at IAM, not only in the GC's code. L1, which runs every minute, holds
# nothing on this bucket; tests/unit/test_exe_snapshot_gc_iam.py scans every
# binding for that.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "the_gc_may_list_the_bucket_and_delete_and_nothing_else" {
  command = plan

  assert {
    condition     = google_project_iam_custom_role.snapshot_gc_list.permissions == toset(["storage.objects.list"])
    error_message = "the GC's list role must hold storage.objects.list alone: names and times are all the decision reads, and storage.objects.get would let it read every snapshot's contents."
  }

  assert {
    condition     = google_project_iam_custom_role.snapshot_gc_delete.permissions == toset(["storage.objects.delete"])
    error_message = "the GC's delete role must hold storage.objects.delete alone."
  }

  assert {
    condition     = google_storage_bucket_iam_member.snapshot_gc_list.bucket == google_storage_bucket.snapshots.name && google_storage_bucket_iam_member.snapshot_gc_list.role == google_project_iam_custom_role.snapshot_gc_list.id && length(google_storage_bucket_iam_member.snapshot_gc_list.condition) == 0
    error_message = "the list role must be granted on the snapshot bucket, unconditionally: a list is checked against the bucket, which no object-name condition matches."
  }

  assert {
    condition     = google_storage_bucket_iam_member.snapshot_gc_delete.bucket == google_storage_bucket.snapshots.name && google_storage_bucket_iam_member.snapshot_gc_delete.role == google_project_iam_custom_role.snapshot_gc_delete.id
    error_message = "the delete role must be granted on the snapshot bucket."
  }

  assert {
    condition = alltrue([
      for member in [
        google_storage_bucket_iam_member.snapshot_gc_list.member,
        google_storage_bucket_iam_member.snapshot_gc_delete.member,
      ] : member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-snapshot-gc"
    ])
    error_message = "both grants must be held by the GC's own Workload Identity, exe-ops/exe-snapshot-gc, and never by L1's exe-ops/exe-reaper, which runs every minute."
  }
}

run "the_delete_reaches_only_the_actors_of_the_two_atespaces" {
  command = plan

  assert {
    condition     = google_storage_bucket_iam_member.snapshot_gc_delete.condition[0].expression == "resource.name.startsWith(\"projects/_/buckets/zz-synthetic-project-exe-snapshots/objects/ax/atespaces/exe/actors/\") || resource.name.startsWith(\"projects/_/buckets/zz-synthetic-project-exe-snapshots/objects/ax/atespaces/ate-golden/actors/\")"
    error_message = "the delete must be conditioned on exactly two prefixes, ax/atespaces/exe/actors/ and ax/atespaces/ate-golden/actors/, so that mirror/ and every Tag's snapshot stay out of the GC's reach."
  }
}

run "the_gc_principal_reaches_the_cluster_stack" {
  command = plan

  assert {
    condition     = output.workload_identity_principals.snapshot_gc == google_storage_bucket_iam_member.snapshot_gc_delete.member
    error_message = "workload_identity_principals must carry the GC's principal: tofu/exe-cluster creates the KSA under exactly that namespace and name."
  }
}
