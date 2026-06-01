# 0017. Retire the pnpm-global subsystem in favor of corepack + mise npm

**Date:** 2026-06-02
**Status:** Accepted

## Context

This repo maintained **two parallel declarative systems** for global Node
CLIs:

1. **mise npm: backend** — `mise.toml` pins AI CLIs as `"npm:@openai/codex"`
   etc. (ADR 0006). This is the modern, version-pinned, SHA-consistency-checked
   path.
2. **pnpm-global subsystem** — a `dump/npm-global` manifest restored/updated by
   `just add-pnpm-g` / `update-pnpm-g(-safe)` / `check-pnpm-g`, wired into
   `install.sh` via `step_pnpm_globals`, with `PNPM_HOME` + global-bin PATH
   baked into `.zshrc` (host) and the dev container (`devcontainer.json`
   `containerEnv` + `/etc/profile.d/pnpm.sh` in the feature), and asserted by
   sandbox tests.

The two systems fight on `PATH` and double-own the same responsibility (make a
global CLI available declaratively). The friction surfaced when corepack-shipped
pnpm advanced from major 10 to 11: `pnpm list -g` reads the new global state
directory (`~/Library/pnpm/global/v11`) while every package installed under
pnpm 10 sits in `~/Library/pnpm/global/5`. The pnpm-global subsystem silently
broke — `pnpm list --global` reported "No global packages found" even though the
CLIs were physically present and still runnable via their bin shims. A
same-day band-aid (`263a222`, "path fix for pnpm") prepended `$PNPM_HOME/bin`
to keep `pnpm add -g` from aborting, deepening the dependence on a subsystem we
no longer want.

`pnpm` is not the daily Node package manager here: `bun` is the default and
`pnpm` is a fallback used only when a repo carries a `pnpm-lock.yaml`. That makes
a globally-managed pnpm an over-investment.

## Decision

**Retire the pnpm-global subsystem entirely. pnpm is provided per-repo by
corepack; global Node CLIs live exclusively in mise's npm: backend.**

Concretely:

- `pnpm` comes from **corepack** (the package-manager shim shipped with node).
  Each project pins its version via the `packageManager` field; corepack runs
  that exact version on demand. `install.sh` and the dev container feature
  run `corepack enable` (guarded by `command -v corepack`).
- The dump-manifest provisioning (`dump/npm-global`, `add-pnpm-g`,
  `update-pnpm-g`, `update-pnpm-g-safe`, `check-pnpm-g`, `step_pnpm_globals`)
  is removed.
- `PNPM_HOME` global-bin is no longer prepended to `PATH` on host or in the
  container. `export PNPM_HOME` is kept on host only so the content-addressed
  **store** stays at `~/Library/pnpm/store` (shared by per-project
  `pnpm install`); deliberately omitting the global-bin from PATH makes
  `pnpm add -g` abort, steering global installs to mise.
- New global CLIs are declared in mise's npm: backend (`mise.toml` for the
  dev-container/workspace set, host global mise config for host-only tools).
- `check-pnpm-dlx` + `dump/npm-dlx` are **kept**: `pnpm dlx` is ephemeral
  execution, not a global install, and remains valid under corepack.

## Enforcement inventory

This ADR pins the invariant: **pnpm is never installed globally; global Node
CLIs always go through mise npm:.**

### Entry points

- `install.sh` bootstrap (`step_corepack`) — host day-1 provisioning.
- `.devcontainer/features/dotfiles-tools/install.sh` — dev container build.
- `.devcontainer/devcontainer.json` `containerEnv.PATH` — runtime PATH layout.
- `.zshrc` — host interactive shell PATH/env.
- `justfile` add/update/check recipe families — operator-driven provisioning.

### Persistent / carried data needed at each enforcement point

- `corepack` binary on PATH (from `npm "corepack"` in `dump/Brewfile`, or the
  dev container node feature).
- `mise.toml` npm: pins for the global CLI set (SHA-consistency-checked against
  the feature's `/etc/mise/config.toml` heredoc per ADR 0006).
- `PNPM_HOME` (host) pointing at the store root only.

### Bypass candidates ("where can this go wrong?")

- A future edit re-adding `pnpm add -g` / `add-pnpm-g` to `install.sh` or the
  justfile.
- Re-prepending `$PNPM_HOME/bin` to PATH in `.zshrc` or `devcontainer.json`,
  re-enabling silent global installs.
- A new `dump/npm-global`-style manifest.

### Tests proving coverage

- `tests/test_install_os_dispatch.py::test_install_sh_enables_corepack_not_pnpm_globals`
  — asserts `install.sh` runs `corepack enable` and contains neither
  `step_pnpm_globals` nor `add-pnpm-g`.
- `tests/test_install_os_dispatch.py` `REQUIRED_STEPS` — pins `step_corepack`
  as a named, invoked step.
- `tests/test_mise_pin_consistency.py::test_system_mise_config_matches_workspace_mise_toml`
  — keeps mise.toml ↔ feature heredoc in lockstep, so the npm: SoT cannot drift.
- `tests/test_just_sandbox.py` — no longer exercises pnpm-global recipes; the
  `add-all` guard test no longer seeds `dump/npm-global`.

## Consequences

### Positive

- One declarative system for global CLIs (mise npm:), not two.
- pnpm version is per-repo and correct-by-construction via `packageManager`.
- The pnpm major-bump breakage class (global state dir `5` vs `v11`) is gone.
- Less host/container PATH surface; `pnpm add -g` is naturally discouraged.

### Negative

- Global CLIs that previously lived in `dump/npm-global`
  (`@smithery/cli`, `@vonage/cli`, `ajv-cli`, `surge`, `takt`) are retired;
  any still wanted must be re-declared in mise npm: explicitly.
- corepack download-on-demand interacts with the npm `min-release-age`
  quarantine; brand-new pnpm versions may need a one-off override.

### Neutral

- `portless` (a host-only local-dev CLI, already a mise npm: tool, never part of
  `dump/npm-global`) is unaffected functionally. Fully repo-tracking it depends
  on bringing the host global mise config into the repo, tracked separately.
- `export PNPM_HOME` remains on host purely as the store-dir anchor.
