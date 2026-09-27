# Inputs. Like exe-platform, the identifiers have no default: a missing value
# fails loudly instead of quietly targeting the wrong project. They live in the
# gitignored terraform.tfvars.

variable "gcp_project_id" {
  description = "The private project the exe cluster lives in."
  type        = string

  validation {
    condition     = length(trimspace(var.gcp_project_id)) > 0
    error_message = "gcp_project_id must be set (terraform.tfvars)."
  }
}

variable "gcp_project_number" {
  description = "The private project's number."
  type        = string

  validation {
    condition     = can(regex("^[0-9]+$", var.gcp_project_number))
    error_message = "gcp_project_number must be the numeric project number."
  }
}

variable "state_kms_key" {
  description = <<-EOT
    The KMS key this stack's state is encrypted with: exe-platform's
    `state_kms_key` output (kms.tf there). Read by the encryption block in
    main.tf, which is why it must be a plain variable.
  EOT
  type        = string

  validation {
    condition     = can(regex("^projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+$", var.state_kms_key))
    error_message = "state_kms_key must be a full KMS crypto key id: projects/P/locations/L/keyRings/R/cryptoKeys/K."
  }
}

variable "exe_src_dir" {
  description = <<-EOT
    Absolute path of the pinned upstream checkouts, <dir>/ax and
    <dir>/substrate, each at the commit exe/versions.json pins. `just
    exe-cluster-src` fetches and verifies them; the plan and apply recipes pass
    the path in. ko_build reads the AX source at plan time, and the Substrate
    install runs from the Substrate checkout.
  EOT
  type        = string

  validation {
    condition     = startswith(var.exe_src_dir, "/")
    error_message = "exe_src_dir must be an absolute path."
  }
}

variable "ateom_gvisor_image" {
  description = <<-EOT
    The gVisor worker image the WorkerPool runs, as printed by `just
    exe-worker-images` (upstream's `ate-setup publish worker-images`): a full
    reference pinned by digest. Empty until that recipe has been run; empty
    means no WorkerPool, so the rest of the stack plans without it.
  EOT
  type        = string
  default     = ""

  validation {
    condition     = var.ateom_gvisor_image == "" || can(regex("^[^@\\s]+@sha256:[0-9a-f]{64}$", var.ateom_gvisor_image))
    error_message = "ateom_gvisor_image must be pinned by digest (<repo>/<name>@sha256:<64 hex>): a worker image that can move under a running pool is a pool nobody can reproduce, and a tag here is exactly that."
  }
}

variable "gemini_api_key" {
  description = <<-EOT
    The Gemini API key AX hands to tasks (Secret gemini-api-secret in the
    atespace's namespace). Null until the operator supplies it in the
    gitignored terraform.tfvars; null means no Secret. Never put it in a
    tracked file, a chat, or a report.
  EOT
  type        = string
  default     = null
  sensitive   = true
}
