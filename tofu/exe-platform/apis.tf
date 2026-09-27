# Service (API) enablement.
#
# The project starts with most APIs off, so the set this stack needs is
# enumerated here and pinned by a test — an API enabled by hand is drift the
# next apply cannot see, and an API missing at apply time surfaces as an opaque
# 403 several resources later.
#
# disable_on_destroy = false is NOT laziness. The project is shared with two
# unrelated OpenTofu stacks; disabling compute or storage while tearing this
# stack down would break them. Enablement is close to idempotent and costs
# nothing when unused, so the safe asymmetry is: enable here, never disable.

locals {
  # Each entry says who needs it, because "why is this on?" is the question
  # asked a year later when someone wants to trim the list.
  project_services = {
    "cloudresourcemanager.googleapis.com" = "IAM bindings and project metadata reads"
    "serviceusage.googleapis.com"         = "enabling the rest of this list"
    "iam.googleapis.com"                  = "dedicated service accounts and the custom resizer role"
    "iamcredentials.googleapis.com"       = "short-lived token minting (Scheduler OAuth, impersonation)"
    "sts.googleapis.com"                  = "Workload Identity token exchange"
    "compute.googleapis.com"              = "VPC, subnet, Cloud Router, Cloud NAT, node VMs"
    "container.googleapis.com"            = "the GKE cluster, and the L3 nodePools.setSize call"
    "networkconnectivity.googleapis.com"  = "Private Service Connect plumbing behind a private cluster"
    "storage.googleapis.com"              = "state, snapshots, lease objects, build sources"
    "artifactregistry.googleapis.com"     = "platform and task image repositories"
    "cloudbuild.googleapis.com"           = "building the task image inside the private project"
    "secretmanager.googleapis.com"        = "the agent credential the task runner is handed at run time"
    "run.googleapis.com"                  = "the L2 enforcer job (added in the next phase)"
    "cloudscheduler.googleapis.com"       = "L3 daily stop, and the L2 tick"
    "monitoring.googleapis.com"           = "L4 alert policies and the notification channel"
    "logging.googleapis.com"              = "cluster logs, and the log-based Scheduler-failure metric"
    "cloudtrace.googleapis.com"           = "Substrate emits traces; the API itself costs nothing"
    "billingbudgets.googleapis.com"       = "the JPY budget"
    "cloudkms.googleapis.com"             = "the key that encrypts tofu/exe-cluster's state (kms.tf)"
  }
}

resource "google_project_service" "enabled" {
  for_each = local.project_services

  project = var.gcp_project_id
  service = each.key

  # See the header: never disable a shared project's APIs on destroy.
  disable_on_destroy         = false
  disable_dependent_services = false
}
