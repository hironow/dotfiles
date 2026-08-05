# 0037. Layered Claude settings fragments (shared / OS / profile / machine-local)

**Date:** 2026-08-05
**Status:** Accepted
**Supersedes:** [0027](./0027-bun-only-retire-per-repo-pnpm-carveout.md) (partial —
only the "settings `permissions` is per-home, not synced" stance; the bun-only
policy and every other layer of ADR 0027 are unchanged and in force)

## Context

The five claude-family homes (`~/.claude`, `~/.claude-work-{a,b,c,d}`) drifted
badly under the single flat `settings.shared.json` fragment:

- The `env` vocabulary forked into two generations: `~/.claude` carried a
  legacy 11-key set (including dead unprefixed names like
  `CLAUDE_AUTO_BACKGROUND_TASKS`), while the four work homes shared a separate
  18-key tuning set.
- The npm/npx/pnpm/pnpx/yarn `permissions.deny` guard existed only in
  `~/.claude` — the work homes had no settings-layer package-manager belt.
- The 23-entry `skillOverrides` map was hand-synced across the work homes but
  missing from `~/.claude`; worse, the shared fragment carried
  `"skillOverrides": {}`, which the next `sync-agents all` would have
  upsert-wiped into all four work homes (live bug).
- Keys identical in all five homes (`theme`, `model`, `language`, notification
  flags) were unmanaged and only consistent by hand.
- Intentional per-profile diffs (effortLevel medium vs xhigh, permissions
  posture, tui) had no declarative home, and nothing supported win/mac/linux
  variation.

Two prior assumptions turned out false during review:

- **`settings.local.json` is project-scope only.** Claude Code does not read
  `~/.claude/settings.local.json` at user scope (official settings hierarchy),
  so the documented "machine-local env escapes to settings.local.json"
  convention never worked. The wholesale env ownership therefore had no valid
  machine-local escape hatch.
- **`DISABLE_AUTOUPDATER=1` does not moot `minimumVersion` /
  `autoUpdatesChannel`**: it stops background checks only; manual
  `claude update` still uses the channel, and `minimumVersion` still acts as a
  downgrade floor. Both keys stay valid per-home state.

## Decision

Compose the settings desired-state from four layers (later wins), then apply it
through the existing single update-in-place merge in `sync_agents.py`:

1. `.claude/settings.shared.json` — all OS / all profiles. Now owns the common
   UX keys (`theme`, `language`, `model`, `includeGitInstructions`,
   `promptSuggestionEnabled`, notification flags), the full 23-entry
   `skillOverrides` map, `permissions.deny` (npm guard, everywhere), and the
   canonical env block. The canonical env is the **original git-managed
   fragment set** (11 keys, with the two dead unprefixed names modernized to
   their `CLAUDE_CODE_` successors) — NOT a union with per-home state: the
   work homes' 14 hand-applied tuning keys (`MAX_THINKING_TOKENS`,
   `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`, `DISABLE_AUTOUPDATER`,
   `ENABLE_TOOL_SEARCH`, output-length caps, ...) do not get promoted into
   the source of truth and drop everywhere on the next sync. Anything
   genuinely wanted again re-enters via a fragment layer (shared, profile,
   or machine-local) as a reviewed change.
2. `.claude/settings.shared.{macos,linux,windows}.json` — overlay for the OS
   running the sync (`platform.system()` map). Missing file = empty layer.
   Initially only `macos.json` (`preferredNotifChannel: "ghostty"` — a property
   of the OS/terminal environment, not of a profile).
3. `.claude/settings.profiles/<AgentTarget.key>.json` — intentional per-profile
   diffs (effortLevel, permissions.defaultMode, skipAutoPermissionPrompt, tui,
   teammateMode, ...), git-managed and reviewable.
4. `<agent_home>/settings.sync-local.json` — machine-local, untracked,
   user-owned, read by sync as the final layer. This replaces the invalid
   `settings.local.json` convention: machine-specific env and
   `permissions.allow` live here and survive the wholesale env ownership.

Composition rules: `env` merges key-wise (later wins) and the composed block is
applied **wholesale** to the target (dropped keys vanish — that is how the
legacy env retires). `settings` merges key-wise with a **one-level deep-merge
when both sides are dicts** (so shared owns `permissions.deny` while a profile
owns `permissions.defaultMode`); application into the target remains the
existing per-top-level-key upsert. Top-level key deletion is still not
propagated (v1).

Windows hook rendering: hook commands render as `sh "<home posix path>/hooks/x.sh"`
on Windows (elsewhere unchanged `bash "..."`). Bare `bash` on Windows resolves
to the System32 WSL bash first (documented hazard); `sh` has no System32
shadow and resolves to Git for Windows' sh — the same strategy as the
justfile's `set windows-shell := ["sh", ...]`. Managed-block detection
normalizes `\` to `/` before matching so pre-existing backslash-rendered
blocks are recognized and replaced instead of duplicated. Git's sh is bash, so
the existing hook scripts run unchanged.

Deliberately **unmanaged** (never in fragments): `enabledPlugins` and
`extraKnownMarketplaces` (large/churny, runtime-mutated by the plugin CLI, and
the marketplace entries embed machine-absolute paths like
`/Users/.../dotfiles/...` that would break cross-platform — same delegation
rationale as ADR 0026's skills stance), `feedbackSurveyState`,
`skipWorkflowUsageWarning`,
`minimumVersion`, `autoUpdatesChannel`, `$schema`, `statusLine` (only
`~/.claude` has one and its script is not a `ROOT_*` source — a follow-up may
distribute it hooks-style with path rendering), and `hooks` (owned by the hook
merge).

Validation: claudelint only auto-detects `.claude/settings.json` /
`.claude/settings.local.json` and cannot validate the `{env, settings}`
fragment wrapper, so `scripts/check_effective_settings.py` generates the
effective settings.json for every profile × OS and runs
`claudelint validate-settings` on the output; wired into both `just
lint-claude` and the `claude-lint` workflow (which does not run `just ci`).
The checker pins claude-code-lint@0.7.1 (0.5.0's settings schema predates
`permissions.defaultMode: "auto"` and string `teammateMode` and rejects
valid live settings).

## Consequences

- One `git pull && just sync-agents all` converges every machine (mac / linux /
  windows) and every profile to the declared state; drift becomes a reviewable
  diff in the repo instead of hand-edited JSON in five homes.
- The npm guard deny list now exists in all five homes (previously
  `~/.claude` only), partially superseding ADR 0027's per-home stance.
- Machine-local overrides move to `settings.sync-local.json`; anything left in
  a home's `settings.json` env that is not in the fragments is removed on the
  next sync (intended — that is the retirement mechanism).
- Integration tests in `tests/test_sync_agents.py` are not wired to any gate
  (`just test` runs the sandbox suite only); layered-composition coverage
  therefore lives in `tests/unit/` under `just ci`. Wiring the Docker
  integration suite to a gate is follow-up work.
- Windows hook execution switches from (shadow-prone) `bash` to `sh` on the
  next sync of a Windows machine; verification of `sh.exe` resolution and a
  live hook firing happens on that machine's next sync, not pre-merge.
