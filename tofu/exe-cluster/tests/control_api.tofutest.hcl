# What this file pins: who may reach Substrate's Control API (plan F5; W2
# finding 7; manager-loop/reports/f5-control-api-audit.md).
#
# The Control API authenticates its callers but does not authorize them (plan
# F1), so this policy is the only authorization there is. It admits the API's
# pod port only from the pods the pinned sources show calling it:
#   - ate-system: atelet, the ate-controller, the atenet router and the atenet
#     egress's ext-proc sidecar;
#   - ax-system: the ax-controller;
#   - exe-ops: L1 (exe-reap) and the snapshot GC.
# The atespace's worker pods are not on the list: no worker component dials
# the API, and a worker pod holds a certificate the API would accept. An
# actor's own traffic leaves through atenet-egress, which is on the list, so
# for that path authentication is the barrier (tests/e2e/exe/
# test_control_api_barrier.py). The metrics and probe port stays open.
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
    condition     = kubernetes_network_policy_v1.control_api.metadata[0].name == "ate-api-server-ingress" && kubernetes_network_policy_v1.control_api.metadata[0].namespace == "ate-system" && kubernetes_network_policy_v1.control_api.spec[0].pod_selector[0].match_labels["app"] == "ate-api-server" && kubernetes_network_policy_v1.control_api.spec[0].policy_types == tolist(["Ingress"])
    error_message = "the policy must be ate-system/ate-api-server-ingress, selecting the ate-api-server pods, for ingress."
  }

  assert {
    condition     = length(kubernetes_network_policy_v1.control_api.spec[0].ingress) == 2
    error_message = "exactly two rules: the metrics and probe port for anyone, and the API port for its callers."
  }

  assert {
    condition     = [for p in kubernetes_network_policy_v1.control_api.spec[0].ingress[0].ports : "${p.port}/${p.protocol}"] == ["9090/TCP"] && length(kubernetes_network_policy_v1.control_api.spec[0].ingress[0].from) == 0
    error_message = "the first rule must leave the metrics and probe port, 9090/TCP, open as it was, and nothing else."
  }

  assert {
    condition     = [for p in kubernetes_network_policy_v1.control_api.spec[0].ingress[1].ports : "${p.port}/${p.protocol}"] == ["443/TCP"]
    error_message = "the second rule must cover the API's pod port, 443/TCP, and nothing else."
  }

  assert {
    condition = toset([
      for f in kubernetes_network_policy_v1.control_api.spec[0].ingress[1].from :
      format("%s:%s %s %s",
        f.namespace_selector[0].match_labels["kubernetes.io/metadata.name"],
        f.pod_selector[0].match_expressions[0].key,
        f.pod_selector[0].match_expressions[0].operator,
        join(",", sort(f.pod_selector[0].match_expressions[0].values)),
      )
      ]) == toset([
      "ate-system:app In ate-controller,atelet,atenet-egress,atenet-router",
      "ax-system:app.kubernetes.io/name In ax-controller",
      "exe-ops:app.kubernetes.io/name In exe-reap,exe-snapshot-gc",
    ])
    error_message = "the API port must admit exactly the audited callers (manager-loop/reports/f5-control-api-audit.md): atelet, the ate-controller, the atenet router and egress; ax-system's ax-controller; exe-ops' exe-reap and exe-snapshot-gc. Nothing in the atespace, where the worker pods run."
  }
}
