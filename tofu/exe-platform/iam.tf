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
#   reaper    - L1, in-cluster via Workload Identity: read the ops bucket,
#               write drain.json and tasks.json; image tags
#   enforcer  - L2, Cloud Run job: read the ops bucket, write enforce.json;
#               read the pool's size and shrink it to 0 (the size read is
#               granted with the job, in l2_enforcer.tf)
#   scheduler - L3, Cloud Scheduler: shrink the pool to 0, nothing else; and
#               start the L2 job (run.invoker on that job, in l2_enforcer.tf)
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
#
# ORDERING. Every principal:// member below names the Workload Identity pool
# <project>.svc.id.goog, and that pool does not exist until a cluster with
# Workload Identity enabled does: bound any earlier, IAM answers "Identity Pool
# does not exist" (the first apply failed exactly so, for all seven). The
# members are built in locals.tf from the cluster's own workload_pool, so each
# binding depends on the cluster through its value and needs no depends_on.
# tests/workload_identity.tofutest.hcl plans each binding on its own and fails
# if the cluster is not part of that plan, here or in artifact_registry.tf.

# This grant is also atelet's read access to the gVisor mirror, which lives in
# the same bucket under mirror/gvisor/ (storage.tf; exe-cluster copies it there
# and names it in the SandboxConfig). Narrowing it to snapshot prefixes would
# make every actor's first boot fail on the sandbox asset download.
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

# --- the ops bucket: one writer per object ---------------------------------
#
# Every object in the ops bucket has exactly one writer, declared in
# exe/lease-constants.json (_writers): the operator writes lease.json and
# keep.json on their own credentials, the reaper (L1) drain.json and
# tasks.json, the enforcer (L2) enforce.json. The grants below enforce that
# declaration rather than restating it.
#
# IAM grants add up, so a condition cannot narrow an unconditional grant, and
# objectUser carries reads and writes alike. Each service identity therefore
# holds two bindings:
#   - roles/storage.objectViewer, unconditional: it reads every object, and
#     listing is checked against the BUCKET, which an object-name condition
#     could never match;
#   - roles/storage.objectUser under a condition naming exactly its own
#     objects. An overwrite under a generation precondition is
#     storage.objects.create plus storage.objects.delete on that object, and
#     objectUser holds both. objectAdmin would add nothing but ACL control,
#     and a UBLA bucket has no ACLs.
#
# Every one of these grants is replaced create-before-destroy, and each read
# grant depends on its write grant, so a replacement adds the new binding
# before it removes the old and a writer is never left without its write. The
# enforcer writes enforce.json on every tick, and a tick without that write is
# a failed execution. The same order is what let the read grants take over the
# addresses of the unconditional objectUser grants they replaced, with L2 live.
#
# tests/ops_bucket_iam.tofutest.hcl pins all of it.

locals {
  # A condition on a Cloud Storage binding compares IAM resource names, and an
  # object's is projects/_/buckets/<bucket>/objects/<name>.
  ops_write_conditions = {
    for writer in ["reaper", "enforcer"] : writer => join(" || ", [
      for object, owner in local.leases["_writers"] :
      "resource.name == \"projects/_/buckets/${google_storage_bucket.ops.name}/objects/${object}\""
      if owner == writer
    ])
  }
}

# --- Workload Identity: our own reaper (L1) ---------------------------------
#
# The reaper's cloud reach is deliberately tiny: it writes drain.json and
# tasks.json, and it retags task images. Everything else it does (scaling
# atenet-router and ax-controller, suspending tasks) happens through the
# Kubernetes API with cluster RBAC, not through GCP IAM — which is why there is
# no container.* role here.

