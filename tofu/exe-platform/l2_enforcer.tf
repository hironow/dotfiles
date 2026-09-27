# L2 — the money stop that works when the cluster does not.
#
# =====================================================================
# WHY THIS LAYER LIVES OUTSIDE THE CLUSTER, AND MUST STAY THERE.
#
# L1 stops things politely, from a CronJob inside the cluster. That covers
# the ordinary case and none of the interesting ones: a node that is up but
# whose kubelet is wedged, a Substrate install that will not schedule the
# reaper, a control plane mid-upgrade, a laptop that went to sleep with the
# lease unextended. In every one of those the in-cluster reaper is exactly as
# broken as the thing it was supposed to stop.
#
# So L2 is a Cloud Run job. It reads two small objects from GCS (lease.json,
# drain.json), writes one (enforce.json) under a generation precondition, and
# when the lease has expired past saving it POSTs nodePools.setSize with zero.
# Two public Google APIs, no cluster involved.
#
# THE INVARIANT: L2 NEVER HOLDS A CLUSTER CREDENTIAL. No kubeconfig, no
# volume, no VPC connector, no env var naming the control plane — see section
# 3.2, which states it as a design constraint and not an implementation
# detail. A change that gives this job kubectl turns the out-of-cluster money
# stop into a second in-cluster one, and the failure it exists to survive
# takes them both. tests/l2_enforcer.tofutest.hcl asserts that as the absence
# of every way this job could be handed one.
# =====================================================================
#
# The image is `var.enforcer_image` and is passed in, digest-pinned; see that
# variable for why this stack does not build it. It is also the switch for this
# whole file: empty (the default) leaves the job, its run.invoker binding, its
# pool-reader grant and its tick out TOGETHER, since any one of them without the
# others is a layer that looks deployed and never works. The enforcer identity and its grants live
# in iam.tf and are not gated: they were applied with the platform. Everything else the job needs to
# act — the bucket, the cluster, the zone, the pool, the setSize URI — is handed
# over as an env var derived from the resource that owns it, never as a literal.
# A literal's failure mode here is the worst one available: the execution
# succeeds, having read an empty bucket or resized a pool that does not exist.

resource "google_cloud_run_v2_job" "l2_enforcer" {
  count = local.l2_enabled ? 1 : 0

  project  = var.gcp_project_id
  name     = "${local.prefix}-l2-enforcer"
  location = local.region

  # Explicitly false. The provider defaults this to TRUE, which would make a
  # deliberate teardown stop at a stateless job rebuilt from a single image ref
  # while the resources that actually bill stayed up. Protection belongs on the
  # cluster, which holds state; see gke.tf.
  deletion_protection = false

  labels = local.common_labels

  template {
    # One task, and therefore one writer. The enforcer decides a single thing —
    # whether the pool goes to zero — and records it in enforce.json under a
    # generation precondition. A second task is a second writer racing for that
    # object, which section 3.2 keeps as a deliberately FAILING Quint instance
    # rather than a configuration anyone should be able to reach from here.
    task_count  = 1
    parallelism = 1

    template {
      # The dedicated L2 identity from iam.tf. Its entire authority is reading
      # the ops bucket, writing enforce.json in it, and the custom
      # node-pool-resizer role (container.clusters.get + update — no create, no
      # delete, no getCredentials). Nothing here can reach the Kubernetes API
      # even if the binary tried.
      service_account = google_service_account.enforcer.email

      # One retry, not the provider's default of three. The next tick is only
      # l2_tick_minutes away and is itself a retry, so a long chain buys nothing
      # and instead overlaps the following execution — two enforcers deciding the
      # same expiry at once.
      max_retries = 1

      # Two small object reads and at most one setSize POST. Anything past a
      # couple of minutes means it is stuck, and a stuck execution allowed to run
      # for the default hour is still running when the next tick starts one
      # beside it.
      timeout = "120s"

      containers {
        # Digest-pinned, validated by the variable. Built by a separate ko recipe
        # into the exe-platform repository; see variables.tf.
        image = var.enforcer_image

        # The reaper is one binary with subcommands; `enforce` is L2's. `wake` /
        # `extend` / `sleep` run on the operator's Mac and `reap` is the
        # in-cluster L1, so naming the subcommand here is what stops this job
        # from being able to do any of the others.
        args = ["enforce"]

        # ==============================================================
        # Every value below is derived, never typed. No kubeconfig, no
        # cluster endpoint, no credential path: see the banner above.
        # ==============================================================

        # The project id is private and this repo is public, so it can only ever
        # arrive through the variable.
        env {
          name  = "EXE_PROJECT_ID"
          value = var.gcp_project_id
        }

        # lease.json, drain.json and enforce.json all live here. Pointed anywhere
        # else, the enforcer reads nothing, concludes nothing has expired, and
        # returns success on every tick.
        env {
          name  = "EXE_OPS_BUCKET"
          value = google_storage_bucket.ops.name
        }

        env {
          name  = "EXE_CLUSTER_NAME"
          value = google_container_cluster.exe.name
        }

        # The CLUSTER's own location, not a second spelling of the zone: a zonal
        # node pool is addressed per zone, so a stale value is a well-formed
        # request against nothing.
        env {
          name  = "EXE_ZONE"
          value = google_container_cluster.exe.location
        }

        env {
          name  = "EXE_NODE_POOL"
          value = google_container_node_pool.main.name
        }

        # The identical string L3 posts to, from the same local. L2 and L3 are the
        # same action taken for different reasons, so they aim at one target
        # assembled once: two independently written URIs is a pair that can drift,
        # and the half that drifts keeps returning 200.
        env {
          name  = "EXE_NODE_POOL_SET_SIZE_URI"
          value = local.node_pool_set_size_uri
        }
      }
    }
  }

  depends_on = [
    google_project_service.enabled,
    # Everything the enforcer is allowed to do. Without them the first
    # executions 403 — on the lease read, on the pool-size read, or worse, on
    # the setSize after it has already decided the pool must go.
    google_project_iam_member.enforcer_resizer,
    google_project_iam_member.enforcer_pool_reader,
    google_storage_bucket_iam_member.enforcer_ops,
    google_storage_bucket_iam_member.enforcer_ops_write,
  ]
}

