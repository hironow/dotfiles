# Plan: agent-hook on native Windows (handoff to the Windows host)

This plan is for the operator, or the agent session, on the native Windows host. It collects everything agent-hook needs there before it replaces today's script hooks on native Windows: what to confirm on the real machine, what to build, and what counts as done.

- The main plan is [agent-hooks-go.md](agent-hooks-go.md). This file is its Windows part.
- The Windows PR is a prerequisite of PR 5, which removes the scripts. Until it lands, native Windows keeps today's scripts, and nothing here changes how they run.
- WSL counts as Linux: it uses the POSIX forms.

## How to work

- Follow the repository's rules (`CLAUDE.md`, the global `AGENTS.md`):
    - each change is designed first, reviewed independently (Codex, else a subagent), shown to the owner, and only then built;
    - tests come first (Red), and `just ci` passes.
- Read `docs/runbook/windows-host.md` before touching recipes or Python on Windows: which shell runs, `cygpath`, `%APPDATA%\uv`, cp932.
- If you run the agent-hook binary by hand, set `LOCALAPPDATA` to a temporary directory (and `XDG_STATE_HOME` under Git Bash). Each run logs where it can, and the real state directory must stay empty until the wiring.
- Report each item of part A with the commands you ran and their output pasted, and the versions: Windows build, Codex, Claude Code, pwsh and Windows PowerShell, Git for Windows, and Go. Put the results in the "Results" section of this file, by PR.

## What exists on Windows today (main, PR 3c)

- **The binary** answers Claude's and Codex's payloads on Windows as on POSIX. Its stage watchdog kills only the direct child at the deadline (no job object yet).
- **No file log on Windows:** the standard library cannot check a file's owner and DACL.
- **Releases** (`cmd/hookrelease`, `just agent-hooks-build`):
    - `id` and `check` work.
    - `build` and `switch` are refused until this PR brings a lock and a stable path tested on Windows.
    - The release directory would be `%LOCALAPPDATA%\dotfiles\agent-hooks\releases`.
- **Rendering** (`agent-hook render`) writes the Windows forms, but only as strings. The render corpus (`tools/agent-hooks/internal/rendercorpus/render.jsonl`) holds them, and sync's ownership rule is tested against it. None has run through Claude or Codex on Windows.
    - Claude: the exec form, `{"type":"command","command":"C:\\…\\agent-hook.exe","args":["claude","pre","--hook","<id>"],"timeout":30,"onFailure":"block"}`.
    - Codex, PowerShell: `& '<path>' codex pre --hook <id>; if ($LASTEXITCODE -ne 0) { '<deny JSON>' }`.
    - Codex, cmd: `"<path>" codex pre --hook <id> || echo <deny JSON>`.
    - The deny JSON is `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"agent-hook failed"}}`.
    - rtk and the formatter use the bare command, with no fallback.
- **Paths render refuses on Windows:** `%`, `!`, and `"` in the cmd form; `‘ ’ ‚ ‛` and `* ? [ ]` in the PowerShell form (`&` resolves wildcards in a missing path: pwsh 7.6.9 on macOS ran another program); a UNC path; a missing `.exe`.
- **The recipe `just agent-hooks-build`** gets no arguments on native Windows: the `windows-shell` hands a recipe no positional arguments, by its `-c` contract. So `check` and `id` cannot go through the recipe there.
- **Doctor's agent-hook checker** prints no shell lines on Windows yet.
- **What Codex 0.166.0 does on Windows, from its source** (`hooks/src/engine/command_runner.rs`, `core/src/session/mod.rs`, `shell-command/src/shell_detect.rs`). These are not yet seen on the host.
    - Its session's shell on Windows is PowerShell when found, else a last fallback.
    - Hooks run with that shell's exec arguments: `-NoProfile -Command` for PowerShell, `/c` for cmd. With no session shell, they run with `%COMSPEC% /C`.
    - For cmd (the default, or any shell whose arguments hold `/c`), the command goes in as one raw argument, wrapped in one more pair of double quotes, which `/C` strips.
    - Codex fails open on anything but exit 2 with non-empty stderr, or a deny JSON.
- **The command guard reads PowerShell text with bash grammar** on Codex there. Its support cell is `degraded` on Windows (PR 2e.4, held by the owner).

## A. Confirm on the host (live)

For each item, record what you ran, what happened, and whether it matches the expectation. A mismatch is a finding: report it, and do not work around it.

