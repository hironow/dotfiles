# 0029. Gate the distributed Claude config with claudelint + official plugin validate

**Date:** 2026-06-22
**Status:** Accepted (PR #200)

## Context

This repo is a source of truth for Claude tooling: `just sync-agents` distributes
**skills, plugins, hooks, agents, and settings** to every agent home
(`~/.claude*`, `~/.codex`, `~/.gemini`). Until now none of these artifacts was
machine-checked. A malformed plugin manifest, a hook with the wrong matcher shape,
or an agent whose `tools` field is a comma-string instead of a list would sync and
ship silently — the first signal would be a broken agent at runtime. Applying a
linter surfaced exactly one such latent defect: `agents/test-generator.md` declared
`tools: Read, Grep, Glob, Write` (a comma-string; valid Claude Code frontmatter but
not the canonical list form).

As of 2026-06 two checker families exist:

- **Official `claude plugin validate [--strict] <path>`** — bundled with Claude
  Code, deterministic, validates plugin/marketplace manifests and the skill /
  agent / command / hook files they reference. Requires the `claude` binary.
- **claudelint** (npm `claude-code-lint`, MIT, run via `bunx`) — `validate-{skills,
  hooks,settings,plugin,agents}`, the only single tool that covers all of the
  artifact kinds this repo distributes.

Key facts that shaped the design:

- This repo's CI **never runs `just ci`**. It runs individual jobs:
  `unit-test.yaml` (`uvx pytest tests/unit/`), `test-just.yaml` (the sandbox
  `just test`), plus iac / shellcheck / etc. Wiring a check only into `just ci`
  therefore gates **locally only** — a PR would not be blocked.
- Runners are **`ubuntu-latest` (GitHub-hosted)**, with neither `bun` nor the
  `claude` binary preinstalled. The `oven-sh` setup action is not on this repo's
  Actions allowlist; bun is installed via the official `bun.sh` script.

## Decision

1. **`just lint-claude` recipe** (wired into `just ci` for the local gate). It runs
   the claudelint validators against the owned artifacts plus the official
   validator as a second pair of eyes:
   - `validate-agents` / `validate-settings` / `validate-hooks` — root-owned files.
   - `validate-skills --path plugins` — owned skills only.
   - `validate-plugin --path plugins/<name>/.claude-plugin/plugin.json` per plugin.
   - `claude plugin validate --strict` over the marketplace and each plugin,
     **skipped when the `claude` CLI is absent** (so it runs locally without
     breaking CI runners).
2. **Dedicated `.github/workflows/claude-lint.yaml`** runs the claudelint half on
   every PR/push, because CI never runs `just ci`. bun is installed via
   `curl bun.sh`; the `claude` binary is absent on runners, so CI runs the
   claudelint validators only (the official validate stays local).
3. **Pin `claude-code-lint@0.5.0`** and pass **`--no-config`** on every invocation.
   The pin is a deliberate carve-out from the repo's forward-by-default version
   policy: a new claudelint release can add rules that turn CI red with no code
   change, and because `bunx` is not in any lockfile, Dependabot cannot see or bump
   it — so the bump is intentional and manual. `--no-config` stops claudelint from
   discovering a config file as far up as `$HOME`, which would make rule selection
   and exit codes diverge between a developer machine and CI.
4. **Run claudelint itself, not a pure-Python reimplementation of its rules.** The
   alternative — re-encoding the checks as `tests/unit/` so CI needs no bun — was
   rejected: it would drift from the real tool the team runs locally and duplicate
   maintenance. The cost is a bun install + a pinned external dependency in CI.

## Enforcement inventory

- `just lint-claude` (`[group('Lint')]`), a dependency of `just ci` — the local
  fast gate.
- `.github/workflows/claude-lint.yaml` (`Claude Config Lint`) — the PR gate, since
  CI runs individual jobs rather than `just ci`. Checkout is SHA-pinned (ADR 0003)
  with `submodules: false`.
- `tests/unit/test_marketplace_manifest.py` (pre-existing) — covers
  `.claude-plugin/marketplace.json` (claudelint's `validate-plugin` does not), so
  the marketplace is gated in CI without the `claude` binary.

### Scope traps (why the invocations look the way they do)

- `validate-plugin` run at the repo root is a **silent no-op** (root has no
  `plugin.json`; its patterns are root-relative and non-recursive). It must target
  each manifest **file** — `--path <dir>` fails with `EISDIR`.
- `validate-skills` has a recursive `**/.claude/skills/*/SKILL.md` pattern that
  would descend into the vendored `skills/` submodule, so it is scoped with
  `--path plugins` (owned skills live only under `plugins/`).
- Vendored submodules are **not** excluded by claudelint's defaults
  (`node_modules/**`, `.git/**`, `.gitignore`); `submodules: false` at checkout is
  the structural guard in CI.
- Per-validator subcommands write no cache (the `.claudelint-cache` directory and
  the `--no-cache` flag belong to `check-all` only), so no artifact leaks into the
  tree.

## Consequences

### Positive

- Structural regressions in the Claude config this repo distributes — malformed
  manifests, wrong hook/agent frontmatter shapes, broken skill references — are
  caught at PR time instead of at agent runtime.

### Negative

- `claude-code-lint` is pinned and invisible to Dependabot, so it floats
  un-bumped until someone updates the version string by hand.
- Each CI run installs bun and resolves the pinned package over the network; a
  bun.sh or npm-registry outage turns the `Claude Config Lint` job red. Accepted as
  a low-frequency risk; the pin keeps the resolution cacheable and stable.
- claudelint is a single-maintainer MIT tool; an upstream change in rule behavior
  is mitigated by the version pin.

### Neutral

- The official `claude plugin validate` half runs only in `just lint-claude`
  (local), never in CI, because the `claude` binary is not installed on GitHub
  runners. CI relies on claudelint + the marketplace unit test for manifest
  coverage.
