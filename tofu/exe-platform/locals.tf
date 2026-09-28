# Derived values. Computation lives here so the resource files stay declarative.

locals {
  prefix = "exe"

  # Tokyo, single zone. Zonal (not regional) is deliberate: a zonal Standard
  # cluster is inside GKE's free management tier, and a single-node cluster has
  # no availability story to protect anyway.
  region = "asia-northeast1"
  zone   = "asia-northeast1-a"

  # The one place ax / Agent Substrate / GKE versions come from. Read the same
  # way by every stack, and gated by scripts/check_exe_pins.py, which fails if
  # any .tf file hardcodes one of these literals instead of reading them here.
  pins = jsondecode(file("${path.module}/../../exe/versions.json"))

  # The one place the auto-sleep's numbers come from, read the same way and for
  # the same reason. The Go reaper and the Quint model mirror this document
  # under lockstep tests, so a literal in a .tf file would be a THIRD opinion about a
  # number whose whole purpose is that all three agree: l2_tick_minutes is a term
  # in the formula that keeps L3 off an awake actor (section 3.2), so a cadence
  # that drifts from the document shortens the real safety margin without
  # changing anything that mentions it.
  leases = jsondecode(file("${path.module}/../../exe/lease-constants.json"))

  # Names. Every one is exe-prefixed: the project is shared with two unrelated
  # OpenTofu stacks and a collision would let this stack adopt or clobber a
  # resource it does not own.
  cluster_name   = local.prefix # "exe"
  node_pool_name = "main"
  network_name   = "${local.prefix}-vpc"
  subnet_name    = "${local.prefix}-nodes-${local.region}"
  router_name    = "${local.prefix}-router-${local.region}"
  nat_name       = "${local.prefix}-nat-${local.region}"

  # Bucket names are globally unique, so they must embed the project id — which
  # is why they are built from a variable and never written literally.
  bucket_snapshots = "${var.gcp_project_id}-${local.prefix}-snapshots"
  bucket_ops       = "${var.gcp_project_id}-${local.prefix}-ops"
  bucket_build     = "${var.gcp_project_id}-${local.prefix}-build"

  ar_platform = "${local.prefix}-platform"
  ar_task     = "${local.prefix}-task"

  # Substrate's Workload Identity KSAs. The namespace is fixed upstream
  # (`ate-setup deploy ate-system`), not a knob.
  substrate_namespace = "ate-system"
  ksa_atelet          = "atelet"
  ksa_api_server      = "ate-api-server"
  reaper_namespace    = "exe-ops"
  ksa_reaper          = "exe-reaper"
  ksa_snapshot_gc     = "exe-snapshot-gc"

  # The orphan-snapshot GC (plan D11) may delete only the actors of these
  # atespaces, under the root AX's ActorTemplates put snapshots in: tofu/
  # exe-cluster's atespace and ax_snapshots_location, and Substrate's golden
  # atespace. tests/unit/test_exe_snapshot_gc_iam.py holds the three in step.
  snapshot_gc_root      = "ax/"
  snapshot_gc_atespaces = ["exe", "ate-golden"]

  # Workload Identity pool: addressed by project NUMBER, named by project ID.
  # Getting these two the wrong way round yields a binding that applies to
  # nothing and a 403 at first use, so it is built once, here.
  #
  # The name segment is read from the cluster rather than rebuilt from the
  # project id, because the pool only comes into existence with the first
  # cluster that enables Workload Identity: a binding sent before it fails with
  # "Identity Pool does not exist" (all seven did on the first apply). Reading
  # the pool from the cluster makes every principal binding depend on the
  # cluster through its value, so the order cannot be lost by deleting a
  # depends_on line. tests/workload_identity.tofutest.hcl pins both the value
  # and the order.
  wi_pool = "projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${google_container_cluster.exe.workload_identity_config[0].workload_pool}"

  wi_atelet      = "principal://iam.googleapis.com/${local.wi_pool}/subject/ns/${local.substrate_namespace}/sa/${local.ksa_atelet}"
  wi_api_server  = "principal://iam.googleapis.com/${local.wi_pool}/subject/ns/${local.substrate_namespace}/sa/${local.ksa_api_server}"
  wi_reaper      = "principal://iam.googleapis.com/${local.wi_pool}/subject/ns/${local.reaper_namespace}/sa/${local.ksa_reaper}"
  wi_snapshot_gc = "principal://iam.googleapis.com/${local.wi_pool}/subject/ns/${local.reaper_namespace}/sa/${local.ksa_snapshot_gc}"

  # Maintenance: 04:00-08:00 JST = 19:00-23:00 UTC. Static timestamps, so the
  # window never shows up as a perpetual plan diff. The date is only an anchor;
  # FREQ=DAILY is what makes it recur.
  maintenance_window_start = "2026-01-01T19:00:00Z"
  maintenance_window_end   = "2026-01-01T23:00:00Z"

  # Upgrades are held off entirely for the life of the 1.37 minor: one node
  # means an upgrade is a full stop, and Substrate v0.1.0 kills every awake
  # actor when a worker pod goes away. Re-dated deliberately when the minor
  # approaches end of support, which is the moment to re-read this decision.
  # scripts/check_exe_pins.py counts the certificates.k8s.io/v1beta1 deadline
  # from the end date (gke.tf, enable_k8s_beta_apis).
  upgrade_exclusion_start = "2026-09-27T00:00:00Z"
  upgrade_exclusion_end   = "2027-03-25T00:00:00Z"

  # L3: the daily forced stop calls the GKE REST API directly, as
  # projects.locations.clusters.nodePools.setSize: POST v1/{name}:setSize with
  # name = projects/P/locations/L/clusters/C/nodePools/N, where a zone is a
  # valid location. The older projects.zones method spells its verb as a path
  # segment instead (.../nodePools/N/setSize); /zones/ joined to :setSize is
  # neither, and is not a path the API defines. The URI is built from the
  # cluster and node pool RESOURCES, never from repeated literals, so a rename
  # cannot leave the Scheduler job pointing at a pool that no longer exists (it
  # would 404 daily and only the failure alert would notice).
  node_pool_set_size_uri = join("", [
    "https://container.googleapis.com/v1/projects/",
    var.gcp_project_id,
    "/locations/",
    google_container_cluster.exe.location,
    "/clusters/",
    google_container_cluster.exe.name,
    "/nodePools/",
    google_container_node_pool.main.name,
    ":setSize",
  ])

  # L2's cadence, COMPUTED from the lease document rather than written as
  # "*/10 * * * *". The tick period is one of the four terms the hour of slack
  # before L3 is made of, so the constant and the cron have to move together; a
  # literal is how the enforcer keeps ticking at the old period after someone
  # widened the constant and recomputed the slack around it.
  #
  # `*/N` restarts at every hour boundary, so N must divide 60 — otherwise the
  # LONGEST gap (not the nominal period) is what the slack has to cover. The
  # invariant test asserts that divisibility, since a locals block cannot.
  l2_cron = "*/${local.leases.l2_tick_minutes} * * * *"

  # L2's trigger: the Cloud Run Admin API's jobs.run verb, assembled from the JOB
  # RESOURCE the same way the setSize URI above is assembled from the cluster —
  # written independently, a rename leaves the tick POSTing at a job that no
  # longer exists, 404ing every ten minutes with only the Scheduler-failure alert
  # to mention it. The Admin API is regional-agnostic on this path; the region
  # appears in the resource name, not the host.
  #
  # Null while L2 is not deployed (no enforcer image; see variables.tf), since
  # there is no job to aim at; only the tick reads it, and the tick is gated on
  # the same switch.
  l2_enabled = var.enforcer_image != ""
  l2_enforcer_run_uri = local.l2_enabled ? join("", [
    "https://run.googleapis.com/v2/projects/",
    var.gcp_project_id,
    "/locations/",
    google_cloud_run_v2_job.l2_enforcer[0].location,
    "/jobs/",
    google_cloud_run_v2_job.l2_enforcer[0].name,
    ":run",
  ]) : null

  common_labels = {
    stack      = local.prefix
    managed-by = "opentofu"
  }
}
