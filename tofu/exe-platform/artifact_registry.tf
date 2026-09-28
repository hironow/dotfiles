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

  # The reaper (L1) puts an `inuse-` tag on every image the cluster's own pods
  # run and on L2's enforcer image, and removes it once nothing has used the
  # image for tag_release_days (M19 C3). This KEEP is what makes that tag hold
  # here, as keep-inuse does on exe-task.
  cleanup_policies {
    id     = "keep-inuse"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["inuse-"]
    }
  }

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

# The reaper (L1) keeps an `inuse-` tag on every image a live task runs, and
# releases it once nothing has used the image for tag_release_days (Phase 6
# plan D10, exe/spec/retention.qnt). It lists packages and tags and creates and
# deletes tags, and nothing else: roles/artifactregistry.writer, which it held
# before, can also push images, which retention never needs. A custom role,
# granted on the two repositories only: exe-task for the images live tasks
# run, and exe-platform for the ones the cluster's own pods and L2's enforcer
# run (M19 C3). tests/reaper_tags.tofutest.hcl pins all three.
resource "google_project_iam_custom_role" "reaper_tags" {
  project     = var.gcp_project_id
  role_id     = "exeReaperTags"
  title       = "exe reaper: inuse- tags"
  description = "Lists packages and tags and creates and deletes tags; no image upload or delete."
  permissions = [
    "artifactregistry.packages.list",
    "artifactregistry.tags.create",
    "artifactregistry.tags.delete",
    "artifactregistry.tags.get",
    "artifactregistry.tags.list",
    "artifactregistry.versions.get",
    "artifactregistry.versions.list",
  ]

  depends_on = [google_project_service.enabled]
}

resource "google_artifact_registry_repository_iam_member" "reaper_task_tags" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.task.location
  repository = google_artifact_registry_repository.task.name
  role       = google_project_iam_custom_role.reaper_tags.id
  member     = local.wi_reaper

  depends_on = [terraform_data.custom_roles_settled]
}

resource "google_artifact_registry_repository_iam_member" "reaper_platform_tags" {
  project    = var.gcp_project_id
  location   = google_artifact_registry_repository.platform.location
  repository = google_artifact_registry_repository.platform.name
  role       = google_project_iam_custom_role.reaper_tags.id
  member     = local.wi_reaper

  depends_on = [terraform_data.custom_roles_settled]
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
