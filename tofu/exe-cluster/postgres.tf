# The Substrate store: our own Postgres, instead of the one upstream bundles.
#
# Upstream's bundled store requests 2 CPUs and claims a 500Gi volume (a cost
# trap on a single e2-standard-4), so the install is given an external DSN and
# skips it entirely. This one is sized for one small control plane: 10Gi of
# pd-standard (the GKE `standard` class). The disk bills around the clock while
# the node sleeps, and cost comes first (manager-loop inbox M20 T2): pd-balanced
# costs 2.5x as much. pd-standard's IOPS scale with size, so S7 measures that the
# store still turns Ready within 60 s (plan Q22's concern).
#
# Plain password auth over the pod network, with the NetworkPolicy below as the
# wall: only ate-api-server may connect. The password is generated here, lives
# in this stack's encrypted state and in a Secret, and nowhere else.

resource "kubernetes_namespace_v1" "store" {
  metadata {
    name   = local.store_namespace
    labels = local.common_labels
  }
}

resource "random_password" "postgres" {
  length  = 32
  special = false
}

resource "kubernetes_secret_v1" "postgres" {
  metadata {
    name      = "postgres"
    namespace = kubernetes_namespace_v1.store.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    POSTGRES_USER     = local.postgres_user
    POSTGRES_PASSWORD = random_password.postgres.result
    POSTGRES_DB       = local.postgres_db
  }
}

# Headless: it governs the StatefulSet and resolves to the one pod.
resource "kubernetes_service_v1" "postgres" {
  metadata {
    name      = "postgres"
    namespace = kubernetes_namespace_v1.store.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    type       = "ClusterIP"
    cluster_ip = "None"
    selector = {
      app = "postgres"
    }

    port {
      name        = "postgres"
      port        = 5432
      target_port = 5432
    }
  }
}

resource "kubernetes_stateful_set_v1" "postgres" {
  metadata {
    name      = "postgres"
    namespace = kubernetes_namespace_v1.store.metadata[0].name
    labels    = local.common_labels
  }

  # The pool is usually at zero, and a Kubernetes object applies without a
  # node. The Substrate install step waits for this rollout itself, with a node
  # up, before it starts anything that needs the store.
  wait_for_rollout = false

  spec {
    replicas     = 1
    service_name = kubernetes_service_v1.postgres.metadata[0].name

    selector {
      match_labels = {
        app = "postgres"
      }
    }

    template {
      metadata {
        labels = merge(local.common_labels, { app = "postgres" })
      }

      spec {
        # The image's postgres user is uid/gid 70. fsGroup makes a fresh volume
        # writable; OnRootMismatch keeps the kubelet from re-walking PGDATA on
        # every start (which would leave it group-writable, and postgres refuses
        # to run on that).
        security_context {
          fs_group               = 70
          fs_group_change_policy = "OnRootMismatch"
        }

        container {
          name  = "postgres"
          image = local.postgres_image

          env_from {
            secret_ref {
              name = kubernetes_secret_v1.postgres.metadata[0].name
            }
          }

          # A subdirectory, not the mount point: a fresh PD carries lost+found,
          # and initdb refuses a non-empty directory.
          env {
            name  = "PGDATA"
            value = "/var/lib/postgresql/data/pgdata"
          }

          port {
            name           = "postgres"
            container_port = 5432
          }

          readiness_probe {
            exec {
              command = ["pg_isready", "-U", local.postgres_user, "-d", local.postgres_db]
            }
            initial_delay_seconds = 2
            period_seconds        = 5
          }

          liveness_probe {
            exec {
              command = ["pg_isready", "-U", local.postgres_user, "-d", local.postgres_db]
            }
            initial_delay_seconds = 20
            period_seconds        = 10
          }

          resources {
            requests = {
              cpu    = "250m"
              memory = "512Mi"
            }
            limits = {
              cpu    = "1"
              memory = "1Gi"
            }
          }

          volume_mount {
            name       = "store"
            mount_path = "/var/lib/postgresql/data"
          }
        }
      }
    }

    # Named "store", not "data": the claim template's name is part of the
    # claim's (store-postgres-0), and the old name would re-bind the old
    # pd-balanced claim instead of creating a pd-standard one.
    volume_claim_template {
      metadata {
        name = "store"
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

# Only ate-api-server may reach the store. Everything else in the cluster --
# including every actor, which runs whatever a task image contains -- is
# refused at the pod network (plan section 3, S5 verifies it).
resource "kubernetes_network_policy_v1" "postgres" {
  metadata {
    name      = "postgres-from-ate-api-server-only"
    namespace = kubernetes_namespace_v1.store.metadata[0].name
    labels    = local.common_labels
  }

  spec {
    pod_selector {
      match_labels = {
        app = "postgres"
      }
    }

    policy_types = ["Ingress"]

    ingress {
      from {
        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = local.substrate_namespace
          }
        }
        pod_selector {
          match_labels = {
            app = "ate-api-server"
          }
        }
      }

      ports {
        protocol = "TCP"
        port     = "5432"
      }
    }
  }
}
