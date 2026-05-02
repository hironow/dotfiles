# Workload Identity Federation for GitHub Actions to push dev
# container images to Artifact Registry without long-lived service
# account keys.
#
# Trust chain:
#   github.com (OIDC) --> WIF pool --> WIF provider --> SA
#   The SA is granted only roles/artifactregistry.writer on the
#   `dotfiles` repository — narrowest possible scope.
#
# Set workflow secrets after `tofu apply`:
#   GCP_WIF_PROVIDER  = output.gcp_wif_provider_resource_name
#   GCP_PUBLISH_SA    = output.gcp_publish_sa_email

# ---- Service Account that GHA acts as ------------------------------
resource "google_service_account" "gha_publish" {
  project      = var.gcp_project_id
  account_id   = "gha-devcontainer-publish"
  display_name = "GitHub Actions — devcontainer image publisher"
  description  = "Pushes .devcontainer image to Artifact Registry. Impersonated via WIF; no key issued."
}

resource "google_artifact_registry_repository_iam_member" "gha_writer" {
  project    = google_artifact_registry_repository.dotfiles.project
  location   = google_artifact_registry_repository.dotfiles.location
  repository = google_artifact_registry_repository.dotfiles.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.gha_publish.email}"
}

# ---- WIF pool ------------------------------------------------------
# `import` block adopts an existing pool (created out-of-band on a
# previous experiment in this project) into tofu state instead of
# erroring with "Requested entity already exists" on first apply.
# Safe to leave in place — `import` is idempotent post-adoption.
import {
  to = google_iam_workload_identity_pool.github
  id = "projects/${var.gcp_project_id}/locations/global/workloadIdentityPools/github"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.gcp_project_id
  workload_identity_pool_id = "github"
  display_name              = "GitHub OIDC pool"
  description               = "Federates GitHub Actions tokens into GCP."
}

# ---- WIF provider tied to github.com -------------------------------
resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.gcp_project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions"
  display_name                       = "GitHub Actions"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.actor"      = "assertion.actor"
  }

  # Restrict the pool to this repo only — token swaps from any other
  # GitHub repo cannot reach the SA.
  attribute_condition = "assertion.repository == 'hironow/dotfiles'"
}

# ---- Bind the SA to the WIF provider for this repo only ------------
resource "google_service_account_iam_member" "gha_publish_wif" {
  service_account_id = google_service_account.gha_publish.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/hironow/dotfiles"
}

# ---- Workspace VM — pull rights on the AR repo ---------------------
# The Coder workspace template (gcp-vm-container pattern) runs
# `docker pull <repo>/devcontainer:<tag>` from the VM's attached
# service account. The SA was originally scoped to read a single
# Secret Manager entry; widen with the narrowest AR role.
resource "google_artifact_registry_repository_iam_member" "exe_workspace_reader" {
  project    = google_artifact_registry_repository.dotfiles.project
  location   = google_artifact_registry_repository.dotfiles.location
  repository = google_artifact_registry_repository.dotfiles.name
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.exe_workspace.email}"
}
