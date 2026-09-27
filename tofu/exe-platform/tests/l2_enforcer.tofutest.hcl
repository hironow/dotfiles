# What this file pins: L2 — the money stop that works when the cluster does not.
#
# L1 lives inside the cluster and stops things politely. L3 is a cron job with no
# judgement at all. L2 is the layer in between, and its whole reason to exist is
# that it runs OUTSIDE the cluster: a Cloud Run job that reads two small objects
# from GCS and, when the lease has expired past saving, POSTs nodePools.setSize
# with zero. If it ever acquires a cluster credential it stops being that layer —
# it becomes a second L1 that dies with the thing it is supposed to outlive
# (section 3.2). That property cannot be asserted by reading the Go binary from
# here, so it is asserted as the absence of every way the JOB could hand one
# over: no volumes, no volume mounts, no VPC connector, and no env var that so
# much as mentions kube.
#
# The rest of the file guards the wiring, because L2's failure mode is silence.
#
#   - the image, pinned by DIGEST. A mutable tag in the job that enforces a spend
#     limit is how a stale enforcer keeps reporting success: the tick fires, an
#     execution starts, it exits 0, and the binary running is last month's. The
#     variable's own validation is what refuses the tag, so it is exercised here
#     with `expect_failures` rather than trusted.
#   - the cadence, DERIVED from l2_tick_minutes in exe/lease-constants.json. That
#     same number is a term in the formula that keeps L3 off an awake actor
#     (04:00 − (1 + 30 + 10 + 19) = 03:00 JST), and it is mirrored by the Go
#     reaper and by the Quint model. A literal `*/10` here is a fourth
#     opinion that nothing reconciles: widen the constant to 15, recompute the
#     slack around it, and the enforcer still ticks every 10 minutes.
#   - the time zone, from the same document. It is cosmetic for a `*/N` schedule
#     and load-bearing the moment the cadence stops being one, and reading it
#     from the document is what makes L2 and L3 share one clock rather than two
#     strings that happen to match today.
#   - the identity, twice over. The JOB runs as the enforcer (lease objects plus
#     the custom resizer role, nothing else); the TICK authenticates as the
#     scheduler and is granted run.invoker ON THE JOB. Project-wide invoker would
#     let a cron job start every Cloud Run job in a SHARED project, and the
#     job-scoped binding would still be sitting there looking correct — so the
#     absence of the project-wide form is asserted directly.
#   - the pages. L2 acts at night with nobody watching, so it is also the layer
#     that has to say what it did: three log-match alerts, for a forced stop, a
#     stop that did not finish, and a failed execution. A log filter is a string
#     only the Logging API parses, so its clauses are pinned one by one — above
#     all the mistakes a plan cannot see: a `!=` where a NOT belongs, which
#     drops Cloud Run's own failure entries silently and for good, and a
#     monitoring.* function, which the Logging API refuses at apply.
#
# Every run here sets enforcer_image, the switch that deploys L2 at all. The
# default, empty, leaves the job, its invoker binding, its tick and its alerts
# out as a unit; l2_enforcer_off.tofutest.hcl pins that case.
#
# command = plan + mock_provider: offline, no credentials, no job created.

mock_provider "google" {}

# Synthetic inputs. The real identifiers live only in terraform.tfvars
# (gitignored) — this repo is public. Each value satisfies its variable's
# validation block, so a plan failure here is a regression and not a rejected
# placeholder.
variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  billing_account_id = "AAAAAA-BBBBBB-CCCCCC"
  alert_email        = "alerts@example.invalid"

  # A digest-pinned ref, which is the only shape the variable accepts. The
  # digest is synthetic; what matters is the @sha256:<64 hex> tail.
  enforcer_image = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/exe-reaper@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}

# A mocked service account's email is a generated 6-character string, so an
# assertion comparing two references to the same mock would pass while its
# failure message said nothing. Pinning two DIFFERENT realistic emails makes the
# distinction legible: if the JOB were ever pointed at the scheduler identity, or
# the TICK at the enforcer's, the assertion fails with both names spelled out.
override_resource {
  target = google_service_account.enforcer
  values = {
    email = "exe-enforcer@zz-synthetic-project.iam.gserviceaccount.com"
  }
}

override_resource {
  target = google_service_account.scheduler
  values = {
    email = "exe-scheduler@zz-synthetic-project.iam.gserviceaccount.com"
  }
}

# Same reasoning for the notification channel: its id is only known after apply,
# so pin a realistic one to make "the page reaches the email channel" legible.
override_resource {
  target = google_monitoring_notification_channel.email
  values = {
    id = "projects/zz-synthetic-project/notificationChannels/000000000000000000"
  }
}

