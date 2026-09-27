# What this file pins: with no enforcer image, which is the default, L2 is not
# deployed at all, and nothing else in the stack moves.
#
# The image is an INPUT (see variables.tf): a digest that only exists once the
# ko build has pushed it. Until then the job has nothing to run, so the stack
# plans without it rather than refusing to plan. That keeps the platform
# re-plannable to "No changes." while the enforcer is still being built, and it
# makes turning L2 on a single, reviewable variable change.
#
# Three things are pinned, and the variable is deliberately NOT set here, so
# every run exercises the declared default:
#
#   - the job, its run.invoker binding, its pool-reader grant and its tick are
#     all absent together. A tick without the job 404s every ten minutes; a job
#     without the tick never runs, and looks deployed.
#   - the L2 outputs are null rather than an error, so status recipes can tell
#     "not deployed" from "deployed".
#   - the enforcer IDENTITY and its two grants stay. They were applied with the
#     platform, before the job existed; gating them with the job would destroy
#     them on the next plan and recreate them the moment L2 is switched on.
#
# l2_enforcer.tofutest.hcl covers the other case: an image set, L2 present.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

run "without_an_image_l2_is_absent_as_a_unit" {
  command = plan

  assert {
    condition     = length(google_cloud_run_v2_job.l2_enforcer) == 0
    error_message = "with no enforcer_image (the default) the L2 Cloud Run job must not be planned: it would have no image to run, and the platform has to keep planning to \"No changes.\" until the ko build has produced a digest."
  }

  assert {
    condition     = length(google_cloud_run_v2_job_iam_member.scheduler_invoker) == 0
    error_message = "with no enforcer_image the run.invoker binding must not be planned either: it is a grant on the L2 job, and without the job it names nothing."
  }

  assert {
    condition     = length(google_project_iam_custom_role.node_pool_reader) == 0 && length(google_project_iam_member.enforcer_pool_reader) == 0
    error_message = "with no enforcer_image the enforcer's pool-reader role and its binding must not be planned: the job is their only user, so they come and go with it."
  }

  assert {
    condition     = length(google_cloud_scheduler_job.l2_tick) == 0
    error_message = "with no enforcer_image the L2 tick must not be planned: a tick aimed at a job that does not exist fails every ten minutes, all night, and fires the Scheduler-failure alert for a layer that was never switched on."
  }
}

run "without_an_image_the_l2_outputs_are_null" {
  command = plan

  assert {
    condition     = output.l2_enforcer_job == null
    error_message = "l2_enforcer_job must be null while L2 is not deployed, so a recipe can say \"not deployed\" instead of failing on a missing attribute."
  }

  assert {
    condition     = output.l2_scheduler_job == null
    error_message = "l2_scheduler_job must be null while L2 is not deployed, so a recipe can say \"not deployed\" instead of failing on a missing attribute."
  }
}

run "without_an_image_the_enforcer_identity_and_its_grants_stay" {
  command = plan

  assert {
    condition     = google_service_account.enforcer.account_id == "exe-enforcer"
    error_message = "the exe-enforcer service account must be planned whether or not L2 is deployed: it was applied with the platform, so gating it with the job would destroy it and recreate it the moment enforcer_image is set."
  }

  assert {
    condition     = google_project_iam_member.enforcer_resizer.member == "serviceAccount:${google_service_account.enforcer.email}"
    error_message = "the enforcer's node-pool-resizer grant must be planned whether or not L2 is deployed, for the same reason as the account: it already exists, and a plan that removes it is not \"No changes.\"."
  }

  assert {
    condition     = google_storage_bucket_iam_member.enforcer_ops.member == "serviceAccount:${google_service_account.enforcer.email}"
    error_message = "the enforcer's ops-bucket grant must be planned whether or not L2 is deployed, for the same reason as the account: it already exists, and a plan that removes it is not \"No changes.\"."
  }
}
