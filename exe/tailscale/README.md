# exe/tailscale/

Tailscale ACL and tag definitions for `exe.hironow.dev`.

## Tag model (Pattern A — tagged auth keys)

| Tag | Holder | Permitted destinations |
|---|---|---|
| `tag:owner` | hironow's personal devices | `*:*` (full tailnet) |
| `tag:exe-coder` | the Coder control-plane VM | `tag:exe-coder:*` (loopback over tailnet) |
| `tag:exe-workspace` | Coder workspace VMs | `tag:exe-coder:7080` (agent download + protocol — see [ADR 0004](../../docs/adr/0004-workspace-tailnet-routing.md)) |
| `tag:agent` | AI agents | `tag:exe-coder:22,80,443,3000-3999` |

## Files

| Path | Purpose |
|---|---|
| [`acl.hujson`](./acl.hujson) | Full ACL document, bound by `tailscale_acl.this` (`prevent_destroy`, `overwrite_existing_content`) |

Auth keys themselves are **never** committed here — they are
provisioned by OpenTofu into GCP Secret Manager
(`exe-tailscale-coder-authkey`, `exe-tailscale-workspace-authkey`,
`exe-tailscale-agent-authkey`) and rotated every 90 days via
`time_rotating.tailscale_keys` in
[`../../tofu/exe/tailscale.tf`](../../tofu/exe/tailscale.tf).

## Related docs

- [`../docs/architecture.md`](../docs/architecture.md) — full
  tailnet topology and trust boundary table
- [`../../docs/adr/0004-workspace-tailnet-routing.md`](../../docs/adr/0004-workspace-tailnet-routing.md)
  — why workspace VMs reach the Coder server over the tailnet
  instead of the public CF Access edge (B-plan)
- [`../../tofu/exe/tailscale.tf`](../../tofu/exe/tailscale.tf)
  — actual auth-key + ACL IaC