run "with_an_image_l2_is_present_as_a_unit" {
  command = plan

  assert {
    condition     = length(google_cloud_run_v2_job.l2_enforcer) == 1
    error_message = "with enforcer_image set, exactly one L2 Cloud Run job must be planned: that variable is the only switch for L2, and setting it is the whole of turning L2 on."
  }

  assert {
    condition     = length(google_cloud_run_v2_job_iam_member.scheduler_invoker) == 1
    error_message = "with enforcer_image set, the run.invoker binding on the job must be planned with it: without the grant the tick 403s every ten minutes and L2 exists but never runs."
  }

  assert {
    condition     = length(google_cloud_scheduler_job.l2_tick) == 1
    error_message = "with enforcer_image set, the L2 tick must be planned with the job: a job nobody triggers looks deployed and enforces nothing."
  }

  assert {
    condition     = output.l2_enforcer_job == google_cloud_run_v2_job.l2_enforcer[0].name && output.l2_scheduler_job == google_cloud_scheduler_job.l2_tick[0].name
    error_message = "with enforcer_image set, the L2 outputs must name the job and the tick, which is how recipes run an enforcement pass without retyping either name."
  }
}

# exe-reaper reads the pool's RUNNING size as the target size of its instance
# groups: initialNodeCount is the creation-time 0 and never moves, and a size
# read from it would make L2 wait forever on a woken pool. That read is a
# Compute API call, so the enforcer needs exactly one permission beyond the
# resizer role, and it lives and dies with the job.
run "the_enforcer_can_read_the_pool_size_and_nothing_more" {
  command = plan

  assert {
    condition     = google_project_iam_custom_role.node_pool_reader[0].permissions == toset(["compute.instanceGroupManagers.get"])
    error_message = "the pool-reader role must hold exactly compute.instanceGroupManagers.get. Without it the enforcer cannot see a woken pool and decides as if a node may be up on every tick; with anything more, a read role in a SHARED project starts reaching other stacks' resources."
  }

  assert {
    condition     = google_project_iam_member.enforcer_pool_reader[0].role == google_project_iam_custom_role.node_pool_reader[0].id
    error_message = "the enforcer's pool-reader binding must grant the pool-reader custom role RESOURCE, so the grant and the role are created and destroyed together."
  }

  assert {
    condition     = google_project_iam_member.enforcer_pool_reader[0].member == "serviceAccount:${google_service_account.enforcer.email}"
    error_message = "the pool-reader role must be held by the exe-enforcer identity, the one the job runs as. Granted to anyone else, the enforcer still cannot read the pool size."
  }
}

run "the_enforcer_job_runs_as_the_enforcer_identity" {
  command = plan

  assert {
    condition     = google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].service_account == google_service_account.enforcer.email
    error_message = "the L2 job must run as the dedicated exe-enforcer service account. Its entire authority is reading the ops bucket, writing enforce.json in it, and the custom node-pool-resizer role; running as anything else (the node SA, a default SA, or the scheduler identity whose job is to TRIGGER this one) either gives the enforcer powers it must not have or leaves it unable to read the lease at all — and an enforcer that cannot read the lease is a money stop that does nothing."
  }

  assert {
    condition     = google_cloud_run_v2_job.l2_enforcer[0].template[0].task_count == 1
    error_message = "task_count must be 1. The enforcer decides ONE thing — whether the pool goes to zero — and writes enforce.json under a generation precondition; a second task is a second writer racing for the same object, which is the shape section 3.2 keeps as a deliberately FAILING Quint instance."
  }

  assert {
    condition     = google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].max_retries <= 1
    error_message = "max_retries must be 0 or 1, not the provider's default of 3. The next tick is only l2_tick_minutes away and is itself a retry, so a long retry chain buys nothing and instead overlaps the next execution — two enforcers deciding the same expiry at once."
  }

  assert {
    condition     = google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].timeout == "120s"
    error_message = "the task timeout must stay short (120s). The enforcer reads two small GCS objects and at most POSTs one setSize; anything longer than a couple of minutes means it is stuck, and a stuck execution that is allowed to run for the provider's default hour is still running when the next tick starts one beside it."
  }

  # Cloud Run jobs default to deletion_protection = true, which would make a
  # deliberate teardown fail at a resource whose loss costs nothing. The CLUSTER
  # is where protection belongs (cluster.tofutest.hcl); this is a stateless
  # 5-second process rebuilt from one variable.
  assert {
    condition     = google_cloud_run_v2_job.l2_enforcer[0].deletion_protection == false
    error_message = "the L2 job must set deletion_protection = false explicitly: the provider defaults it to true, so a deliberate teardown would stop at a stateless job that is rebuilt from a single image ref — while leaving the resources that actually bill still standing."
  }
}