# --- the pool's running size, for the enforcer only --------------------------
#
# L2's first rule is "already at zero: nothing to do", so it has to know the
# RUNNING size, and the node pool does not report one: initialNodeCount is the
# creation-time constant from gke.tf and stays 0 however many nodes are up.
# exe-reaper reads the target size of the pool's managed instance groups
# instead (the same read the provider does for node_count), which is one
# Compute API permission that neither the resizer role nor anything else here
# grants.
#
# Its own role rather than a line in the resizer's: L3 shares that role and
# never reads a size, and this grant has exactly one user, so it is created and
# destroyed with the job. Without it the enforcer still stops the pool — it
# counts an unreadable size as a node that may be up — but it would then act,
# and report a forced stop, on every tick of a sleeping cluster.
resource "google_project_iam_custom_role" "node_pool_reader" {
  count = local.l2_enabled ? 1 : 0

  project     = var.gcp_project_id
  role_id     = "exeNodePoolReader"
  title       = "exe node pool reader"
  description = "Read an exe node pool's running size (its instance groups' target size). L2 only."
  stage       = "GA"

  permissions = [
    "compute.instanceGroupManagers.get",
  ]

  depends_on = [google_project_service.enabled]
}

resource "google_project_iam_member" "enforcer_pool_reader" {
  count = local.l2_enabled ? 1 : 0

  project = var.gcp_project_id
  role    = google_project_iam_custom_role.node_pool_reader[0].id
  member  = "serviceAccount:${google_service_account.enforcer.email}"
}

# --- run.invoker, on this job only ------------------------------------------
#
# The power to START the enforcer is kept separate from the power the enforcer
# holds, so the scheduler identity gets run.invoker (which carries run.jobs.run)
# and nothing else here.
#
# Scoped to the JOB, not the project. The project is shared with two unrelated
# OpenTofu stacks: a project-level roles/run.invoker would let this stack's cron
# identity start THEIR Cloud Run jobs, and because the job-scoped binding would
# still be in place nothing about the config would look wrong. The test asserts
# the absence of the project-wide form as well as the presence of this one.
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  count = local.l2_enabled ? 1 : 0

  project  = var.gcp_project_id
  location = google_cloud_run_v2_job.l2_enforcer[0].location
  name     = google_cloud_run_v2_job.l2_enforcer[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

# --- the tick ---------------------------------------------------------------
#
# Cloud Scheduler, every l2_tick_minutes, POSTing the Cloud Run Admin API's
# jobs.run verb. The schedule and the time zone both come from
# exe/lease-constants.json through locals.tf: that document is what the Go reaper
# and the Quint model mirror, and the tick period is a term in the
# formula that keeps L3 off an awake actor. A literal `*/10` here would be a
# fourth opinion nothing reconciles.
#
# Failures are invisible from the outside — a tick that never fires looks exactly
# like a tick with nothing to do — which is what the Scheduler-failure alert in
# monitoring.tf exists for. Its log-based metric already matches every `exe-*`
# job, so this one is covered the moment it is created.
resource "google_cloud_scheduler_job" "l2_tick" {
  count = local.l2_enabled ? 1 : 0

  project     = var.gcp_project_id
  region      = local.region
  name        = "${local.prefix}-l2-tick"
  description = "L2: run the out-of-cluster lease enforcer every ${local.leases.l2_tick_minutes} minutes"

  schedule  = local.l2_cron
  time_zone = local.leases.timezone

  # jobs.run returns as soon as the execution is CREATED; it does not wait for
  # the task. Generous enough to absorb a slow API response, short enough that a
  # hung attempt cannot still be open when the next tick arrives.
  attempt_deadline = "180s"

  retry_config {
    # A smaller budget than L3's, deliberately: L3 gets one chance every 24
    # hours, while the next L2 tick is minutes away and is itself a retry. What
    # this covers is a transient 5xx on the Admin API, not an outage.
    retry_count          = 2
    min_backoff_duration = "10s"
    max_backoff_duration = "60s"
    max_doublings        = 1
  }

  http_target {
    http_method = "POST"

    # Built in locals.tf from the job RESOURCE, for the same reason L3's setSize
    # URI is built from the cluster: a retyped name is a 404 every ten minutes,
    # all night, and the layer meant to stop a broken cluster never starts.
    uri = local.l2_enforcer_run_uri

    headers = {
      "Content-Type" = "application/json"
    }

    # No body. jobs.run takes an optional overrides object; sending none is what
    # makes the execution exactly the job as declared above, so the args, the
    # identity and the env cannot be varied from the trigger side.

    # OAuth, not OIDC. The target is the Cloud Run ADMIN API — a Google API,
    # which takes a Google-minted access token. OIDC is for reaching a Cloud Run
    # SERVICE's own handler, which is not what is being called here, and an OIDC
    # token against this endpoint is a 401 every tick.
    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }

  depends_on = [
    google_cloud_run_v2_job_iam_member.scheduler_invoker,
  ]
}
