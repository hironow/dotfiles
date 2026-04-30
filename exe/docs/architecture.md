# Architecture — exe.hironow.dev

This document describes the components currently provisioned by
[`tofu/exe`](../../tofu/exe/) and the artifacts under [`exe/`](../).

## Component map

```
                  +-----------------------------+
                  |   Cloudflare (DNS + Edge)   |
                  |   zone: hironow.dev         |
                  +--+------------------------+-+
                     |                        |
       (Access OIDC) |                        | (Argo Tunnel out)
                     v                        ^
+--------------+     +----------------+       |
|  hironow     |---->| exe.hironow.dev|       |
|  (browser)   |     | (Coder UI gate)|       |
+--------------+     +-------+--------+       |
                             |                |
+--------------+             |                |
|  AI agent    |--(Tailscale tag:agent)--+    |
|  (CLI)       |                         |    |
+--------------+                         v    |
                                  +----------------------+
                                  |  GCE VM exe-coder    |
                                  |  region: northeast1  |
                                  |  cos-stable, e2-small|
                                  |  preemptible         |
                                  |                      |
                                  |  cloudflared --------+
                                  |  tailscaled          |
                                  |  Coder server (7080) |
                                  |  (embedded postgres) |
                                  +----------+-----------+
                                             |
                                             v
                                  +----------------------+
                                  | dev container        |
                                  | JustSandbox.Dockerfile|
                                  +----------------------+
```

```
Legend / 凡例:
- Cloudflare Edge: Cloudflare のエッジ (DNS + Tunnel + Access)
- Argo Tunnel: Cloudflare Tunnel (origin から発信する outbound 接続)
- Access OIDC: Cloudflare Access の認証 (OIDC ベース)
- Tailscale tag:agent: Agent 用に制限された Tailscale tag
- exe-coder: workspace VM のホスト名 (Tailscale 上の名前と一致)
- cos-stable: Container-Optimized OS (Google 提供)
- preemptible: 24 時間で自動停止する割引 VM
```

## Boundaries and trust

| Boundary | Trust transition | Mechanism |
|---|---|---|
| Public internet → CF edge | Untrusted → CDN | TLS 1.3 + Cloudflare WAF (default) |
| CF edge → exe.hironow.dev origin | Untrusted → Owner identity | CF Access OIDC; only `owner_email` admitted |
| CF edge → workspace VM | Edge → Origin | Argo Tunnel (outbound from VM, no inbound port open) |
| Owner laptop → workspace VM | Owner identity | Tailscale `tag:owner` ACL allowing `*:*` |
| AI agent → workspace VM | Restricted role | Tailscale `tag:agent` ACL allowing only ports 22, 80, 443, 3000-3999 on `tag:exe-coder` |
| Workspace VM → GCP APIs | VM identity | Service account `exe-coder@…` with scoped IAM (Secret Manager accessor on two specific secrets, logging.logWriter, monitoring.metricWriter) |
| Public internet → workspace VM | NONE | `deny_all_ingress` firewall + no public ports listening |

## State and secrets

| Artifact | Location | Encryption |
|---|---|---|
| OpenTofu state | `gs://gen-ai-hironow-tofu-state/exe/` | tofu native (pbkdf2 + aes_gcm), passphrase at `~/.config/tofu/exe.passphrase` (mode 0600) |
| Tailscale auth keys | Secret Manager: `exe-tailscale-coder-authkey`, `exe-tailscale-agent-authkey` | Google-managed (default) |
| Cloudflare tunnel credentials | Secret Manager: `exe-cloudflared-credentials` | Google-managed (default) |
| Cloudflare API token | env var `CLOUDFLARE_API_TOKEN` (operator side, never persisted) | n/a |
| Tailscale API key | env var `TAILSCALE_API_KEY` (operator side, never persisted) | n/a |

## Network topology

VPC `exe-vpc` with subnet `exe-subnet` (`10.10.0.0/24`) in
`asia-northeast1`. The VM has:

- One ephemeral external IP (egress + Tailscale NAT traversal only).
- `private_ip_google_access` enabled — GCP API calls go via
  Google's private fabric, not the public internet.
- Firewall rule `exe-deny-all-ingress` (priority 65000, source
  `0.0.0.0/0`, deny all protocols) — defense in depth on top of the
  fact that nothing is listening on a public port.

Egress is allowed by default (required for `tailscale up` and
`cloudflared tunnel run`).

## Permission model — Pattern A

Three Tailscale tags govern reachability:

| Tag | Holder | Allowed destinations |
|---|---|---|
| `tag:owner` | hironow's personal devices | `*:*` (full tailnet) |
| `tag:exe-coder` | the workspace VM itself | `tag:exe-coder:*` (loopback over tailnet) |
| `tag:agent` | AI agents | `tag:exe-coder:22,80,443,3000-3999` |

Auth keys (declared in [`tofu/exe/tailscale.tf`](../../tofu/exe/tailscale.tf)):

- `exe-coder` key: reusable, non-ephemeral, 90-day expiry,
  preauthorized — used by VM startup-script.
- `agent` key: reusable, **ephemeral** (abandoned sessions auto-prune
  from the tailnet), 90-day expiry, preauthorized.

A `time_rotating` resource with 90-day cadence triggers
`replace_triggered_by` on both keys, so `tofu apply` rotates them.
Old key versions are retained in Secret Manager so an in-flight
session continues with the previous key.

ACL document lives at
[`exe/tailscale/acl.hujson`](../tailscale/acl.hujson). It is **not**
wired to a `tailscale_acl` resource yet; the policy must be exercised
manually before declarative bind to avoid lockout.

## Tunnel ingress

Three rules in `cloudflare_zero_trust_tunnel_cloudflared_config.exe`:

1. `exe.hironow.dev` → `http://localhost:7080` (Coder UI).
2. `*.sandbox.hironow.dev` → `http://localhost:8080` (placeholder for
   the (P)ublic publish path; the listener at 8080 is deferred until
   Coder workspace apps are wired up).
3. catch-all → `http_status:404`.

Both real routes have `http2_origin = true` and `no_tls_verify = true`
(localhost-only HTTP/2; TLS verification off because the origin is
loopback).

## Cost (estimated, monthly)

| Item | Config | Approx. |
|---|---|---|
| GCE VM | e2-small, preemptible (24h), 30 GiB pd-balanced | $5–$7 |
| Cloudflare Tunnel | Free | $0 |
| Cloudflare Access | Free (Zero Trust, ≤ 50 users) | $0 |
| Tailscale | Personal Free | $0 |
| Secret Manager | < 10 secrets, low access frequency | < $1 |
| Egress | Light interactive use | < $1 |
| GCS state bucket | Versioned, < 1 MB | < $0.10 |
| **Total** | | **~$7–$10** |

## Coder server

Started by the VM startup-script as a background process (cos lacks
systemd). Configuration is purely env-var driven:

| Variable | Value | Purpose |
|---|---|---|
| `CODER_ACCESS_URL` | `https://exe.hironow.dev` | URL clients use; matches the Argo Tunnel CNAME |
| `CODER_HTTP_ADDRESS` | `127.0.0.1:7080` | Localhost-only; cloudflared forwards to it |
| `CODER_TLS_ENABLE` | `false` | TLS terminates at Cloudflare edge |
| `CODER_WILDCARD_ACCESS_URL` | `*.sandbox.hironow.dev` | Workspace app preview hostnames |
| `CODER_PG_CONNECTION_URL` | empty | Triggers embedded PostgreSQL |
| `CODER_CACHE_DIRECTORY` | `/var/lib/coder/cache` | Embedded postgres data + asset cache |
| `CODER_TELEMETRY` / `CODER_TELEMETRY_TRACE` | `false` / `false` | Telemetry off |
| `CODER_SECURE_AUTH_COOKIE` | `true` | Auth cookie set with Secure flag |
| `CODER_STRICT_TRANSPORT_SECURITY` | `31536000` | One-year HSTS |
| `CODER_STRICT_TRANSPORT_SECURITY_OPTIONS` | `includeSubDomains;preload` | Cover sandbox subdomains and qualify for HSTS preload |

Binary lives at `/var/lib/coder/coder` (downloaded from the GitHub
release on first boot) and is symlinked to `/usr/local/bin/coder`.
Embedded postgres state and Coder data live under `/var/lib/coder/`,
which is on the boot disk (auto-deletes only on `tofu destroy`).

The first-boot admin password is generated to
`/var/lib/coder/.admin_password` (mode 0600). Change it via the Coder
UI immediately after first login.

## Out of scope (reserved for later commits)

- `tailscale_acl` resource that binds the live ACL.
- The `:8080` reverse-proxy that fans `*.sandbox.hironow.dev` to
  per-app ports — this is the (P)ublic publish path and is gated
  behind the default-tailnet-only posture.
- ADRs documenting the major decisions (Pattern A, OpenTofu over
  Terraform, gcp-vm-container over gcp-devcontainer).