run "the_enforcer_image_is_pinned_by_digest" {
  command = plan

  assert {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].image))
    error_message = "the job's container image must be a digest ref. The variable's validation refuses a tag, so this assertion is about the JOB actually using that variable rather than some other string: a tag here makes the deployed enforcer unauditable — the execution succeeds, the node pool is resized by whatever code the tag points at today, and nothing records which."
  }
}

# The variable validation is the wall; this run is what proves the wall is there.
# A tag-shaped ref must be refused BEFORE a plan exists, because the alternative
# failure is invisible: a job that runs an image nobody can name afterwards.
run "a_mutable_tag_is_refused_before_the_plan_exists" {
  command = plan

  variables {
    enforcer_image = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/exe-reaper:latest"
  }

  expect_failures = [var.enforcer_image]
}

run "the_tick_cadence_comes_from_the_lease_constants" {
  command = plan

  # Read exe/lease-constants.json exactly as locals.tf does, and for the same
  # reason: the Go reaper and the Quint model both mirror this document, so
  # a literal cron string here would be a third writer of one number.
  assert {
    condition     = google_cloud_scheduler_job.l2_tick[0].schedule == "*/${jsondecode(file("${path.module}/../../exe/lease-constants.json")).l2_tick_minutes} * * * *"
    error_message = "L2's schedule must be built from l2_tick_minutes in exe/lease-constants.json. That number is a term in the formula that keeps L3 off an awake actor (04:00 − (l1_tick + drain_ceiling + l2_tick + slack) = 03:00 JST); a literal here means the constant can be widened, the slack recomputed around it, and the enforcer still ticking at the old period — which shortens the real safety margin without changing a single line that mentions it."
  }

  # `*/N` restarts at the top of every hour, so the LONGEST gap — not the nominal
  # period — is what the slack in section 3.2's formula has to cover.
  assert {
    condition     = 60 % jsondecode(file("${path.module}/../../exe/lease-constants.json")).l2_tick_minutes == 0
    error_message = "l2_tick_minutes must divide 60. cron's */N steps restart at each hour boundary, so a non-divisor (45, say) fires at :00 and :45 and leaves a 15-minute gap next to a 45-minute one — and it is the longest gap, not the declared period, that section 3.2's slack is sized against."
  }

  assert {
    condition     = google_cloud_scheduler_job.l2_tick[0].time_zone == jsondecode(file("${path.module}/../../exe/lease-constants.json")).timezone
    error_message = "L2's time_zone must be the timezone from exe/lease-constants.json. For a */N cadence it changes nothing today, which is exactly why it gets dropped — and the moment the cadence becomes an hour-of-day one, L2 and L3 are reading two different clocks that used to agree. One document, one zone."
  }
}

run "the_tick_targets_the_job_resource_and_nothing_else" {
  command = plan

  # Assembled in locals.tf from the JOB RESOURCE, the same way L3's setSize URI
  # is assembled from the cluster: written independently, a rename leaves this
  # tick POSTing at a job that no longer exists — failing every ten minutes, all
  # night, with only the Scheduler-failure alert to mention it.
  assert {
    condition     = strcontains(google_cloud_scheduler_job.l2_tick[0].http_target[0].uri, "/jobs/${google_cloud_run_v2_job.l2_enforcer[0].name}:")
    error_message = "the L2 tick's URI must name the Cloud Run job RESOURCE's own name. A retyped name is a 404 every ten minutes: the Scheduler console shows failures nobody is watching, and the layer that was supposed to stop the cluster when the cluster is broken never starts."
  }

  assert {
    condition     = strcontains(google_cloud_scheduler_job.l2_tick[0].http_target[0].uri, "/locations/${google_cloud_run_v2_job.l2_enforcer[0].location}/")
    error_message = "the L2 tick's URI must name the job resource's own location. A Cloud Run job is addressed per region, so a stale region segment is a well-formed URI that resolves to nothing."
  }

  assert {
    condition     = endswith(google_cloud_scheduler_job.l2_tick[0].http_target[0].uri, ":run")
    error_message = "the L2 tick's URI must end with the :run verb. It is the only verb that starts an execution — :patch or a bare GET on the same path returns 200 and runs nothing, which is a tick that reports success forever while L2 never executes once."
  }

  assert {
    condition     = google_cloud_scheduler_job.l2_tick[0].http_target[0].http_method == "POST"
    error_message = "the L2 tick must POST. jobs.run is a POST-only verb; a GET on that URI is accepted as a read and starts no execution."
  }

  # The Cloud Run Admin API is a Google API, so it takes a Google-minted OAuth
  # token. OIDC is for reaching a Cloud Run SERVICE's own handler, which is not
  # what is being called here.
  assert {
    condition     = google_cloud_scheduler_job.l2_tick[0].http_target[0].oauth_token[0].service_account_email == google_service_account.scheduler.email
    error_message = "the L2 tick must authenticate as the dedicated exe-scheduler service account with an OAuth token. The target is the Cloud Run ADMIN API (a Google API), which takes OAuth and not OIDC — and the identity must be the scheduler's, not the enforcer's, so that the power to START the enforcer stays separate from the power the enforcer itself holds. No key material exists for either."
  }
}

