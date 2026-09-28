# Who may reach Substrate's Control API (plan F5; W2 finding 7; the audit in
# manager-loop/reports/f5-control-api-audit.md).
#
# L1's drain barrier (plan D2) holds only if nothing but the components it
# stops can resume an actor. The Control API authenticates its callers (a
# Kubernetes SA token for audience api.ate-system.svc, or a podidentity client
# certificate) but does not authorize them (plan F1): any caller with a
# credential controls everything. This policy is the only authorization there
# is. It admits the API's pod port only from the pods that call it, according
# to the pinned sources:
#   - ate-system: atelet, the ate-controller, the atenet router and the atenet
#     egress's ext-proc sidecar;
#   - ax-system: the ax-controller (the ax-server makes no Substrate call);
#   - exe-ops: L1 (exe-reap) and the snapshot GC.
#
# It closes the worker POD's own path. A worker pod holds a podidentity
# certificate the API accepts, so dialing the API from the pod is how a
# sandbox escape would reach the control plane. No worker component needs the
# API: capacity reports and actor certificates go to the node's atelet over a
# unix socket.
#
# It cannot close the actor's own path, and does not try. With tunneled egress
# armed (ate-api-server's --egress-gateway-address), an actor's TCP leaves
# through atenet-egress, which has to stay admitted. What stands there is
# authentication: the guest holds no credential the API accepts. The F5 e2e
# (tests/e2e/exe/test_control_api_barrier.py) is that path's regression guard.
#
# The operator's install and `kubectl ate` come through a pod port-forward,
# which this policy neither blocks nor protects. The metrics and probe port
# stays open.
#
# tests/control_api.tofutest.hcl pins every peer and port.
# tests/unit/test_exe_control_api_policy.py checks the admitted labels
# against the manifests that set them.

locals {
  # Namespace => the pod label key, and the values the API admits under it.
  control_api_callers = {
    (local.substrate_namespace) = {
      key    = "app"
      values = ["atelet", "ate-controller", "atenet-router", "atenet-egress"]
    }
    (kubernetes_namespace_v1.ax.metadata[0].name) = {
      key    = "app.kubernetes.io/name"
      values = ["ax-controller"]
    }
    (kubernetes_namespace_v1.ops.metadata[0].name) = {
      key    = "app.kubernetes.io/name"
      values = [local.reaper_app, local.snapshot_gc_app]
    }
  }
}

resource "kubernetes_network_policy_v1" "control_api" {
  metadata {
    name      = "ate-api-server-ingress"
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

    # Metrics and all three probes, from anywhere, as before.
    ingress {
      ports {
        protocol = "TCP"
        port     = "9090"
      }
    }

    ingress {
      dynamic "from" {
        for_each = local.control_api_callers

        content {
          namespace_selector {
            match_labels = {
              "kubernetes.io/metadata.name" = from.key
            }
          }
          pod_selector {
            match_expressions {
              key      = from.value.key
              operator = "In"
              values   = from.value.values
            }
          }
        }
      }

      ports {
        protocol = "TCP"
        port     = "443"
      }
    }
  }

  # The API's pods exist once Substrate is installed.
  depends_on = [terraform_data.ate_system]
}
