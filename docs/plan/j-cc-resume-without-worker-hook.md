# Do not attach the worker hook to resumed j-cc sessions

Date: 2026-11-18 (JST)

Owner approval (2026-11-18 19:04): fix by ensuring "on resume, do not attach the hook either" (translated).

## Facts

- `j-cc` attaches the same two flags to both new sessions and resumed sessions (`-c`, `-r`) (`scripts/jev_launch.py:279`, `scripts/jev_core.py:217-230`):
    - `--agents`: definitions for `worker-medium` and `worker-high`.
    - `--settings`: `PreToolUse` hook (`scripts/jev_claude_hook.py`), which rewrites default worker launches (`subagent_type` = `general-purpose`, `worker`, or omitted) to `worker-<effort>` and adds `--model` and `--effort` to `codex:codex-rescue` prompts.
- On 2026-11-18 on this machine, all subagent launches in a session resumed with `j-cc -r` failed with `Agent type 'worker-high' not found`.
    - The Claude Code process command line had `--agents`, `--settings`, and `--resume` (`Win32_Process` check).
    - After resuming, the session displayed a notice that "`worker-high` and `worker-medium` are no longer available".
    - Thus, in resumed sessions the `--settings` hook still runs while `--agents` definitions are ignored, so the hook rewrites to a nonexistent type.
- Whether `--agents` being ignored on resume is a Claude Code specification or a bug is not verified.
- `docs/runbook/jev-launchers.md:77` states "resumed sessions also receive the same worker config as new sessions".

## Changes

1. **Red**: update `test_a_resumed_j_cc_session_keeps_the_jev_wiring` in `tests/unit/test_jev_launch.py` to assert:
   - Resumed `j-cc` sessions still receive model, effort, `--append-system-prompt`, and `--resume <id> <prompt>`.
   - `--settings` and `--agents` are not attached.
   - Same for `-c`.
   - New sessions still receive both (existing `test_claude_gets_the_worker_hook_and_agents_but_pi_does_not`).
2. **Green**: in `main` of `scripts/jev_launch.py`, attach `claude_session_args` only when `host == "claude"` and `launch.resume` is empty.
3. **Documentation**: update line 77 and the "Claude Code" section of `docs/runbook/jev-launchers.md`:
   - In resumed sessions, worker effort routing and `codex:codex-rescue` model/effort routing do not apply.
   - Subagents launch with Claude Code's default definitions.
   - Reason: Claude Code ignores `--agents` definitions on resumed sessions, so leaving only the hook breaks launches.
4. Verification: `just ci` and PR CI.

## On failure

Revert the PR. Only resumed sessions will fail subagent launches again, with no other impact.

## Review record

Codex round 1 (2026-11-18): APPROVE. Verified against implementation and existing tests that branching on `launch.resume` covers both `-c` and `-r` and the test scope needs no changes.

## Out of scope

- Investigating why Claude Code ignores `--agents` on resume.
- Restoring effort routing in resumed sessions (e.g., placing definitions in `~/.claude/agents/`). The owner chose the safe option first.
