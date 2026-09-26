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

  # Workload Identity pool: addressed by project NUMBER, named by project ID.
  # Getting these two the wrong way round yields a binding that applies to
  # nothing and a 403 at first use, so it is built once, here.
  wi_pool = "projects/${var.gcp_project_number}/locations/global/workloadIdentityPools/${var.gcp_project_id}.svc.id.goog"

  wi_atelet     = "principal://iam.googleapis.com/${local.wi_pool}/subject/ns/${local.substrate_namespace}/sa/${local.ksa_atelet}"
  wi_api_server = "principal://iam.googleapis.com/${local.wi_pool}/subject/ns/${local.substrate_namespace}/sa/${local.ksa_api_server}"
  wi_reaper     = "principal://iam.googleapis.com/${local.wi_pool}/subject/ns/${local.reaper_namespace}/sa/${local.ksa_reaper}"

  # Maintenance: 04:00-08:00 JST = 19:00-23:00 UTC. Static timestamps, so the
  # window never shows up as a perpetual plan diff. The date is only an anchor;
  # FREQ=DAILY is what makes it recur.
  maintenance_window_start = "2026-01-01T19:00:00Z"
  maintenance_window_end   = "2026-01-01T23:00:00Z"

  # Upgrades are held off entirely for the life of the 1.37 minor: one node
  # means an upgrade is a full stop, and Substrate v0.1.0 kills every awake
  # actor when a worker pod goes away. Re-dated deliberately when the minor
  # approaches end of support, which is the moment to re-read this decision.
  upgrade_exclusion_start = "2026-09-27T00:00:00Z"
  upgrade_exclusion_end   = "2027-03-25T00:00:00Z"

  # L3: the daily forced stop calls the GKE REST API directly. The URI is built
  # from the cluster and node pool RESOURCES, never from repeated literals, so a
  # rename cannot leave the Scheduler job pointing at a pool that no longer
  # exists (it would 404 daily and only the failure alert would notice).
  node_pool_set_size_uri = join("", [
    "https://container.googleapis.com/v1/projects/",
    var.gcp_project_id,
    "/zones/",
    google_container_cluster.exe.location,
    "/clusters/",
    google_container_cluster.exe.name,
    "/nodePools/",
    google_container_node_pool.main.name,
    ":setSize",
  ])

  common_labels = {
    stack      = local.prefix
    managed-by = "opentofu"
  }
}
