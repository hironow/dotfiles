# What this file pins: AX's images and Redis.
#
# Upstream deploys AX with `ko apply` over a `:latest` base and a Redis with no
# persistence and no password. Here the images are built from the pinned
# checkout over a digest-pinned base, and Redis keeps an append-only log on a
# PD, demands a password, and answers only the two AX pods.

# command = plan + mock providers: offline, no credentials, nothing created. The
# platform's outputs are synthetic stand-ins for exe-platform's state.

mock_provider "google" {}
mock_provider "kubernetes" {}
mock_provider "kubectl" {}
mock_provider "random" {}

mock_provider "ko" {
  mock_resource "ko_build" {
    defaults = {
      image_ref = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform/ax/built@sha256:1111111111111111111111111111111111111111111111111111111111111111"
    }
  }
}

override_data {
  target = data.terraform_remote_state.platform
  values = {
    outputs = {
      region               = "asia-northeast1"
      zone                 = "asia-northeast1-a"
      cluster_name         = "exe"
      cluster_dns_endpoint = "gke-zz.asia-northeast1.gke.goog"
      bucket_snapshots     = "zz-synthetic-project-exe-snapshots"
      bucket_ops           = "zz-synthetic-project-exe-ops"
      ar_platform_repo     = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform"
      workload_identity_principals = {
        atelet     = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/ate-system/sa/atelet"
        api_server = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/ate-system/sa/ate-api-server"
        reaper     = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/exe-ops/sa/exe-reaper"
      }
    }
  }
}

variables {
  gcp_project_id     = "zz-synthetic-project"
  gcp_project_number = "000000000000"
  state_kms_key      = "projects/zz-synthetic-project/locations/asia-northeast1/keyRings/exe-state/cryptoKeys/exe-cluster-state"
  exe_src_dir        = "/zz/src"

  # Stated, not left to the defaults: `tofu test` also loads the operator's
  # gitignored terraform.tfvars, which sets both once they exist.
  ateom_gvisor_image = ""
  gemini_api_key     = null
}

run "ax_images_build_from_the_pinned_checkout_over_a_digest_pinned_base" {
  command = plan

  assert {
    condition     = ko_build.ax_server.importpath == "github.com/google/ax/cmd/ax-server" && ko_build.ax_controller.importpath == "github.com/google/ax/cmd/ax-controller"
    error_message = "ax-server and ax-controller must be built from their upstream import paths (upstream's .ko.yaml has no entry for ax-server; this stack states both)."
  }

  assert {
    condition     = ko_build.ax_server.working_dir == "/zz/src/ax" && ko_build.ax_controller.working_dir == "/zz/src/ax"
    error_message = "AX must build from the pinned checkout under exe_src_dir (`just exe-cluster-src` fetches and verifies it)."
  }

  assert {
    condition     = can(regex("@sha256:[0-9a-f]{64}$", ko_build.ax_server.base_image)) && ko_build.ax_server.base_image == ko_build.ax_controller.base_image
    error_message = "AX's base image must be pinned by digest: upstream's defaultBaseImage is cgr.dev/chainguard/static:latest, which moves under every rebuild."
  }

  assert {
    condition     = ko_build.ax_server.platforms == tolist(["linux/amd64"]) && ko_build.ax_controller.platforms == tolist(["linux/amd64"])
    error_message = "AX builds for linux/amd64 only, the node's architecture."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.ax_controller.yaml_body).spec.template.spec.containers[0].image == ko_build.ax_controller.image_ref && kubernetes_deployment_v1.ax_server.spec[0].template[0].spec[0].container[0].image == ko_build.ax_server.image_ref
    error_message = "the Deployments must run exactly the digests ko_build pushed."
  }
}

