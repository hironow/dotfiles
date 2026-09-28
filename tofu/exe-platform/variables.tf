# Inputs. NONE of these has a default, on purpose.
#
# The target project is private and this repo is public, so every identifier
# arrives through terraform.tfvars (gitignored). A default would mean a missing
# tfvars silently targets something — most likely the operator's other project,
# which this stack must never touch. No default = fail loudly.

variable "gcp_project_id" {
  description = "The private GCP project this stack owns. Supplied via terraform.tfvars."
  type        = string

  validation {
    # Google's project-id grammar. Catches an empty or obviously wrong value
    # before any API call is made with it.
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.gcp_project_id))
    error_message = "gcp_project_id must be a valid GCP project id (6-30 chars, lowercase)."
  }
}

variable "gcp_project_number" {
  description = <<-EOT
    The project's numeric id, as a string. Required because Workload Identity
    principal:// members address the pool by project NUMBER while naming the
    pool by project ID, and because the billing budget filter addresses the
    project by number.
  EOT
  type        = string

  validation {
    condition     = can(regex("^[0-9]{6,20}$", var.gcp_project_number))
    error_message = "gcp_project_number must be the numeric project number, as a string."
  }
}

variable "billing_account_id" {
  description = "Billing account that funds the project; scope of the JPY budget."
  type        = string

  validation {
    condition     = can(regex("^[0-9A-Z]{6}-[0-9A-Z]{6}-[0-9A-Z]{6}$", var.billing_account_id))
    error_message = "billing_account_id must look like XXXXXX-XXXXXX-XXXXXX."
  }
}

variable "alert_email" {
  description = "Address the budget and the L4 alerts notify. Never tracked."
  type        = string

  validation {
    condition     = can(regex("^[^@[:space:]]+@[^@[:space:]]+\\.[^@[:space:]]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}

variable "monthly_budget_jpy" {
  description = <<-EOT
    Monthly budget ceiling in JPY (decision Q9: 3000). Alerts only — no
    automatic spend cap, because a hard cap on a shared project would take the
    neighbouring stacks down with it.
  EOT
  type        = number
  default     = 3000

  validation {
    condition     = var.monthly_budget_jpy > 0 && var.monthly_budget_jpy == floor(var.monthly_budget_jpy)
    error_message = "monthly_budget_jpy must be a positive whole number of yen."
  }
}

variable "enforcer_image" {
  description = <<-EOT
    Container image for the L2 enforcer Cloud Run job, pinned by digest
    (…/exe-platform/exe-reaper@sha256:<64 hex>).

    Passed IN rather than built here. The reaper is a Go binary built with ko,
    and a ko provider in this stack would build and push an image during `tofu
    plan` — which would make a plan a side-effecting operation, break the offline
    invariant tests, and require registry credentials to review a diff. So the
    build is a separate recipe and its output digest is an input.

    The digest requirement is the part that matters. A mutable tag in the job
    that enforces a spend limit is how a silently stale enforcer survives: the
    tick fires, an execution starts, it exits 0, and the binary that ran is last
    month's — with nothing in the plan, the state or the execution record saying
    which code resized the node pool. A digest makes the deployed enforcer
    auditable after the fact, which for a money stop is the whole point.

    Empty, the default, means L2 is not deployed: the job, its run.invoker
    binding and its tick are left out together, and the rest of the stack
    (the enforcer identity and its grants included) plans unchanged. The digest
    only exists once the ko build has pushed the image, so this is also what
    lets the platform keep planning to "No changes." until then.
  EOT
  type        = string
  default     = ""

  validation {
    # Only the digest tail is checked. Requiring a particular registry host or
    # repository path would mean writing the project id into a public repo, and
    # the property being defended here is immutability, not provenance.
    condition     = var.enforcer_image == "" || can(regex("@sha256:[0-9a-f]{64}$", var.enforcer_image))
    error_message = "enforcer_image must be empty (L2 not deployed) or pinned by digest, ending in @sha256:<64 lowercase hex>. A tag is mutable, so a tagged enforcer cannot be audited after it has resized the pool."
  }
}

variable "node_machine_type" {
  description = "Node machine type (M20 T3, sized by S7: e2-highmem-2 fits the stack plus 2 concurrent 4Gi actors at ~68% of e2-standard-4's rate)."
  type        = string
  default     = "e2-highmem-2"
}

variable "node_disk_size_gb" {
  description = "Node boot disk size. 50 GB until the spike measures the real need."
  type        = number
  default     = 50
}

variable "node_pool_initial_count" {
  description = <<-EOT
    The node pool's creation-time size, and the ONLY size this stack ever
    states. It is a constant, never a variable the auto-sleep writes back: the
    running size belongs to the lease loop (see gke.tf). 0 means the stack
    creates a cold pool and nothing bills until the first wake; if GKE refuses
    to create a pool at 0, 1 is the only other allowed value and L3 must be run
    immediately after the apply.
  EOT
  type        = number
  default     = 0

  validation {
    condition     = var.node_pool_initial_count == 0 || var.node_pool_initial_count == 1
    error_message = "node_pool_initial_count must be the constant 0 or 1 (see decision Q13)."
  }
}
