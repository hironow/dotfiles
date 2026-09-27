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
#
# Every run here sets enforcer_image, the switch that deploys L2 at all. The
# default, empty, leaves the job, its invoker binding and its tick out as a
# unit; l2_enforcer_off.tofutest.hcl pins that case.
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
    error_message = "the L2 job must run as the dedicated exe-enforcer service account. Its entire authority is objectUser on the ops bucket plus the custom node-pool-resizer role; running as anything else (the node SA, a default SA, or the scheduler identity whose job is to TRIGGER this one) either gives the enforcer powers it must not have or leaves it unable to read the lease at all — and an enforcer that cannot read the lease is a money stop that does nothing."
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
