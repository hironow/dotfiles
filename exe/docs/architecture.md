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
                             v                |
                      +----------------------+
                      | exe-coder VM         |
                      | exe-vpc 10.10.0.0/24 |
                      | debian-12, e2-small  |
                      | tag:exe-coder        |
                      | cloudflared, tailscaled|
                      | Coder server         |
                      | CODER_HTTP_ADDRESS=  |
                      |   0.0.0.0:7080       |
                      |  (embedded postgres) |
                      +----------+-----------+
                                 ^
                                 | tailnet (WireGuard)
                                 | http://exe-coder:7080
                                 |  (MagicDNS resolves)
                                 |
                      +----------+-----------+
                      | workspace VM(s)      |
                      | default VPC          |
                      | debian-12, e2-small  |
                      | tag:exe-workspace    |
                      | tailscaled, docker   |
                      | docker run prebuilt  |
                      | dev container image  |
                      | (from Artifact Reg)  |
                      |   + Coder agent      |
                      +----------------------+
```

```
Legend / 凡例:
- Cloudflare Edge: Cloudflare のエッジ (DNS + Tunnel + Access)
- Argo Tunnel: Cloudflare Tunnel (origin から発信する outbound 接続)
- Access OIDC: Cloudflare Access の認証 (OIDC ベース)
- exe-coder VM: control-plane (Coder server を常駐)
- workspace VM: ユーザの Coder workspace (template が作る)
- tag:exe-coder / tag:exe-workspace: Tailscale tag (ACL で関係を限定)
- tailnet (WireGuard): exe-coder と workspace 間の internal channel
- MagicDNS: tailnet 内 hostname 解決 (exe-coder → 100.x.x.x)
- prebuilt dev container image: GitHub Actions が main merge 時に build + push (Artifact Registry)、workspace VM は docker pull のみ。envbuilder は ADR 0002 で廃止
- debian-12: VM ホスト OS / dev container ベース (共通)
```

## Boundaries and trust

| Boundary | Trust transition | Mechanism |
|---|---|---|
| Public internet → CF edge | Untrusted → CDN | TLS 1.3 + Cloudflare WAF (default) |
| CF edge → exe.hironow.dev origin | Untrusted → Owner identity | CF Access OIDC; only `owner_email` admitted |
| CF edge → workspace VM | Edge → Origin | Argo Tunnel (outbound from VM, no inbound port open) |
| Owner laptop → exe-coder | Owner identity | Tailscale `tag:owner` → `*:*` |
| AI agent → exe-coder | Restricted role | Tailscale `tag:agent` → `tag:exe-coder:22,80,443,3000-3999` |
| Workspace → exe-coder | Per-workspace role | Tailscale `tag:exe-workspace` → `tag:exe-coder:7080` (agent download + protocol) |
| exe-coder → GCP APIs | VM identity | SA `exe-coder@…` (Secret Manager accessor on tailnet/tunnel secrets, compute.instanceAdmin, iam.serviceAccountUser, logging/monitoring) |
| Workspace → GCP APIs | VM identity | SA `exe-workspace@…` (only the workspace authkey; logging/monitoring) |
| Public internet → workspace VM | NONE | `deny_all_ingress` firewall + no public ports listening |
| Workspace **container** → tailnet RPC | NONE (intentional) | `tailscaled` Unix socket is **not** mounted into the container; `tailscale` CLI is **not** installed in the dev container image |

### Why no tailscale CLI inside the workspace container

The workspace VM joins the tailnet at the **host** layer (apt-
installed `tailscale`, fingerprint-pinned per
[`PR #61`](https://github.com/hironow/dotfiles/pull/61)). The dev
container runs with `--network host`, so:

- **Outbound tailnet reach works without a CLI.** Container
  processes can `curl http://gpu-host.tailnet:8080` directly —
  the host's resolver handles MagicDNS, and the host's
  WireGuard tunnel handles the transport.
- **Inbound exposure works without a CLI.** A web server bound
  inside the container (e.g. `python -m http.server :8080`) is
  reachable at `<vm-host>.tailnet:8080` because of host-network
  sharing. No `tailscale serve` needed for plain tailnet-private
  access.

The `tailscale` CLI is intentionally NOT installed in the
container, and the host's `/var/run/tailscale/tailscaled.sock`
is intentionally NOT mounted. Reason: the socket is a
control-plane endpoint with **no per-command auth**. Anything
with socket access can `tailscale serve --funnel` (public
internet exposure), `tailscale logout` (DoS the VM), or
`tailscale ssh hironow@<other-node>` (lateral move using the
VM's `tag:exe-workspace` identity, or worse, `tag:owner` via
ACL escalation paths). For an environment that runs AI agents
inside the container, granting that level of authority to any
in-container process is unacceptable.

If `tailscale serve --funnel` or other CLI-only operations are
needed, run them from the **VM host shell** instead:

```bash
gcloud compute ssh coder-<owner>-<workspace>-root \
  --zone=asia-northeast1-a \
  --command='sudo tailscale serve --bg http://localhost:8080'
```

This requires explicit operator action (gcloud auth + sudo) and
is auditable; an AI agent running inside the container cannot
reach this path.

## State and secrets

| Artifact | Location | Encryption |
|---|---|---|
| OpenTofu state | `gs://gen-ai-hironow-tofu-state/exe/` | tofu native (pbkdf2 + aes_gcm), passphrase at `~/.config/tofu/exe.passphrase` (mode 0600) |
| Tailscale auth keys | Secret Manager: `exe-tailscale-coder-authkey`, `exe-tailscale-agent-authkey`, `exe-tailscale-workspace-authkey` | Google-managed (default) |
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

Four Tailscale tags govern reachability:

