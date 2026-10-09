# RTK — Rust Token Killer

Read this when you run shell commands through `rtk`, check its token savings,
or debug output that looks filtered when you did not expect it.

`rtk` is a CLI proxy that cuts command output to save tokens (up to 90% of bash
output). It is **mandatory base tooling**, and you cannot opt out (ADR 0047).
Each agent reaches it in one of these ways:

- **Claude Code and Codex**: a hook rewrites commands for you (for example,
  `git status` becomes `rtk git status`).
- **Pi**: rtk's own extension does the same for the bash tool
  (`config/pi/extensions/rtk.ts`, vendored and placed by
  `just pi-extensions-install`; after an rtk upgrade, run `just rtk-pi-refresh`).
- **Other agents**: call `rtk` explicitly.

## dotfiles manages the hook

The PreToolUse hook is `hooks/rtk-hook-claude.sh`. `.claude/settings.hooks.json`
declares it, and `just sync-agents` distributes it like every other hook. It
wraps `rtk hook claude` instead of replacing it, so rtk still decides what gets
rewritten.

Codex gets `hooks/rtk-hook-codex.sh` from `.codex/hooks.json` the same way. This
wrapper passes on `rtk hook codex`'s answer with its approval (Codex grants no
approval from it). It does change the rewrite: it names rtk's real binary
(`mise which rtk`). The command runs in Codex's sandbox, and there a mise shim
cannot read mise's config ("No version is set for shim: rtk"). As in the Claude
wrapper, the hook keeps only a plain `rtk <command>` rewrite, and only when the
path needs no quoting (pwsh runs it on Windows). In every other case, the typed
command runs. `just doctor` shows whether Codex trusts the hooks (see
`docs/agent-sync.md` in the dotfiles repo).

**Never add `"command": "rtk hook claude"` (or `rtk hook codex`) to a settings
or hooks file by hand.** If rtk's installer adds it during an upgrade, leave it:
`just sync-agents` retires that block on every run (`RETIRED_HOOK_COMMAND` in
`scripts/sync_agents.py`). With two rewriting hooks in one session, rtk wins and
the carve-out below never fires.

The wrapper **fails open**: if rtk is missing or fails, the command runs
unchanged. It is an optimiser, not a guard.

## Install and telemetry

rtk (and headroom) come from mise on every OS (`config/mise/config.toml`). So
you never need `rtk init -g`. Running it would add the hook block that sync
retires, and write its own `RTK.md` into agent homes that sync owns.

Telemetry stays off through `RTK_TELEMETRY_DISABLED=1` (and
`HEADROOM_BEACON=off`). These are set in three places: mise's global `[env]`,
the shared Claude settings env, and on Windows the persisted User env
(`just harden-env`).

rtk's own "No hook installed — run `rtk init -g`" notice, and `rtk init --show` reporting "Hook: not found", are expected: rtk only looks for its installer's layout, not for the dotfiles-managed hook above. Ignore them; `just doctor`'s `claude-rtk-hook` line is the real check.

### Which rtk the hook runs: PATH first, then mise

**PATH first, always.** The rtk at the front of the session's PATH wins. This
way the hook never overrides a copy the operator put there on purpose. mise's
answer is also not always better: when the live mise config does not declare
rtk, `mise x -- rtk` falls back to PATH and finds exactly the stale copy that a
prune is meant to retire.

**mise second**, only when PATH has no rtk at all. A Claude Code session's
environment is a snapshot taken when the session started. It cannot see a tool
that mise installed later. Once a hand-placed `~/.local/bin/rtk` is pruned, such
a session has no rtk on PATH. `mise which rtk` answers from mise's own
configuration, so the hook reaches the pinned copy without restarting the
session. The hook pays for that subprocess only when it would otherwise do
nothing.

The shell that runs the rewritten command has the same PATH, without rtk. There,
a bare `rtk …` would fail with "command not found". So the hook keeps a rewrite
only when it has the plain shape `rtk <command>` (the leading launcher is its
only `rtk`), and names the absolute path that mise gave. The hook drops any
other rewrite (compound commands, an assignment prefix), and the typed command
runs as typed. That costs the compression, never the command.

