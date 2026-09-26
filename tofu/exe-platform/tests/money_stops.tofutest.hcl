# What this file pins: the things that STOP THE MONEY, and the things that notice
# when stopping failed.
#
# L3 (the daily forced stop) is the only automatic stop that exists until the
# next phase adds L1 and L2, and it has no decision logic on purpose: a cron job
# that unconditionally resizes the pool to zero at 04:00 JST cannot be confused
# by a lease it failed to read. That design choice moves the whole risk into
# WIRING, which is what this file guards:
#
#   - the target URI. It is assembled in locals.tf from the cluster and node pool
#     RESOURCES, never from repeated literals, because a rename that touched only
#     one of the two would leave the job POSTing to a pool that no longer exists.
#     It would 404 once a day, in the middle of the night, and nothing but the
#     Scheduler-failure alert would ever mention it. The assertions below rebuild
#     the URI's identifying parts from the resources themselves, so agreement is
#     proved rather than assumed.
#   - the schedule and its time zone. "0 4 * * *" in Asia/Tokyo is an hour of
#     slack after the longest possible lease (which can never extend past 03:00
#     JST). In UTC the same expression would fire at 13:00 JST — in the middle of
#     the working day, mid-task.
#   - the body. setSize takes the new size in the POST body; a body that decodes
#     to anything other than nodeCount = 0 is a job that runs successfully every
#     night and stops nothing.
#   - the identity. A Google-minted OAuth token for the DEDICATED L3 service
#     account, whose only power is the custom resizer role. Pointing this at a
#     broader identity (the enforcer's, say) hands a cron job with no decision
#     logic more authority than it needs.
#
# L4 is detection, and each of the three signals is chosen to survive the failure
# of the others. The node-uptime alert reads a COMPUTE ENGINE metric, so it holds
# even when the cluster's own monitoring is broken or switched off (and it is
# switched off: see cluster.tofutest.hcl). The budget is scoped to this project by
# NUMBER, because the billing account funds unrelated projects — an unscoped
# budget would fire on a neighbour's spend while looking like it reported ours.
#
# command = plan + mock_provider: offline, no credentials, no job created.

mock_provider "google" {}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"
}

# A mocked service account's email is a generated 6-character string. Comparing
# two references to the same mocked resource would still work, but the failure
# message would be unreadable and the assertion would not show WHICH identity is
# expected. Pinning two DIFFERENT realistic emails makes the distinction visible:
# if the job's oauth_token were ever pointed at the enforcer instead, the
# assertion below fails with both names spelled out.
override_resource {
  target = google_service_account.scheduler
  values = {
    email = "exe-scheduler@zz-synthetic-project.iam.gserviceaccount.com"
  }
}

override_resource {
  target = google_service_account.enforcer
  values = {
    email = "exe-enforcer@zz-synthetic-project.iam.gserviceaccount.com"
  }
}

# Same reasoning for the notification channel: its id is only known after apply,
# so pin a realistic one to make "the alert reaches the email channel" legible.
override_resource {
  target = google_monitoring_notification_channel.email
  values = {
    id = "projects/zz-synthetic-project/notificationChannels/000000000000000000"
  }
}

run "the_l3_uri_and_the_cluster_resources_come_from_one_source" {
  command = plan

  assert {
    condition     = strcontains(google_cloud_scheduler_job.l3_daily_stop.http_target[0].uri, "/clusters/${google_container_cluster.exe.name}/")
    error_message = "the L3 setSize URI must name the cluster resource's OWN name. If the two are written independently, renaming the cluster leaves this job POSTing at a cluster that no longer exists: it 404s once a day at 04:00 JST and nothing stops the pool any more."
  }

  assert {
    condition     = strcontains(google_cloud_scheduler_job.l3_daily_stop.http_target[0].uri, "/zones/${google_container_cluster.exe.location}/")
    error_message = "the L3 setSize URI must name the cluster resource's OWN zone. A zonal cluster's nodePools.setSize is addressed per zone, so a stale zone segment is a 404 — the job reports success in the Scheduler console only because the retry budget is exhausted quietly."
  }

  assert {
    condition     = strcontains(google_cloud_scheduler_job.l3_daily_stop.http_target[0].uri, "/nodePools/${google_container_node_pool.main.name}:")
    error_message = "the L3 setSize URI must name the node pool RESOURCE's name. This is the pool whose size the auto-sleep owns; a URI pointing at any other pool name means the daily forced stop resizes nothing at all."
  }

  assert {
    condition     = endswith(google_cloud_scheduler_job.l3_daily_stop.http_target[0].uri, ":setSize")
    error_message = "the L3 URI must end with the :setSize verb. Any other verb on the same path is a different operation — :setSize is the only one that changes the node count, and e.g. :update would return 200 while leaving the pool running."
  }

  # The URI's zone segment comes from the CLUSTER; the pool it addresses is the
  # NODE POOL. If those two resources were ever placed in different zones the URI
  # would be well-formed and still wrong, so the agreement is asserted directly.
  assert {
    condition     = google_container_node_pool.main.location == google_container_cluster.exe.location
    error_message = "the node pool and the cluster must be in the same zone: the L3 URI takes its /zones/ segment from the CLUSTER, so a pool created elsewhere would be addressed by a well-formed URI that resolves to nothing."
  }
}

