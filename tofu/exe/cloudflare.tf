# Cloudflare — Tunnel + DNS + Access for exe.hironow.dev: parked.
#
# RETIREMENT (Phase 7): by the operator's decision the stack's Cloudflare
# objects stay exactly as they are, unmanaged and in no state: the tunnel
# and its config, the two DNS records, the two Access policies, the
# service token and the Access application. The `removed` blocks below
# drop them from this stack's state without touching them (destroy =
# false), and nothing in this configuration reads a Cloudflare attribute
# any more, so neither the forget nor the destroy needs a Cloudflare API
# token. A `tofu plan -destroy` ignores these blocks, so the retirement
# sheet applies the forget before any destroy plan exists.
#
# The Secret Manager copies of Cloudflare values (the tunnel credentials,
# the service token's client id and secret) are GCP objects of this stack
# and are destroyed with it. The tunnel's credentials can be fetched from
# Cloudflare again, and the service token rotated there.

# ----- parked in Cloudflare, out of this stack's state -----------------

removed {
  from = cloudflare_zero_trust_tunnel_cloudflared.exe

  lifecycle {
    destroy = false
  }
}

removed {
  from = cloudflare_zero_trust_tunnel_cloudflared_config.exe

  lifecycle {
    destroy = false
  }
}

removed {
  from = cloudflare_dns_record.coder

  lifecycle {
    destroy = false
  }
}

removed {
  from = cloudflare_dns_record.sandbox_wildcard

  lifecycle {
    destroy = false
  }
}

removed {
  from = cloudflare_zero_trust_access_policy.coder_owner

  lifecycle {
    destroy = false
  }
}

removed {
  from = cloudflare_zero_trust_access_service_token.coder_cli

  lifecycle {
    destroy = false
  }
}

removed {
  from = cloudflare_zero_trust_access_policy.coder_service_token

  lifecycle {
    destroy = false
  }
}

removed {
  from = cloudflare_zero_trust_access_application.coder

  lifecycle {
    destroy = false
  }
}

# ----- the Secret Manager copies: destroyed with the stack ------------
#
# Their values came from the Cloudflare resources above, which this
# configuration no longer has, so the versions leave the configuration
# and are destroyed. The secrets that held them stay declared until the
# stack's destroy.

removed {
  from = google_secret_manager_secret_version.tunnel_credentials

  lifecycle {
    destroy = true
  }
}

removed {
  from = google_secret_manager_secret_version.coder_cli_client_id

  lifecycle {
    destroy = true
  }
}

removed {
  from = google_secret_manager_secret_version.coder_cli_client_secret

  lifecycle {
    destroy = true
  }
}

# The tunnel's secret. Only the parked tunnel used it; kept so the
# stack's destroy removes it with everything else.
resource "random_id" "tunnel_secret" {
  byte_length = 35
}

resource "google_secret_manager_secret" "tunnel_credentials" {
  secret_id = "${local.prefix}-cloudflared-credentials"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "tunnel_credentials_reader" {
  secret_id = google_secret_manager_secret.tunnel_credentials.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.exe_coder.email}"
}

resource "google_secret_manager_secret" "coder_cli_client_id" {
  secret_id = "${local.prefix}-coder-cli-client-id"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "coder_cli_client_secret" {
  secret_id = "${local.prefix}-coder-cli-client-secret"
  labels    = local.common_labels
  replication {
    auto {}
  }
}
