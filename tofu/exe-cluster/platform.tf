# What this stack needs from tofu/exe-platform, read from its state rather than
# retyped: the cluster's DNS endpoint, the snapshot bucket, the platform
# registry. A second copy of a name here is a name that can drift from the
# resource it names, and most of these embed the private project id anyway.
#
# The state bucket follows the one naming rule the bootstrap script uses
# (scripts/exe_platform_bootstrap.sh): <project>-exe-tofu-state.

data "terraform_remote_state" "platform" {
  backend = "gcs"

  config = {
    bucket = "${var.gcp_project_id}-exe-tofu-state"
    prefix = "exe-platform"
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = local.platform.region
}

# The control plane is reachable only through its IAM-guarded DNS endpoint
# (exe-platform has no IP endpoint at all). The endpoint presents a publicly
# trusted certificate, so there is no CA to pin, and every request carries the
# operator's own Google access token: there is no kubeconfig and no client
# certificate anywhere in this stack.
#
# The token is minted when the provider talks to the cluster, by
# gke-gcloud-auth-plugin (the same plugin `gcloud container clusters
# get-credentials` configures), never read at plan time: a saved plan carries
# every data source's values, and a planned access token dies after an hour --
# a later apply then fails half-way on "provide credentials" (2026-09-27).
provider "kubernetes" {
  host = "https://${local.platform.cluster_dns_endpoint}"

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "gke-gcloud-auth-plugin"
  }
}

provider "kubectl" {
  host             = "https://${local.platform.cluster_dns_endpoint}"
  load_config_file = false

  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "gke-gcloud-auth-plugin"
  }
}

# AX's images build into the platform registry, next to exe-reaper's and
# Substrate's; its cleanup policy bounds how many versions stay.
provider "ko" {
  repo = "${local.platform.ar_platform_repo}/ax"
}
