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

  # PLACEHOLDER — state encryption is intentionally NOT declared here yet.
  #
  # Why this is a known gap, not a forgotten one:
  # Provider configs (CLOUDFLARE_API_TOKEN, TAILSCALE_API_KEY) never
  # land in state, but resource attributes do — including
  #   - cloudflare_zero_trust_tunnel_cloudflared.exe.secret
  #   - tailscale_tailnet_key.*.key
  #   - random_id.tunnel_secret.b64_std
  # Without `encryption {}`, those land in plaintext under
  # gs://gen-ai-hironow-tofu-state.
  #
  # Until the encryption block is wired (separate commit), the state
  # bucket protections (uniform IAM, public-access-prevention,
  # versioning, no public IAM members) are the only safeguard, and
  # the GCS bucket itself stores objects with Google-managed
  # encryption-at-rest. That is acceptable for a single-tenant personal
  # project but should NOT be exported to multi-operator setups.
  #
  # Plan to land it: HCL `encryption {}` block here with a literal
  # sentinel passphrase, then TF_ENCRYPTION env-var override (HCL
  # payload, not JSON) in the just exe-* recipes — see
  # docs/setup.md § "Future: state encryption".

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
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
