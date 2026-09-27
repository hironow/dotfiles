# AX: ax-server (stateless gRPC in front of Redis), ax-controller (the one
# component that calls Substrate), and the Redis they share.
#
# Upstream deploys these with `ko apply` over deploy/*.yaml and a Redis with no
# persistence and no password, which loses every task record on a restart and
# serves the rest of the cluster unauthenticated. Here: the images are
# ko_build resources over the pinned checkout with a digest-pinned base, Redis
# is a StatefulSet with AOF on a pd-standard volume and a requirepass, and a
# NetworkPolicy lets only the two AX pods reach it.

resource "kubernetes_namespace_v1" "ax" {
  metadata {
    name   = local.ax_namespace
    labels = local.common_labels
  }
}

# --- the images ------------------------------------------------------------
#
# The build definitions upstream keeps in .ko.yaml, stated here instead, for all
# the components we run (upstream's file has no entry for ax-server): the
# pinned checkout, a base image pinned by digest, linux/amd64 only (the node's
# architecture), no SBOM. ko itself adds -trimpath and a zero build date, so
# the same source builds the same digest; on every plan the provider rebuilds
# locally to notice a changed source, and only pushes on apply.

resource "ko_build" "ax_server" {
  importpath  = "github.com/google/ax/cmd/ax-server"
  working_dir = local.ax_src
  base_image  = local.ax_base_image
  platforms   = ["linux/amd64"]
  sbom        = "none"
  env         = ["CGO_ENABLED=0"]
  ldflags     = ["-s", "-w"]
}

resource "ko_build" "ax_controller" {
  importpath  = "github.com/google/ax/cmd/ax-controller"
  working_dir = local.ax_src
  base_image  = local.ax_base_image
  platforms   = ["linux/amd64"]
  sbom        = "none"
  env         = ["CGO_ENABLED=0"]
  ldflags     = ["-s", "-w"]
}

# --- Redis -------------------------------------------------------------------

resource "random_password" "redis" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "redis" {
  metadata {
    name      = "ax-redis"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    REDIS_PASSWORD = random_password.redis.result
  }
}

# The name and port upstream's components dial (ax-redis.ax-system.svc:6379).
resource "kubernetes_service_v1" "redis" {
  metadata {
    name      = "ax-redis"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    type = "ClusterIP"
    selector = {
      app = "ax-redis"
    }

    port {
      name        = "redis"
      port        = 6379
      target_port = 6379
    }
  }
}

resource "kubernetes_stateful_set_v1" "redis" {
  metadata {
    name      = "ax-redis"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = local.common_labels
  }

  # Applies with the pool at zero; the pod starts when a node does.
  wait_for_rollout = false

  spec {
    replicas     = 1
    service_name = kubernetes_service_v1.redis.metadata[0].name

    selector {
      match_labels = {
        app = "ax-redis"
      }
    }

    template {
      metadata {
        labels = merge(local.common_labels, { app = "ax-redis" })
      }

      spec {
        # The image's redis user is uid/gid 999.
        security_context {
          fs_group               = 999
          fs_group_change_policy = "OnRootMismatch"
        }

        container {
          name  = "redis"
          image = local.redis_image

          # AOF on (every write logged, fsync once a second), so a restart
          # replays the task records instead of starting empty. The password
          # comes in through the environment, never the command line of a
          # tracked file: $(REDIS_PASSWORD) is expanded by the kubelet.
          args = [
            "redis-server",
            "--appendonly", "yes",
            "--appendfsync", "everysec",
            "--dir", "/data",
            "--requirepass", "$(REDIS_PASSWORD)",
          ]

          env {
            name = "REDIS_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.redis.metadata[0].name
                key  = "REDIS_PASSWORD"
              }
            }
          }

          port {
            name           = "redis"
            container_port = 6379
          }

          # A TCP probe: an authenticated `redis-cli ping` would have to carry
          # the password in the probe's own command line.
          readiness_probe {
            tcp_socket {
              port = "6379"
            }
            initial_delay_seconds = 2
            period_seconds        = 5
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "256Mi"
            }
            limits = {
              cpu    = "500m"
              memory = "512Mi"
            }
          }

          volume_mount {
            name       = "data"
            mount_path = "/data"
          }
        }
      }
    }

    # pd-standard (the GKE `standard` class): Redis with AOF writes little, and
    # the cheaper class is enough (plan Q22; S7 measures the latency).
    volume_claim_template {
      metadata {
        name = "data"
      }

      spec {
        access_modes       = ["ReadWriteOnce"]
        storage_class_name = "standard"

        resources {
          requests = {
            storage = "10Gi"
          }
        }
      }
    }
  }
}

# Only ax-server and ax-controller may reach Redis. Every task's actor runs
# arbitrary code on the same pod network, and upstream's Redis answered anyone.
resource "kubernetes_network_policy_v1" "redis" {
  metadata {
    name      = "ax-redis-from-ax-only"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    pod_selector {
      match_labels = {
        app = "ax-redis"
      }
    }

    policy_types = ["Ingress"]

    ingress {
      from {
        pod_selector {
          match_expressions {
            key      = "app.kubernetes.io/name"
            operator = "In"
            values   = ["ax-server", "ax-controller"]
          }
        }
      }

      ports {
        protocol = "TCP"
        port     = "6379"
      }
    }
  }
}

