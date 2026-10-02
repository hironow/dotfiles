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
# STATE lives in the OLD personal project's state bucket under the prefix
# tailnet, encrypted by passphrase like the retired stack's. This stack stays
# in this public repo, so it stays out of the private exe project: that
# project's bucket is named after it and its KMS key belongs to it, so either
# would tie the public repo to the private project. The bucket already holds
# the retired stack's state and other stacks' besides; the prefix keeps them
# apart, and the bucket outlives the retirement.
#
# CONFIDENTIALITY: the bucket and the prefix are public values, so they are
# spelled out below. Only the tailnet's name comes from terraform.tfvars
# (gitignored), and the passphrase never leaves ~/.config/tofu.

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

  # The old personal project's state bucket, which the retired stack also
  # used. Both values are public and both are pinned here: a partial config
  # lets a typo start a second, empty state, and an empty state means the next
  # plan proposes to create the ACL this stack already owns.
  backend "gcs" {
    bucket = "gen-ai-hironow-tofu-state"
    prefix = "tailnet"
  }

  # State encryption, the retired stack's mechanism (tofu/exe/main.tf): pbkdf2
  # over a local passphrase, aes_gcm, enforced for the state AND for a saved
  # plan. The passphrase below is a SENTINEL that fails closed -- every
  # `just tailnet-*` recipe overrides this block with TF_ENCRYPTION, built by
  # `just _tailnet-encryption` from ~/.config/tofu/tailnet.passphrase (mode
  # 0600). Run without that override and OpenTofu encrypts with the sentinel,
  # which the operator cannot decrypt afterwards: wrong, but deterministic and
  # caught on the spot rather than silently.
  #
  # Why it matters here: the ACL is the tailnet's whole authorization model,
  # and the state holds its text. A Tailscale credential never reaches the
  # state (the provider reads the environment), but the policy does.
  #
  # Its own passphrase, not the retired stack's: that one goes when the stack
  # does. This state is empty until 7.3's first apply, so there is nothing to
  # migrate.
  encryption {
    key_provider "pbkdf2" "default" {
      passphrase = "OVERRIDDEN_BY_TF_ENCRYPTION_ENV"
    }

    method "aes_gcm" "default" {
      keys = key_provider.pbkdf2.default
    }

    state {
      method   = method.aes_gcm.default
      enforced = true
    }

    plan {
      method   = method.aes_gcm.default
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
