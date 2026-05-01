# tofu/

OpenTofu (1.10+) infrastructure-as-code stacks. Each subdirectory is an
isolated stack with its own backend / state file.

| Stack | Purpose |
|---|---|
| [`exe/`](./exe/) | `exe.hironow.dev` — GCE workspace + Tailscale + Cloudflare |

## Conventions

- `tofu` CLI only — never `terraform` (license boundary).
- Remote state in GCS bucket per stack; state encryption enabled.
- `terraform.tfvars` is gitignored. Real values live in GCP Secret
  Manager and are wired in via `data "google_secret_manager_secret_version"`.
- Run `tofu fmt -recursive` before commit.
