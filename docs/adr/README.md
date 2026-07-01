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
| 0011 | [exe-coder workspace VM multi-project systemd env delivery](./0011-exe-multi-project-systemd-env.md) | Accepted | 2026-05-07 | `exe/coder/templates/`, `exe/scripts/` |
| 0012 | [exe-coder workspace VM RUNOPS_ACTOR_TYPE env injection (per caller path)](./0012-exe-actor-type-env-injection.md) | Accepted | 2026-05-09 | `exe/coder/templates/`, `exe/scripts/cdr-exec` |
| 0013 | [Project lifecycle severity classification (= cdr-project / runops project)](./0013-project-lifecycle-severity-classification.md) | Proposed | 2026-05-09 | `exe/` runops project lifecycle |
| 0014 | [Vendor emulator and telemetry from submodules into dotfiles](./0014-vendor-emulator-telemetry-from-submodules.md) | Accepted | 2026-05-30 | `emulator/`, `telemetry/` |
| 0015 | [Adopt portless for stable .localhost URLs of local HTTP UIs](./0015-adopt-portless-for-local-dev-urls.md) | Accepted | 2026-05-30 | `config/portless-aliases.yaml`, `docs/portless-urls.md` |
| 0016 | [Integrate vercel-labs/emulate API emulators via npx wrapper](./0016-integrate-emulate-api-emulators-via-npx.md) | Accepted | 2026-05-30 | `emulator/emulate/`, `justfile` (`emu-api`) |
| 0017 | [Retire the pnpm-global subsystem in favor of corepack + mise npm](./0017-retire-pnpm-global-for-corepack.md) | Accepted; partial supersede by [0027](./0027-bun-only-retire-per-repo-pnpm-carveout.md) | 2026-06-02 | `mise.toml`, `install.sh`, `dump/npm-global` |
| 0018 | [Windows native: minimum-viable deploy with explicit-skip step_*](./0018-windows-native-mvp.md) | Accepted | 2026-06-02 | `install.sh`, `justfile` (Windows deploy) |
| 0019 | [Windows scoop manifest in `dump/` — record-only](./0019-windows-scoop-dump-record-only.md) | Accepted; partial supersede by [0030](./0030-per-host-dump-layout.md) | 2026-06-02 | `dump/scoop.json`, `justfile` |
| 0020 | [Normalize shell-script line endings via `.gitattributes`](./0020-normalize-shell-script-line-endings.md) | Accepted | 2026-06-02 | `.gitattributes` |
| 0021 | [Split git config via `[include]` so dotfiles owns aliases + shared settings](./0021-git-config-include-split.md) | Accepted | 2026-06-02 | `~/.gitconfig`, `config/git/` |
| 0022 | [PowerShell `$PROFILE` starship init from `just deploy` (Windows native)](./0022-powershell-starship-profile-init.md) | Accepted | 2026-06-02 | PowerShell `$PROFILE` |
| 0023 | [Use `mise activate` only in interactive shells, drop manual `shims` PATH entries](./0023-mise-activate-only-no-shims-path.md) | Accepted | 2026-06-02 | `.zshrc`, `mise.toml` |
| 0024 | [PowerShell `$PROFILE` mise activate from `just deploy` (Windows native)](./0024-powershell-mise-activate-profile.md) | Accepted | 2026-06-02 | PowerShell `$PROFILE`, `mise.toml` |
| 0025 | [Wrap mise-managed tools at every justfile call site (補強 of ADR 0023)](./0025-justfile-mise-tool-wrap.md) | Accepted | 2026-06-02 | `justfile` |
| 0026 | [Antigravity CLI: instruction 層のみ共有、skills/settings/mcp は agy 委譲](./0026-antigravity-cli-instruction-layer.md) | Accepted | 2026-06-10 | `~/.gemini/GEMINI.md`, `scripts/sync_agents.py` |
| 0027 | [Bun-only Node policy: retire the per-repo pnpm carve-out](./0027-bun-only-retire-per-repo-pnpm-carveout.md) | Accepted | 2026-06-14 | `.claude/` hooks, `ROOT_AGENTS*` |
| 0028 | [Standardize on the Flatt Security PyPI mirror as the default uv index](./0028-flatt-pypi-mirror-default-index.md) | Accepted | 2026-06-19 | `*/pyproject.toml`, `*/uv.lock` |
| 0029 | [Gate the distributed Claude config with claudelint + official plugin validate](./0029-claude-config-lint-gate.md) | Accepted (PR #200) | 2026-06-22 | `justfile`, `.github/workflows/claude-lint.yaml` |
| 0030 | [Per-host dump layout (`dump/<host>/`)](./0030-per-host-dump-layout.md) | Accepted | 2026-07-01 | `justfile`, `scripts/dump_host.sh`, `dump/<host>/`, `install.sh` |

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
