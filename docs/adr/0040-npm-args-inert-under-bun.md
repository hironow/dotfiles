# 0040. `npm_args` is inert under the bun backend — drop it, correct ADR 0036's rationale

**Date:** 2026-08-15
**Status:** Accepted

## Context

ADR 0036 switched mise's npm backend to bun and kept
`npm_args = "--ignore-scripts=false"` on the claude-code entry, reasoning
that "bun accepts it, and it remains correct intent: the postinstall is what
puts the binary in place."

Half of that is wrong, verified two independent ways on 2026-08-15:

- **mise never passes `npm_args` to bun.** mise's `NpmOptions` reads a
  per-package-manager key — `npm_args` for npm, `bun_args` for bun,
  `pnpm_args` / `aube_args` likewise — with no shared fallback
  (mise `src/backend/npm.rs`). Under `package_manager = "bun"` the option is
  silently dead config.
- **The binary works for a different reason.** `@anthropic-ai/claude-code`
  is on bun's **default-trusted dependencies list** (`bun pm
  default-trusted`, 368 entries), so bun runs its postinstall without any
  flag; `install.cjs` then hardlinks the real native binary from the
  platform optionalDependency. Measured on this host: mise's bun install of
  2.1.225 has `bin/claude.exe` at 287 MB with hardlink count 3 — the
  postinstall's signature — while `npm_args` sat unread.

The false causal claim had already propagated: `config/mise/config.toml`'s
comment, the repo CLAUDE.md trap list, and the devcontainer feature comment
all credited `npm_args` (or "bun never runs postinstalls") for the working
binary. Wrong causality here is load-bearing: someone renaming the option to
`bun_args` "to make it effective", or trusting `npm_args` to protect a
future npm-tool with a postinstall NOT on bun's trusted list, would be
misled.

## Decision

- Remove the inert `npm_args` from the claude-code entries
  (`config/mise/config.toml`; the devcontainer feature already dropped it in
  ADR 0039's PR) and rewrite the comments to state the verified mechanism:
  bun runs claude-code's postinstall because the package is default-trusted,
  and mise reads `bun_args`, not `npm_args`, under the bun backend.
- ADR 0036's Decision section is amended by this ADR (status-line link);
  its body stays immutable per the ADR contract. The decision it made —
  bun over aube — is unchanged and remains in force.
- Future npm-backend tools whose postinstall must run but which are NOT on
  bun's default-trusted list need `bun_args` (or a `trustedDependencies`
  mechanism), not `npm_args` — that is the check to make when adding one.

## Consequences

- `config/mise/config.toml` and the devcontainer feature agree with mise's
  actual behavior; deleting the option changes nothing at runtime (verified
  inert), so this is a pure record correction plus config hygiene.
- The repo CLAUDE.md trap list and the `project_mise_npm_ignore_scripts`
  memory note are updated to point at the real mechanism.
- If mise's bun path ever gains lifecycle-script control, or bun drops
  claude-code from its default-trusted list, the failure mode returns as a
  500-byte stub (ADR 0036's table) — the doctor/`claude --version` check
  after upgrades remains the tripwire.
