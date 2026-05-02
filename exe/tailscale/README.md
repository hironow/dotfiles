# exe/tailscale/

Tailscale ACL for `exe.hironow.dev` (Pattern A — tagged auth keys).

| Path | Purpose |
|---|---|
| [`acl.hujson`](./acl.hujson) | Live ACL (`tailscale_acl.this`, `prevent_destroy`) |

Auth keys are issued by tofu and stored in Secret Manager
(`exe-tailscale-{coder,workspace,agent}-authkey`); see
[`../../tofu/exe/tailscale.tf`](../../tofu/exe/tailscale.tf) for
issuance + 90-day rotation.

Tag model and trust boundaries: [`../docs/architecture.md`](../docs/architecture.md#permission-model--pattern-a).
