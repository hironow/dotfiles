# L4 — detection. What notices when the money stops did not work.
#
# Three signals, chosen so that each one survives the failure of the others:
#   - node uptime, read from a COMPUTE ENGINE metric, so it holds even if the
#     cluster's own monitoring is broken or switched off;
#   - Cloud Scheduler failures, so a silently dead L3 (or, next phase, L2) is
#     visible rather than merely absent;
#   - a JPY budget, which catches everything the first two missed.
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

  filter = join(" AND ", [
    "resource.type = \"cloud_scheduler_job\"",
    "severity >= ERROR",
    "resource.labels.job_id = monitoring.regex.full_match(\"${local.prefix}-.*\")",
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

  depends_on = [google_project_service.enabled]
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
