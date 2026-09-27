# The atespace tasks run in ("exe"), its namespace, and the workers.
#
# AX puts a task in Substrate atespace `metadata.atespace` and looks its Gemini
# key up in the Kubernetes namespace of the same name, so the two carry one
# name. Tasks name this atespace in their YAML (`atespace: exe`).

resource "kubernetes_namespace_v1" "atespace" {
  metadata {
    name   = local.atespace
    labels = local.common_labels
  }
}

# --- the Gemini key (plan Q5): gated until the operator supplies one ----------
#
# AX reads Secret gemini-api-secret, key GEMINI_API_KEY, from the task's
# atespace namespace and hands it to the task. Nothing in the spike (S1-S3)
# needs it, so the Secret exists only once gemini_api_key is set in the
# gitignored tfvars.
resource "kubernetes_secret_v1" "gemini" {
  count = var.gemini_api_key == null ? 0 : 1

  metadata {
    name      = "gemini-api-secret"
    namespace = kubernetes_namespace_v1.atespace.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    GEMINI_API_KEY = var.gemini_api_key
  }
}

# ax-controller reads exactly that one Secret, in exactly this namespace.
# Upstream grants it get/list/watch on every Secret in the cluster; the lookup
# is a single GET by name (internal/model/client.go), so this is all it needs.
resource "kubernetes_role_v1" "ax_controller_gemini" {
  metadata {
    name      = "ax-controller-gemini"
    namespace = kubernetes_namespace_v1.atespace.metadata[0].name
    labels    = local.common_labels
  }

  rule {
    api_groups     = [""]
    resources      = ["secrets"]
    resource_names = ["gemini-api-secret"]
    verbs          = ["get"]
  }
}

resource "kubernetes_role_binding_v1" "ax_controller_gemini" {
  metadata {
    name      = "ax-controller-gemini"
    namespace = kubernetes_namespace_v1.atespace.metadata[0].name
    labels    = local.common_labels
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.ax_controller_gemini.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.ax_controller.metadata[0].name
    namespace = kubernetes_namespace_v1.ax.metadata[0].name
  }
}

# --- the WorkerPool ------------------------------------------------------------
#
# Two gVisor workers on the version-labelled node, running the worker image
# `just exe-worker-images` printed. Absent until that image is recorded.
#
# CHANGING THIS POOL KILLS AWAKE ACTORS. On Substrate v0.1.0 an actor whose
# worker pod goes away is CRASHED within about a minute unless it was suspended
# first, and editing a serving pool replaces its pods. So a change is guarded:
# the guard below re-runs whenever the pool's manifest changes, before the
# pool is applied, and fails the apply while any task in the atespace is
# Running. The way to change a pool that is in use is to suspend every task
# first (the runbook's "new pool, then switch" procedure is Phase 8's).

locals {
  worker_pool_enabled = var.ateom_gvisor_image != ""

  worker_pool = {
    apiVersion = "ate.dev/v1alpha1"
    kind       = "WorkerPool"
    metadata = {
      name      = local.worker_pool_name
      namespace = local.atespace
      labels    = local.common_labels
    }
    spec = {
      replicas     = local.worker_pool_replicas
      sandboxClass = "gvisor"
      workerImage  = var.ateom_gvisor_image
      template = {
        # Only the node the Substrate install labelled with this exact version:
        # a pool on an unlabelled or older node would host workers nothing
        # serves.
        nodeSelector = {
          (local.pins.substrate.version_label_key) = local.pins.substrate.version_label_value
        }
        resources = local.worker_resources
      }
    }
  }
}

resource "terraform_data" "worker_pool_guard" {
  count = local.worker_pool_enabled ? 1 : 0

  triggers_replace = {
    pool   = sha256(jsonencode(local.worker_pool))
    script = sha256(local.worker_pool_guard_script)
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = local.worker_pool_guard_script
    environment = local.worker_pool_guard_env
  }
}

locals {
  worker_pool_guard_script = <<-EOT
      set -euo pipefail
      work="$(mktemp -d)"
      export KUBECONFIG="$work/kubeconfig" AX_HOME="$work/ax"
      trap 'ax tunnel stop >/dev/null 2>&1 || true; rm -rf "$work"' EXIT
      gcloud container clusters get-credentials "$CLUSTER_NAME" \
        --zone "$CLUSTER_LOCATION" --project "$PROJECT_ID" --dns-endpoint >/dev/null 2>&1
      if ! kubectl -n "$ATESPACE" get workerpools.ate.dev "$POOL" >/dev/null 2>&1; then
        echo "worker pool guard: $POOL does not exist yet, so no actor can be on it"
        exit 0
      fi
      if [ "$(kubectl get nodes -o name | wc -l | tr -d ' ')" = "0" ]; then
        echo "worker pool guard: the pool is asleep, so no actor is awake"
        exit 0
      fi
      running="$(ax get tasks -a "$ATESPACE" | awk 'NR > 1 && $3 == "Running"' | wc -l | tr -d ' ')"
      if [ "$running" != "0" ]; then
        echo "worker pool guard: $running task(s) Running in atespace $ATESPACE." >&2
        echo "Changing $POOL now would CRASH them. Suspend every task (ax suspend task <name>) and apply again." >&2
        exit 1
      fi
      echo "worker pool guard: no task Running in atespace $ATESPACE"
  EOT

  worker_pool_guard_env = {
    PROJECT_ID       = var.gcp_project_id
    CLUSTER_NAME     = local.platform.cluster_name
    CLUSTER_LOCATION = local.platform.zone
    ATESPACE         = local.atespace
    POOL             = local.worker_pool_name
  }
}

resource "kubectl_manifest" "worker_pool" {
  count = local.worker_pool_enabled ? 1 : 0

  server_side_apply = true
  yaml_body         = yamlencode(local.worker_pool)

  depends_on = [
    kubernetes_namespace_v1.atespace,
    # The CRD comes with the Substrate install.
    terraform_data.ate_system,
    terraform_data.worker_pool_guard,
  ]
}
