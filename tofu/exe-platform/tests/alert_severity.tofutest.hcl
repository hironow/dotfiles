# What this file pins: every exe page says how urgent it is (Phase 6 plan D9).
#
# A policy with no severity opens incidents with none, and its email carries
# none: a forced stop that cut off a running task and a failed tick that the
# next tick retried look the same in the inbox. Cloud Monitoring carries a
# policy's severity into its incidents and notifications, so each page states
# one, by what it tells the operator:
#
#   CRITICAL  money is going where it should not, or work was cut off: a node
#             up past any lease, a forced stop, a stop that did not finish.
#   ERROR     one layer of the money stop is failing while the others stand:
#             a failed Scheduler job (L2's tick or L3), a failed L2 execution.
#
# The table is the plan's decision, so a page moving between rows is a decision
# too, not an edit: every row is pinned by value.
#
# enforcer_image is set, because the three L2 pages exist only with L2.
#
# command = plan + mock_provider: offline, no credentials, nothing created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"

  # A digest-pinned ref, the only shape the variable accepts; the digest is
  # synthetic.
  enforcer_image = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/exe-reaper@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}

run "every_page_states_its_severity" {
  command = plan

  assert {
    condition     = google_monitoring_alert_policy.node_uptime.severity == "CRITICAL"
    error_message = "the node-uptime alert must be CRITICAL. A node up for more than 9 hours has outlived every lease, so every automatic stop has failed and it is billing now."
  }

  assert {
    condition     = google_monitoring_alert_policy.l2_forced_stop[0].severity == "CRITICAL"
    error_message = "the L2 forced-stop alert must be CRITICAL. The stop worked, but whatever was running was cut off without L1's drain, and the operator has to find out why before the next wake."
  }

  assert {
    condition     = google_monitoring_alert_policy.l2_stop_latency[0].severity == "CRITICAL"
    error_message = "the L2 stop-latency alert must be CRITICAL. The pool's target is zero and a VM is still there, so the stop everyone believes happened has not, and the VM bills until someone looks."
  }

  assert {
    condition     = google_monitoring_alert_policy.scheduler_failure.severity == "ERROR"
    error_message = "the Scheduler-failure alert must be ERROR: one layer of the money stop (L2's tick or L3) is failing, and the others still stand."
  }

  assert {
    condition     = google_monitoring_alert_policy.l2_execution_failed[0].severity == "ERROR"
    error_message = "the L2 failed-execution alert must be ERROR: L2 is failing while L1 and L3 still stand, and a single failed attempt fires it even when the retry succeeded."
  }
}
