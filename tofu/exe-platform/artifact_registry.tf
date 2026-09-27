# Image repositories, and the cleanup policies that keep them from growing
# forever (section 3.3).
#
# Three Artifact Registry behaviours shape every policy below, and getting any
# of them wrong produces a repository that looks managed and deletes nothing:
#
#   1. KEEP beats DELETE. When both match a version, it is kept.
#   2. `most_recent_versions` is a FLOOR, not a cap. On its own it deletes
#      nothing at all — it only protects the newest N.
#   3. A conditional KEEP and a `most_recent_versions` KEEP cannot live in the
#      same policy block, so "keep the in-use tags AND the newest few" is two
#      KEEP policies, not one.
#
# `cleanup_policy_dry_run = false` is stated explicitly on both: with dry-run on,
# every policy here is inert while the config still reads as correct — the exact
# silent failure scripts/check_storage_bounds.py exists to refuse.
#
# Deletion lags reality by about a day, so `exe-status` reports measured size
# rather than inferring it from these rules.

resource "google_artifact_registry_repository" "platform" {
  project       = var.gcp_project_id
  location      = local.region
  repository_id = local.ar_platform
  description   = "exe: Substrate, ax and reaper images (built with ko)"
  format        = "DOCKER"
  labels        = local.common_labels

  cleanup_policy_dry_run = false

  # A running install references its images BY DIGEST, so deleting untagged
  # versions promptly — the usual reflex — would pull the floor out from under
  # a live cluster. Keep the newest 10 regardless of tags.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
    }
  }

  cleanup_policies {
    id     = "delete-stale"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "2592000s" # 30 days
    }
  }

  depends_on = [google_project_service.enabled]
}

resource "google_artifact_registry_repository" "task" {
  project       = var.gcp_project_id
  location      = local.region
  repository_id = local.ar_task
  description   = "exe: task runner images (agent CLIs on the upstream runner base)"
  format        = "DOCKER"
  labels        = local.common_labels

  cleanup_policy_dry_run = false

  # The reaper (L1) puts an `inuse-` tag on the image every live task
  # references, and removes it when the last one goes away. This KEEP is what
  # makes that tag mean something: a 14-day-old image is safe to delete unless a
  # suspended task would come back to it.
  cleanup_policies {
    id     = "keep-inuse"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["inuse-"]
    }
  }

  # Separate block, because rule 3 above forbids merging it with the conditional
  # KEEP. Two is the smallest rollback window that still lets a bad task image
  # be replaced without losing the one before it.
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 2
    }
  }

  cleanup_policies {
    id     = "delete-stale"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "1209600s" # 14 days
    }
  }

  depends_on = [google_project_service.enabled]
}

# --- image pull permissions, per repository ---------------------------------
#
# Repository-scoped rather than project-wide reader, so a new repository in this
# shared project is not automatically readable by the cluster.

resource "google_artifact_registry_repository_iam_member" "node_platform_reader" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.platform.location
  repository = google_artifact_registry_repository.platform.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.node.email}"
}

resource "google_artifact_registry_repository_iam_member" "node_task_reader" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.task.location
  repository = google_artifact_registry_repository.task.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.node.email}"
}

# Substrate's atelet pulls ACTOR images itself rather than letting kubelet do
# it (--gcp-auth-for-image-pulls), so it needs its own reader. Upstream grants
# this project-wide; narrowed here to the repository actor images come from.
#
# This binding and the reaper's below name a Workload Identity principal, whose
# pool only exists once the cluster does; see the ORDERING note in iam.tf.
resource "google_artifact_registry_repository_iam_member" "atelet_task_reader" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.task.location
  repository = google_artifact_registry_repository.task.name
  role       = "roles/artifactregistry.reader"
  member     = local.wi_atelet
}

# The reaper adds and removes `inuse-` tags, which is a write against the
# repository even though it creates no new image.
resource "google_artifact_registry_repository_iam_member" "reaper_task_writer" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.task.location
  repository = google_artifact_registry_repository.task.name
  role       = "roles/artifactregistry.writer"
  member     = local.wi_reaper
}

resource "google_artifact_registry_repository_iam_member" "build_task_writer" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.task.location
  repository = google_artifact_registry_repository.task.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.build.email}"
}

resource "google_artifact_registry_repository_iam_member" "build_platform_writer" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.platform.location
  repository = google_artifact_registry_repository.platform.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.build.email}"
}
