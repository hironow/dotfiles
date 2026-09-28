# The operator's orphan-snapshot GC (Phase 6 plan D11, option B in
# manager-loop inbox M35).
#
# Substrate collects the snapshots of the actors it deletes. What it cannot
# collect are the prefixes of actors a lost store forgot, and a store is lost
# only by an operator action, so the GC is the operator's too: `just
# exe-snapshot-gc` makes a one-off Job from the CronJob below, prints what
# `exe-reap snapshot-gc` would take (tools/exe-reaper/internal/snapshotgc says
# why), and deletes the Job. It deletes only with -apply, which the operator
# adds per run.
#
# It runs as its own KSA, the one exe-platform lets list the snapshot bucket
# and delete under two prefixes of it, never as L1's: L1 runs every minute
# and holds nothing on that bucket. Each piece is pinned by
# tests/snapshot_gc.tofutest.hcl.

resource "kubernetes_service_account_v1" "snapshot_gc" {
  metadata {
    name      = local.snapshot_gc_ksa
    namespace = kubernetes_namespace_v1.ops.metadata[0].name
    labels    = local.common_labels
  }

  # It calls no Kubernetes API: no API token, and no Role
  # (tests/unit/test_exe_snapshot_gc_iam.py fails on a RoleBinding naming it).
  # Workload Identity and the Control API's projected token need neither.
  automount_service_account_token = false

  lifecycle {
    precondition {
      condition     = local.snapshot_gc_namespace == kubernetes_namespace_v1.ops.metadata[0].name
      error_message = "exe-platform's snapshot_gc principal names another namespace than the ops namespace this stack creates its KSA in: the KSA would hold no grant."
    }
  }
}

# A raw manifest (server-side applied), like L1's CronJob, because the pod
# mounts a clusterTrustBundle projection the typed resources do not have.
resource "kubectl_manifest" "snapshot_gc" {
  server_side_apply = true

  yaml_body = yamlencode({
    apiVersion = "batch/v1"
    kind       = "CronJob"
    metadata = {
      name      = "exe-snapshot-gc"
      namespace = kubernetes_namespace_v1.ops.metadata[0].name
      labels    = merge(local.common_labels, { "app.kubernetes.io/name" = local.snapshot_gc_app })
    }
    spec = {
      # Never scheduled: suspended, it is only the template the recipe makes
      # its one-off Job from. A CronJob must have a schedule, so it has a
      # yearly one; if the suspend were ever lifted, the run it made would be
      # a dry run.
      suspend                    = true
      schedule                   = "0 0 1 1 *"
      concurrencyPolicy          = "Forbid"
      successfulJobsHistoryLimit = 0
      failedJobsHistoryLimit     = 1

      jobTemplate = {
        spec = {
          # No retries: a second run is the operator's call. The recipe runs
          # it only with a node up, and a run still going after 15 minutes is
          # stuck, not busy.
          backoffLimit          = 0
          activeDeadlineSeconds = 900

          # Nothing holding the GC's identity lingers: the recipe deletes the
          # Job once it has read the report, and this removes it anyway.
          ttlSecondsAfterFinished = 300

          template = {
            metadata = {
              labels = merge(local.common_labels, { "app.kubernetes.io/name" = local.snapshot_gc_app })
            }
            spec = {
              serviceAccountName           = kubernetes_service_account_v1.snapshot_gc.metadata[0].name
              automountServiceAccountToken = false
              restartPolicy                = "Never"

              securityContext = {
                runAsNonRoot   = true
                seccompProfile = { type = "RuntimeDefault" }
              }

              containers = [{
                name  = "snapshot-gc"
                image = ko_build.exe_reap.image_ref
                args  = ["snapshot-gc"]

                # The Control API and ax-server at exe-reap's in-cluster
                # defaults, as for L1; the location is the one AX's
                # ActorTemplates put snapshots under.
                env = [
                  { name = "EXE_SNAPSHOTS_LOCATION", value = local.ax_snapshots_location },
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

              # L1's, volume for volume (the tofu test compares the two): the
              # audience the Control API accepts and the chain it serves.
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

  depends_on = [terraform_data.ate_system, kubernetes_deployment_v1.ax_server]
}
