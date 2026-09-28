variable "tailnet" {
  description = "The tailnet's name, as the Tailscale API knows it (e.g. <user>@github or <org>.ts.net); `-` means the API key's own tailnet."
  type        = string
}

variable "adopt_live_acl" {
  description = "Import the tailnet's live ACL into this stack's state (acl.tf). Only tofu test turns it off: its mock providers cannot import."
  type        = bool
  default     = true
}

variable "state_kms_key" {
  description = "The KMS key that encrypts this stack's state and saved plans: exe-platform's state_kms_key output (projects/P/locations/L/keyRings/R/cryptoKeys/K)."
  type        = string

  validation {
    condition     = can(regex("^projects/[^/]+/locations/[^/]+/keyRings/[^/]+/cryptoKeys/[^/]+$", var.state_kms_key))
    error_message = "state_kms_key must be a KMS key's resource name, projects/P/locations/L/keyRings/R/cryptoKeys/K."
  }
}
