# Storage sinks. Every one declares an explicit bound (section 3.3).
#
# scripts/check_storage_bounds.py gates this file repo-wide: UBLA on, public
# access prevention enforced, soft delete at zero, and a stated cap — with the
# snapshot bucket as the one inverted case, where a delete rule is the bug.
#
# Soft delete is disabled everywhere on purpose. Its 7-day default retention is
# billed storage for objects already deleted, which on a lease bucket rewritten
# every minute is pure accumulation.

resource "google_storage_bucket" "snapshots" {
  project  = var.gcp_project_id
  name     = local.bucket_snapshots
  location = local.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  # ==================================================================
  # NO DELETE LIFECYCLE HERE, AND THAT IS THE POINT.
  #
  # These are actor snapshots. Deleting one that a suspended task still
  # references makes that task unresumable — the loss is silent until
  # someone tries to resume it, and there is no recovery. Substrate GCs
  # unreferenced snapshots itself; the real bound is the task lifetime
  # (30 days, decision Q15), enforced by the reaper deleting tasks.
  #
  # The storage-bounds gate asserts the ABSENCE of a delete rule here.
  # ==================================================================

  # No versioning: a snapshot object is written once under a content-addressed
  # name, so versions would only ever be duplicates.
  versioning {
    enabled = false
  }

  # Left false deliberately: this is the one bucket whose contents cannot be
  # rebuilt, so a teardown must refuse until someone empties it on purpose.
  force_destroy = false

  labels     = local.common_labels
  depends_on = [google_project_service.enabled]
}

resource "google_storage_bucket" "ops" {
  project  = var.gcp_project_id
  name     = local.bucket_ops
  location = local.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  # Versioning is load-bearing, not a safety net: lease.json, drain.json and
  # enforce.json are written under generation preconditions so that exactly one
  # writer wins a race (section 3.2). Generations are what the preconditions
  # compare against.
  versioning {
    enabled = true
  }

  # Cap the history at 5 noncurrent versions. These objects are a few hundred
  # bytes and are rewritten every minute while a node is awake, so unbounded
  # versioning is ~1,400 dead objects a day.
  lifecycle_rule {
    condition {
      num_newer_versions = 5
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  # Lease state is ephemeral by definition — a destroy that refuses because
  # yesterday's lease is still there would block Phase 7 for nothing.
  force_destroy = true

  labels     = local.common_labels
  depends_on = [google_project_service.enabled]
}

resource "google_storage_bucket" "build" {
  project  = var.gcp_project_id
  name     = local.bucket_build
  location = local.region

  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  soft_delete_policy {
    retention_duration_seconds = 0
  }

  # Cloud Build's own default staging bucket has no expiry at all, which is how
  # a build source tarball from two years ago is still billed. This bucket
  # exists so that `--gcs-source-staging-dir` points somewhere bounded.
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }

  versioning {
    enabled = false
  }

  force_destroy = true

  labels     = local.common_labels
  depends_on = [google_project_service.enabled]
}