run "run_invoker_is_granted_on_the_job_and_not_project_wide" {
  command = plan

  assert {
    condition     = google_cloud_run_v2_job_iam_member.scheduler_invoker[0].role == "roles/run.invoker"
    error_message = "the scheduler identity must hold roles/run.invoker (it carries run.jobs.run) on the enforcer job. Without it the tick 403s every ten minutes and L2 exists in the config but never once runs."
  }

  assert {
    condition     = google_cloud_run_v2_job_iam_member.scheduler_invoker[0].name == google_cloud_run_v2_job.l2_enforcer[0].name
    error_message = "the run.invoker binding must name the enforcer job RESOURCE. A binding on a retyped job name grants nothing and refuses nothing — the tick still 403s, and the config still reads as if the permission were there."
  }

  assert {
    condition     = google_cloud_run_v2_job_iam_member.scheduler_invoker[0].location == google_cloud_run_v2_job.l2_enforcer[0].location
    error_message = "the run.invoker binding must be in the job's own region: Cloud Run IAM is per-resource and per-region, so a binding created elsewhere applies to no job at all."
  }

  assert {
    condition     = google_cloud_run_v2_job_iam_member.scheduler_invoker[0].member == "serviceAccount:${google_service_account.scheduler.email}"
    error_message = "the run.invoker binding must be held by the exe-scheduler identity — the one the tick authenticates as. Granting it to the enforcer instead would let the enforcer re-trigger itself while leaving the tick unable to start it."
  }

  # The other half, and it can only be asserted as an ABSENCE: a project-level
  # run.invoker would let a cron job with no decision logic start every Cloud Run
  # job in a SHARED project, and the correct job-scoped binding above would still
  # be present, still passing its own assertions.
  assert {
    condition = !contains(concat(
      [for m in google_project_iam_member.node : m.role],
      [
        google_project_iam_member.build_logs.role,
        google_project_iam_member.enforcer_resizer.role,
        google_project_iam_member.enforcer_pool_reader[0].role,
        google_project_iam_member.scheduler_resizer.role,
      ],
    ), "roles/run.invoker")
    error_message = "no google_project_iam_member may grant roles/run.invoker. The project is shared with two unrelated OpenTofu stacks, so a project-wide invoker lets this stack's cron identity start THEIR Cloud Run jobs — and because the job-scoped binding would still be in place, nothing about the config would look wrong."
  }
}

run "l2_never_holds_a_cluster_credential" {
  command = plan

  # This is the property that makes L2 a different layer from L1 rather than a
  # copy of it. It cannot be read off the Go binary from here, so it is asserted
  # as the absence of every way the JOB could supply one.
  assert {
    condition     = length(google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].volumes) == 0
    error_message = "the L2 job must declare no volumes. A volume is how a kubeconfig or a service-account key would get in, and an enforcer that authenticates to the CLUSTER is an enforcer that fails whenever the cluster does — which is the one situation it exists for (section 3.2)."
  }

  assert {
    condition     = length(google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].volume_mounts) == 0
    error_message = "the L2 job's container must mount nothing. Same reason as the volumes assertion, one level in: a mount is the half of the pair that is easy to add later without touching anything that mentions L2's independence."
  }

  # No connector either: the enforcer talks to storage.googleapis.com and
  # container.googleapis.com, both public Google endpoints. A connector would be
  # a continuously-billed object, and the only thing it would buy is reachability
  # into the VPC the cluster lives in — i.e. the coupling this layer refuses.
  assert {
    condition     = length(google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].vpc_access) == 0
    error_message = "the L2 job must have no VPC access configuration. It calls two public Google APIs and needs nothing inside the VPC; a connector bills per hour whether or not it is used, and the only capability it adds is the route to the cluster's private control plane — which is precisely the dependency L2 must not have."
  }

  assert {
    condition = !strcontains(lower(join(" ", concat(
      [for e in google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].env : e.name],
      [for e in google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].env : e.value == null ? "" : e.value],
    ))), "kube")
    error_message = "no env var on the L2 job may mention kube (KUBECONFIG, a kubeconfig path, a cluster endpoint). L2's independence from cluster credentials is a design invariant, not a coincidence of the current binary: the first env var that hands it a cluster identity turns the out-of-cluster money stop into a second in-cluster one."
  }
}

