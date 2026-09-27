# Agent Substrate, installed by upstream's own installer at the pinned commit.
#
# Section 3.1's ownership rule: Substrate's own objects (ate-system, its CRDs,
# the CA and JWT Secrets it generates, its images) belong to `ate-setup deploy
# ate-system`, which this stack calls rather than re-implements. What this file
# owns is everything AROUND the installer: the store's DSN Secret it reads, the
# gVisor asset it points workers at, and the exact inputs it is run with.
#
# The installer runs from a terraform_data step during apply, in BUILD mode:
# ko builds every control-plane image from the pinned checkout and pushes it to
# the exe-platform registry (KO_DOCKER_REPO), VERSION fixes the node label to
# the pin, and ATE_API_POSTGRES_CONNECTION_STRING being set makes it skip its
# bundled store. It then waits for its workloads to roll out -- which is why an
# apply that re-runs it needs a node up under a lease (`just exe-wake`). It
# re-runs only when one of its inputs (triggers_replace) changes, and it is
# idempotent when it does (server-side apply; its generated Secrets are
# create-if-absent).
#
# Two files of the pinned checkout are replaced in a scratch copy before it
# runs, and both are pinned by tests:
#   - atenet-router-monitoring.yaml is REMOVED. It is a PodMonitoring (Google
#     Managed Prometheus), a kind this cluster does not serve because GMP is off
#     (exe-platform gke.tf), and the installer applies that directory strictly:
#     one unknown kind fails the whole install.
#   - sandboxconfig-gvisor.yaml is REPLACED by ours (locals.tf): the gVisor
#     asset from our own mirror instead of upstream's nightly path, and the
#     in-project GKE pause image. The installer stays the single writer of that
#     object; it just writes our content.

# Created here, not by the installer, because the Secret below has to exist in
# it before ate-api-server first starts. The installer's own apply of the
# namespace is server-side and co-owns it without conflict; the labels it may
# add are its business, hence ignore_changes.
resource "kubernetes_namespace_v1" "ate_system" {
  metadata {
    name = local.substrate_namespace
  }

  lifecycle {
    ignore_changes = [metadata[0].labels, metadata[0].annotations]
  }
}

# The store's DSN, password included. ate-api-server reads this Secret after the
# installer's ConfigMap and lets it win (ate-api-server.yaml at the pinned
# commit), so the ConfigMap only ever carries the password-less form the
# installer was given.
resource "kubernetes_secret_v1" "ate_api_server_env" {
  metadata {
    name      = "ate-api-server-secret-envvars"
    namespace = kubernetes_namespace_v1.ate_system.metadata[0].name
    labels    = local.common_labels
  }

  data = {
    ATE_API_POSTGRES_CONNECTION_STRING = local.postgres_dsn
  }
}

# The gVisor asset, copied into our own bucket and verified by sha256 on both
# ends: upstream's copy is a nightly path that can disappear, and a resumed
# actor needs this exact tarball. atelet verifies the sha256 again on every
# download, so a wrong object fails closed.
resource "terraform_data" "gvisor_mirror" {
  triggers_replace = {
    source = local.gvisor_upstream_url
    mirror = local.gvisor_mirror_url
    sha256 = local.gvisor_amd64_sha256
    script = sha256(local.gvisor_mirror_script)
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = local.gvisor_mirror_script
    environment = local.gvisor_mirror_env
  }
}

resource "terraform_data" "ate_system" {
  # Everything the install depends on. A change to any of them re-runs it.
  triggers_replace = {
    substrate_sha     = local.pins.substrate.sha
    substrate_version = local.pins.substrate.version_label_value
    ko_repo           = local.substrate_ko_repo
    sandbox_config    = sha256(local.sandbox_config_yaml)
    postgres_dsn_base = local.postgres_dsn_base
    script            = sha256(local.ate_setup_script)
  }

  provisioner "local-exec" {
    interpreter = ["bash", "-c"]
    command     = local.ate_setup_script
    environment = local.ate_setup_env
  }

  depends_on = [
    kubernetes_secret_v1.ate_api_server_env,
    kubernetes_stateful_set_v1.postgres,
    kubernetes_network_policy_v1.postgres,
    terraform_data.gvisor_mirror,
  ]
}

