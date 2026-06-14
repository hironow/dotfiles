# 0027. Bun-only Node policy: retire the per-repo pnpm carve-out

**Date:** 2026-06-14
**Status:** Accepted
**Supersedes:** [0017](./0017-retire-pnpm-global-for-corepack.md) (partial — only
the per-repo pnpm fallback carve-out at the **agent-policy** layer; ADR 0017's
corepack/mise global-CLI **machine provisioning** is unchanged and in force)

## Context

ADR 0017 retired the pnpm-global subsystem but kept pnpm as a per-repo fallback:
"`bun` is the default and `pnpm` is a fallback used only when a repo carries a
`pnpm-lock.yaml`." That carve-out was encoded in three agent-facing places:

- `ROOT_AGENTS.md`: "`bun` only for Node, **unless `pnpm-lock.yaml` exists**
  (then `pnpm`)."
- the command guard `block-prohibited-commands.py`: `pnpm` was allowed when a
  `pnpm-lock.yaml` governed the invocation's target directory (a per-invocation
  lockfile gate with `cd`/`-C`/`--dir` resolution), and `corepack pnpm` was not
  caught at all.
- `ROOT_AGENTS_docs_agents_enforcement.md` describing that gate.

The lockfile gate added real parsing complexity (directory tracking, upward
lockfile search, fail-safe-on-unresolvable) for a fallback the operator no
longer wants agents to reach. The decision is to make Node tooling **bun-only**
at the agent layer: no `npm`, `yarn`, or `pnpm` — including `corepack pnpm`.

This is explicitly a **policy-layer** change. ADR 0017's machine provisioning —
`corepack enable` in `install.sh` and the dev-container feature, `PNPM_HOME` as a
store-dir anchor, `npm "corepack"` in `dump/Brewfile`, global CLIs via mise's
`npm:` backend — is intentionally **retained**. corepack is a node-shipped shim;
removing it is a separate, larger teardown (out of scope here).

## Decision

**Node package management is `bun` only. Agents may never run `npm`, `yarn`, or
`pnpm`, and may not run a package manager through `corepack` (`corepack pnpm`,
`corepack yarn`, `corepack npm`). The `pnpm-lock.yaml` carve-out is removed.**

Concretely:

- The command guard treats `pnpm` like `npm`/`yarn`: an unconditional block as a
  command name (`NODE_COMMANDS`), regardless of any `pnpm-lock.yaml`. The
  per-invocation lockfile gate (`_check_pnpm`, `find_pnpm_lock_upward`,
  `cd`/`-C`/`--dir` target resolution) is deleted as now-dead code.
- The guard detects the **direct PM-run form** of corepack and blocks it:
  `corepack <pm>[@version] …`, with corepack's own flags and their values
  skipped first (`corepack --cwd /x pnpm …`) and the `@version` suffix stripped
  before matching (`corepack pnpm@9 …`). Provisioning subcommands —
  `corepack enable` / `prepare` / `use` — pass through, since their first
  positional is the subcommand name, not a PM. This keeps ADR 0017's machine
  provisioning workable.
- `ROOT_AGENTS.md` and `ROOT_AGENTS_docs_agents_enforcement.md` state bun-only;
  the lockfile-gate prose is removed.
- settings.json `permissions.deny` (global `~/.claude` hand-applied + the repo's
  `.claude/settings.json`) denies `Bash(npm:*)` `Bash(npx:*)` `Bash(pnpm:*)`
  `Bash(pnpx:*)` `Bash(yarn:*)`. `corepack pnpm` is covered by the guard, not
  settings (the space-prefixed colon form is unreliable). `npx`/`pnpx` are not
  guard-blocked (they do not write lockfiles, so the desync rationale does not
  apply) but are settings-denied — a deliberate per-layer division of labor.

### Accepted scope of corepack detection

- **Caught:** `corepack pnpm …`, `corepack pnpm@9 …`, `corepack --cwd /x pnpm …`,
  `corepack yarn …`, `corepack yarn@4 …`, `corepack npm …`.
- **Allowed (provisioning, by design):** `corepack enable`, `corepack prepare
  pnpm@latest --activate`, `corepack use …` — first positional is a subcommand,
  not a PM.
- **Accepted gap (long tail):** wrapper forms outside the known set
  (`mise exec -- pnpm …`, `bash -c "pnpm i"`) slip the tokenizer, same as the
  existing npm/yarn long tail; prose rules + review cover them.

## Enforcement inventory

This ADR pins the invariant: **agents never run npm/yarn/pnpm (incl.
`corepack <pm>`); Node tooling is bun.**

### Entry points

- `ROOT_AGENTS_hooks_block-prohibited-commands.py` — the synced command guard
  (distributed to every claude-family agent home by `just sync-agents`). This is
  the only cross-agent enforcement path: `sync_agents.py` merges the hook blocks
  but **not** the `permissions` key, so settings deny is per-home, not synced.
- `tests/unit/test_agent_hooks.py` — pins the block list and the corepack forms.
- `ROOT_AGENTS.md` / `ROOT_AGENTS_docs_agents_enforcement.md` — the prose rule
  (the *why*, covering the long tail a hook can't pattern-match).
- settings.json `permissions.deny` — the permission-layer belt for the main
  agent on each machine.

### Bypass candidates ("where can this go wrong?")

- Re-adding a `pnpm-lock.yaml` carve-out to the guard.
- A wrapper form (`mise exec -- pnpm`, `bash -c`) — accepted long tail.
- A new corepack value-flag that consumes its operand and is not in
  `COREPACK_VALUE_FLAGS` (only `--cwd` is handled today).

### Tests proving coverage

- `tests/unit/test_agent_hooks.py::test_pnpm_with_lockfile_is_still_blocked`
  — pnpm is blocked even with a `pnpm-lock.yaml` present (the carve-out is gone).
- `::test_corepack_pnpm_is_blocked` / `::test_corepack_pnpm_versioned_is_blocked`
  / `::test_corepack_cwd_flag_pnpm_is_blocked` / `::test_corepack_yarn_is_blocked`
  — the direct corepack PM-run forms block.
- `::test_corepack_enable_is_allowed` — provisioning subcommands pass through.

## Consequences

### Positive

- One Node package manager (bun), no conditional fallback — simpler mental model
  and a simpler guard (the lockfile-gate parser and its directory tracking go).
- `corepack pnpm` is no longer a silent bypass of the npm/yarn block.

### Negative

- A genuine per-repo pnpm need (a repo that only ships a `pnpm-lock.yaml`) can no
  longer be served by an agent directly; the operator must run it via the `!`
  prefix, or the repo must migrate to bun.

### Neutral

- ADR 0017's corepack/mise/`PNPM_HOME` machine provisioning is untouched —
  corepack remains installed and `corepack enable`/`prepare` still work for
  humans and build steps.
- `justfile` `doctor` still reports `pnpm`/`npm` versions if present on the host
  (a Layer-B provisioning probe). It is mild documentation drift against the
  agent-layer ban but harmless, and is left for a future provisioning-teardown
  ADR should one happen.
