# What this file pins: with no enforcer image, which is the default, L2 is not
# deployed at all, and nothing else in the stack moves.
#
# The image is an INPUT (see variables.tf): a digest that only exists once the
# ko build has pushed it. Until then the job has nothing to run, so the stack
# plans without it rather than refusing to plan. That keeps the platform
# re-plannable to "No changes." while the enforcer is still being built, and it
# makes turning L2 on a single, reviewable variable change.
#
# Three things are pinned, for an EMPTY image. It is stated in the variables
# block below rather than left to the declared default, because `tofu test`
# also loads the operator's gitignored terraform.tfvars, and once L2 is on that
# file sets the image: left unset here, these runs would test whatever the
# local file says instead of the empty case:
#
#   - the job, its run.invoker binding, its pool-reader grant, its tick and its
#     three alerts are all absent together. A tick without the job 404s every ten
#     minutes; a job without the tick never runs, and looks deployed; an alert
#     without the job watches a log that never arrives.
#   - the L2 outputs are null rather than an error, so status recipes can tell
#     "not deployed" from "deployed".
#   - the enforcer IDENTITY and its grants stay. They were applied with the
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

  # Empty, which is also the declared default; see the header for why it is
  # stated.
  enforcer_image = ""
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

run "without_an_image_the_l2_alerts_are_absent" {
  command = plan

  assert {
    condition     = length(google_monitoring_alert_policy.l2_forced_stop) == 0
    error_message = "with no enforcer_image the L2 forced-stop alert must not be planned: its filter names the L2 job, so without the job it watches a log that never arrives — an alert that looks armed and can never fire."
  }

  assert {
    condition     = length(google_monitoring_alert_policy.l2_execution_failed) == 0
    error_message = "with no enforcer_image the L2 failed-execution alert must not be planned: its filter names the L2 job, so without the job it watches a log that never arrives — and its presence would read as \"L2 is deployed and healthy\" on a platform where L2 was never switched on."
  }

  assert {
    condition     = length(google_monitoring_alert_policy.l2_stop_latency) == 0
    error_message = "with no enforcer_image the L2 stop-latency alert must not be planned: the enforcer is what measures a stop, so without the job it watches a log that never arrives, and reads as a slow stop being watched for when nothing is."
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
    error_message = "the enforcer's ops-bucket read grant must be planned whether or not L2 is deployed, for the same reason as the account: it already exists, and a plan that removes it is not \"No changes.\"."
  }

  assert {
    condition     = google_storage_bucket_iam_member.enforcer_ops_write.member == "serviceAccount:${google_service_account.enforcer.email}"
    error_message = "the enforcer's enforce.json write grant must be planned whether or not L2 is deployed, like its read grant: gated with the job, switching L2 off would destroy it and switching it back on would start the job before its write is granted again."
  }
}
