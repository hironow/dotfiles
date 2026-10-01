variable "tailnet" {
  description = "The tailnet's name, as the Tailscale API knows it (e.g. <user>@github or <org>.ts.net); `-` means the API key's own tailnet."
  type        = string
}

variable "adopt_live_acl" {
  description = "Import the tailnet's live ACL into this stack's state (acl.tf). Only tofu test turns it off: its mock providers cannot import."
  type        = bool
  default     = true
}

# There is no variable for the state's encryption: a passphrase is a secret, so
# it reaches OpenTofu through TF_ENCRYPTION only (main.tf), never a variable a
# plan file or the state could record.
