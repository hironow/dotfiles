# What this file pins: nothing in this stack is reachable from outside the
# cluster. Every Service is ClusterIP; the ax CLI and ate-setup reach the
# cluster through the IAM-guarded control plane only.

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

run "every_service_is_cluster_internal" {
  command = plan

  assert {
    condition     = alltrue([for s in [kubernetes_service_v1.postgres, kubernetes_service_v1.redis, kubernetes_service_v1.ax_server] : s.spec[0].type == "ClusterIP"])
    error_message = "every Service must be ClusterIP: no LoadBalancer and no NodePort, ever (plan section 1, public surface zero)."
  }
}
