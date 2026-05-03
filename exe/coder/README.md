# exe/coder/

Coder workspace templates for `exe.hironow.dev`.

The active template is based on
[`coder/coder/examples/templates/gcp-vm-container`](https://github.com/coder/coder/tree/main/examples/templates/gcp-vm-container)
(per [ADR 0002](../../docs/adr/0002-coder-prebuilt-image.md)) and
runs the prebuilt dev container image from Artifact Registry.
Workspace == CI environment because the same
`.devcontainer/devcontainer.json` drives both.

## Layout

| Path | Purpose |
|---|---|
| [`templates/dotfiles-devcontainer/`](./templates/dotfiles-devcontainer/) | Long-lived interactive workspace template (`main.tf` + lockfile + README). Operator's daily IDE / SSH target. |
| [`templates/dotfiles-job/`](./templates/dotfiles-job/) | Ephemeral one-shot headless runner template (`main.tf` + lockfile + README) per [ADR 0008](../../docs/adr/0008-event-driven-workspace-runner.md). Driven by the [`cdr-job`](../scripts/cdr-job) wrapper. |

## Related docs

- [`../docs/architecture.md`](../docs/architecture.md) — full
  `exe.hironow.dev` architecture (Cloudflare + Tailscale + Coder + GCP)
- [`../docs/runbook.md`](../docs/runbook.md) — operator workflow
  (`cdr templates push`, smoke, key rotation)
- [`../scripts/`](../scripts/) — `cdr` wrapper used by this
  template's push procedure
- [`../../tofu/exe/coder.tf`](../../tofu/exe/coder.tf) — control-
  plane VM that hosts the Coder server this template registers with
- [`../../docs/adr/0002-coder-prebuilt-image.md`](../../docs/adr/0002-coder-prebuilt-image.md)
  — why prebuilt image instead of envbuilder
- [`../../docs/adr/0007-coder-server-install-hardening.md`](../../docs/adr/0007-coder-server-install-hardening.md)
  — Coder server install pinning
