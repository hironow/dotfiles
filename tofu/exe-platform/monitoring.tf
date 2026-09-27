# L4 — detection. What notices when the money stops did not work.
#
# Three signals, chosen so that each one survives the failure of the others:
#   - node uptime, read from a COMPUTE ENGINE metric, so it holds even if the
#     cluster's own monitoring is broken or switched off;
#   - Cloud Scheduler failures, so a silently dead L3 (or L2's tick) is visible
#     rather than merely absent;
#   - a JPY budget, which catches everything the first two missed.
#
# L2, once deployed, also pages on its own account: when it had to force a stop,
# and when one of its executions failed. Those two close this file and come and
# go with the L2 job.
#
# The notification address lives only in terraform.tfvars.

resource "google_monitoring_notification_channel" "email" {
  project      = var.gcp_project_id
  display_name = "exe alerts"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }

  depends_on = [google_project_service.enabled]
}

# --- node uptime ------------------------------------------------------------
#
# The real question is "has a node been up longer than any legitimate lease?".
# The longest lease is 8 hours, so 9 hours means something failed to stop.
#
# Read from compute.googleapis.com deliberately: a GKE-sourced metric would
# make the alarm depend on the thing it is watching. Scoped by instance name
# prefix because the project is shared — every GKE node is named
# gke-<cluster>-<pool>-..., so gke-exe- cannot match a neighbouring stack's VM.
resource "google_monitoring_alert_policy" "node_uptime" {
  project      = var.gcp_project_id
  display_name = "exe: node up longer than 9h"
  combiner     = "OR"

  documentation {
    content   = <<-EOT
      An exe node has been running for more than 9 hours, which is longer than
      the maximum lease (8h) plus enforcement slack. Every automatic stop has
      therefore failed, or the pool was resized by hand.

      Check, in order: `just exe-status`; whether the L3 Scheduler job ran; and
      whether the node pool's size was changed outside the auto-sleep. To stop
      it now, run the L3 job manually.
    EOT
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "gke-exe node uptime > 9h"

    condition_threshold {
      filter = join(" AND ", [
        "metric.type = \"compute.googleapis.com/instance/uptime_total\"",
        "resource.type = \"gce_instance\"",
        "metadata.system_labels.name = starts_with(\"gke-${local.cluster_name}-\")",
      ])

      comparison      = "COMPARISON_GT"
      threshold_value = 9 * 60 * 60
      duration        = "300s"

      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    # Close the incident once the node is gone, so a stopped cluster does not
    # leave an open alert behind.
    auto_close = "1800s"
  }

  depends_on = [google_project_service.enabled]
}

# --- Cloud Scheduler failures ----------------------------------------------
#
# A log-based metric rather than one of the built-in Scheduler metrics: the
# failure modes that matter here (a 403 because the resizer role was removed, a
# 404 because the pool was renamed) surface as error-severity log entries, and a
# log-based counter catches all of them without enumerating response codes.
resource "google_logging_metric" "scheduler_failures" {
  project     = var.gcp_project_id
  name        = "${local.prefix}_scheduler_job_failures"
  description = "Error-severity log entries from exe Cloud Scheduler jobs (L2 / L3)"

  # Cloud LOGGING query language: `=~` is an RE2 match, anchored here so only
  # exe-prefixed jobs count. (`monitoring.regex.full_match()` belongs to Cloud
  # Monitoring's filter syntax; the Logging API rejects it as an unparseable
  # filter, which is how the first apply failed.)
  filter = join(" AND ", [
    "resource.type = \"cloud_scheduler_job\"",
    "severity >= ERROR",
    "resource.labels.job_id =~ \"^${local.prefix}-\"",
  ])

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
    unit        = "1"
  }

  depends_on = [google_project_service.enabled]
}

