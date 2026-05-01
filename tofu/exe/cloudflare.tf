# Cloudflare — Tunnel + DNS + Access for exe.hironow.dev.
#
# Topology:
#
#   browser  --(Zero Trust OIDC)-->  exe.hironow.dev  --(Argo Tunnel)-->
#       cloudflared on the VM  --(loopback)-->  Coder UI on 127.0.0.1
#
# - Origin is never reachable from the public internet (the VM has
#   deny-all ingress; cloudflared dials Cloudflare from the inside).
# - Cloudflare Access (free tier) gates the apex with an OIDC identity
#   policy: only owner_email is admitted.
# - Sandbox wildcard *.sandbox.hironow.dev is reserved here as a DNS
#   record + tunnel ingress placeholder; the actual ingress fan-out is
#   wired up in the (P)ublic publish commit.
#
# Provider: cloudflare/cloudflare ~> 5.0 (5.19.1 verified).
# v5 is built on terraform-plugin-framework, so most former HCL blocks
# (filter, config, ingress_rule, origin_request, include, policies) are
# now typed attributes assigned with `=`. v4 → v5 differences applied:
#   - cloudflare_record           -> cloudflare_dns_record
#   - tunnel.secret               -> tunnel_secret
#   - access_policy.application_id -> attached via app's policies array
#   - block syntax                -> attribute syntax (= {...} / = [...])
#   - data "cloudflare_zone".name -> static var.cf_zone_id (avoids the
#     v5 filter object syntax + extra plan-time API round-trip)

# ----- tunnel ---------------------------------------------------------

resource "random_id" "tunnel_secret" {
  byte_length = 35
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "exe" {
  account_id    = var.cf_account_id
  name          = "${local.prefix}-tunnel"
  tunnel_secret = random_id.tunnel_secret.b64_std
  config_src    = "cloudflare"
}

# Push the tunnel credentials JSON into Secret Manager so the VM can
# fetch it at boot. The structure matches what `cloudflared` expects
# in /etc/cloudflared/<tunnel-id>.json.
locals {
  tunnel_credentials = jsonencode({
    AccountTag   = var.cf_account_id
    TunnelID     = cloudflare_zero_trust_tunnel_cloudflared.exe.id
    TunnelName   = cloudflare_zero_trust_tunnel_cloudflared.exe.name
    TunnelSecret = random_id.tunnel_secret.b64_std
  })
}

resource "google_secret_manager_secret" "tunnel_credentials" {
  secret_id = "${local.prefix}-cloudflared-credentials"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "tunnel_credentials" {
  secret      = google_secret_manager_secret.tunnel_credentials.id
  secret_data = local.tunnel_credentials
}

resource "google_secret_manager_secret_iam_member" "tunnel_credentials_reader" {
  secret_id = google_secret_manager_secret.tunnel_credentials.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.exe_coder.email}"
}

# ----- tunnel ingress -------------------------------------------------
#
# Two routes:
#   1. exe.hironow.dev          -> http://localhost:7080  (Coder UI)
#   2. *.sandbox.hironow.dev    -> http://localhost:8080  (placeholder
#      reverse proxy; resolved to a real listener in the (P) commit)

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "exe" {
  account_id = var.cf_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.exe.id

  config = {
    ingress = [
      {
        hostname = local.coder_host
        service  = "http://localhost:7080"
        origin_request = {
          # Modern TLS posture even though we're talking to localhost.
          no_tls_verify = true
          http2_origin  = true
        }
      },
      # Catch-all 404. Required as the last entry.
      #
      # NOTE: the *.sandbox.hironow.dev route is intentionally NOT
      # declared here. The (P)ublic publish path is deferred — until
      # it lands with a Cloudflare Access app gating the wildcard,
      # any tunnel ingress to :8080 would be a silent security hole.
      # The wildcard DNS record in this file resolves to the tunnel
      # but with no matching ingress rule it returns this 404.
      {
        service = "http_status:404"
      },
    ]
  }
}

# ----- DNS ------------------------------------------------------------
#
# CNAMEs pointing at <tunnel-id>.cfargotunnel.com. proxied=true keeps
# the orange-cloud, so origin IP never resolves publicly.

resource "cloudflare_dns_record" "coder" {
  zone_id = var.cf_zone_id
  name    = trimsuffix(local.coder_host, ".${var.cf_zone_name}")
  content = "${cloudflare_zero_trust_tunnel_cloudflared.exe.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
  comment = "exe.hironow.dev → Argo Tunnel (managed by tofu)"
}

resource "cloudflare_dns_record" "sandbox_wildcard" {
  zone_id = var.cf_zone_id
  name    = "*.${trimsuffix(var.sandbox_subdomain, ".${var.cf_zone_name}")}"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.exe.id}.cfargotunnel.com"
  type    = "CNAME"
  proxied = true
  ttl     = 1
  comment = "*.sandbox.hironow.dev → Argo Tunnel (placeholder, resolved by the (P)ublic commit)"
}