run "the_job_is_told_where_everything_is_by_reference" {
  command = plan

  # Every value below comes from the resource or variable that owns it. The
  # failure a literal produces here is the worst shape available: the execution
  # succeeds, having read an empty bucket or resized nothing.
  assert {
    condition     = one([for e in google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].env : e.value if e.name == "EXE_PROJECT_ID"]) == var.gcp_project_id
    error_message = "EXE_PROJECT_ID must come from var.gcp_project_id. The project id is private and this repo is public, so it cannot be written here at all — and a literal would additionally be a second opinion about which project the enforcer acts on."
  }

  assert {
    condition     = one([for e in google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].env : e.value if e.name == "EXE_OPS_BUCKET"]) == google_storage_bucket.ops.name
    error_message = "EXE_OPS_BUCKET must be the ops bucket RESOURCE's name. lease.json, drain.json and enforce.json all live there; pointed at anything else the enforcer reads nothing, concludes nothing has expired, and returns success on every tick."
  }

  assert {
    condition     = one([for e in google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].env : e.value if e.name == "EXE_CLUSTER_NAME"]) == google_container_cluster.exe.name
    error_message = "EXE_CLUSTER_NAME must be the cluster RESOURCE's name, so a rename moves both sides at once instead of leaving the enforcer describing a cluster that no longer exists."
  }

  assert {
    condition     = one([for e in google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].env : e.value if e.name == "EXE_ZONE"]) == google_container_cluster.exe.location
    error_message = "EXE_ZONE must be the CLUSTER's own location, not a second spelling of the zone. A zonal node pool is addressed per zone: a stale value here is a well-formed request against nothing."
  }

  assert {
    condition     = one([for e in google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].env : e.value if e.name == "EXE_NODE_POOL"]) == google_container_node_pool.main.name
    error_message = "EXE_NODE_POOL must be the node pool RESOURCE's name. This is the pool whose running size the auto-sleep owns; any other name means L2 forces a pool that does not exist to zero and reports that it worked."
  }

  # The same string L3 posts to, from the same local. Two layers aiming at one
  # target is the point: if a rename breaks it, both fail together and loudly,
  # rather than one silently enforcing against a stale pool.
  assert {
    condition     = one([for e in google_cloud_run_v2_job.l2_enforcer[0].template[0].template[0].containers[0].env : e.value if e.name == "EXE_NODE_POOL_SET_SIZE_URI"]) == local.node_pool_set_size_uri
    error_message = "EXE_NODE_POOL_SET_SIZE_URI must be local.node_pool_set_size_uri — the identical string L3 posts to. L2 and L3 are the same action taken for different reasons, so they must aim at one target assembled once: two independently written URIs is a pair that can drift, and the half that drifts keeps returning 200."
  }
}

# --- the pages (decision D5) ------------------------------------------------
#
# All three alerts read the enforcer's own log contract. Every `exe-reaper
# enforce` prints one JSON object per line to stdout; Cloud Run lifts `severity`
# into the LogEntry and the rest lands in jsonPayload, with L2's fields under
# jsonPayload.exe_l2. A decision line carries event "decision" and the action,
# and is at ERROR exactly for a forced stop that does not repeat the tick before
# (repeats are WARNING). A stop-latency line carries event "stop-latency": the
# pool's target has been zero past the stop latency and an instance is still
# there. It is at ERROR the first time for a stop, and WARNING on every later
# tick of the same stop. A failure line carries event "failure", at ERROR, and
# is the last thing the binary writes before it exits 1.
#
# The failed-execution alert must also see what the binary never wrote: a task
# that crashed, timed out or was killed leaves only Cloud Run's own entries for
# the job — plain text or an audit record, with no jsonPayload at all. The
# Logging query language makes every comparison on a missing field false and
# `NOT` of one TRUE, while `!=` on a missing field is FALSE. So
# `NOT jsonPayload.exe_l2.event = "decision"` keeps those entries, and the `!=`
# spelling, which reads the same, drops every one of them without an error.