resource "google_monitoring_alert_policy" "scheduler_failure" {
  project      = var.gcp_project_id
  display_name = "exe: Cloud Scheduler job failed"
  combiner     = "OR"

  documentation {
    content   = <<-EOT
      An exe Cloud Scheduler job failed. L3 is the last automatic stop, so a
      failing L3 means nothing forces the cluster off any more — treat this as
      urgent even though nothing is visibly broken yet.

      Most likely causes: the custom resizer role or its binding was removed
      (403), or the cluster / node pool was renamed so the target URI no longer
      resolves (404).
    EOT
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "exe scheduler job error logged"

    condition_threshold {
      filter = join(" AND ", [
        "metric.type = \"logging.googleapis.com/user/${google_logging_metric.scheduler_failures.name}\"",
        "resource.type = \"cloud_scheduler_job\"",
      ])

      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "600s"
        per_series_aligner = "ALIGN_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  # After the L3 job, i.e. after the cluster build, and not merely after the
  # metric. Cloud Monitoring registers a new log-based metric's descriptor
  # asynchronously ("If a metric was created recently, it could take up to 10
  # minutes to become available"), the provider does not retry that 404
  # (hashicorp/terraform-provider-google#11102), and a policy created straight
  # after the metric fails the apply. The cluster build is the wait; it is also
  # the natural order, since this alert watches that job.
  depends_on = [
    google_project_service.enabled,
    google_cloud_scheduler_job.l3_daily_stop,
  ]
}

# --- JPY budget -------------------------------------------------------------
#
# Scoped to THIS project only. The billing account funds unrelated projects and
# already carries other budgets; a budget without a project filter would fire on
# their spend and, worse, look like it was reporting this stack's.
#
# Alerts only, no automatic spend cap: a hard cap on a shared billing account
# takes the neighbours down too.
resource "google_billing_budget" "exe_monthly" {
  # The BARE id. The provider builds billingAccounts/<id>/budgets itself, so a
  # prefixed value turns into billingAccounts/billingAccounts/<id> and a 404.
  billing_account = var.billing_account_id
  display_name    = "exe monthly (JPY)"

  budget_filter {
    projects               = ["projects/${var.gcp_project_number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "INCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      # The billing account's currency is JPY, and a budget must match it.
      currency_code = "JPY"
      units         = tostring(var.monthly_budget_jpy)
    }
  }

  # 50 / 90 / 100 % of actual spend (decision Q9). Actual rather than forecast:
  # a forecast on a spiky, few-hours-a-day workload cries wolf constantly.
  dynamic "threshold_rules" {
    for_each = [0.5, 0.9, 1.0]
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  all_updates_rule {
    monitoring_notification_channels = [google_monitoring_notification_channel.email.id]
    # The billing-account admins already get the default emails; this makes the
    # same signal land in the same place as the L4 alerts.
    disable_default_iam_recipients = false
  }

  depends_on = [google_project_service.enabled]
}

# --- L2: forced stops and failed executions ---------------------------------
#
# L2 acts at night with nobody watching, so it is also the layer that has to say
# what it did. Two pages, created and destroyed with the L2 job on its switch:
# an alert on a job that does not exist watches a log that never arrives, and
# looks armed doing it.
#
#   - a FORCED stop. The pool went to zero without L1's clean drain — the lease
#     was unreadable three ticks running, L1 reported a failed drain, its drain
#     heartbeat went stale, or the grace after the deadline ran out with no drain
#     at all — and whatever was still running was cut off (decision Q14). The
#     stop is the system working; the page is for why L1 did not get there first.
#   - a FAILED execution. The tick reports success once an execution is CREATED,
#     so an enforcer that fails on every tick is otherwise invisible until L3 or
#     the budget notices.
#
# Log-MATCH conditions, not a log-based metric like the Scheduler alert above: a
# forced stop is one event to be told about, not a rate to put a threshold on,
# and a log-match condition evaluates its filter directly, so there is no metric
# descriptor for the policy to race.
#
# Both filters read the log contract `exe-reaper enforce` writes: one JSON object
# per line on stdout, whose `severity` Cloud Run lifts into the LogEntry and
# whose other fields land in jsonPayload — L2's under jsonPayload.exe_l2.
#   decision  event "decision", with action / reason / notify. ERROR exactly
#             when the action is stop-forced AND notify is set, i.e. a forced
#             stop that does not repeat the tick before it (the same stop under
#             the same lease generation); every repeat is WARNING.
#   failure   event "failure", at ERROR: the last line before the binary exits 1.
# Both are Cloud LOGGING queries, so no monitoring.* functions (the
# Scheduler-failure metric above records how that fails at apply).
#
# alert_strategy is not optional on either. The Monitoring API requires a
# notification rate limit on every log-match policy and refuses the create
# without one; the provider does not check it, so a missing block passes plan
# and fails apply. The rate limit throttles notifications for an alert that is
# already open, and a log-based policy sends at most 20 notifications a day
# (cloud.google.com/monitoring/quotas); the two limits below differ because the
# two signals repeat differently. Both close an incident after 1800s, the
# minimum: a log-match incident has no recovery signal and closes only after
# that long without a repeat of its entry, and the 7-day default would leave one
# forced stop open for a week with every later one reduced to a throttled repeat
# inside it. notification_prompts is the one value the API allows for a
# log-based policy (["OPENED"]: nothing is sent on close). It is stated rather
# than left to a server default, because the provider does not mark the field
# computed; its own log-match acceptance config states it too.
# tests/l2_enforcer.tofutest.hcl pins all of it.

resource "google_monitoring_alert_policy" "l2_forced_stop" {
  count = local.l2_enabled ? 1 : 0

  project      = var.gcp_project_id
  display_name = "exe: L2 forced a stop"

  # A log-match condition is a policy of its own: exactly one condition, OR.
  combiner = "OR"

  documentation {
    content   = <<-EOT
      L2, the out-of-cluster enforcer, took the exe node pool to zero BY FORCE:
      the lease had expired and L1's clean drain had not happened (lease
      unreadable three ticks running, drain reported failed, drain heartbeat
      stale, or the grace after the deadline ran out with no drain at all).
      Whatever was still running on the node was cut off.

      Nothing needs doing to stop the spend — this was the stop. What needs a
      look is why L1 did not get there first: `just exe-status` shows the
      enforcement record and its reason, and the decision line in the
      ${google_cloud_run_v2_job.l2_enforcer[0].name} job's logs carries the reason,
      the node count and the lease read failures.
    EOT
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "L2 logged a forced stop"

    condition_matched_log {
      # Severity is the page-once rule: the enforcer writes a forced stop at
      # ERROR and a repeat of the tick before it at WARNING, so without the
      # severity clause one stuck stop pages on every tick.
      filter = join(" AND ", [
        "resource.type = \"cloud_run_job\"",
        "resource.labels.job_name = \"${google_cloud_run_v2_job.l2_enforcer[0].name}\"",
        "severity >= ERROR",
        "jsonPayload.exe_l2.event = \"decision\"",
        "jsonPayload.exe_l2.action = \"stop-forced\"",
      ])
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    # The floor (5 minutes). The enforcer already limits this line to one per
    # run of forced stops, so the policy adds no second limit of its own: a
    # longer window could skip a genuine forced stop of the NEXT wake, and every
    # forced stop is one the operator has to hear about. If that page-once rule
    # ever broke, this would page on every tick — loud, which is the direction
    # a money stop should fail in.
    notification_rate_limit {
      period = "300s"
    }

    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  depends_on = [google_project_service.enabled]
}

resource "google_monitoring_alert_policy" "l2_execution_failed" {
  count = local.l2_enabled ? 1 : 0

  project      = var.gcp_project_id
  display_name = "exe: L2 execution failed"

  # A log-match condition is a policy of its own: exactly one condition, OR.
  combiner = "OR"

  documentation {
    content   = <<-EOT
      An execution of the L2 enforcer job
      (${google_cloud_run_v2_job.l2_enforcer[0].name}) logged an error: the
      enforcer's own failure line, or Cloud Run's record of an execution whose
      task crashed, timed out or was killed. A single failed attempt fires this
      even when the retry then succeeded, so check whether the following ticks
      succeed.

      While L2 is failing, an expired lease that L1 does not stop runs until the
      04:00 JST L3 stop. `just exe-l2-run` runs one pass and waits for it,
      which shows whether the failure is still happening and why.
    EOT
    mime_type = "text/markdown"
  }

  conditions {
    display_name = "L2 job logged an error that is not a decision"

    condition_matched_log {
      # Everything at ERROR from this job except the enforcer's decision lines
      # (a forced stop's decision is ERROR too, and has its own page above).
      #
      # What this has to catch besides the enforcer's failure line is what the
      # binary never wrote. Cloud Run records a failed execution against this
      # job itself, as a system-event audit entry at ERROR
      # (cloudaudit.googleapis.com/system_event: "Execution <name> has failed to
      # complete, 0/1 tasks were a success."), and that entry is what trips on a
      # crash, a timeout or a kill, where the enforcer wrote nothing. A Go
      # panic's own stack trace is NOT relied on: it is plain text, which Cloud
      # Run stores as textPayload, and only a structured line's `severity` field
      # is documented to set an entry's level (cloud.google.com/run/docs/logging).
      #
      # Those entries have no jsonPayload at all, which is why the exclusion is
      # spelled NOT <field> = "decision" and never <field> != "decision". In the
      # Logging query language every comparison on a missing field is false,
      # `NOT` of one is TRUE, and `!=` on a missing field is FALSE
      # (cloud.google.com/logging/docs/view/logging-query-language, "Missing
      # fields"): the != spelling reads the same and silently drops exactly the
      # failures above. Nor is there any other payload clause (those entries
      # fail it for the same missing-field reason) or a logName clause (they are
      # not in the enforcer's stdout log).
      filter = join(" AND ", [
        "resource.type = \"cloud_run_job\"",
        "resource.labels.job_name = \"${google_cloud_run_v2_job.l2_enforcer[0].name}\"",
        "severity >= ERROR",
        "NOT jsonPayload.exe_l2.event = \"decision\"",
      ])
    }
  }

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    # An hour. Unlike a forced stop, a failure repeats by nature: every tick,
    # and more than once per tick with the retry and Cloud Run's own entries.
    # At the 5-minute floor one broken night spends the 20-a-day cap in a few
    # hours and the policy then goes quiet while L2 is still broken; hourly, the
    # first failure still pages at once and a night-long outage stays under the
    # cap. The price is that a failure recurring within the hour of the last
    # email is not emailed again — it was, less than an hour ago.
    notification_rate_limit {
      period = "3600s"
    }

    auto_close           = "1800s"
    notification_prompts = ["OPENED"]
  }

  depends_on = [google_project_service.enabled]
}
