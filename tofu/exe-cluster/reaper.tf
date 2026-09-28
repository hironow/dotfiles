# L1: the in-cluster reaper (docs/plan/exe-google-ax.md section 3.2, Phase 6
# plan D1, D2).
#
# exe-reap runs once a minute. It reads every actor through the Substrate
# Control API and the lease and its own drain record from the ops bucket,
# decides with lease.DecideL1, writes drain.json, and then acts: it scales the
# atenet-router and the ax-controller, asks ax-server to suspend awake tasks,
# and deletes a wedged worker's pod. It never touches the node pool; that is
# L2's (exe-platform).
#
# Its authority, each piece pinned by tests/reaper.tofutest.hcl:
#   - the ops bucket, through the Workload Identity binding exe-platform makes
#     for exactly this namespace and KSA: read everything, write drain.json and
#     tasks.json;
#   - the Control API, exactly as the ax-controller reaches it: a projected
#     token for api.ate-system.svc and the servicedns trust bundle;
#   - ax-server, through one NetworkPolicy allow rule (ax.tf);
#   - the Kubernetes API, through RBAC naming the two Deployments it scales,
#     pod lists behind them, and pod deletes in the atespace.

resource "kubernetes_namespace_v1" "ops" {
  metadata {
    name   = local.reaper_namespace
    labels = local.common_labels
  }
}

resource "kubernetes_service_account_v1" "reaper" {
  metadata {
    name      = local.reaper_ksa
    namespace = kubernetes_namespace_v1.ops.metadata[0].name
    labels    = local.common_labels
  }
}

# From this repo's module, over the same digest-pinned base as AX, into its own
# repository in the platform registry (whose cleanup policy bounds it).
resource "ko_build" "exe_reap" {
  importpath  = "github.com/hironow/dotfiles/tools/exe-reaper/cmd/exe-reap"
  working_dir = "${path.module}/../../tools/exe-reaper"
  repo        = "${local.platform.ar_platform_repo}/exe-reap"
  base_image  = local.ax_base_image
  platforms   = ["linux/amd64"]
  sbom        = "none"
  # No VCS stamps: go would stamp the commit and a dirty-tree flag into the
  # binary, so every commit anywhere in this repo, or any uncommitted file,
  # would give a new digest and roll both CronJobs for no change of code.
  env     = ["CGO_ENABLED=0", "GOFLAGS=-buildvcs=false"]
  ldflags = ["-s", "-w"]
}

# A raw manifest (server-side applied), for the same reason as the
# ax-controller's: the pod mounts a clusterTrustBundle projection, which the
# typed resources' schema does not have.
resource "kubectl_manifest" "reaper" {
  server_side_apply = true

  yaml_body = yamlencode({
    apiVersion = "batch/v1"
    kind       = "CronJob"
    metadata = {
      name      = "exe-reap"
      namespace = kubernetes_namespace_v1.ops.metadata[0].name
      labels    = merge(local.common_labels, { "app.kubernetes.io/name" = local.reaper_app })
    }
    spec = {
      # L1's tick (exe/lease-constants.json). `*/1` is every minute.
      schedule = "*/${local.leases.l1_tick_minutes} * * * *"

      # One tick at a time, and a tick that could not start on time is
      # replaced by the next rather than run late beside it.
      concurrencyPolicy       = "Forbid"
      startingDeadlineSeconds = 30

      # 1,440 runs a day: keep only what a reader needs.
      successfulJobsHistoryLimit = 1
      failedJobsHistoryLimit     = 3

      jobTemplate = {
        spec = {
          # No retries: the next minute is the retry. And no Job deadline
          # (inbox M28): while the pool sleeps the tick's pod stays Pending,
          # and Forbid holds every later tick behind it, so one Pending Job
          # waits out the whole sleep and runs the moment a node is up. A
          # deadline would fail it and create the next one every minute, all
          # night. A tick that runs ends itself on exe-reap's own 45 s
          # deadline; a pod stuck on a node goes when the node does, at the
          # next stop.
          backoffLimit = 0

          template = {
            metadata = {
              labels = merge(local.common_labels, { "app.kubernetes.io/name" = local.reaper_app })
            }
            spec = {
              serviceAccountName = kubernetes_service_account_v1.reaper.metadata[0].name
              restartPolicy      = "Never"

              securityContext = {
                runAsNonRoot   = true
                seccompProfile = { type = "RuntimeDefault" }
              }

              containers = [{
                name  = "reap"
                image = ko_build.exe_reap.image_ref

                # The Control API and ax-server at exe-reap's in-cluster
                # defaults, which are the ax-controller's; the bucket, the
                # repositories whose images retention keeps tagged, and L2's
                # enforcer image (no pod runs it) come from exe-platform's
                # state. The namespaces are the ones whose pods' images
                # retention protects (M19 C3).
                env = [
                  { name = "EXE_OPS_BUCKET", value = local.platform.bucket_ops },
                  { name = "EXE_AR_REPOS", value = join(",", [local.platform.ar_task_repository, local.platform.ar_platform_repository]) },
                  { name = "EXE_POD_NAMESPACES", value = join(",", local.reaper_pod_namespaces) },
                  { name = "EXE_PROTECT_IMAGES", value = local.platform.enforcer_image },
                ]

                resources = {
                  requests = { cpu = "50m", memory = "64Mi" }
                  limits   = { cpu = "250m", memory = "128Mi" }
                }

                securityContext = {
                  readOnlyRootFilesystem   = true
                  allowPrivilegeEscalation = false
                  capabilities             = { drop = ["ALL"] }
                }

                volumeMounts = [
                  { name = "ate-token", mountPath = "/var/run/secrets/ateapi", readOnly = true },
                  { name = "servicedns-ca", mountPath = "/run/servicedns-ca", readOnly = true },
                ]
              }]

              volumes = [
                {
                  name = "ate-token"
                  projected = {
                    defaultMode = 420
                    sources = [{
                      serviceAccountToken = {
                        audience          = "api.${local.substrate_namespace}.svc"
                        expirationSeconds = 3600
                        path              = "token"
                      }
                    }]
                  }
                },
                {
                  name = "servicedns-ca"
                  projected = {
                    defaultMode = 420
                    sources = [{
                      clusterTrustBundle = {
                        signerName = "servicedns.podcert.ate.dev/identity"
                        path       = "trust-bundle.pem"
                        labelSelector = {
                          matchLabels = { "podcert.ate.dev/canarying" = "live" }
                        }
                      }
                    }]
                  }
                },
              ]
            }
          }
        }
      }
    }
  })

  # The trust bundle and the Control API exist once Substrate is installed,
  # and ax-server once AX is: a tick before them fails, and says so.
  depends_on = [terraform_data.ate_system, kubernetes_deployment_v1.ax_server]

  lifecycle {
    precondition {
      condition     = local.platform.enforcer_image == "" || startswith(local.platform.enforcer_image, "${local.platform.ar_platform_repo}/")
      error_message = "exe-platform's enforcer_image is not in its platform repository. exe-reap refuses to start on an EXE_PROTECT_IMAGES entry it cannot protect, so every tick, the drain included, would fail: build the enforcer with `just exe-reaper-image`."
    }
  }
}

