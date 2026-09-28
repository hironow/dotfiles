# tailnet — the Tailscale policy file, on its own.
#
# The retired Coder stack (tofu/exe) used to own the tailnet's ACL, because
# its VMs and agents joined the tailnet. exe on google/ax does not: nothing of
# it is on the tailnet. This stack keeps the ACL itself -- the owner's
# devices, both break-glass rules, and the tags other stacks mint keys for --
# and nothing else. Auth keys stay with the stacks that use them.
#
# It took the ACL over by `import` (acl.tf), after the old stack dropped it
# from its own state with a `removed` block (destroy = false): the policy never
# had two owners and never went away (Phase 7: 7.4, then 7.3).
#
# STATE lives in the exe project's state bucket under the prefix tailnet,
# encrypted with the KMS key exe-platform owns, like exe-cluster's. That ties
# the tailnet's state to the exe project's lifetime: README.md says how to
# move it if the project goes.
#
# CONFIDENTIALITY: the project is private and this repo is public. The state
# key and the tailnet's name come from terraform.tfvars, the bucket from
# backend.hcl; both are gitignored (see .gitignore).

terraform {
  required_version = ">= 1.12.0"

  required_providers {
    # 0.x, so dependency class 2: pinned exactly, and only moved after a
    # cooldown and a changelog read. The same version the old stack last ran.
    tailscale = {
      source  = "tailscale/tailscale"
      version = "0.29.2"
    }
  }

  # Partial backend config: `tofu init -backend-config=backend.hcl`, the exe
  # project's state bucket (its name embeds the project id). The prefix is
  # pinned here so a typo cannot start a second, empty state.
  backend "gcs" {
    prefix = "tailnet"
  }

  encryption {
    key_provider "gcp_kms" "state" {
      kms_encryption_key = var.state_kms_key
      key_length         = 32
    }

    method "aes_gcm" "state" {
      keys = key_provider.gcp_kms.state
    }

    # enforced: OpenTofu refuses to write this stack's state, or a saved plan
    # of it, in plaintext.
    state {
      method   = method.aes_gcm.state
      enforced = true
    }

    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

provider "tailscale" {
  # TAILSCALE_API_KEY (or an OAuth client's TAILSCALE_OAUTH_CLIENT_ID and
  # _SECRET) from the environment, never a variable: a credential must not
  # reach the state or a saved plan. Scope: acl:read and acl:write (policy
  # file), devices:read for the sheet's tag check.
  tailnet = var.tailnet
}