1. **Which shell Codex runs hooks with:** pwsh (PowerShell 7), Windows PowerShell 5.1, or cmd through `%COMSPEC%`. Use a probe hook that writes `$PSVersionTable.PSVersion`, or `%COMSPEC%`, to a file. Record the executable and its arguments.
2. **The PowerShell form, through Codex's own runner.** Use a binary path holding a space, `&`, `(`, `)`, `'`, `$`, and non-ASCII. Cases:
    - a normal block (deny JSON, exit 0) and a pass;
    - the binary missing. Record what `$LASTEXITCODE` holds then: `&` sets nothing when the program is not found;
    - a non-zero exit;
    - exit 0 with malformed output;
    - a hang past the stage deadline (10 s), and past the registration timeout (30 s).
    - Expected: a guard blocks in every failure case except a hang past the registration timeout (Codex then fails open). rtk and the formatter let the call go on.
3. **The cmd form, through `cmd /C "<command>"`:** the same cases as 2.
4. **What a shell does before the command:**
    - cmd runs the `AutoRun` value under `HKCU\Software\Microsoft\Command Processor` and `HKLM\Software\Microsoft\Command Processor` first. Anything it prints, or a non-zero exit, breaks every hook, today's scripts included. This is the Windows twin of zsh's `.zshenv`. Record both values.
    - PowerShell runs with `-NoProfile`: confirm no profile output reaches the hook.
5. **Output encoding:** a block whose reason, or path, holds non-ASCII must reach Codex intact through pwsh and through cmd. Record `[Console]::OutputEncoding` and the console code page (`chcp`).
6. **Claude Code on Windows:**
    - The exec form runs the `.exe` with no shell, and `onFailure: "block"` blocks a missing binary, a timeout, and malformed output.
    - Check with and without Git Bash (the contracts note an extra default block on Windows without Git Bash).
    - Record the tools Claude's hooks see there: is there a PowerShell tool? It would be a `pending` tool, with no guard registered for it.
7. **Each hook's real level on Windows:**
    - the guards on Claude (Git Bash commands) and on Codex (PowerShell commands);
    - rtk;
    - the formatter (uv and ruff, gofmt, Windows paths).
    - The plan's matrix states only Codex's command guard as degraded on Windows. Report every other gap.
8. **WSL:** the Linux rules hold inside WSL. Codex and Claude there use the sh form and the exec form. Record any difference from Linux.

## B. Build in the Windows PR (each designed and reviewed first)

1. **A lock for `hookrelease build` on Windows:** `LockFileEx`, or an open with no sharing, retried. It must be dropped when the process dies, and tested on Windows. Then lift the refusal of `build`.
2. **The stable path on Windows:** a symlink needs Developer Mode or elevation, and a running `.exe` can neither be replaced nor deleted. Choose one, decide `switch` on Windows, and test switching while a hook runs:
    - a directory junction `current\<home>` → `releases\<id>`;
    - a tiny launcher;
    - a versioned copy.
3. **The watchdog on Windows:** put each child in a job object, so the deadline kills its descendants too.
4. **The file log on Windows:** check the owner and the DACL through handles (`golang.org/x/sys/windows` needs the dependency policy's reason, or `syscall`), test it on a Windows runner, then log on Windows.
5. **`just agent-hooks-build` on native Windows:** make arguments reach the recipe (for example a `windows-shell` that passes `"$@"`, which changes a contract `tests/unit/test_windows_shell_usr_bin_path.py` pins), and run `tests/unit/test_agent_hooks_build_recipe.py` on Windows.
6. **Sync and doctor on Windows:**
    - sync renders the form for the shell Codex uses (A1);
    - doctor's Windows lines name that shell, and check cmd's `AutoRun` (A4) and the found PowerShell executable.
7. **Codex trust, rollback, uninstall, and gc on Windows:** gc must skip, and report, a release whose `.exe` is in use.
8. **CI:** a Windows job for the Go tests. Today Windows code is only vetted, in the Linux job.
9. **The command guard's Windows gap** (2e.4) stays held until the owner decides. The plan records it, and the loss report names it.

## C. Done means

- The launcher failure cases of A2, A3, and A6 behave as expected on the host, and a normal block stays a block.
- Trust and rollback work, and a revert plus `just sync-agents` registers the scripts again, with no duplicate.
- The stable path switches while sessions run, and a running `.exe` is never replaced.
- Windows logs, with the owner and DACL checked.
- Live tests on the host:
    - Claude and Codex sessions block `npm --version` and a `.yml` write, and rtk rewrites `git status`;
    - each firing logs one line.
- The old subprocess tests pass against the installed release.
- `just ci` passes on the host, and PR CI is green.

## Results

(Empty. The Windows host fills this in, item by item, with the date, the versions, and the output.)