run "the_controller_snapshots_into_its_prefix_and_trusts_substrates_bundle" {
  command = plan

  assert {
    condition     = contains([for e in yamldecode(kubectl_manifest.ax_controller.yaml_body).spec.template.spec.containers[0].env : lookup(e, "value", "") if e.name == "AX_SNAPSHOTS_BUCKET"], "gs://zz-synthetic-project-exe-snapshots/ax/")
    error_message = "AX_SNAPSHOTS_BUCKET must be the ax/ prefix of the snapshot bucket: upstream's manifest hardcodes someone else's bucket, and atelet may only write this one."
  }

  assert {
    condition     = length([for v in yamldecode(kubectl_manifest.ax_controller.yaml_body).spec.template.spec.volumes : v if try(v.projected.sources[0].clusterTrustBundle.signerName, "") == "servicedns.podcert.ate.dev/identity"]) == 1
    error_message = "the controller must verify the Substrate Control API against the servicedns trust bundle Substrate publishes."
  }

  assert {
    condition     = length([for v in yamldecode(kubectl_manifest.ax_controller.yaml_body).spec.template.spec.volumes : v if try(v.projected.sources[0].serviceAccountToken.audience, "") == "api.ate-system.svc"]) == 1
    error_message = "the controller must present a projected token for the audience the Control API accepts (api.ate-system.svc)."
  }
}

run "redis_persists_demands_a_password_and_answers_only_ax" {
  command = plan

  assert {
    condition     = contains(kubernetes_stateful_set_v1.redis.spec[0].template[0].spec[0].container[0].args, "--appendonly") && contains(kubernetes_stateful_set_v1.redis.spec[0].template[0].spec[0].container[0].args, "yes")
    error_message = "Redis must run with the append-only file on: it holds every task record, and upstream's in-memory Redis loses them all on a restart."
  }

  assert {
    condition     = contains(kubernetes_stateful_set_v1.redis.spec[0].template[0].spec[0].container[0].args, "--requirepass") && contains(kubernetes_stateful_set_v1.redis.spec[0].template[0].spec[0].container[0].args, "$(REDIS_PASSWORD)")
    error_message = "Redis must demand a password, and the password must arrive through the environment ($(REDIS_PASSWORD)), never as a literal in the args."
  }

  assert {
    condition     = kubernetes_secret_v1.redis.data.REDIS_PASSWORD == random_password.redis.result
    error_message = "the Redis password must be generated here, so it lives only in encrypted state and the Secret."
  }

  assert {
    condition     = kubernetes_stateful_set_v1.redis.spec[0].volume_claim_template[0].spec[0].storage_class_name == "standard" && kubernetes_stateful_set_v1.redis.spec[0].volume_claim_template[0].spec[0].resources[0].requests.storage == "10Gi"
    error_message = "Redis keeps its AOF on a 10Gi pd-standard volume (GKE's standard class), the cheaper class plan Q22 chose for it."
  }

  assert {
    condition     = kubernetes_stateful_set_v1.redis.spec[0].template[0].spec[0].container[0].image == "redis:7-alpine@sha256:858f009f9709ce576febc734aa78b8f6d624b82571f9ddb6bda4377c833b3499"
    error_message = "Redis must run upstream's redis:7-alpine, pinned by digest."
  }

  assert {
    condition     = toset(kubernetes_network_policy_v1.redis.spec[0].ingress[0].from[0].pod_selector[0].match_expressions[0].values) == toset(["ax-server", "ax-controller"]) && kubernetes_network_policy_v1.redis.spec[0].ingress[0].ports[0].port == "6379"
    error_message = "only ax-server and ax-controller may reach Redis, on 6379: every actor runs task code on the same pod network."
  }
}

# S5: a task's actor runs arbitrary code on the pod network. The only client of
# ax-server is the operator's `ax` CLI, which arrives through a kubectl
# port-forward -- through the kubelet, not the pod network, so NetworkPolicy
# does not apply to it. Every pod-network connection to ax-server is refused.
run "ax_server_takes_no_connection_from_the_pod_network" {
  command = plan

  assert {
    condition     = kubernetes_network_policy_v1.ax_server.spec[0].pod_selector[0].match_labels["app.kubernetes.io/name"] == "ax-server"
    error_message = "the ax-server NetworkPolicy must select the ax-server pods."
  }

  assert {
    condition     = kubernetes_network_policy_v1.ax_server.spec[0].policy_types == tolist(["Ingress"]) && length(kubernetes_network_policy_v1.ax_server.spec[0].ingress) == 0
    error_message = "ax-server must deny every ingress from the pod network (policy type Ingress, no rules): a task could otherwise create, resume or delete tasks through the API. The ax CLI is unaffected, because its port-forward does not cross the pod network."
  }
}
