# tofu/exe/

OpenTofu stack provisioning `exe.hironow.dev`.

## Inputs

| Variable | Default | Description |
|---|---|---|
| `gcp_project_id` | `gen-ai-hironow` | GCP project (single-project, single-stack) |
| `gcp_region` | `asia-northeast1` | (TBD) |
| `gcp_zone` | `asia-northeast1-a` | (TBD) |
| `domain` | `exe.hironow.dev` | Cloudflare-managed apex |
| `tailnet` | (from `tailscale_token` secret) | Tailscale tailnet identifier |

## Files (added in subsequent commits)

- `main.tf` — backend, providers, locals
- `variables.tf` — input variables
- `coder.tf` — GCE + Coder workspace (gcp-vm-container template)
- `tailscale.tf` — tagged auth keys, ACL bootstrap
- `cloudflare.tf` — Tunnel + Access policy + DNS records
- `outputs.tf` — workspace URL, tailnet IP, tunnel ID

## State

Backend: GCS bucket `gs://gen-ai-hironow-tofu-state/exe/`
(bucket creation is a one-time bootstrap step; see
`exe/scripts/bootstrap.sh`).

State encryption: native `tofu` state encryption (1.7+) with passphrase
from `~/.config/tofu/exe.passphrase` (700 mode, gitignored).

## Lifecycle

```bash
just exe-plan    # tofu plan
just exe-apply   # tofu apply
just exe-down    # tofu destroy (keeps state)
```
