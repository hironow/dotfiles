# exe/docs/

Documentation for `exe.hironow.dev`.

| File | Scope |
|---|---|
| [`usage.md`](./usage.md) | User-facing quick reference for the four `cdr` commands (`cdr`, `cdr-job`, `cdr-exec`, `cdr-header`) — what each does and when to pick which |
| [`architecture.md`](./architecture.md) | Components, data flow, security boundaries (Cloudflare + Tailscale + Coder + GCP) |
| [`runbook.md`](./runbook.md) | Operational playbook (apply, smoke, rotate keys, push template, bump Coder) |

Architectural decisions go in [`../../docs/adr/`](../../docs/adr/)
at the repository root — current state lives here, the "why" of
each decision lives there.

## Related docs

- [`../README.md`](../README.md) — `exe/` directory layout
- [`../coder/README.md`](../coder/README.md) — Coder template
- [`../scripts/README.md`](../scripts/README.md) — `cdr` wrapper
- [`../tailscale/README.md`](../tailscale/README.md) — ACL + tags
- [`../cloudflared/README.md`](../cloudflared/README.md) — Tunnel
- [`../../tofu/exe/README.md`](../../tofu/exe/README.md) — IaC
