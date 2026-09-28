# What this file pins: the reaper's authority over task-image tags (Phase 6
# plan D10, exe/spec/retention.qnt).
#
# L1 keeps an `inuse-` tag on every image a live task runs. The exe-task
# repository's cleanup policy KEEPs a tagged version and deletes an untagged
# one after 14 days, and every wake is a fresh node, so a suspended task's
# image has to survive until its next resume. To do that L1 lists packages and
# tags, and creates and deletes tags, and nothing else: it must not be able to
# push or delete an image. roles/artifactregistry.writer, which it held until
# now, can push; a custom role holds exactly the tag work.
#
# The same role is granted on the exe-platform repository (M19 C3, inbox M53
# B6). The running install pulls its images from there by digest, and L2's
# enforcer runs one of them; L1 protects those with the same tags, so that
# repository can keep fewer versions.
#
# Both repositories' resource names reach tofu/exe-cluster as outputs, which
# the CronJob hands to exe-reap as EXE_AR_REPOS, and so does the enforcer's
# image, which no pod runs (EXE_PROTECT_IMAGES).
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "the_reaper_may_tag_and_nothing_else" {
  command = plan

  assert {
    condition = google_project_iam_custom_role.reaper_tags.permissions == toset([
      "artifactregistry.packages.list",
      "artifactregistry.tags.create",
      "artifactregistry.tags.delete",
      "artifactregistry.tags.get",
      "artifactregistry.tags.list",
      "artifactregistry.versions.get",
      "artifactregistry.versions.list",
    ])
    error_message = "the reaper's tag role must hold exactly the tag work: list packages and tags, create and delete a tag, read versions. Any upload or delete of a version is authority over the images themselves, which retention never needs."
  }

  assert {
    condition     = google_artifact_registry_repository_iam_member.reaper_task_tags.repository == google_artifact_registry_repository.task.name && google_artifact_registry_repository_iam_member.reaper_task_tags.role == google_project_iam_custom_role.reaper_tags.id
    error_message = "the reaper's tag role must be granted on the exe-task repository, and on no wider scope: a project-wide grant would reach every repository in a SHARED project."
  }

  assert {
    condition     = google_artifact_registry_repository_iam_member.reaper_task_tags.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-reaper"
    error_message = "the tag role must be held by the reaper's Workload Identity, exe-ops/exe-reaper."
  }

  assert {
    condition     = google_artifact_registry_repository_iam_member.reaper_platform_tags.repository == google_artifact_registry_repository.platform.name && google_artifact_registry_repository_iam_member.reaper_platform_tags.role == google_project_iam_custom_role.reaper_tags.id
    error_message = "the same tag role must be granted on the exe-platform repository, the only other scope: the running install pulls its images there by digest, and L1 protects them with the same inuse- tags (M19 C3)."
  }

  assert {
    condition     = google_artifact_registry_repository_iam_member.reaper_platform_tags.member == "principal://iam.googleapis.com/projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}/subject/ns/exe-ops/sa/exe-reaper"
    error_message = "the platform repository's tag role must be held by the reaper's Workload Identity, exe-ops/exe-reaper."
  }
}

run "the_task_repository_reaches_the_cluster_by_resource_name" {
  command = plan

  assert {
    condition     = output.ar_task_repository == "projects/zz-synthetic-project/locations/asia-northeast1/repositories/${google_artifact_registry_repository.task.repository_id}"
    error_message = "ar_task_repository must be the repository's resource name (projects/P/locations/L/repositories/R): exe-reap compares it with the repository parsed out of each task's image reference, and any other form protects nothing."
  }
}

run "the_platform_repository_and_the_enforcers_image_reach_the_cluster" {
  command = plan

  variables {
    enforcer_image = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/exe-l2@sha256:1111111111111111111111111111111111111111111111111111111111111111"
  }

  assert {
    condition     = output.ar_platform_repository == "projects/zz-synthetic-project/locations/asia-northeast1/repositories/${google_artifact_registry_repository.platform.repository_id}"
    error_message = "ar_platform_repository must be the repository's resource name (projects/P/locations/L/repositories/R), the form exe-reap compares with each image reference it protects."
  }

  assert {
    condition     = output.enforcer_image == var.enforcer_image
    error_message = "enforcer_image must be the image L2's Cloud Run job runs, pinned by digest: no pod runs it, so exe-reap learns of it only from this output (EXE_PROTECT_IMAGES)."
  }
}