run "with_an_image_l2_pages_through_three_log_match_alerts" {
  command = plan

  assert {
    condition     = length(google_monitoring_alert_policy.l2_forced_stop) == 1
    error_message = "with enforcer_image set, the L2 forced-stop alert must be planned with the job. A forced stop cuts off whatever was running; without the page, the operator learns about it from the work that went missing."
  }

  assert {
    condition     = length(google_monitoring_alert_policy.l2_execution_failed) == 1
    error_message = "with enforcer_image set, the L2 failed-execution alert must be planned with the job. The tick reports success as soon as an execution is CREATED, so an enforcer that crashes on every tick is otherwise invisible: the money stop meant to work when the cluster does not would silently not work at all."
  }

  assert {
    condition     = length(google_monitoring_alert_policy.l2_stop_latency) == 1
    error_message = "with enforcer_image set, the L2 stop-latency alert must be planned with the job. A setSize(0) that returned 200 is not a stopped node: a disruption budget or a stuck operation can hold the VM for an hour or more, billing, while every layer reports the stop as done (inbox M18)."
  }

  # A log-match condition is a policy of its own: the API refuses a second
  # condition beside it, and any combiner but OR.
  assert {
    condition = alltrue([
      for p in [google_monitoring_alert_policy.l2_forced_stop[0], google_monitoring_alert_policy.l2_execution_failed[0], google_monitoring_alert_policy.l2_stop_latency[0]] :
      p.combiner == "OR" && length(p.conditions) == 1 && length(p.conditions[0].condition_matched_log) == 1
    ])
    error_message = "each L2 alert must be exactly one condition_matched_log condition, combined with OR. That is the only shape the Monitoring API accepts for a log-based policy: a metric condition beside the log match, or any other combiner, is refused at apply — after a plan that looked fine."
  }

  assert {
    condition     = one(google_monitoring_alert_policy.l2_forced_stop[0].notification_channels) == google_monitoring_notification_channel.email.id
    error_message = "the L2 forced-stop alert must notify exactly the exe email channel. A policy with no channel still opens incidents in a console nobody reads — indistinguishable from no alert, except that it looks configured."
  }

  assert {
    condition     = one(google_monitoring_alert_policy.l2_execution_failed[0].notification_channels) == google_monitoring_notification_channel.email.id
    error_message = "the L2 failed-execution alert must notify exactly the exe email channel. With L2 broken, a failed L1 leaves only the 04:00 L3 stop between an expired lease and the rest of the night's billing, and this alert is the one thing that says so."
  }

  assert {
    condition     = one(google_monitoring_alert_policy.l2_stop_latency[0].notification_channels) == google_monitoring_notification_channel.email.id
    error_message = "the L2 stop-latency alert must notify exactly the exe email channel. L3 posts the same setSize(0) that already returned 200, so nothing else will ever notice a VM the stop left behind."
  }
}

run "a_forced_stop_pages_on_the_enforcers_own_decision_line" {
  command = plan

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_forced_stop[0].conditions[0].condition_matched_log[0].filter, "resource.type = \"cloud_run_job\"")
    error_message = "the forced-stop filter must select resource.type = \"cloud_run_job\". The enforcer's lines are logged against the JOB resource; without the type clause the job-name comparison runs against every resource in a SHARED project."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_forced_stop[0].conditions[0].condition_matched_log[0].filter, "resource.labels.job_name = \"${google_cloud_run_v2_job.l2_enforcer[0].name}\"")
    error_message = "the forced-stop filter must name the L2 job RESOURCE's own name (resource.labels.job_name). A retyped name that has drifted matches nothing — no error, no incident, an alert that can never fire."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_forced_stop[0].conditions[0].condition_matched_log[0].filter, "severity >= ERROR")
    error_message = "the forced-stop filter must require severity >= ERROR. The enforcer logs a forced stop at ERROR and a repeat of the tick before it at WARNING, so severity IS the page-once rule: without it one stuck stop pages on every tick, all night, until the alert is muted."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_forced_stop[0].conditions[0].condition_matched_log[0].filter, "jsonPayload.exe_l2.event = \"decision\"") && strcontains(google_monitoring_alert_policy.l2_forced_stop[0].conditions[0].condition_matched_log[0].filter, "jsonPayload.exe_l2.action = \"stop-forced\"")
    error_message = "the forced-stop filter must select the enforcer's decision line whose action is stop-forced (jsonPayload.exe_l2.event = \"decision\" AND jsonPayload.exe_l2.action = \"stop-forced\"). Looser, it also matches the failure line — and the operator is told the pool was stopped on exactly the night the enforcer could not stop it."
  }

  assert {
    condition     = !strcontains(google_monitoring_alert_policy.l2_forced_stop[0].conditions[0].condition_matched_log[0].filter, "monitoring.")
    error_message = "the forced-stop filter must not use monitoring.* functions. A log-match filter is a Cloud LOGGING query, which rejects them as unparseable at apply — exactly how the first apply of the Scheduler-failure metric failed."
  }
}