# Nothing on the pod network may reach ax-server (S5): every task's actor runs
# arbitrary code there, and the API creates, resumes and deletes tasks. Its one
# client, the operator's `ax` CLI, arrives through a kubectl port-forward, which
# enters the pod through the kubelet rather than the pod network, so a policy
# with no ingress rules leaves it working.
resource "kubernetes_network_policy_v1" "ax_server" {
  metadata {
    name      = "ax-server-from-nothing"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    pod_selector {
      match_labels = {
        "app.kubernetes.io/name" = "ax-server"
      }
    }

    policy_types = ["Ingress"]
  }
}

# --- ax-server ---------------------------------------------------------------

resource "kubernetes_deployment_v1" "ax_server" {
  metadata {
    name      = "ax-server"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = merge(local.common_labels, { "app.kubernetes.io/name" = "ax-server" })
  }

  wait_for_rollout = false

  spec {
    replicas = 1

    selector {
      match_labels = {
        "app.kubernetes.io/name" = "ax-server"
      }
    }

    template {
      metadata {
        labels = merge(local.common_labels, { "app.kubernetes.io/name" = "ax-server" })
      }

      spec {
        container {
          name  = "ax-server"
          image = ko_build.ax_server.image_ref

          args = [
            "--addr=:8080",
            "--redis-addr=${kubernetes_service_v1.redis.metadata[0].name}.${local.ax_namespace}.svc.cluster.local:6379",
          ]

          env {
            name = "REDIS_PASSWORD"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.redis.metadata[0].name
                key  = "REDIS_PASSWORD"
              }
            }
          }

          port {
            name           = "http"
            container_port = 8080
          }

          readiness_probe {
            http_get {
              path = "/healthz"
              port = "8080"
            }
            initial_delay_seconds = 2
            period_seconds        = 5
          }

          liveness_probe {
            http_get {
              path = "/healthz"
              port = "8080"
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }

          resources {
            requests = {
              cpu    = "100m"
              memory = "128Mi"
            }
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
          }
        }
      }
    }
  }
}

# ClusterIP only, like everything here: the ax CLI reaches it by port-forward
# through the IAM-guarded control plane.
resource "kubernetes_service_v1" "ax_server" {
  metadata {
    name      = "ax-server"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    type = "ClusterIP"
    selector = {
      "app.kubernetes.io/name" = "ax-server"
    }

    port {
      name        = "http"
      port        = 8080
      target_port = 8080
    }
  }
}

# --- ax-controller -----------------------------------------------------------

resource "kubernetes_service_account_v1" "ax_controller" {
  metadata {
    name      = "ax-controller"
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
    labels    = local.common_labels
  }
}

# A raw manifest (server-side applied), not kubernetes_deployment_v1: the
# controller mounts a clusterTrustBundle projection, which the typed resource's
# schema does not have.
resource "kubectl_manifest" "ax_controller" {
  server_side_apply = true
  wait_for_rollout  = false

  yaml_body = yamlencode({
    apiVersion = "apps/v1"
    kind       = "Deployment"
    metadata = {
      name      = "ax-controller"
      namespace = kubernetes_namespace_v1.ax.metadata[0].name
      labels    = merge(local.common_labels, { "app.kubernetes.io/name" = "ax-controller" })
    }
    spec = {
      replicas = 1
      selector = {
        matchLabels = { "app.kubernetes.io/name" = "ax-controller" }
      }
      template = {
        metadata = {
          labels = merge(local.common_labels, { "app.kubernetes.io/name" = "ax-controller" })
        }
        spec = {
          serviceAccountName = kubernetes_service_account_v1.ax_controller.metadata[0].name
          containers = [{
            name  = "controller"
            image = ko_build.ax_controller.image_ref

            # Upstream's arguments (deploy/ax-controller.yaml), unchanged: the
            # Substrate Control API through its in-cluster service,
            # authenticated with a projected token for that audience and
            # verified against the trust bundle Substrate's podcertificate
            # controller publishes.
            args = [
              "--redis-addr=${kubernetes_service_v1.redis.metadata[0].name}.${local.ax_namespace}.svc.cluster.local:6379",
              "--substrate-endpoint=api.${local.substrate_namespace}.svc.cluster.local:443",
              "--substrate-authority=api.${local.substrate_namespace}.svc",
              "--substrate-token-file=/var/run/secrets/ateapi/token",
              "--substrate-ca-file=/run/servicedns-ca/trust-bundle.pem",
              "--template=default-template",
              "--template-atespace=${local.ax_namespace}",
            ]

            env = [
              {
                name = "REDIS_PASSWORD"
                valueFrom = {
                  secretKeyRef = {
                    name = kubernetes_secret_v1.redis.metadata[0].name
                    key  = "REDIS_PASSWORD"
                  }
                }
              },
              # Where every task's actor snapshots go: its own prefix in the
              # one bucket atelet and ate-api-server may write (exe-platform
              # iam.tf).
              { name = "AX_SNAPSHOTS_BUCKET", value = local.ax_snapshots_location },
              { name = "ATENET_ROUTER_ADDR", value = "atenet-router.${local.substrate_namespace}.svc.cluster.local:80" },
            ]

            resources = {
              requests = { cpu = "100m", memory = "128Mi" }
              limits   = { cpu = "500m", memory = "512Mi" }
            }

            securityContext = {
              readOnlyRootFilesystem   = true
              allowPrivilegeEscalation = false
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
                    expirationSeconds = 7200
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
  })

  # The trust bundle and the Control API only exist once Substrate is
  # installed; a controller started earlier crash-loops until then.
  depends_on = [terraform_data.ate_system]
}
