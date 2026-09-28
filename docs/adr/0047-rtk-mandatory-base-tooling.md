# 0047. rtk is mandatory base tooling and dotfiles owns its Claude hook

**Date:** 2026-09-29
**Status:** Accepted (operator directive, 2026-09-29).

## Context

`rtk` (Rust Token Killer) is a CLI proxy that compresses command output before
it reaches an agent's context. It has been in use on this machine for a while,
but entirely outside the dotfiles contract:

- the binary was a hand-placed 7.6 MB file at `~/.local/bin/rtk` (v0.45.0),
  not declared in `config/mise/config.toml` and not mentioned anywhere in the
  repo except the `rtk` spoke;
- its config (`~/Library/Application Support/rtk/config.toml`) is machine-local
  and untracked;
- its Claude Code PreToolUse hook was a machine-local line that rtk's installer
  wrote straight into `~/.claude*/settings.json` as
  `{"matcher": "Bash", "hooks": [{"command": "rtk hook claude"}]}`.

The operator has since ruled that rtk (with `headroom`) is a **base tool of the
environment, with no option not to use it**. That turns three latent problems
into standing ones.

**1. Worktree-isolated agents lose git.** rtk's hook rewrites a bare `git …`
into `rtk git …`. Claude Code's worktree-isolation guard reads the command
*after* hook rewrites, sees a launcher it cannot look through, and refuses the
whole call — for a command typed as a bare `git status --short`:

> …but this command runs rtk with a git command among its operands: what runs
> it, and from which directory or root, cannot be read here … so what it runs
> cannot be shown not to be git. Refusing to run it …

The message names rtk for a command the agent typed as `git`, which is how we
know the rewrite lands before the guard evaluates. Every `isolation: worktree`
subagent had to fall back to `/usr/bin/git` for all git work.

**2. The stray hook entry is unreproducible and sync preserves it.** Because
its command does not point at `<agent>/hooks/`, `_is_managed_hook_block`
classifies it as a user block, so `just sync-agents` keeps it forever and a new
machine does not get it at all.

**3. rtk laundered banned commands past the command guard.** `rtk` was not in
the guard's wrapper set, so the prefix carried any banned tool through.
Measured on the shipped guard before this ADR:

| command | guard |
| --- | --- |
| `pnpm install` | exit 2, blocked |
| `rtk pnpm install` | exit 0, allowed |
| `make --version` | exit 2, blocked |
| `rtk make --version` | exit 0, allowed |
| `rtk proxy pnpm install` | exit 0, allowed |
| `rtk err pip install foo` | exit 0, allowed |

Not reachable through rtk's own rewrite — Claude Code hands each hook the
*original* command and does not chain `updatedInput` between them (verified
live: `make --version` was still blocked). But an agent typing the prefix by
hand bypassed the bun-only and just-only non-negotiables.

Separately, rtk's hook answers `permissionDecision: "allow"` for everything it
rewrites, i.e. installing a token filter silently auto-approved most Bash
traffic.

## Decision

1. **rtk and headroom are mandatory base tools, installed through mise.** They
   are declared in the shared mise config and the devcontainer like any other
   Class 1 toolchain (ADR 0023 layout, ADR 0006 pinning). No repo or agent may
   opt out. (The mise/devcontainer declaration itself lands as separate work;
   this ADR fixes the policy and the hook contract.)

2. **dotfiles owns the Claude hook.** The PreToolUse entry is
   `hooks/rtk-hook-claude.sh`, a wrapper declared in
   `.claude/settings.hooks.json` and distributed by `just sync-agents`. It
   delegates to `rtk hook claude`, so rtk stays the single source of truth for
   what gets rewritten; deciding from rtk's own answer rather than re-deriving
   its command table means the wrapper cannot drift as rtk gains subcommands.

3. **The installer's `rtk hook claude` block is retired on every sync.**
   `RETIRED_HOOK_COMMANDS` in `scripts/sync_agents.py` drops it in the same
   pass that replaces managed blocks. Every run, not once: rtk is upgraded
   routinely now, and a reinstall that re-adds the entry would otherwise
   resurrect the old behavior silently. A block is retired only when *every*
   command in it is a retired one, so a hand-written block that merely also
   calls it is left alone.

4. **git is not rewritten inside a Claude Code isolation worktree.** When the
   tool's cwd is under `*/.claude/worktrees/*` and rtk proposes to put its
   launcher in front of `git`, the wrapper drops the rewrite and the plain
   command runs. The veto is git-only and worktree-only: everything else keeps
   rtk's compression, and outside such a worktree nothing changes. Isolation is
   detected from the path, because no `CLAUDE_*` environment variable marks
   such a session.

5. **rtk is an output optimiser, not an approver.** The wrapper strips rtk's
   `permissionDecision` (and its reason) and forwards only the rewrite, so
   rewritten commands keep going through the normal permission flow — rules,
   classifier and prompts. Installing a token filter must not change the
   permission posture. This is a single named constant
   (`PERMISSION_DECISION_POLICY`) defaulting to strip, with both values covered
   by tests. Its `RTK_HOOK_PERMISSION_DECISION` environment variable is a **test
   seam only** and must never be set in managed settings — not in any
   `.claude/settings*.json` fragment (a unit test fails the build if one does)
   and not in the untracked `settings.sync-local.json`, which no test can
   police.

6. **The command guard unwraps rtk.** `rtk` joins the known wrapper set: the
   real command is the first operand after rtk's own flags, one token further
   right behind a run-anything subcommand (`proxy`, `err`, `test`, `summary`,
   `smart`). It leaves the "accepted long tail" of `enforcement.md` precisely
   because it is mandatory and its hook prefixes commands by default.

7. **The wrapper fails open.** Any error — rtk absent, non-zero, unparseable
   output, unparseable payload — exits 0 with no output, leaving the command
   untouched. It is an optimiser; `block-prohibited-commands.sh` is the guard
   and keeps failing closed beside it.

## Consequences

- Worktree-isolated agents get plain `git` back and keep rtk everywhere else.
- The hook is reproducible on a new machine and self-heals after an rtk
  upgrade, instead of living as an untracked line in one `settings.json`.
- Prefixing a banned tool with `rtk` no longer bypasses the ban. This only ever
  adds blocks — the ban list is untouched, and `rtk ls`, `rtk git status`,
  `rtk gain` and `rtk proxy uv sync` stay allowed.
- Rewritten commands prompt for permission where they previously did not. That
  is a deliberate restoration, not a regression; the token saving is unaffected.
- Two isolation-guard false positives remain and are **not** fixable here,
  because they are the Claude Code harness's own and involve no rtk rewrite:
  `git` matched as a substring inside unrelated words (`for f in gitpython; …`
  is refused while the same loop over `pythonlib` runs), and any compound
  construct (`eval "$(echo echo hi)"` is refused naming neither git nor a
  launcher). Both are reported upstream; the documented workaround is
  `/usr/bin/git` plus splitting compound constructs. See
  `docs/agents/rtk.md`.
- rtk becomes a single point of failure for command output. The fail-open
  wrapper bounds the blast radius to "no compression", never "no shell".
