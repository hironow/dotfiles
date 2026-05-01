# exe.hironow.dev — root configuration.
#
# Backend: GCS bucket created out-of-band by exe/scripts/bootstrap.sh.
# State encryption uses tofu's native passphrase-based encryption (1.7+);
# the passphrase lives at ~/.config/tofu/exe.passphrase (mode 0600) and
# is exported as TF_ENCRYPTION at apply time.

terraform {
  required_version = ">= 1.10.0"

  backend "gcs" {
    bucket = "gen-ai-hironow-tofu-state"
    prefix = "exe"
  }

  # State encryption.
  #
  # The HCL block is static-only — env(), var, and locals are all
  # forbidden inside it. The literal passphrase below is a sentinel
  # that fails closed: every `just exe-*` recipe overrides this
  # block via the TF_ENCRYPTION env-var (HCL payload assembled from
  # ~/.config/tofu/exe.passphrase). Without that override, OpenTofu
  # encrypts state with the sentinel, which the operator can no
  # longer decrypt — i.e. the wrong-but-deterministic case is
  # caught immediately rather than silently.
  #
  # Why this matters: provider configs (CLOUDFLARE_API_TOKEN,
  # TAILSCALE_API_KEY) never land in state, but resource attributes
  # do — including cloudflare_zero_trust_tunnel_cloudflared.exe.tunnel_secret,
  # tailscale_tailnet_key.*.key, random_id.tunnel_secret.b64_std,
  # and every google_secret_manager_secret_version.secret_data.
  # Without encryption those leak in plaintext under
  # gs://gen-ai-hironow-tofu-state.
  #
  # See docs/setup.md § "State encryption" for the operator-side
  # passphrase generation and TF_ENCRYPTION env-var details.
  # State encryption — sentinel passphrase + migration fallback.
  #
  # OpenTofu 1.11 merges this static block with TF_ENCRYPTION rather
  # than replacing it, so the static block must already be in the
  # current migration posture (enforced = false + unencrypted
  # fallback) to avoid 'Unable to use unencrypted method since the
  # enforced flag is set'. The recipe / script overrides only inject
  # the real passphrase.
  #
  # Exiting migration mode is therefore a TWO-FILE change (committed
  # together so the two cannot drift):
  #   1. tofu/exe/main.tf — drop method "unencrypted" "migration",
  #      drop both fallback {...}, set enforced = true.
  #   2. justfile (_exe-encryption recipe) and
  #      exe/scripts/{smoke,teardown}.sh — drop the same lines.
  # See docs/setup.md § "How encryption is wired" for the verify
  # command and the harden checklist.
  #
  # Why this matters: provider configs (CLOUDFLARE_API_TOKEN,
  # TAILSCALE_API_KEY) never land in state, but resource attributes
  # do — including cloudflare_zero_trust_tunnel_cloudflared.exe.tunnel_secret,
  # tailscale_tailnet_key.*.key, random_id.tunnel_secret.b64_std,
  # and every google_secret_manager_secret_version.secret_data.
  # Without encryption those leak in plaintext under
  # gs://gen-ai-hironow-tofu-state.
  encryption {
    key_provider "pbkdf2" "default" {
      passphrase = "OVERRIDDEN_BY_TF_ENCRYPTION_ENV"
    }
    method "aes_gcm" "default" {
      keys = key_provider.pbkdf2.default
    }
    method "unencrypted" "migration" {}
    state {
      method   = method.aes_gcm.default
      enforced = false
      fallback {
        method = method.unencrypted.migration
      }
    }
    plan {
      method   = method.aes_gcm.default
      enforced = false
      fallback {
        method = method.unencrypted.migration
      }
    }
  }

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
    tailscale = {
      source  = "tailscale/tailscale"
      version = "~> 0.18"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
  zone    = var.gcp_zone
}

provider "cloudflare" {
  # CLOUDFLARE_API_TOKEN env var is read implicitly. Token scope:
  #   Zone:Read, DNS:Edit, Access:Edit, Tunnel:Edit  (apex: hironow.dev only)
}

provider "tailscale" {
  # TAILSCALE_API_KEY env var is read implicitly. OAuth client recommended;
  # scope to "auth_keys:write,acl:read" only.
  tailnet = var.tailnet
}