run "a_slow_stop_pages_on_the_enforcers_stop_latency_line" {
  command = plan

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_stop_latency[0].conditions[0].condition_matched_log[0].filter, "resource.type = \"cloud_run_job\"")
    error_message = "the stop-latency filter must select resource.type = \"cloud_run_job\". The enforcer's lines are logged against the JOB resource; without the type clause the job-name comparison runs against every resource in a SHARED project."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_stop_latency[0].conditions[0].condition_matched_log[0].filter, "resource.labels.job_name = \"${google_cloud_run_v2_job.l2_enforcer[0].name}\"")
    error_message = "the stop-latency filter must name the L2 job RESOURCE's own name (resource.labels.job_name). A retyped name that has drifted matches nothing: the one alert that notices a VM the stop left behind could never fire."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_stop_latency[0].conditions[0].condition_matched_log[0].filter, "severity >= ERROR")
    error_message = "the stop-latency filter must require severity >= ERROR. The enforcer writes the first stop-latency line of a stop at ERROR and every later tick of the same stop at WARNING, so severity IS the page-once rule: without it one stuck VM pages every ten minutes until the alert is muted."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_stop_latency[0].conditions[0].condition_matched_log[0].filter, "jsonPayload.exe_l2.event = \"stop-latency\"")
    error_message = "the stop-latency filter must select the enforcer's stop-latency line (jsonPayload.exe_l2.event = \"stop-latency\"). Looser, it also matches a forced stop's decision and the failure line, and the operator is sent to look for a VM that is not there."
  }

  assert {
    condition     = !strcontains(google_monitoring_alert_policy.l2_stop_latency[0].conditions[0].condition_matched_log[0].filter, "monitoring.")
    error_message = "the stop-latency filter must not use monitoring.* functions. A log-match filter is a Cloud LOGGING query, which rejects them as unparseable at apply."
  }
}

run "a_failed_execution_pages_on_anything_at_error_but_a_decision_or_a_slow_stop" {
  command = plan

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "resource.type = \"cloud_run_job\"")
    error_message = "the failed-execution filter must select resource.type = \"cloud_run_job\". Cloud Run records a failed task and a failed execution against the JOB resource; without the type clause the job-name comparison runs against every resource in a SHARED project."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "resource.labels.job_name = \"${google_cloud_run_v2_job.l2_enforcer[0].name}\"")
    error_message = "the failed-execution filter must name the L2 job RESOURCE's own name (resource.labels.job_name). A retyped name that has drifted matches nothing, so the alert meant to catch a broken enforcer is itself broken, silently."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "severity >= ERROR")
    error_message = "the failed-execution filter must require severity >= ERROR. Its only payload clause EXCLUDES decision lines, so without the severity clause every other entry the job produces — Cloud Run's routine records of a healthy run included — counts as a failure, and the alert pages on every tick until it is muted."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "NOT jsonPayload.exe_l2.event = \"decision\"")
    error_message = "the failed-execution filter must exclude the enforcer's decision lines as NOT jsonPayload.exe_l2.event = \"decision\". A forced stop's decision line is at ERROR too, so without the exclusion every forced stop also pages as a failure — and a failure page that is usually a false alarm is the one that gets muted."
  }

  assert {
    condition     = strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "NOT jsonPayload.exe_l2.event = \"stop-latency\"")
    error_message = "the failed-execution filter must exclude the enforcer's stop-latency lines as NOT jsonPayload.exe_l2.event = \"stop-latency\". The first line of a slow stop is at ERROR and has its own page; without the exclusion it also pages as a failed execution, on a tick that did everything right."
  }

  assert {
    condition     = !strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "!=")
    error_message = "the failed-execution filter must not use != . In the Logging query language `field != value` is FALSE when the field is missing, and Cloud Run's own entries for a crashed, timed-out or killed task have no jsonPayload at all — the != spelling of the decision exclusion silently drops exactly the failures in which the enforcer never wrote a line. `NOT field = value` is TRUE for them."
  }

  # Any other payload clause is one those same entries cannot satisfy, for the
  # same missing-field reason; so the NOT exclusions are the ONLY payload
  # clauses, and the filter is not narrowed to one log either.
  assert {
    condition     = length(regexall("Payload", google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter)) == length(regexall("NOT jsonPayload\\.exe_l2\\.event = \"[a-z-]+\"", google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter))
    error_message = "the failed-execution filter may mention the payload only in NOT jsonPayload.exe_l2.event = \"...\" exclusions. Any other payload clause (jsonPayload.exe_l2.event = \"failure\", a textPayload match, ...) is a comparison Cloud Run's own entries cannot satisfy: a crash, a timeout or an OOM kill — the failures in which the enforcer wrote nothing — would all pass unreported."
  }

  assert {
    condition     = !strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "logName") && !strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "log_id(")
    error_message = "the failed-execution filter must not be narrowed to one log. The enforcer writes to stdout, but Cloud Run records a failed execution in a log of its own (the cloudaudit system_event entry \"Execution ... has failed to complete\"): narrowed to stdout, the alert sees only the failures the binary lived to describe."
  }

  assert {
    condition     = !strcontains(google_monitoring_alert_policy.l2_execution_failed[0].conditions[0].condition_matched_log[0].filter, "monitoring.")
    error_message = "the failed-execution filter must not use monitoring.* functions. A log-match filter is a Cloud LOGGING query, which rejects them as unparseable at apply — exactly how the first apply of the Scheduler-failure metric failed."
  }
}

