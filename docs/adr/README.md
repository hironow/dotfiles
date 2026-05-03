# Architecture Decision Records (ADR)

This directory captures the **why** behind significant architecture
and tooling decisions across the dotfiles repository (local IDE
environment, Coder workspace, `exe.hironow.dev` stack, CI). Live
documentation under `docs/`, `exe/docs/`, and `tofu/exe/` describes
the **what** of the current implementation; this index points to the
recorded decisions that shaped it.

## Conventions

- File naming: `NNNN-short-title.md` (sequential, lowercase, hyphens)
- Status workflow: `Proposed` → `Accepted` → (`Deprecated` |
  `Superseded by [NNNN]`)
- Once `Accepted`, ADRs are **immutable**. To revisit a decision,
  write a new ADR that supersedes the old one and update the old
  ADR's status line — that is the only allowed modification.
- Template lives in [`CLAUDE.md`](../../CLAUDE.md) under
  `<adr-guidelines>`.

## Index

| #    | Title                                                                                       | Status                                       | Date       | Affects                          |
| ---- | ------------------------------------------------------------------------------------------- | -------------------------------------------- | ---------- | -------------------------------- |
| 0001 | [Migrate dev container to debian-12 + features (single SoT)](./0001-devcontainer-debian-features.md) | Accepted                                     | 2026-05-02 | `.devcontainer/`                 |
| 0002 | [Coder workspace template uses a prebuilt dev container image](./0002-coder-prebuilt-image.md)       | Accepted                                     | 2026-05-02 | `exe/coder/templates/`           |
| 0003 | [Pin GitHub Actions to commit SHAs and add Dependabot updates](./0003-actions-pin-sha.md)            | Accepted (PR #48)                            | 2026-05-02 | `.github/workflows/`             |
| 0004 | [Workspace VMs reach the Coder control plane over the tailnet (B-plan)](./0004-workspace-tailnet-routing.md) | Accepted (PR #47)                    | 2026-05-02 | `exe/coder/templates/`, `exe/tailscale/acl.hujson` |
| 0005 | [Rationalise install paths across Mac host and Coder workspace (Linux)](./0005-install-path-rationalization.md) | Accepted                          | 2026-05-02 | `install.sh`, `Brewfile`         |
| 0006 | [mise tool version pinning strategy](./0006-mise-version-pinning.md)                                 | Accepted                                     | 2026-05-02 | `mise.toml`                      |
| 0007 | [Coder server install hardening on the control-plane VM](./0007-coder-server-install-hardening.md)   | Accepted                                     | 2026-05-02 | `tofu/exe/coder.tf`, `tofu/exe/variables.tf` |
| 0008 | [Event-driven Coder workspace runner (GHA-style without GHA)](./0008-event-driven-workspace-runner.md) | Superseded by [0009](./0009-retract-cron-trigger-from-adr-0008.md) (partial — trigger source 2 retracted) | 2026-05-03 | `exe/coder/templates/dotfiles-job/`, `exe/scripts/cdr-job` |
| 0009 | [Retract the systemd-timer cron trigger from ADR 0008](./0009-retract-cron-trigger-from-adr-0008.md) | Accepted (2026-05-04 — cron infra reverted in PR #76, intentionally absent) | 2026-05-03 | retracts `tofu/exe` cron / systemd timer (none added) |
| 0010 | [Cloud SQL Postgres for Coder data plane](./0010-cloud-sql-postgres-for-coder.md)                    | Proposed                                     | 2026-05-03 | `tofu/exe/cloudsql.tf`, `tofu/exe/coder.tf`, `tofu/exe/monitoring.tf` |

## Reading order for newcomers

1. [`0001`](./0001-devcontainer-debian-features.md) — why debian-12
   with devcontainer features instead of an Alpine or Ubuntu base.
2. [`0002`](./0002-coder-prebuilt-image.md) — why a prebuilt image
   instead of envbuilder; same SoT as local IDE and CI.
3. [`0007`](./0007-coder-server-install-hardening.md) — supply-chain
   hardening on the control-plane VM (sha256 pin, no curl|bash).
4. [`0010`](./0010-cloud-sql-postgres-for-coder.md) — current data
   plane (Cloud SQL with IAM auth via CSAP `--auto-iam-authn`).
5. [`0008`](./0008-event-driven-workspace-runner.md) followed by
   [`0009`](./0009-retract-cron-trigger-from-adr-0008.md) — read as a
   pair: 0008 framed the runner; 0009 retracted its cron trigger
   while keeping the operator-pulled job runner.

## Related

- [`../../CLAUDE.md`](../../CLAUDE.md) — ADR template + when to write
  one (`<adr-guidelines>` section)
- [`../../exe/docs/architecture.md`](../../exe/docs/architecture.md)
  — current `exe.hironow.dev` architecture
- [`../../tofu/exe/README.md`](../../tofu/exe/README.md) — IaC overview