If both routes fail, that is normal, not an error. `mise which` exits non-zero
when the tool is not active in this directory, and the hook then fails open:
the command runs without a rewrite. `just doctor` is what notices a shadowing
copy or a copy not from mise.

## rtk does not approve commands

rtk answers `permissionDecision: "allow"` for everything it rewrites. That
would auto-approve most Bash traffic. So the wrapper **forwards only the
rewrite** (`updatedInput`) and drops every other field. Rewritten commands still
go through the normal permission flow, and an approving field that a later rtk
adds cannot slip through. rtk optimises output; it does not approve. Installing
it must not change the permission posture (ADR 0047).

The wrapper's `RTK_HOOK_PERMISSION_DECISION` variable is a **test seam only**.
Never set it in managed settings (any `.claude/settings*.json` fragment, or
`settings.sync-local.json`). Any value other than `strip` brings back rtk's
blanket auto-approval, and a unit test fails the build if a tracked fragment
sets it.

## Worktree-isolated agents: the hook does not rewrite git

Inside a Claude Code isolation worktree (`*/.claude/worktrees/*`), the wrapper
drops rtk's git rewrite, so plain `git` runs. Everything else (`ls`, `grep`,
`rg`, `docker`, …) keeps rtk's compression. Outside such a worktree, nothing
changes.

Why: the isolation guard reads the command *after* hook rewrites. It sees a
launcher it cannot look through and refuses the whole call. For a command typed
as a bare `git`, it says:

> …but this command runs rtk with a git command among its operands: what runs
> it, and from which directory or root, cannot be read here … so what it runs
> cannot be shown not to be git. Refusing to run it …

## When the isolation guard still refuses: use `/usr/bin/git`

Two refusals come from the Claude Code harness itself, not from rtk or any
dotfiles hook, so nothing here can fix them. You can recognise both by the
words "too complex to verify":

1. **`git` matched inside an unrelated word.** The harness refuses
   `for f in gitpython; do echo "$f"; done`, but runs the same loop over
   `pythonlib`.
2. **Any compound construct.** The harness refuses `eval "$(echo echo hi)"`,
   even though it names neither git nor a launcher. It refuses loops and
   command substitutions that run `bash`/`mise`/`eval` the same way.

Workarounds: call `/usr/bin/git` (a full path, so rtk does not rewrite it), and
split compound constructs into plain, separate commands.

## The command guard looks through rtk

`block-prohibited-commands` finds the real command behind the proxy. So it
blocks `rtk pnpm install` exactly like `pnpm install`. This includes the
run-anything subcommands (`rtk proxy …`, `rtk run …`, `rtk err …`,
`rtk test …`, `rtk summary …`, `rtk smart …`). Putting `rtk` in front of a
banned tool does not get around the ban.

## After an rtk upgrade

mise tracks rtk's latest release, so upgrades arrive without notice.
`just doctor` (and `just status`) compares what dotfiles relies on with the
installed rtk:

- `rtk-pi-extension`: the vendored Pi extension came from an older rtk. Run
  `just rtk-pi-refresh`.
- `rtk-guard`: rtk gained a subcommand the command guard has not classified.
  If the subcommand runs a command it is given, add it to
  `RTK_RUN_SUBCOMMANDS`; otherwise add it to `RTK_FILTER_SUBCOMMANDS` (both in
  `hooks/block-prohibited-commands.py`).
- `rtk-telemetry`: rtk itself reports telemetry on, or no longer mentions
  `RTK_TELEMETRY_DISABLED` (`rtk telemetry status`).

Sync retires the hook blocks that an rtk installer writes, whatever their
version or path. So `rtk init` drift needs no action.

## Meta commands (always call rtk directly)

```bash
rtk gain              # Show token savings analytics
rtk gain --history    # Show command usage history with savings
rtk discover          # Analyze command history for missed opportunities
rtk proxy <cmd>       # Execute raw command without filtering (for debugging)
```

## Check the installation

```bash
rtk --version         # Should show: rtk X.Y.Z
rtk gain              # Should work (not "command not found")
which rtk             # Verify correct binary
rtk hook check "<cmd>"  # Dry-run: how the hook engine would rewrite <cmd>
```

⚠️ **Name collision**: if `rtk gain` fails, you may have the wrong rtk:
reachingforthejack/rtk (Rust Type Kit).