| Tag | Holder | Allowed destinations |
|---|---|---|
| `tag:owner` | hironow's personal devices | `*:*` (full tailnet) |
| `tag:exe-coder` | the Coder control-plane VM | `tag:exe-coder:*` (loopback over tailnet) |
| `tag:exe-workspace` | Coder workspace VMs | `tag:exe-coder:7080` (agent binary download + agent <-> server protocol) |
| `tag:agent` | AI agents | `tag:exe-coder:22,80,443,3000-3999` |

Auth keys (in [`tofu/exe/tailscale.tf`](../../tofu/exe/tailscale.tf)):
all reusable, ephemeral, preauthorized, 90-day expiry, rotated by
`time_rotating`. The `exe-workspace` key `depends_on
tailscale_acl.this` so its tag is in the live ACL before issuance.

ACL: [`exe/tailscale/acl.hujson`](../tailscale/acl.hujson), bound by
`tailscale_acl.this` (`prevent_destroy`, `overwrite_existing_content`).

## Tunnel ingress

Two rules in `cloudflare_zero_trust_tunnel_cloudflared_config.exe`:

1. `exe.hironow.dev` → `http://localhost:7080` (Coder UI, gated by
   Cloudflare Access).
2. catch-all → `http_status:404`.

The `*.sandbox.hironow.dev` wildcard CNAME exists in DNS but has
**no matching tunnel ingress rule** until the (P)ublic publish path
lands with its own Cloudflare Access protection. Any request to
`*.sandbox.hironow.dev` therefore returns the catch-all 404. This
prevents a silent exposure if a process accidentally listens on
:8080 inside the VM.

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
systemd). The Coder binary is fetched at the pinned
`var.coder_version` and verified against `var.coder_sha256`
(ADR 0007 supply-chain hardening — replaces the curl-piped install
script and the GitHub-API `latest` fallback). Configuration is
purely env-var driven:

| Variable | Value | Purpose |
|---|---|---|
| `CODER_ACCESS_URL` | `https://exe.hironow.dev` | URL clients use; matches the Argo Tunnel CNAME |
| `CODER_HTTP_ADDRESS` | `0.0.0.0:7080` | Loopback for cloudflared + tun0 for workspace VMs. Public IP blocked at L3 by deny-all-ingress |
| `CODER_TLS_ENABLE` | `false` | TLS terminates at Cloudflare edge |
| `CODER_WILDCARD_ACCESS_URL` | `*.sandbox.hironow.dev` | Workspace app preview hostnames |
| `CODER_PG_CONNECTION_URL` | empty | Triggers embedded PostgreSQL |
| `CODER_CACHE_DIRECTORY` | `/var/lib/coder/cache` | Embedded postgres data + asset cache |
| `CODER_TELEMETRY` / `CODER_TELEMETRY_TRACE` | `false` / `false` | Telemetry off |
| `CODER_SECURE_AUTH_COOKIE` | `true` | Auth cookie set with Secure flag |
| `CODER_STRICT_TRANSPORT_SECURITY` | `31536000` | One-year HSTS |
| `CODER_STRICT_TRANSPORT_SECURITY_OPTIONS` | `includeSubDomains;preload` | Cover sandbox subdomains and qualify for HSTS preload |

Binary lives at `/usr/local/bin/coder` (extracted from the pinned
release tarball at first boot, sha256-verified before extraction;
`gh attestation verify` runs as defence-in-depth when gh is
authenticated). Embedded postgres state and Coder data live under
`/var/lib/coder/`, which is on the boot disk (auto-deletes only on
`tofu destroy`). Bumping Coder is `var.coder_version` +
`var.coder_sha256` + `just exe-apply` in lock-step.

The first-boot admin password is generated to
`/var/lib/coder/.admin_password` (mode 0600). Change it via the Coder
UI immediately after first login.

## Workspace template — `dotfiles-devcontainer`

Source: [`exe/coder/templates/dotfiles-devcontainer/`](../coder/templates/dotfiles-devcontainer/).
Push via runbook. Per `cdr create`, a workspace VM lands in the
project's `default` VPC and joins the tailnet as `tag:exe-workspace`.

- `provider "coder" { url = "http://exe-coder:7080" }` overrides
  `${ACCESS_URL}` per-template so the agent binary download
  resolves over the tailnet (CF Access edge bypass-free).
- VM startup_script installs three vendors via apt with **GPG
  fingerprint pinning** for all three: Tailscale (observed
  `2596A9...957F5868`), Google Cloud (`35BAA0...DC6315A3`),
  Docker (`9DC858...0EBFCD88`). Mismatch fails the bootstrap
  closed (no curl|bash, no `|| true`).
- VM startup_script then `docker pull`s the prebuilt dev
  container image from Artifact Registry, `docker run`s it with
  `--volume /home/<user>:/root` (operator state persistence) and
  `--network host` (tailnet visibility for the agent).
- Agent startup_script exports `INSTALL_SKIP_HOMEBREW=1
  INSTALL_SKIP_ADD_UPDATE=1` (belt-and-suspenders; ADR 0005
  install.sh OS dispatch already auto-skips Mac-only steps on
  Linux), then `MISE_OFFLINE=1 mise install` against the workspace
  mise.toml. The mise data dir is `/opt/mise` (ADR 0006 relocation)
  so the build-time-baked installs survive the `/root` overlay
  mask.
- Workspace VM runs as `exe-workspace@…` (not the default compute
  SA). Holds `roles/secretmanager.secretAccessor` on the workspace
  tailnet authkey and `roles/artifactregistry.reader` on the
  dotfiles repo (for docker pull).

## Out of scope

- (P)ublic publish path (`*.sandbox.hironow.dev` reverse proxy).
- ADRs for Pattern A, OpenTofu choice, tailnet routing.
