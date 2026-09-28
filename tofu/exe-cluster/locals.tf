# Derived values. Computation lives here so the resource files stay declarative.

locals {
  # The one place the ax / Agent Substrate / GKE pins come from, read the same
  # way by every exe stack (scripts/check_exe_pins.py fails a stack that
  # hardcodes one instead).
  pins = jsondecode(file("${path.module}/../../exe/versions.json"))

  # The one place the auto-sleep's numbers come from (exe-platform reads it the
  # same way): the reaper's cadence is l1_tick_minutes.
  leases = jsondecode(file("${path.module}/../../exe/lease-constants.json"))

  # exe-platform's outputs (platform.tf).
  platform = data.terraform_remote_state.platform.outputs

  # --- namespaces -------------------------------------------------------------
  #
  # ate-system is upstream's, fixed by `ate-setup` and by the Workload Identity
  # principals exe-platform binds (ns/ate-system/sa/atelet, .../ate-api-server).
  # ax-system is what the ax CLI port-forwards into by default. The atespace
  # namespace carries the atespace's name because AX looks the Gemini Secret up
  # in the namespace named after the task's atespace.
  substrate_namespace = "ate-system"
  store_namespace     = "exe-store"
  ax_namespace        = "ax-system"
  atespace            = "exe"

  # --- the upstream checkouts (exe_src_dir, fetched by `just exe-cluster-src`) --
  substrate_src = "${var.exe_src_dir}/substrate"
  ax_src        = "${var.exe_src_dir}/ax"

  # --- third-party images, every one pinned by digest -------------------------
  #
  # Postgres is the exact image upstream's bundled store uses at the pinned
  # Substrate commit (manifests/ate-install/postgres/postgres.yaml): the one
  # combination upstream runs its store on.
  postgres_image = "postgres:18-alpine@sha256:9a8afca54e7861fd90fab5fdf4c42477a6b1cb7d293595148e674e0a3181de15"

  # Redis: upstream's deploy/redis.yaml tag (redis:7-alpine), resolved to a
  # digest so a pod rescheduled next month runs the same bytes.
  redis_image = "redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"

  # AX's build definitions live in exe/ax/.ko.yaml (upstream's, with every base
  # pinned by digest), which the spike's task-image recipe reads the runner's
  # base from as well; the ko_build resources in ax.tf take their base image
  # from it.
  ax_ko         = yamldecode(file("${path.module}/../../exe/ax/.ko.yaml"))
  ax_base_image = local.ax_ko.defaultBaseImage

  # --- gVisor ------------------------------------------------------------------
  #
  # The sandbox asset the pinned Substrate names (sandboxconfig-gvisor.yaml at
  # exe/versions.json's substrate.sha): a NIGHTLY path on upstream's public
  # bucket, which can disappear. It is copied, verified by sha256, into the
  # snapshot bucket under mirror/gvisor/ (substrate.tf), and our own
  # SandboxConfig names the copy. atelet reads it through the grant it already
  # holds on that bucket (exe-platform iam.tf). The worker node is an amd64 E2
  # (exe-platform's node_machine_type), so only the amd64 asset is mirrored and
  # named.
  #
  # Moving the Substrate pin means re-reading upstream's
  # sandboxconfig-gvisor.yaml at the new commit and moving these two lines with
  # it; the mirror step refuses an object whose sha256 is not this one.
  gvisor_release      = "nightly/2026-09-02"
  gvisor_amd64_sha256 = "d547d81401461fd1c679c5c4fa0a6c2b8ef7dc3c22ce23c9e25dcc4c69cfd06f"
  gvisor_upstream_url = "gs://gvisor/releases/${local.gvisor_release}/x86_64/gvisor.tar.zstd"
  gvisor_mirror_path  = "mirror/gvisor/${local.gvisor_release}/x86_64/gvisor.tar.zstd"
  gvisor_mirror_url   = "gs://${local.platform.bucket_snapshots}/${local.gvisor_mirror_path}"

  # The sandbox's pause image: the in-project GKE mirror upstream recommends for
  # GCP, instead of registry.k8s.io, pinned by digest (the CRD demands one).
  pause_image = "gcr.io/gke-release/pause@sha256:bcbd57ba5653580ec647b16d8163cdd1112df3609129b01f912a8032e48265da"

  # Named gvisor-default because AX v0.3.1 hardcodes that name into every
  # ActorTemplate it creates (internal/substrate/client.go). It REPLACES
  # upstream's file in the install (substrate.tf), so exactly one writer ever
  # applies it.
  sandbox_config = {
    apiVersion = "ate.dev/v1alpha1"
    kind       = "SandboxConfig"
    metadata = {
      name = "gvisor-default"
    }
    spec = {
      sandboxClass = "gvisor"
      pauseImage   = local.pause_image
      assets = {
        amd64 = {
          gvisor = {
            url    = local.gvisor_mirror_url
            sha256 = local.gvisor_amd64_sha256
          }
        }
      }
    }
  }
  sandbox_config_yaml = yamlencode(local.sandbox_config)

  # --- the Substrate store -------------------------------------------------------
  postgres_host     = "postgres.${local.store_namespace}.svc.cluster.local"
  postgres_db       = "ate"
  postgres_user     = "ate"
  postgres_dsn_base = "postgres://${local.postgres_user}@${local.postgres_host}:5432/${local.postgres_db}?sslmode=disable"

  # The full DSN, password included: only ever in a Secret (substrate.tf).
  postgres_dsn = "postgres://${local.postgres_user}:${random_password.postgres.result}@${local.postgres_host}:5432/${local.postgres_db}?sslmode=disable"

  # --- Substrate's install -------------------------------------------------------
  substrate_ko_repo = "${local.platform.ar_platform_repo}/substrate"

  # --- AX --------------------------------------------------------------------------
  #
  # Snapshots under their own prefix of the snapshot bucket (the one bucket
  # atelet and ate-api-server may write), next to the gVisor mirror.
  ax_snapshots_location = "gs://${local.platform.bucket_snapshots}/ax/"

  # --- the WorkerPool ------------------------------------------------------------
  #
  # Two workers, one actor each (the pinned Substrate's ateom hosts one actor at
  # a time: internal/ateomcapacity, actorsPerAteom), so two tasks awake at once
  # (plan Q17). Limits are the worker's advertised capacity AND what the
  # kube-scheduler has to place, next to the control plane, on the one node
  # (exe-platform's node_machine_type, sized by S7 to fit exactly this); memory
  # is not compressible, so its request equals the limit.
  worker_pool_name     = "exe-gvisor"
  worker_pool_replicas = 2
  worker_resources = {
    limits = {
      cpu    = "1500m"
      memory = "4Gi"
    }
    requests = {
      cpu    = "250m"
      memory = "4Gi"
    }
  }

  # --- L1, the reaper ------------------------------------------------------------
  #
  # Its namespace and KSA are the ones exe-platform binds to the ops bucket
  # (workload_identity_principals.reaper), parsed from that principal rather
  # than retyped: a KSA under any other name holds no grant, and every tick
  # 403s on the lease.
  reaper_subject   = regex("/subject/ns/([^/]+)/sa/([^/]+)$", local.platform.workload_identity_principals.reaper)
  reaper_namespace = local.reaper_subject[0]
  reaper_ksa       = local.reaper_subject[1]

  # The label the ax-server allow rule admits (ax.tf) and the CronJob's pods
  # carry (reaper.tf).
  reaper_app = "exe-reap"

  # --- the orphan-snapshot GC ------------------------------------------------------
  #
  # Its KSA is the one exe-platform lets list the snapshot bucket and delete
  # under two prefixes of it (workload_identity_principals.snapshot_gc), parsed
  # like the reaper's. Same namespace and binary as L1, never the same identity:
  # L1 runs every minute, and holds nothing on that bucket (plan D11, inbox M35).
  snapshot_gc_subject   = regex("/subject/ns/([^/]+)/sa/([^/]+)$", local.platform.workload_identity_principals.snapshot_gc)
  snapshot_gc_namespace = local.snapshot_gc_subject[0]
  snapshot_gc_ksa       = local.snapshot_gc_subject[1]

  # The label the GC's own ax-server allow rule admits (ax.tf) and its Job's
  # pods carry (snapshot_gc.tf).
  snapshot_gc_app = "exe-snapshot-gc"

  common_labels = {
    "app.kubernetes.io/part-of"    = "exe"
    "app.kubernetes.io/managed-by" = "opentofu"
  }
}
