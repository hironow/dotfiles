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
  # State encryption — strict aes_gcm with sentinel passphrase.
  #
  # OpenTofu 1.11 merges this static block with TF_ENCRYPTION rather
  # than replacing it, so the static block must agree with the
  # operating posture. After the 2026-05-01 first apply confirmed
  # encrypted state on GCS, the migration phase ended: the
  # 'unencrypted.migration' method and the legacy fallback blocks
  # are gone, and 'enforced = true' rejects any non-encrypted state
  # from now on. Every just exe-* recipe and smoke/teardown script
  # injects the real passphrase via TF_ENCRYPTION; without that,
  # OpenTofu hits the sentinel and refuses to run (fail-closed).
  #
  # Why this matters: provider configs (CLOUDFLARE_API_TOKEN,
  # TAILSCALE_API_KEY) never land in state, but resource attributes
  # do — cloudflare_zero_trust_tunnel_cloudflared.exe.tunnel_secret,
  # tailscale_tailnet_key.*.key, random_id.tunnel_secret.b64_std,
  # google_secret_manager_secret_version.*.secret_data. Without
  # encryption these leak in plaintext under
  # gs://gen-ai-hironow-tofu-state.
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
