# Service accounts and IAM.
#
# An org policy disables the automatic IAM grants to default service accounts,
# so every identity here is created and granted explicitly. That is the right
# default anyway: the node SA, the build SA and the three auto-sleep identities
# have almost no overlap in what they may touch.
#
# Five identities, matching section 3.2's table of who writes what:
#   node      - kubelet: pull images, ship logs and metrics
#   build     - Cloud Build: read the source bucket, push the task image
#   reaper    - L1, in-cluster via Workload Identity: lease objects, image tags
#   enforcer  - L2, Cloud Run job: lease objects, and shrink the pool to 0
#   scheduler - L3, Cloud Scheduler: shrink the pool to 0, nothing else
#
# The two pool-shrinking identities share a custom role rather than
# roles/container.clusterAdmin, which would also let them delete the cluster.

resource "google_service_account" "node" {
  project      = var.gcp_project_id
  account_id   = "${local.prefix}-node"
  display_name = "exe GKE node"
  description  = "Node pool identity: image pulls, logs, metrics. No data access."

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "build" {
  project      = var.gcp_project_id
  account_id   = "${local.prefix}-build"
  display_name = "exe Cloud Build"
  description  = "Builds the task image inside the private project."

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "reaper" {
  project      = var.gcp_project_id
  account_id   = "${local.prefix}-reaper"
  display_name = "exe reaper (L1, in-cluster)"
  description  = "Graceful drain: writes drain.json, retags live task images."

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "enforcer" {
  project      = var.gcp_project_id
  account_id   = "${local.prefix}-enforcer"
  display_name = "exe enforcer (L2, Cloud Run job)"
  description  = "Out-of-cluster lease enforcement. Never uses cluster credentials."

  depends_on = [google_project_service.enabled]
}

resource "google_service_account" "scheduler" {
  project      = var.gcp_project_id
  account_id   = "${local.prefix}-scheduler"
  display_name = "exe scheduler (L3)"
  description  = "Daily forced stop. Its only power is resizing the node pool."

  depends_on = [google_project_service.enabled]
}

# --- the pool-resizing role -------------------------------------------------

# GKE has no permission narrower than container.clusters.update for
# nodePools.setSize, so this is as small as the API allows: it can read and
# update the cluster, and it cannot create, delete, or get credentials for one.
# The predefined alternative (roles/container.clusterAdmin) additionally allows
# deleting the cluster, which is not a power the daily cron job needs.
resource "google_project_iam_custom_role" "node_pool_resizer" {
  project     = var.gcp_project_id
  role_id     = "exeNodePoolResizer"
  title       = "exe node pool resizer"
  description = "Resize an exe node pool (nodePools.setSize). No create/delete."
  stage       = "GA"

  permissions = [
    "container.clusters.get",
    "container.clusters.update",
  ]

  depends_on = [google_project_service.enabled]
}

resource "google_project_iam_member" "enforcer_resizer" {
  project = var.gcp_project_id
  role    = google_project_iam_custom_role.node_pool_resizer.id
  member  = "serviceAccount:${google_service_account.enforcer.email}"
}

resource "google_project_iam_member" "scheduler_resizer" {
  project = var.gcp_project_id
  role    = google_project_iam_custom_role.node_pool_resizer.id
  member  = "serviceAccount:${google_service_account.scheduler.email}"
}

# --- node SA ----------------------------------------------------------------

# Project-level, because these are telemetry writers with no data reach. Image
# pull permission is granted per-repository instead (artifact_registry.tf), so
# the node cannot read a repository it was never meant to.
resource "google_project_iam_member" "node" {
  for_each = toset([
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/stackdriver.resourceMetadata.writer",
  ])

  project = var.gcp_project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.node.email}"
}

# --- build SA ---------------------------------------------------------------

resource "google_project_iam_member" "build_logs" {
  project = var.gcp_project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.build.email}"
}

# --- Workload Identity: the Substrate bindings (upstream's six) -------------
#
# Upstream (tools/setup-gcp, substrate v0.1.0) enumerates six Workload Identity
# bindings across two KSAs in ate-system. They are reproduced here with two
# deliberate narrowings, both recorded because a silent narrowing becomes a 403
# that looks like a bug:
#
#   dropped  atelet / roles/storage.objectAdmin at PROJECT level
#            Subsumed by the bucket-level grant below, because every
#            ActorTemplate takes its snapshot location from AX_SNAPSHOTS_BUCKET,
#            which is this one bucket. Upstream's own comment says this should
#            not be project-level. A template pointed elsewhere would 403 on its
#            first suspend — which is the failure we want, not one we want to
#            paper over with project-wide object admin.
#
#   narrowed atelet / roles/artifactregistry.reader from PROJECT to the
#            repositories atelet actually pulls actor images from (see
#            artifact_registry.tf).
#
# Everything else is kept verbatim. Dropping the ate-api-server pair silently
# breaks snapshot GC and tag copying, so those stay.

resource "google_storage_bucket_iam_member" "atelet_snapshots_object_admin" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectAdmin"
  member = local.wi_atelet
}

resource "google_storage_bucket_iam_member" "atelet_snapshots_bucket_viewer" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.bucketViewer"
  member = local.wi_atelet
}

resource "google_storage_bucket_iam_member" "api_server_snapshots_object_admin" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.objectAdmin"
  member = local.wi_api_server
}

resource "google_storage_bucket_iam_member" "api_server_snapshots_bucket_viewer" {
  bucket = google_storage_bucket.snapshots.name
  role   = "roles/storage.bucketViewer"
  member = local.wi_api_server
}

# --- Workload Identity: our own reaper (L1) ---------------------------------
#
# The reaper's cloud reach is deliberately tiny: it writes drain.json and it
# retags task images. Everything else it does (scaling atenet-router,
# suspending tasks) happens through the Kubernetes API with cluster RBAC, not
# through GCP IAM — which is why there is no container.* role here.

resource "google_storage_bucket_iam_member" "reaper_ops" {
  bucket = google_storage_bucket.ops.name
  role   = "roles/storage.objectUser"
  member = local.wi_reaper
}

# --- L2 enforcer: lease objects ---------------------------------------------
#
# objectUser, not objectAdmin: the enforcer reads lease.json/drain.json and
# writes enforce.json under generation preconditions. It never needs to change
# an object's ACL, and on a UBLA bucket there are none to change.

resource "google_storage_bucket_iam_member" "enforcer_ops" {
  bucket = google_storage_bucket.ops.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.enforcer.email}"
}

# --- Cloud Build source bucket ---------------------------------------------

resource "google_storage_bucket_iam_member" "build_source" {
  bucket = google_storage_bucket.build.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.build.email}"
}
