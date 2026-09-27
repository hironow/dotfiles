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

data "google_client_config" "current" {}

provider "google" {
  project = var.gcp_project_id
  region  = local.platform.region
}

# The control plane is reachable only through its IAM-guarded DNS endpoint
# (exe-platform has no IP endpoint at all). The endpoint presents a publicly
# trusted certificate, so there is no CA to pin, and every request carries the
# operator's own Google access token: there is no kubeconfig and no client
# certificate anywhere in this stack.
provider "kubernetes" {
  host  = "https://${local.platform.cluster_dns_endpoint}"
  token = data.google_client_config.current.access_token
}

provider "kubectl" {
  host             = "https://${local.platform.cluster_dns_endpoint}"
  token            = data.google_client_config.current.access_token
  load_config_file = false
}

# AX's images build into the platform registry, next to exe-reaper's and
# Substrate's; its cleanup policy bounds how many versions stay.
provider "ko" {
  repo = "${local.platform.ar_platform_repo}/ax"
}