run "l3_fires_at_0400_jst_not_utc" {
  command = plan

  assert {
    condition     = google_cloud_scheduler_job.l3_daily_stop.schedule == "0 4 * * *"
    error_message = "L3's schedule must be '0 4 * * *'. 04:00 is one hour of slack after the latest moment a lease can survive (03:00 JST), sized to cover L1's 1-minute tick, its 30-minute drain ceiling and L2's 10-minute tick; moving it earlier can cut a legitimate lease short, later leaves a whole idle night billed."
  }

  assert {
    condition     = google_cloud_scheduler_job.l3_daily_stop.time_zone == "Asia/Tokyo"
    error_message = "L3's time_zone must be Asia/Tokyo. Cloud Scheduler defaults to UTC, where '0 4 * * *' fires at 13:00 JST — the middle of the working day, which would shrink the pool out from under a running task instead of after it."
  }
}

run "the_l3_body_sets_the_pool_to_zero" {
  command = plan

  assert {
    condition     = keys(jsondecode(base64decode(google_cloud_scheduler_job.l3_daily_stop.http_target[0].body))) == ["nodeCount"]
    error_message = "the L3 POST body must decode to exactly one field, nodeCount. setSize ignores fields it does not know, so a body carrying a misspelled or extra key is accepted with a 200 and resizes nothing — a money stop that reports success every night while the cluster keeps running."
  }

  assert {
    condition     = jsondecode(base64decode(google_cloud_scheduler_job.l3_daily_stop.http_target[0].body)).nodeCount == 0
    error_message = "the L3 POST body must set nodeCount = 0. This is the forced STOP: any other value turns the last automatic money stop into a job that guarantees a node is running at 04:00 JST every day."
  }
}

run "l3_authenticates_as_its_own_least_privileged_identity" {
  command = plan

  assert {
    condition     = google_cloud_scheduler_job.l3_daily_stop.http_target[0].oauth_token[0].service_account_email == google_service_account.scheduler.email
    error_message = "L3 must authenticate as the dedicated exe-scheduler service account, whose only power is the custom node-pool-resizer role (container.clusters.get + update, no create/delete/getCredentials). Any broader identity gives an unconditional nightly cron job authority it does not need, and no key material exists for it anywhere."
  }
}

