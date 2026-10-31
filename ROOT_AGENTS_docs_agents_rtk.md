# RTK — Rust Token Killer

Read this when you run shell commands through `rtk`, check its token savings,
or debug output that looks filtered when you did not expect it.

`rtk` is a CLI proxy that cuts command output to save tokens (up to 90% of bash
output). It is **mandatory base tooling**, and you cannot opt out (dotfiles ADR 0047).
Each agent reaches it in one of these ways:

- **Claude Code and Codex**: a PreToolUse hook (`hooks/rtk-hook-claude.sh` /
  `hooks/rtk-hook-codex.sh`, distributed by `just sync-agents`) rewrites
  commands automatically (for example `git status` → `rtk git status`).
- **Pi**: `config/pi/extensions/rtk.ts` does the same for the bash tool (placed
  by `just pi-extensions-install`; refresh after an rtk upgrade with
  `just rtk-pi-refresh`).
- **Other agents**: call `rtk` explicitly.

## Hook and permission rules

- **Never run `rtk init -g` or add `"command": "rtk hook claude"` /
  `"rtk hook codex"` by hand.** mise installs rtk (`config/mise/config.toml`),
  and `just sync-agents` owns the hook entries and retires any raw installer
  block (`RETIRED_HOOK_COMMAND`).
- **The hook fails open and never auto-approves.** If rtk is missing or fails,
  the original command runs. The Claude wrapper forwards only `updatedInput` and
  strips `permissionDecision`, so rewritten commands keep the normal permission
  flow. Never set `RTK_HOOK_PERMISSION_DECISION` in any settings file (it is a
  test-only seam).
- **Telemetry stays off** via `RTK_TELEMETRY_DISABLED=1` (and
  `HEADROOM_BEACON=off`) in mise's global `[env]`, shared Claude settings, and
  Windows User env (`just harden-env`).

rtk may print "No hook installed — run `rtk init -g`", and `rtk init --show`
may report "Hook: not found". Both are expected: rtk looks only for its
installer's layout, not for the dotfiles-managed hook above. Ignore them. The
real check is the `claude-rtk-hook` line of `just doctor`.

## Worktree-isolated agents: git and compound commands

Inside a Claude Code isolation worktree (`*/.claude/worktrees/*`), the wrapper
drops rtk's git rewrite so plain `git` runs, while other commands (`ls`, `grep`,
`rg`, `docker`, …) keep rtk's compression.

If the Claude Code harness itself still refuses a command inside a worktree with
"too complex to verify" (for example `git` matched inside a word like
`gitpython`, or a compound loop/`eval`), call `/usr/bin/git` directly and split
compound constructs into separate commands.

## rtk's own commands

Call these directly: `rtk gain` shows token savings (`--history` per command),
`rtk discover` finds commands rtk could have filtered, and `rtk proxy <cmd>`
runs a command without filtering (`block-prohibited-commands` still inspects the
wrapped command; see docs/agents/enforcement.md). To check the install, run
`rtk --version`, `which rtk`, and `rtk hook check "<cmd>"`.

⚠️ **Name collision**: if `rtk gain` fails, you may have the wrong rtk:
reachingforthejack/rtk (Rust Type Kit).
