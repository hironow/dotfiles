# exe/tailscale/

Tailscale ACL and tag definitions for `exe.hironow.dev`.

Tag model (Pattern A — tagged auth keys):

| Tag | Holder | Permitted destinations |
|---|---|---|
| `tag:owner` | hironow's devices | `*:*` |
| `tag:agent` | AI agents | `tag:exe-coder:22,80,443` only |

Files (added in subsequent commits):

- `acl.hujson` — full ACL document
- `*.authkey` — generated tagged keys, never committed
  (provisioned via OpenTofu into Secret Manager)