run "the_budget_is_jpy_and_scoped_to_this_project_alone" {
  command = plan

  # The provider builds the request path as billingAccounts/<id>/budgets, so it
  # wants the bare id. The first apply sent the prefixed form and got a 404 for
  # billingAccounts/billingAccounts/<id>.
  assert {
    condition     = google_billing_budget.exe_monthly.billing_account == var.billing_account_id && !startswith(google_billing_budget.exe_monthly.billing_account, "billingAccounts/")
    error_message = "the budget's billing_account must be the bare billing account id (var.billing_account_id), not billingAccounts/<id>: the provider adds that prefix itself, and a doubled prefix is a 404 at apply — leaving the stack with no budget and nothing saying so until the bill arrives."
  }

  assert {
    condition     = google_billing_budget.exe_monthly.amount[0].specified_amount[0].currency_code == "JPY"
    error_message = "the budget's currency must be JPY: a budget has to match its billing account's currency, and a mismatched code is rejected at apply — or worse, compares a yen spend against a dollar ceiling."
  }

  assert {
    condition     = google_billing_budget.exe_monthly.amount[0].specified_amount[0].units == "3000"
    error_message = "the budget ceiling must be 3000 JPY (decision Q9). It is the number every cost estimate in docs/plan/exe-google-ax.md is measured against; raising it silently is how a cost regression stops being visible."
  }

  assert {
    condition     = length(google_billing_budget.exe_monthly.threshold_rules) == 3
    error_message = "the budget must carry exactly three threshold rules. Fewer means one of the 50/90/100% warnings is gone; more means an undocumented threshold has been added, and a budget nobody trusts the thresholds of is a budget people mute."
  }

  assert {
    condition     = [for rule in google_billing_budget.exe_monthly.threshold_rules : rule.threshold_percent] == [0.5, 0.9, 1.0]
    error_message = "the budget thresholds must be 0.5 / 0.9 / 1.0 in that order (decision Q9): 50% is the 'something changed' signal early in the month, 90% the 'act now', 100% the record that the ceiling was actually crossed."
  }

  assert {
    condition     = alltrue([for rule in google_billing_budget.exe_monthly.threshold_rules : rule.spend_basis == "CURRENT_SPEND"])
    error_message = "every threshold must use CURRENT_SPEND, not forecast. Spend here is a few hours a day and spiky, and a forecast basis on that shape cries wolf constantly — an alert that is usually wrong is an alert that gets filtered to a folder."
  }

  # The billing account funds unrelated projects and already carries other
  # budgets. A filter-less budget would fire on their spend while appearing to
  # report this stack's.
  assert {
    condition     = google_billing_budget.exe_monthly.budget_filter[0].projects == toset(["projects/${var.gcp_project_number}"])
    error_message = "the budget must be filtered to exactly this one project. The billing account funds unrelated projects: an empty or wider filter produces an alarm that fires on a neighbour's spend and reads as if it were reporting this stack's, which is worse than no budget at all."
  }

  assert {
    condition     = can(regex("^projects/[0-9]+$", one(google_billing_budget.exe_monthly.budget_filter[0].projects)))
    error_message = "the budget filter must address the project by NUMBER (projects/<digits>), which is the only form the Billing Budgets API resolves. A project ID here is accepted by the plan and then matches nothing, giving a budget that can never fire."
  }
}

run "l4_alerts_reach_the_email_channel" {
  command = plan

  assert {
    condition     = one(google_monitoring_alert_policy.node_uptime.notification_channels) == google_monitoring_notification_channel.email.id
    error_message = "the node-uptime alert must notify exactly the exe email channel. A policy with no channel still opens incidents in the console that nobody looks at — which is indistinguishable from having no alert, except that it looks configured."
  }

  assert {
    condition     = one(google_monitoring_alert_policy.scheduler_failure.notification_channels) == google_monitoring_notification_channel.email.id
    error_message = "the Scheduler-failure alert must notify exactly the exe email channel. L3's own failure is otherwise invisible — a silently dead L3 is a cluster that can run for a full day, and this alert is the only thing that says so."
  }
}

run "node_uptime_alert_does_not_depend_on_gke_monitoring" {
  command = plan

  # 9h = the longest legitimate lease (8h) plus enforcement slack. If a node has
  # been up longer, every automatic stop has failed.
  assert {
    condition     = google_monitoring_alert_policy.node_uptime.conditions[0].condition_threshold[0].threshold_value == 32400
    error_message = "the node-uptime threshold must be 32400 seconds (9h) — the 8h maximum lease plus enforcement slack. Lower and it fires on legitimate long tasks until it is muted; higher and a whole billed day can pass before anyone is told the stops failed."
  }

  # Deliberately a Compute Engine metric: a GKE-sourced one would make the alarm
  # depend on the very thing it is watching, and this cluster has Managed Service
  # for Prometheus switched off entirely.
  assert {
    condition     = strcontains(google_monitoring_alert_policy.node_uptime.conditions[0].condition_threshold[0].filter, "compute.googleapis.com/instance/uptime_total")
    error_message = "the node-uptime condition must read compute.googleapis.com/instance/uptime_total. A GKE- or Prometheus-sourced metric would make the last line of defence depend on the cluster's own monitoring — which is deliberately minimal here, with Managed Service for Prometheus off — so the alarm would go quiet exactly when the cluster is unhealthy."
  }
}