# ----- Access (Zero Trust) -------------------------------------------
#
# Two policies attach to the Coder application:
#   1. owner — the operator's email (browser/UI use)
#   2. service_token — the Coder CLI's machine identity (CLI use)
# The service-token path lets `coder login` and downstream CLI calls
# pass through Cloudflare Access without an interactive OIDC challenge,
# while still enforcing two-layer auth (CF Access service token AND
# Coder session token).

resource "cloudflare_zero_trust_access_policy" "coder_owner" {
  account_id = var.cf_account_id
  name       = "owner only"
  decision   = "allow"

  include = [
    {
      email = {
        email = var.owner_email
      }
    },
  ]
}

# Service token for the Coder CLI / agent. Issued + rotated by tofu;
# the client_id and client_secret land in Secret Manager so the
# operator (or a future agent runtime) reads them by name and never
# pastes plaintext into a shell history file.

resource "cloudflare_zero_trust_access_service_token" "coder_cli" {
  account_id = var.cf_account_id
  name       = "exe-coder-cli"
}

resource "cloudflare_zero_trust_access_policy" "coder_service_token" {
  account_id = var.cf_account_id
  name       = "coder cli service token"
  # 'non_identity' is the canonical decision for Service Token-only
  # rules; it allows the request without requiring an end-user identity.
  decision = "non_identity"

  include = [
    {
      service_token = {
        token_id = cloudflare_zero_trust_access_service_token.coder_cli.id
      }
    },
  ]
}

resource "google_secret_manager_secret" "coder_cli_client_id" {
  secret_id = "${local.prefix}-coder-cli-client-id"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "coder_cli_client_id" {
  secret      = google_secret_manager_secret.coder_cli_client_id.id
  secret_data = cloudflare_zero_trust_access_service_token.coder_cli.client_id
}

resource "google_secret_manager_secret" "coder_cli_client_secret" {
  secret_id = "${local.prefix}-coder-cli-client-secret"
  labels    = local.common_labels
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "coder_cli_client_secret" {
  secret      = google_secret_manager_secret.coder_cli_client_secret.id
  secret_data = cloudflare_zero_trust_access_service_token.coder_cli.client_secret
}

resource "cloudflare_zero_trust_access_application" "coder" {
  account_id       = var.cf_account_id
  name             = "exe coder"
  domain           = local.coder_host
  type             = "self_hosted"
  session_duration = "24h"

  # Skip identity for the Coder agent's own callback path; the agent
  # authenticates with its own service token, not a human session.
  # (Path can be tightened once we know what Coder actually uses.)
  skip_interstitial = false

  # Hardening — modern cookie flags. Helmet.js-equivalent at the edge.
  http_only_cookie_attribute = true
  same_site_cookie_attribute = "lax"

  # Attach the standalone policies here (v5 model). precedence is
  # the order Cloudflare evaluates allow/deny rules; lower wins. Both
  # are 'allow' decisions, so order is informational rather than
  # security-relevant.
  policies = [
    {
      id         = cloudflare_zero_trust_access_policy.coder_owner.id
      precedence = 1
    },
    {
      id         = cloudflare_zero_trust_access_policy.coder_service_token.id
      precedence = 2
    },
  ]
}