# The Monitoring API refuses a log-match policy that has no notification rate
# limit. The provider does not check it, so without these assertions a plan
# with the block missing is green and the apply meant to arm L2's pages is what
# fails.
run "l2_alerts_carry_the_rate_limit_a_log_match_policy_requires" {
  command = plan

  assert {
    condition     = try(google_monitoring_alert_policy.l2_forced_stop[0].alert_strategy[0].notification_rate_limit[0].period, null) == "300s"
    error_message = "the forced-stop alert must set alert_strategy.notification_rate_limit.period = \"300s\", the floor; without a rate limit the API rejects a log-match policy at apply. The enforcer already limits this line to one per run of forced stops, so the policy adds no second limit of its own: a longer window could swallow a genuine forced stop of the NEXT wake, and every forced stop is one the operator has to hear about."
  }

  assert {
    condition     = try(google_monitoring_alert_policy.l2_execution_failed[0].alert_strategy[0].notification_rate_limit[0].period, null) == "3600s"
    error_message = "the failed-execution alert must set alert_strategy.notification_rate_limit.period = \"3600s\"; without a rate limit the API rejects a log-match policy at apply. A failure that persists matches on every tick, more than once with the retry: at the 5-minute floor one broken night spends the 20-notifications-a-day cap for log-based alerts in a few hours and the policy goes quiet while L2 is still broken. Hourly, the first failure still pages at once."
  }

  assert {
    condition     = try(google_monitoring_alert_policy.l2_stop_latency[0].alert_strategy[0].notification_rate_limit[0].period, null) == "300s"
    error_message = "the stop-latency alert must set alert_strategy.notification_rate_limit.period = \"300s\", the floor; without a rate limit the API rejects a log-match policy at apply. The enforcer already writes this line at ERROR once per stop, so the policy adds no second limit of its own: a longer window could swallow the slow stop of the NEXT sleep."
  }

  assert {
    condition = alltrue([
      for p in [google_monitoring_alert_policy.l2_forced_stop[0], google_monitoring_alert_policy.l2_execution_failed[0], google_monitoring_alert_policy.l2_stop_latency[0]] :
      try(p.alert_strategy[0].auto_close, null) == "1800s"
    ])
    error_message = "every L2 alert must auto-close after 1800s, the minimum. A log-match incident has no recovery signal — it closes only after this long without a repeat of its entry — and the default is 7 days: one forced stop would stay open for a week with every later one reduced to a throttled repeat inside it, and a failure that has long cleared would still read as current."
  }

  # The one value the API allows for a log-based policy, stated rather than left
  # to a server default because the provider does not mark the field computed
  # (monitoring.tf).
  assert {
    condition = alltrue([
      for p in [google_monitoring_alert_policy.l2_forced_stop[0], google_monitoring_alert_policy.l2_execution_failed[0], google_monitoring_alert_policy.l2_stop_latency[0]] :
      try(p.alert_strategy[0].notification_prompts, null) == tolist(["OPENED"])
    ])
    error_message = "every L2 alert must state alert_strategy.notification_prompts = [\"OPENED\"], the one value the API allows for a log-based policy: nothing is sent when an incident closes, which for a log match is only the end of its 30-minute window, not a recovery."
  }
}
