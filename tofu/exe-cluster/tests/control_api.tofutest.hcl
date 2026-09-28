# What this file pins: who may reach Substrate's Control API (plan F5; W2
# finding 7).
#
# L1's drain barrier (plan D2) assumes a task cannot resume actors by calling
# the Control API itself. W2 showed the network half of that assumption false:
# from inside a task, api.ate-system.svc resolves and answers. This policy
# admits the API's port only from the pods that call it, found in the pinned
# Substrate and AX sources:
#   - ate-system, the API's own namespace: atelet (cmd/atelet/main.go:328),
#     the ate-controller (cmd/atecontroller/main.go:160) and the atenet router
#     and egress (cmd/atenet/internal/router/router.go:183);
#   - ax-system's ax-controller (ax internal/substrate/client.go:147);
#   - exe-ops: L1 (exe-reap) and the snapshot GC.
# The worker pods in the atespace, and so the actors inside them, are not on
# the list: no worker component dials the API. The metrics and probe port
# stays open, as before.
#
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
      ar_task_repository   = "projects/zz-synthetic-project/locations/asia-northeast1/repositories/exe-task"
      ar_platform_repo     = "asia-northeast1-docker.pkg.dev/zz-synthetic-project/exe-platform"
      workload_identity_principals = {
        atelet      = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/ate-system/sa/atelet"
        api_server  = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/ate-system/sa/ate-api-server"
        reaper      = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/exe-ops/sa/exe-reaper"
        snapshot_gc = "principal://iam.googleapis.com/projects/000000000000/locations/global/workloadIdentityPools/zz-synthetic-project.svc.id.goog/subject/ns/exe-ops/sa/exe-snapshot-gc"
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

run "the_api_admits_only_its_callers" {
  command = plan

  assert {
    condition     = kubernetes_network_policy_v1.control_api.metadata[0].namespace == "ate-system" && kubernetes_network_policy_v1.control_api.spec[0].pod_selector[0].match_labels["app"] == "ate-api-server" && kubernetes_network_policy_v1.control_api.spec[0].policy_types == tolist(["Ingress"])
    error_message = "the policy must select the ate-api-server pods in ate-system, for ingress."
  }

  assert {
    condition     = length(kubernetes_network_policy_v1.control_api.spec[0].ingress) == 2
    error_message = "exactly two rules: the API port for its callers, and the metrics and probe port."
  }

  assert {
    condition     = [for p in kubernetes_network_policy_v1.control_api.spec[0].ingress[0].ports : "${p.port}/${p.protocol}"] == ["443/TCP"]
    error_message = "the first rule must cover the API's pod port, 443/TCP, and nothing else."
  }

  assert {
    condition = toset([
      for f in kubernetes_network_policy_v1.control_api.spec[0].ingress[0].from :
      "${f.namespace_selector[0].match_labels["kubernetes.io/metadata.name"]}/${length(f.pod_selector) == 0 ? "*" : f.pod_selector[0].match_labels["app.kubernetes.io/name"]}"
    ]) == toset(["ate-system/*", "ax-system/ax-controller", "exe-ops/exe-reap", "exe-ops/exe-snapshot-gc"])
    error_message = "the API port must admit exactly its callers: all of ate-system, ax-system's ax-controller, and exe-ops' exe-reap and exe-snapshot-gc. The atespace's worker pods, where the actors run, must not be on the list."
  }

  assert {
    condition     = [for p in kubernetes_network_policy_v1.control_api.spec[0].ingress[1].ports : "${p.port}/${p.protocol}"] == ["9090/TCP"] && length(kubernetes_network_policy_v1.control_api.spec[0].ingress[1].from) == 0
    error_message = "the second rule must leave the metrics and probe port, 9090/TCP, open as it was, and nothing else."
  }
}
