# L3 — the daily forced stop. The last money stop, and the only automatic one
# that exists until the next phase adds L1 and L2.
#
# It has NO decision logic, deliberately. Judgement is what breaks; a cron job
# that unconditionally sets the pool to zero at 04:00 JST cannot be confused by
# a lease it failed to read. In normal operation it is a no-op, because a lease
# can never extend past 03:00 JST — the hour of slack is sized to cover L1's
# 1-minute tick, its 30-minute drain ceiling, L2's 10-minute tick and 19 minutes
# spare (section 3.2).
#
# Its own failure is therefore invisible unless someone watches for it, which is
# what the alert in monitoring.tf is for. A silent L3 is a cluster that can run
# for a day.

resource "google_cloud_scheduler_job" "l3_daily_stop" {
  project     = var.gcp_project_id
  region      = local.region
  name        = "${local.prefix}-l3-daily-stop"
  description = "L3: unconditionally resize the exe node pool to 0 every day at 04:00 JST"

  schedule  = "0 4 * * *"
  time_zone = "Asia/Tokyo"

  # Generous but finite. setSize returns as soon as the operation is accepted;
  # it does not wait for nodes to drain.
  attempt_deadline = "320s"

  retry_config {
    retry_count          = 3
    min_backoff_duration = "10s"
    max_backoff_duration = "120s"
    max_doublings        = 2
  }

  http_target {
    http_method = "POST"

    # Built in locals.tf from the cluster and node pool RESOURCES, never from
    # repeated literals: a rename would otherwise leave this job POSTing to a
    # pool that no longer exists, 404ing once a day, with only the failure alert
    # to notice. The invariant tests assert the URI and the resources agree.
    uri = local.node_pool_set_size_uri

    headers = {
      "Content-Type" = "application/json"
    }

    body = base64encode(jsonencode({ nodeCount = 0 }))

    # A Google-minted OAuth token for the dedicated L3 identity, whose only
    # power is the custom resizer role. No key material exists anywhere.
    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_project_iam_member.scheduler_resizer,
    google_container_node_pool.main,
  ]
}
