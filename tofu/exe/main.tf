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

  encryption {
    key_provider "pbkdf2" "default" {
      passphrase = env("TF_ENCRYPTION_PASSPHRASE")
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
