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
- `.terraform.lock.hcl` IS tracked (HashiCorp recommends this; per
  [PR #62](https://github.com/hironow/dotfiles/pull/62)). The
  runtime cache dir `.terraform/` and state files stay ignored.
- Run `tofu fmt -recursive` before commit.

## Related docs

- [`exe/README.md`](./exe/README.md) — exe.hironow.dev stack
  (variables, files, lifecycle, state)
- [`../exe/docs/architecture.md`](../exe/docs/architecture.md)
  — full architecture and trust boundary table for the stack
- [`../docs/adr/`](../docs/adr/) — Architecture Decision Records
