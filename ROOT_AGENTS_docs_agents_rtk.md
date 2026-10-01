# RTK — Rust Token Killer

Read this when running shell commands through `rtk`, checking its token
savings, or debugging output that looks unexpectedly filtered.

`rtk` is a token-optimized CLI proxy (cuts up to 90% of bash output) and is
**mandatory base tooling** — there is no opt-out (ADR 0047). In Claude Code
and Codex a hook rewrites commands transparently (e.g. `git status` →
`rtk git status`), and in Pi rtk's own extension does the same for the bash
tool (`config/pi/extensions/rtk.ts`, vendored and placed by
`just pi-extensions-install`; after an rtk upgrade, `just rtk-pi-refresh`);
other agents invoke it explicitly.

## The hook is dotfiles-managed

The PreToolUse hook is `hooks/rtk-hook-claude.sh`, declared in
`.claude/settings.hooks.json` and distributed by `just sync-agents` like every
other hook. It wraps `rtk hook claude` rather than replacing it, so rtk stays
the source of truth for what gets rewritten. Codex gets
`hooks/rtk-hook-codex.sh` from `.codex/hooks.json` the same way, passing
`rtk hook codex`'s answer through unchanged (Codex grants no approval from it).
`just doctor` shows whether Codex trusts the hooks (see `docs/agent-sync.md`
in the dotfiles repo).

**Never add `"command": "rtk hook claude"` (or `rtk hook codex`) to a settings
or hooks file by hand**, and if rtk's installer adds it on an upgrade, leave it —
`just sync-agents` retires that block on every run (`RETIRED_HOOK_COMMAND` in
`scripts/sync_agents.py`).
Two rewriting hooks in one session means rtk wins and the carve-out below never
fires.

The wrapper **fails open**: if rtk is missing or errors, the command runs
unchanged. It is an optimiser, not a guard.

## Install and telemetry

rtk (and headroom) come from mise on every OS (`config/mise/config.toml`), so
`rtk init -g` is never needed: it would add the hook block sync retires and
write its own `RTK.md` into agent homes sync owns. Telemetry stays off through
`RTK_TELEMETRY_DISABLED=1` (and `HEADROOM_BEACON=off`), set in mise's global
`[env]`, the shared Claude settings env, and on Windows the persisted User env
(`just harden-env`).

## rtk does not approve commands

rtk answers `permissionDecision: "allow"` for everything it rewrites, which
would auto-approve most Bash traffic. The wrapper **forwards only the
rewrite** (`updatedInput`) and drops every other field, so rewritten commands
still go through the normal permission flow, and an approving field a later rtk
adds cannot slip through. rtk is an output optimiser, not an approver:
installing it must not change the permission posture (ADR 0047).

The wrapper's `RTK_HOOK_PERMISSION_DECISION` variable is a **test seam only** —
never set it in managed settings (any `.claude/settings*.json` fragment, or
`settings.sync-local.json`); any value but `strip` restores rtk's blanket
auto-approval, and a unit test fails the build if a tracked fragment sets it.

## Worktree-isolated agents: git is not rewritten

Inside a Claude Code isolation worktree (`*/.claude/worktrees/*`) the wrapper
drops rtk's git rewrite, so plain `git` runs. Everything else — `ls`, `grep`,
`rg`, `docker`, … — keeps rtk's compression, and outside such a worktree nothing
changes.

Why: the isolation guard reads the command *after* hook rewrites, sees a
launcher it cannot look through, and refuses the whole call — for a command
typed as a bare `git`:

> …but this command runs rtk with a git command among its operands: what runs
> it, and from which directory or root, cannot be read here … so what it runs
> cannot be shown not to be git. Refusing to run it …

## When the isolation guard still refuses (use `/usr/bin/git`)

Two refusals come from the Claude Code harness itself, not from rtk or from any
dotfiles hook, so nothing here can fix them. Both are recognisable by the words
"too complex to verify":

1. **`git` matched inside an unrelated word.** `for f in gitpython; do echo
   "$f"; done` is refused; the identical loop over `pythonlib` runs.
2. **Any compound construct.** `eval "$(echo echo hi)"` is refused even though
   it names neither git nor a launcher. Loops and command substitutions that run
   `bash`/`mise`/`eval` are refused the same way.

Workarounds: call `/usr/bin/git` (path-qualified, so rtk does not rewrite it),
and split compound constructs into plain, separate commands.

## rtk is a wrapper, and the command guard unwraps it

`block-prohibited-commands` resolves the real command behind the proxy, so
`rtk pnpm install` is blocked exactly like `pnpm install`, including the
run-anything subcommands (`rtk proxy …`, `rtk run …`, `rtk err …`,
`rtk test …`, `rtk summary …`, `rtk smart …`). Prefixing a banned tool with
`rtk` is not an escape hatch.

## After an rtk upgrade

mise tracks rtk's latest release, so upgrades arrive unannounced. `just doctor`
(and `just status`) compares what dotfiles relies on with the installed rtk:

- `rtk-pi-extension`: the vendored Pi extension came from an older rtk —
  `just rtk-pi-refresh`.
- `rtk-guard`: rtk gained a subcommand the command guard has not classified —
  add it to `RTK_RUN_SUBCOMMANDS` if it runs a command it is given, else to
  `RTK_FILTER_SUBCOMMANDS` (both in `hooks/block-prohibited-commands.py`).
- `rtk-telemetry`: rtk itself reports telemetry on, or no longer mentions
  `RTK_TELEMETRY_DISABLED` (`rtk telemetry status`).

The hook blocks an rtk installer writes are retired by sync whatever their
version or path, so `rtk init` drift needs no action.

## Meta commands (always call rtk directly)

```bash
rtk gain              # Show token savings analytics
rtk gain --history    # Show command usage history with savings
rtk discover          # Analyze command history for missed opportunities
rtk proxy <cmd>       # Execute raw command without filtering (for debugging)
```

## Installation verification

```bash
rtk --version         # Should show: rtk X.Y.Z
rtk gain              # Should work (not "command not found")
which rtk             # Verify correct binary
rtk hook check "<cmd>"  # Dry-run: how the hook engine would rewrite <cmd>
```

⚠️ **Name collision**: if `rtk gain` fails, you may have
reachingforthejack/rtk (Rust Type Kit) installed instead.
