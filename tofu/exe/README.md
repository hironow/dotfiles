# tofu/exe/

OpenTofu stack provisioning `exe.hironow.dev`.

## Inputs

| Variable | Default | Description |
|---|---|---|
| `gcp_project_id` | `gen-ai-hironow` | GCP project (single-project, single-stack) |
| `gcp_region` | `asia-northeast1` | Primary region |
| `gcp_zone` | `asia-northeast1-a` | Primary zone |
| `domain` | `exe.hironow.dev` | Cloudflare-managed apex |
| `tailnet` | (from `terraform.tfvars`, e.g. `hironow.github`) | Tailscale tailnet identifier |
| `coder_version` | `v2.31.11` | Pinned Coder server release tag (see [ADR 0007](../../docs/adr/0007-coder-server-install-hardening.md)) |
| `coder_sha256` | (see `variables.tf`) | Sha256 of `coder_<ver>_linux_amd64.tar.gz` from the release's `checksums.txt` |

## Files

| Path | Purpose |
|---|---|
| [`main.tf`](./main.tf) | Backend (GCS), providers, locals |
| [`variables.tf`](./variables.tf) | Input variables (incl. Coder pin) |
| [`outputs.tf`](./outputs.tf) | Workspace SA email, AR repo, control-plane URL |
| [`coder.tf`](./coder.tf) | Control-plane VM startup_script (Coder server install + cloudflared + tailscaled, with apt-key fingerprint pin) |
| [`tailscale.tf`](./tailscale.tf) | Tagged auth keys, ACL bootstrap, 90-day rotation |
| [`cloudflare.tf`](./cloudflare.tf) | Tunnel + Access policy + DNS records |
| [`artifact_registry.tf`](./artifact_registry.tf) | Dev container image AR repo (`devcontainer:main` + `devcontainer:<sha>`) |
| [`iam.tf`](./iam.tf) | Workload Identity Federation (GHA → AR) + workspace SA |
| [`locals.tf`](./locals.tf) | Hostnames, tag names |
| [`.terraform.lock.hcl`](./.terraform.lock.hcl) | Provider plugin lockfile (tracked) |

## State

Backend: GCS bucket `gs://gen-ai-hironow-tofu-state/exe/`
(bucket creation is a one-time bootstrap step; see
[`../../exe/scripts/bootstrap.sh`](../../exe/scripts/bootstrap.sh)).

State encryption: native `tofu` state encryption (1.7+) with passphrase
from `~/.config/tofu/exe.passphrase` (0600 mode, gitignored).

## Lifecycle

```bash
just exe-plan    # tofu plan
just exe-apply   # tofu apply
just exe-down    # tofu destroy (keeps state)
```

## Related docs

- [`../../exe/docs/architecture.md`](../../exe/docs/architecture.md)
  — full architecture diagram and trust boundary table
- [`../../exe/docs/runbook.md`](../../exe/docs/runbook.md) —
  operator workflow (apply, smoke, key rotation, Coder bump)
- [`../../docs/adr/`](../../docs/adr/) — architectural decisions
  (debian-12 dev container, prebuilt image, Actions hardening,
  tailnet routing, install path, mise pinning, Coder hardening)
- [`../../tests/exe/test_startup_script.py`](../../tests/exe/test_startup_script.py)
  — heredoc extraction + bash lint + systemd-analyze for the
  control-plane startup script