# --- RBAC: two replica counts, the pods behind them, wedged workers, and the ---
# --- images the cluster's pods run --------------------------------------------

resource "kubernetes_role_v1" "reaper_router" {
  metadata {
    name      = "exe-reaper"
    namespace = kubernetes_namespace_v1.ate_system.metadata[0].name
    labels    = local.common_labels
  }

  rule {
    api_groups     = ["apps"]
    resources      = ["deployments/scale"]
    resource_names = ["atenet-router"]
    verbs          = ["get", "patch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods"]
    verbs      = ["list"]
  }
}

resource "kubernetes_role_v1" "reaper_controller" {
  metadata {
    name      = "exe-reaper"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = local.common_labels
  }

  rule {
    api_groups     = ["apps"]
    resources      = ["deployments/scale"]
    resource_names = ["ax-controller"]
    verbs          = ["get", "patch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods"]
    verbs      = ["list"]
  }
}

# Pod deletes cannot be narrowed to one label by RBAC; exe-reap deletes only a
# pod the Substrate store names as a wedged actor's worker, with that pod's UID
# as a precondition (plan D6). It lists the workers for the images they run.
resource "kubernetes_role_v1" "reaper_workers" {
  metadata {
    name      = "exe-reaper"
    namespace = kubernetes_namespace_v1.atespace.metadata[0].name
    labels    = local.common_labels
  }

  rule {
    api_groups = [""]
    resources  = ["pods"]
    verbs      = ["delete", "list"]
  }
}

# The namespaces in local.reaper_pod_namespaces where no role above lets the
# reaper list pods: its own, and the pod certificate controller's, which the
# Substrate install creates.
resource "kubernetes_role_v1" "reaper_pods" {
  for_each = toset([local.reaper_namespace, local.podcertificate_namespace])

  metadata {
    name      = "exe-reaper"
    namespace = each.key
    labels    = local.common_labels
  }

  rule {
    api_groups = [""]
    resources  = ["pods"]
    verbs      = ["list"]
  }

  depends_on = [kubernetes_namespace_v1.ops, terraform_data.ate_system]
}

resource "kubernetes_role_binding_v1" "reaper_pods" {
  for_each = kubernetes_role_v1.reaper_pods

  metadata {
    name      = "exe-reaper"
    namespace = each.value.metadata[0].namespace
    labels    = local.common_labels
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = each.value.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.reaper.metadata[0].name
    namespace = kubernetes_service_account_v1.reaper.metadata[0].namespace
  }
}

resource "kubernetes_role_binding_v1" "reaper_router" {
  metadata {
    name      = "exe-reaper"
    namespace = kubernetes_role_v1.reaper_router.metadata[0].namespace
    labels    = local.common_labels
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.reaper_router.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.reaper.metadata[0].name
    namespace = kubernetes_service_account_v1.reaper.metadata[0].namespace
  }
}

resource "kubernetes_role_binding_v1" "reaper_controller" {
  metadata {
    name      = "exe-reaper"
    namespace = kubernetes_role_v1.reaper_controller.metadata[0].namespace
    labels    = local.common_labels
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.reaper_controller.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.reaper.metadata[0].name
    namespace = kubernetes_service_account_v1.reaper.metadata[0].namespace
  }
}

resource "kubernetes_role_binding_v1" "reaper_workers" {
  metadata {
    name      = "exe-reaper"
    namespace = kubernetes_role_v1.reaper_workers.metadata[0].namespace
    labels    = local.common_labels
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.reaper_workers.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.reaper.metadata[0].name
    namespace = kubernetes_service_account_v1.reaper.metadata[0].namespace
  }
}
