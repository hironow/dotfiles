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

  # Container Optimized OS pulls images at workspace-create time;
  # keep image history bounded so the AR storage bill does not grow
  # unboundedly with every commit.
  cleanup_policies {
    id     = "keep-recent-versions"
    action = "KEEP"
    most_recent_versions {
      keep_count = 10
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
