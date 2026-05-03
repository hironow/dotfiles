# Cloud Monitoring uptime check + alert policy for the public Coder
# UI healthz endpoint.
#
# What this does
# --------------
# Every 5 minutes a Google-hosted prober in ASIA_PACIFIC sends
# `GET https://exe.hironow.dev/healthz` carrying the same CF Access
# service-token headers the operator's `cdr` wrapper uses, expecting
# a 2xx response. Two consecutive failures (~10-15 min) trigger an
# email alert to the operator (`var.owner_email`).
#
# Cost is ~$0.10/month for one region @ 5 min cadence. Coder upstream
# does not provide an unauthenticated health endpoint behind CF
# Access, so the check has to carry the same headers `cdr` /
# `cdr-header` emit. The CF Access tokens already live in Secret
# Manager (`coder_cli_client_id` / `coder_cli_client_secret`) — we
# read them via data sources at apply time and inject them into the
# uptime check's `headers` map.
#
# State exposure: the rendered token values land in tofu state, but
# state is encrypted (existing posture). The same secret values
# already flow through the smoke / cdr code paths; this adds one
# more consumer.

# ----- read CF Access service-token values from Secret Manager -------

data "google_secret_manager_secret_version" "coder_cli_client_id_for_uptime" {
  secret = google_secret_manager_secret.coder_cli_client_id.id
}

data "google_secret_manager_secret_version" "coder_cli_client_secret_for_uptime" {
  secret = google_secret_manager_secret.coder_cli_client_secret.id
}

# ----- notification channel: operator email --------------------------

resource "google_monitoring_notification_channel" "operator_email" {
  display_name = "${local.prefix}-operator-email"
  type         = "email"
  labels = {
    email_address = var.owner_email
  }

  # Email channels do not need verification but the API can flap;
  # ignore the timestamp drift that comes from re-verification cycles.
  user_labels = local.common_labels
}

# ----- uptime check --------------------------------------------------

resource "google_monitoring_uptime_check_config" "exe_coder_healthz" {
  display_name = "${local.prefix}-coder-healthz"
  timeout      = "10s"
  period       = "300s" # 5 min cadence — single-operator stack, no need for 60s

  http_check {
    path           = "/healthz"
    port           = 443
    use_ssl        = true
    validate_ssl   = true
    request_method = "GET"

    headers = {
      "CF-Access-Client-Id"     = data.google_secret_manager_secret_version.coder_cli_client_id_for_uptime.secret_data
      "CF-Access-Client-Secret" = data.google_secret_manager_secret_version.coder_cli_client_secret_for_uptime.secret_data
    }
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.gcp_project_id
      host       = local.coder_host
    }
  }

  # Cloud Monitoring uptime checks require **at least three**
  # selected_regions (or none = all six). Three is the minimum the
  # API accepts — picking a single region returns:
  #   Error 400: selected_regions must include at least three locations
  # Three regions also matches Cloud Monitoring's default "uptime"
  # availability semantics (a check is "down" only when all probes
  # fail, smoothing transient single-region edge issues).
  selected_regions = [
    "ASIA_PACIFIC", # primary — operator is in JP
    "USA",
    "EUROPE",
  ]
}

# ----- alert policy: page on 2 consecutive uptime failures -----------

resource "google_monitoring_alert_policy" "exe_coder_healthz_down" {
  display_name = "${local.prefix}-coder-healthz down"
  combiner     = "OR"
  enabled      = true

  user_labels = local.common_labels

  conditions {
    display_name = "Coder healthz is failing"
    condition_threshold {
      filter = format(
        "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.labels.check_id=\"%s\" AND resource.type=\"uptime_url\"",
        google_monitoring_uptime_check_config.exe_coder_healthz.uptime_check_id,
      )
      duration        = "300s" # 5 min sustained = 2 consecutive 5-min checks
      comparison      = "COMPARISON_GT"
      threshold_value = 1

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.operator_email.id]

  alert_strategy {
    auto_close = "1800s" # auto-close after 30 min of recovery
  }

  documentation {
    content   = <<-DOC
      `https://exe.hironow.dev/healthz` is returning non-2xx for
      ~10 minutes. Likely causes:
      - VM preempt / GCE maintenance restart in progress (gives
        itself ~3-5 min to reprovision)
      - cloudflared / coder.service crashed
      - Cloud SQL data plane outage (rare; check Cloud SQL logs)

      Triage steps:
      1. `just exe-smoke`
      2. `gcloud compute instances describe exe-coder ...` — RUNNING?
      3. `gcloud sql instances describe exe-coder-pg ...` — RUNNABLE?
      4. Cloud SQL logs:
         `logName="projects/gen-ai-hironow/logs/cloudsql.googleapis.com%2Fpostgres.log"`
      5. Operator playbook: `exe/docs/runbook.md` ("Incident — VM is preempted").
    DOC
    mime_type = "text/markdown"
  }
}
