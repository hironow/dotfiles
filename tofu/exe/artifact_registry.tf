# Artifact Registry repository for the dotfiles dev container image.
#
# Coder workspaces (exe/coder/templates/dotfiles-devcontainer) pull
# from `<region>-docker.pkg.dev/<project>/<repo>/devcontainer:<tag>`
# instead of running envbuilder per workspace. The publish workflow at
# .github/workflows/publish-devcontainer.yaml builds the image from
# .devcontainer/devcontainer.json and pushes it here.

resource "google_artifact_registry_repository" "dotfiles" {
  project       = var.gcp_project_id
  location      = var.gcp_region
  repository_id = "dotfiles"
  description   = "Dev container image for exe.hironow.dev Coder workspaces"
  format        = "DOCKER"
  labels        = local.common_labels

  # Retention (ADR 0034, revising ADR 0002's 10-version cap).
  #
  # Every publish tags the image (`main` + `<sha>`), so the original
  # UNTAGGED delete policy never fired and versions accumulated
  # unboundedly (20+ versions, ~21 GiB by 2026-07). Cleanup semantics:
  # KEEP beats DELETE, and keep_count is a floor, not a cap — the
  # steady state is max(3, builds in the last 30 days) + main.
  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = 3
    }
  }
  # Workspaces pull `:main`; without this KEEP a >30-day publish gap
  # would let delete-stale remove the rolling tag and break workspace
  # creation (recovery: re-run publish-devcontainer via workflow_dispatch).
  cleanup_policies {
    id     = "keep-main-tag"
    action = "KEEP"
    condition {
      tag_state    = "TAGGED"
      tag_prefixes = ["main"]
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
  cleanup_policies {
    id     = "delete-old-untagged"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s" # 7 days
    }
  }
}
