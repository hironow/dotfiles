# Who may reach Substrate's Control API (plan F5; W2 finding 7).
#
# L1's drain barrier (plan D2) holds only if nothing but the components it
# stops can resume an actor. The Control API authenticates its callers (a
# Kubernetes SA token for audience api.ate-system.svc, or a pod-identity
# client certificate) but does not authorize them (plan F1), so any caller
# with a credential can resume anything. W2 found that a task CAN reach it:
# from inside an actor, api.ate-system.svc resolves and answers a TLS
# handshake. Authentication then stands alone between a task and a resume.
#
# This policy adds the network back. The API's pod port admits only the pods
# that call it, from the pinned sources:
#   - ate-system, the API's own namespace: atelet (substrate
#     cmd/atelet/main.go:328), the ate-controller (cmd/atecontroller/main.go:
#     160), and the atenet router and egress (cmd/atenet/internal/router/
#     router.go:183);
#   - ax-system's ax-controller (ax internal/substrate/client.go:147; the
#     ax-server makes no Substrate call);
#   - exe-ops: L1 (exe-reap) and the snapshot GC.
# No worker component dials the API (no Control or WorkerService client in
# cmd/ateom-gvisor), so the atespace's worker pods, and the actors inside
# them, get no rule. The operator's install and `kubectl ate` come through a
# port-forward, which reaches the pod from its own node, not over the pod
# network. The metrics and probe port stays open, as it was.
#
# tests/control_api.tofutest.hcl pins every peer and port.
resource "kubernetes_network_policy_v1" "control_api" {
  metadata {
    name      = "ate-api-server-from-its-callers"
    namespace = local.substrate_namespace
    labels    = local.common_labels
  }

  spec {
    pod_selector {
      match_labels = {
        app = "ate-api-server"
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
      }
      from {
        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = kubernetes_namespace_v1.ax.metadata[0].name
          }
        }
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = "ax-controller"
          }
        }
      }
      from {
        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = kubernetes_namespace_v1.ops.metadata[0].name
          }
        }
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = local.reaper_app
          }
        }
      }
      from {
        namespace_selector {
          match_labels = {
            "kubernetes.io/metadata.name" = kubernetes_namespace_v1.ops.metadata[0].name
          }
        }
        pod_selector {
          match_labels = {
            "app.kubernetes.io/name" = local.snapshot_gc_app
          }
        }
      }

      ports {
        protocol = "TCP"
        port     = "443"
      }
    }

    ingress {
      ports {
        protocol = "TCP"
        port     = "9090"
      }
    }
  }

  # The API's pods exist once Substrate is installed.
  depends_on = [terraform_data.ate_system]
}
