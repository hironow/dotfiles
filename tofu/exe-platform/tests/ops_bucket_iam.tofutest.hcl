# What this file pins: in the ops bucket every identity reads everything and
# writes only the objects it owns (Phase 6 plan D10, codex pass 2 #3).
#
# The lease protocol gives each object one writer:
#
#   lease.json, keep.json   the operator (L0), on their own credentials
#   drain.json, tasks.json  the reaper (L1)
#   enforce.json            the enforcer (L2)
#
# Until now only review held that rule. Both service identities held
# roles/storage.objectUser on the whole bucket, so a bug in L1 could rewrite
# the operator's lease, and a bug in L2 could forge the drain record that tells
# it a stop may be graceful.
#
# IAM grants add up, so a condition cannot narrow an unconditional grant, and
# objectUser carries reads and writes alike. Each identity therefore holds two
# bindings:
#
#   - roles/storage.objectViewer with no condition, for reads. Listing is
#     checked against the BUCKET, which no object-name condition could ever
#     match.
#   - roles/storage.objectUser under a condition naming exactly the objects it
#     writes. Overwriting one takes storage.objects.create and
#     storage.objects.delete on that object, and objectUser holds both.
#
# The read grant keeps the address that held the old unconditional objectUser.
# It depends on the write grant and is replaced create-before-destroy, so the
# old grant goes last: the enforcer is live and writes enforce.json on every
# tick. The ORDER runs below pin the dependency;
# expected-changes/stop-latency-and-writers.txt pins the +/- replacement.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "each_identity_reads_the_whole_bucket_without_a_condition" {
  command = plan

  assert {
    condition     = google_storage_bucket_iam_member.reaper_ops.bucket == google_storage_bucket.ops.name && google_storage_bucket_iam_member.reaper_ops.role == "roles/storage.objectViewer" && length(google_storage_bucket_iam_member.reaper_ops.condition) == 0
    error_message = "reaper_ops must grant roles/storage.objectViewer on the ops bucket, with no condition. objectUser here would let L1 write every object, the operator's lease included, whatever its write grant says; a condition would take away the listing, which is checked against the bucket."
  }

  assert {
    condition     = google_storage_bucket_iam_member.enforcer_ops.bucket == google_storage_bucket.ops.name && google_storage_bucket_iam_member.enforcer_ops.role == "roles/storage.objectViewer" && length(google_storage_bucket_iam_member.enforcer_ops.condition) == 0
    error_message = "enforcer_ops must grant roles/storage.objectViewer on the ops bucket, with no condition. objectUser here would let L2 write every object, L1's drain record included, whatever its write grant says."
  }
}

run "the_reaper_writes_drain_and_tasks_and_nothing_else" {
  command = plan

  assert {
    condition     = google_storage_bucket_iam_member.reaper_ops_write.bucket == google_storage_bucket.ops.name && google_storage_bucket_iam_member.reaper_ops_write.role == "roles/storage.objectUser" && google_storage_bucket_iam_member.reaper_ops_write.member == google_storage_bucket_iam_member.reaper_ops.member
    error_message = "reaper_ops_write must grant roles/storage.objectUser on the ops bucket to the same principal as reaper_ops, the reaper's Workload Identity. An overwrite takes create and delete on the object, and objectUser is the predefined role that holds both."
  }

  assert {
    condition     = google_storage_bucket_iam_member.reaper_ops_write.condition[0].expression == "resource.name == \"projects/_/buckets/${google_storage_bucket.ops.name}/objects/drain.json\" || resource.name == \"projects/_/buckets/${google_storage_bucket.ops.name}/objects/tasks.json\""
    error_message = "reaper_ops_write's condition must name exactly drain.json and tasks.json, as IAM resource names (projects/_/buckets/<bucket>/objects/<name>). Those two are L1's; any other object in the list is one L1 could overwrite behind its owner, and a name in another form matches nothing, so every drain record L1 writes is denied."
  }
}

run "the_enforcer_writes_enforce_and_nothing_else" {
  command = plan

  assert {
    condition     = google_storage_bucket_iam_member.enforcer_ops_write.bucket == google_storage_bucket.ops.name && google_storage_bucket_iam_member.enforcer_ops_write.role == "roles/storage.objectUser" && google_storage_bucket_iam_member.enforcer_ops_write.member == google_storage_bucket_iam_member.enforcer_ops.member
    error_message = "enforcer_ops_write must grant roles/storage.objectUser on the ops bucket to the same principal as enforcer_ops, the exe-enforcer service account."
  }

  assert {
    condition     = google_storage_bucket_iam_member.enforcer_ops_write.condition[0].expression == "resource.name == \"projects/_/buckets/${google_storage_bucket.ops.name}/objects/enforce.json\""
    error_message = "enforcer_ops_write's condition must name exactly enforce.json, as an IAM resource name. It is the only object L2 writes. A name in another form matches nothing, so every tick fails to record itself and pages as a failed execution."
  }
}

# The operator's objects appear in neither condition. The two value runs above
# already imply it; this says why, for the day someone is tempted.
run "no_service_identity_can_write_the_operators_objects" {
  command = plan

  assert {
    condition = alltrue([
      for c in [google_storage_bucket_iam_member.reaper_ops_write.condition[0].expression, google_storage_bucket_iam_member.enforcer_ops_write.condition[0].expression] :
      !strcontains(c, "lease.json") && !strcontains(c, "keep.json")
    ])
    error_message = "neither the reaper nor the enforcer may write lease.json or keep.json. They are the operator's word: the lease is the only thing that says a node may run, and keep.json is the only thing that holds a task back from the 30-day TTL. A service identity that can rewrite either can keep a node up, or delete a kept task, on its own authority."
  }
}

# --- ORDER: the old grant goes last ------------------------------------------
#
# A plan TARGETED at a read grant contains everything that grant depends on.
# Each run reads the matching write grant's condition title: without the
# depends_on the write grant is not in the targeted plan and its title is
# unknown, so the run fails with "Unknown condition". Read that error here as
# "the old unconditional objectUser can be removed before the write grant
# exists", which for the enforcer is a tick that cannot record itself.

run "the_reaper_read_grant_waits_for_its_write_grant" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.reaper_ops]
  }

  assert {
    condition     = google_storage_bucket_iam_member.reaper_ops_write.condition[0].title != ""
    error_message = "reaper_ops must depend on reaper_ops_write, so that replacing the old unconditional grant at this address creates the write grant first."
  }
}

run "the_enforcer_read_grant_waits_for_its_write_grant" {
  command = plan

  plan_options {
    target = [google_storage_bucket_iam_member.enforcer_ops]
  }

  assert {
    condition     = google_storage_bucket_iam_member.enforcer_ops_write.condition[0].title != ""
    error_message = "enforcer_ops must depend on enforcer_ops_write, so that replacing the old unconditional grant at this address creates the write grant first: the enforcer writes enforce.json on every tick, and a tick between the two is a failed execution."
  }
}