# The two install steps' scripts and inputs, as values the tests can pin.
locals {
  gvisor_mirror_script = <<-EOT
      set -euo pipefail
      verify() {
        local got
        got="$(gcloud storage cat "$1" | shasum -a 256 | cut -d' ' -f1)"
        if [ "$got" != "$GVISOR_SHA256" ]; then
          echo "gvisor mirror: sha256 of $1 is $got, want $GVISOR_SHA256" >&2
          return 1
        fi
      }
      if gcloud storage objects describe "$GVISOR_MIRROR" >/dev/null 2>&1 && verify "$GVISOR_MIRROR"; then
        echo "gvisor mirror: already present and verified"
        exit 0
      fi
      verify "$GVISOR_SOURCE"
      gcloud storage cp "$GVISOR_SOURCE" "$GVISOR_MIRROR"
      verify "$GVISOR_MIRROR"
      echo "gvisor mirror: copied and verified"
  EOT

  gvisor_mirror_env = {
    GVISOR_SOURCE = local.gvisor_upstream_url
    GVISOR_MIRROR = local.gvisor_mirror_url
    GVISOR_SHA256 = local.gvisor_amd64_sha256
  }

  ate_setup_script = <<-EOT
      set -euo pipefail
      work="$(mktemp -d)"
      trap 'rm -rf "$work"' EXIT

      # The checkout must be the pinned commit; `just exe-cluster-src` fetches it.
      head="$(git -C "$SUBSTRATE_SRC" rev-parse HEAD)"
      if [ "$head" != "$SUBSTRATE_SHA" ]; then
        echo "ate-setup: $SUBSTRATE_SRC is at $head, want $SUBSTRATE_SHA (run: just exe-cluster-src)" >&2
        exit 1
      fi

      # A kubeconfig of its own, through the DNS endpoint (there is no other).
      export KUBECONFIG="$work/kubeconfig"
      gcloud container clusters get-credentials "$CLUSTER_NAME" \
        --zone "$CLUSTER_LOCATION" --project "$PROJECT_ID" --dns-endpoint
      context="$(kubectl config current-context)"

      echo "ate-setup: waiting for the store"
      kubectl --context "$context" -n "$STORE_NAMESPACE" rollout status statefulset/postgres --timeout=5m

      # A scratch copy with the two replaced files (see the header).
      rsync -a --exclude .git "$SUBSTRATE_SRC/" "$work/substrate/"
      rm "$work/substrate/manifests/ate-install/atenet-router-monitoring.yaml"
      printf '%s' "$SANDBOX_CONFIG_YAML" > "$work/substrate/manifests/ate-install/sandboxconfig-gvisor.yaml"

      cd "$work/substrate"
      echo "ate-setup: deploy ate-system $VERSION (build mode)"
      go run ./cmd/ate-setup --kubeconfig "$KUBECONFIG" --context "$context" \
        --no-dev-env --rollout-timeout 5m deploy ate-system

      # Upstream's ate-api-server budget (maxUnavailable 1) cannot keep an API
      # server up on one node that every stop removes: the evicted pod's
      # replacement cannot schedule on the cordoned node, the budget reads zero,
      # and the drain waits on the other pod for up to GKE's one-hour PDB limit
      # while the node bills. Let it allow a full stop. The installer rewrites
      # the budget only when this step runs again, and this line runs after it.
      kubectl --context "$context" -n ate-system patch poddisruptionbudget ate-api-server \
        --type=merge -p '{"spec":{"maxUnavailable":"100%"}}'
  EOT

  ate_setup_env = {
    SUBSTRATE_SRC       = local.substrate_src
    SUBSTRATE_SHA       = local.pins.substrate.sha
    VERSION             = local.pins.substrate.version_label_value
    KO_DOCKER_REPO      = local.substrate_ko_repo
    KO_DEFAULTPLATFORMS = "linux/amd64"
    NO_DEV_ENV          = "1"
    PROJECT_ID          = var.gcp_project_id
    CLUSTER_NAME        = local.platform.cluster_name
    CLUSTER_LOCATION    = local.platform.zone
    STORE_NAMESPACE     = local.store_namespace
    SANDBOX_CONFIG_YAML = local.sandbox_config_yaml
    # Password-less on purpose: the installer writes this into a ConfigMap.
    # The real DSN is the Secret above, which wins.
    ATE_API_POSTGRES_CONNECTION_STRING = local.postgres_dsn_base
  }
}