resource "google_storage_bucket_iam_member" "reaper_ops" {
  bucket = google_storage_bucket.ops.name
  role   = "roles/storage.objectViewer"
  member = local.wi_reaper

  depends_on = [google_storage_bucket_iam_member.reaper_ops_write]

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "reaper_ops_write" {
  bucket = google_storage_bucket.ops.name
  role   = "roles/storage.objectUser"
  member = local.wi_reaper

  condition {
    title      = "exe-reaper writes its own ops objects"
    expression = local.ops_write_conditions.reaper
  }

  lifecycle {
    create_before_destroy = true
  }
}

# --- L2 enforcer: lease objects ---------------------------------------------

resource "google_storage_bucket_iam_member" "enforcer_ops" {
  bucket = google_storage_bucket.ops.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.enforcer.email}"

  depends_on = [google_storage_bucket_iam_member.enforcer_ops_write]

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_storage_bucket_iam_member" "enforcer_ops_write" {
  bucket = google_storage_bucket.ops.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.enforcer.email}"

  condition {
    title      = "exe-enforcer writes its own ops objects"
    expression = local.ops_write_conditions.enforcer
  }

  lifecycle {
    create_before_destroy = true
  }
}

# --- Cloud Build source bucket ---------------------------------------------

resource "google_storage_bucket_iam_member" "build_source" {
  bucket = google_storage_bucket.build.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.build.email}"
}

# --- Workload Identity: the operator's orphan-snapshot GC (plan D11) --------
#
# Substrate collects the snapshots of the actors it deletes; the GC takes the
# prefixes of actors a lost store forgot. It runs as its own KSA, only inside
# the one-off Job `just exe-snapshot-gc` makes (tofu/exe-cluster), and never as
# L1: L1 runs every minute, and holds nothing on this bucket (inbox M35).
#
# Two custom roles, because no predefined role is narrow enough:
#   - storage.objects.list, unconditional: a list is checked against the
#     bucket, which no object-name condition matches. Names and times are all
#     the decision reads; storage.objects.get would let it read every
#     snapshot's contents.
#   - storage.objects.delete, under a condition naming the two prefixes it may
#     delete under. The gVisor mirror every actor boots from (mirror/) and a
#     Tag's snapshot (atespaces/<a>/tags/) stay out of reach at IAM.
#
# The residual risk: anyone who can create pods in exe-ops can run as this KSA.
# That adds no reach beyond what already stands: atelet and ate-api-server hold
# roles/storage.objectAdmin on the whole bucket (above), and whoever can create
# pods in exe-ops can create them in ate-system as well.
#
# tests/snapshot_gc.tofutest.hcl pins the roles, the members and the condition.

locals {
  snapshot_gc_delete_condition = join(" || ", [
    for atespace in local.snapshot_gc_atespaces :
    "resource.name.startsWith(\"projects/_/buckets/${google_storage_bucket.snapshots.name}/objects/${local.snapshot_gc_root}atespaces/${atespace}/actors/\")"
  ])
}

resource "google_project_iam_custom_role" "snapshot_gc_list" {
  project     = var.gcp_project_id
  role_id     = "exeSnapshotGcList"
  title       = "exe snapshot GC: list"
  description = "Lists object names and times; reads no object."
  permissions = ["storage.objects.list"]

  depends_on = [google_project_service.enabled]
}

resource "google_project_iam_custom_role" "snapshot_gc_delete" {
  project     = var.gcp_project_id
  role_id     = "exeSnapshotGcDelete"
  title       = "exe snapshot GC: delete"
  description = "Deletes objects; granted only under a condition naming the prefixes."
  permissions = ["storage.objects.delete"]

  depends_on = [google_project_service.enabled]
}

resource "google_storage_bucket_iam_member" "snapshot_gc_list" {
  bucket = google_storage_bucket.snapshots.name
  role   = google_project_iam_custom_role.snapshot_gc_list.id
  member = local.wi_snapshot_gc
}

resource "google_storage_bucket_iam_member" "snapshot_gc_delete" {
  bucket = google_storage_bucket.snapshots.name
  role   = google_project_iam_custom_role.snapshot_gc_delete.id
  member = local.wi_snapshot_gc

  condition {
    title      = "exe-snapshot-gc deletes only actor snapshots"
    expression = local.snapshot_gc_delete_condition
  }
}
