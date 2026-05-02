# 0004. Workspace VMs reach the Coder control plane over the tailnet (B-plan)

**Date:** 2026-05-02
**Status:** Accepted (recorded retroactively for PR #47)

## Context

`exe.hironow.dev` is fronted by Cloudflare Access. Browser sessions
authenticate via Cloudflare OIDC; the `cdr` CLI authenticates via a
Cloudflare Access service token. Workspace VMs spawned by the Coder
template **have neither**: they are headless GCE instances created
by the Coder server, with no browser session and no service token
plumbed in.

The first workspace boot under Layer 2 failed because the
`bootstrap_linux.sh` script that the Coder server injects into the
workspace VM fetched the Coder agent binary from
`${CODER_ACCESS_URL}/bin/coder-linux-amd64`. With `CODER_ACCESS_URL`
set to the public `https://exe.hironow.dev`, the binary download
hit Cloudflare Access without a service token. CF Access returned
the OIDC interstitial **HTML** with a 200 status. The bootstrap
script `chmod +x`-ed the HTML and tried to exec it. Bash interpreted
the HTML as a shell script and emitted

```
./coder: line 2: syntax error: unexpected newline
```

The workspace then never connected.

Two options were considered:

- **A-plan: punch a hole in CF Access for `/bin/*`.** Configure CF
  Access to allow unauthenticated requests to the agent binary
  path. Operationally simple but weakens the edge — a URL that was
  previously private becomes publicly reachable, and the agent
  binary would be downloadable by anyone who can resolve the
  public DNS. The agent binary is publicly available from Coder
  upstream anyway, but the precedent of "punch holes in CF Access
  for internal traffic" is bad.

- **B-plan: route workspace agent download over the tailnet.**
  Workspace VMs join the tailnet under a new `tag:exe-workspace`
  identity and reach the control plane via the tailnet-internal
  hostname `exe-coder` (resolved by Tailscale MagicDNS). The
  bootstrap script's `CODER_ACCESS_URL` is overridden per-template
  to `http://exe-coder:7080`, so the binary download bypasses the
  public CF Access edge entirely.

## Decision

Adopt B-plan.

### Tailscale layer

- New tag `tag:exe-workspace` (in `exe/tailscale/acl.hujson`) with
  ACL allow rule `tag:exe-workspace -> tag:exe-coder:7080`.
- New reusable + ephemeral auth key `tailscale_tailnet_key.exe_workspace`
  (in `tofu/exe/tailscale.tf`), `depends_on = [tailscale_acl.this]`
  to avoid issuing a key for a tag that the live ACL has not yet
  acknowledged (which the API rejects with HTTP 400
  "requested tags ... are invalid or not permitted").
- Auth key mirrored to Secret Manager
  (`exe-tailscale-workspace-authkey`).
- Workspace SA (`exe-workspace@…`) granted
  `roles/secretmanager.secretAccessor` on that secret.

### Coder server layer

- `CODER_HTTP_ADDRESS=0.0.0.0:7080` so the listener binds the
  tailnet interface (tun0) in addition to loopback.
- Cloudflare Argo Tunnel still terminates the public edge at
  `exe.hironow.dev`; only the workspace-internal path moves onto
  the tailnet.

### Coder workspace template layer

- `provider "coder" { url = var.coder_internal_url }` overrides the
  deployment-wide `CODER_ACCESS_URL`. Coder OSS renders this value
  into `${ACCESS_URL}` substitutions in `bootstrap_linux.sh` via
  `metadata.GetCoderUrl()` in `provisioner/terraform/provision.go`
  `provisionEnv()`.
- VM startup-script installs tailscale + gcloud, fetches the
  workspace authkey from Secret Manager, and runs
  `tailscale up --advertise-tags=tag:exe-workspace` BEFORE any
  step that depends on the agent binary.

### Auth chain (3-layer)

1. **CF Access edge** — browser OIDC or `cdr` service token
2. **Coder session** — OAuth or admin password (after edge auth)
3. **Workspace agent identity** — token issued by Coder, transported
   over the tailnet (no edge involvement)

## Consequences

### Positive

- **CF Access edge stays intact.** No `/bin/*` bypass; no precedent
  for poking holes in the edge for internal traffic.
- **Workspace binaries authenticated by tailnet-membership**, which
  is itself authenticated by the WireGuard auth key issued from
  Tailscale's admin plane and stored in Secret Manager.
- **MagicDNS gives stable hostnames.** `exe-coder` resolves to the
  control-plane VM's tailnet IP regardless of GCE-side IP changes.
- **Per-template override.** The `provider "coder" { url = ... }`
  is template-level, so the public CODER_ACCESS_URL still serves
  browser / cdr CLI traffic correctly.

### Negative

- **Three Tailscale auth keys to rotate** (`exe-coder`, `exe-workspace`,
  `agent`). All driven by `time_rotating.tailscale_keys` in
  `tofu/exe/tailscale.tf` (90-day cadence).
- **MTU-related warning spam.** GCP default MTU 1460 vs Tailscale's
  expectation; `magicsock disco: failed to send … sendto: message
  too long` once per few minutes in agent logs. Cosmetic; can be
  silenced with `tailscale up --mss-clamping` if desired.
- **Workspace boot depends on Tailscale + Secret Manager + tag ACL**
  all being healthy. A Tailscale outage would block new workspace
  creation; existing connected workspaces are unaffected.

### Neutral

- **Workspace VMs are still on the default VPC**, not exe-vpc. They
  are reachable to/from the public internet for outbound (for
  `apt-get`, `docker pull` etc.); ingress is gated by the firewall
  default-deny + the host running tailscaled.
- **The B-plan does not change Layer 2 cost characteristics.**
  Workspace VMs were going to need tailscaled regardless; the Layer
  2 design already assumes tailnet membership for the control
  plane.
- **A-plan is permanently retired.** Reintroducing the `/bin/*`
  bypass would require explicit ADR superseding this one.
