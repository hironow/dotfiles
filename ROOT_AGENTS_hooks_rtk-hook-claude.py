#!/usr/bin/env python3
"""PreToolUse wrapper around `rtk hook claude` — stdlib only.

Invoked by the thin rtk-hook-claude.sh wrapper. Reads Claude Code tool input
JSON on stdin and answers on stdout with rtk's own hook output, with two
deliberate edits. Full rationale: docs/agents/rtk.md.

1. The worktree carve-out
   ----------------------
   rtk rewrites a bare `git …` into `rtk git …`. Claude Code's
   worktree-isolation guard reads the command *after* hook rewrites, sees a
   launcher it cannot look through, and refuses the call outright:

       "... this command runs rtk with a git command among its operands: what
       runs it, and from which directory or root, cannot be read here ... so
       what it runs cannot be shown not to be git. Refusing to run it ..."

   (Observed verbatim for a command typed as bare `git status --short` — the
   message names rtk because the rewrite already landed.) A worktree-isolated
   agent therefore loses git completely and has to fall back to /usr/bin/git.

   So when the tool's cwd is inside a Claude Code isolation worktree AND rtk
   proposes to put its launcher in front of git, the rewrite is dropped: the
   plain command runs and the guard is satisfied. The veto is git-only and
   worktree-only — everything else (ls, grep, rg, docker, ...) keeps rtk's
   compression, and outside an isolation worktree nothing changes at all.

   Deciding from rtk's *answer* rather than re-deriving which commands rtk
   rewrites keeps rtk the single source of truth, so this never drifts as rtk
   gains or loses subcommands.

2. The permission decision (ADR 0047)
   ----------------------------------
   rtk answers `permissionDecision: "allow"` for everything it rewrites, which
   auto-approves most Bash traffic and suppresses the normal permission flow.
   rtk is an output optimiser, not an approver: installing it must not change
   the permission posture. PERMISSION_DECISION_POLICY strips that field so the
   rewrite (the token saving) survives while Claude Code still decides.

FAILS OPEN everywhere: any error exits 0 with no stdout, leaving the command
untouched. This is NOT a guard — block-prohibited-commands.py is, it runs
independently, and it sees the original command (hooks are not chained).
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys

EXIT_ALLOW = 0

# Claude Code creates `isolation: worktree` agent checkouts under this path
# segment. There is no environment variable that marks such a session (checked
# against the full CLAUDE_* set), so the harness's own layout is the signal.
ISOLATION_WORKTREE_MARKER = "/.claude/worktrees/"

# "strip" (ADR 0047) or "keep". The env var is a test seam — the default is
# the policy.
PERMISSION_DECISION_POLICY = os.environ.get("RTK_HOOK_PERMISSION_DECISION", "strip")

RTK_LAUNCHER = "rtk"
VETOED_COMMAND = "git"

_RTK_TIMEOUT_SECONDS = 10


def _basename(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1]


def _in_isolation_worktree(payload: dict) -> bool:
    """True when this tool call runs inside a Claude Code isolation worktree."""
    cwd = payload.get("cwd") or os.getcwd()
    if not isinstance(cwd, str):
        return False
    normalized = cwd.replace("\\", "/").rstrip("/") + "/"
    return ISOLATION_WORKTREE_MARKER in normalized


def _is_vetoed_rewrite(command: str) -> bool:
    """True for `rtk [rtk-options] git …` — the form the guard cannot verify."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens or _basename(tokens[0]) != RTK_LAUNCHER:
        return False
    for token in tokens[1:]:
        if token.startswith("-"):
            continue  # rtk's own options, e.g. --ultra-compact
        return _basename(token) == VETOED_COMMAND
    return False


def _run_rtk(raw: str) -> dict | None:
    """rtk's hook answer, or None when it declines / is absent / misbehaves."""
    try:
        proc = subprocess.run(  # noqa: S603,S607 - fixed argv, PATH lookup intended
            [RTK_LAUNCHER, "hook", "claude"],
            input=raw,
            capture_output=True,
            text=True,
            timeout=_RTK_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        answer = json.loads(proc.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return answer if isinstance(answer, dict) else None


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return EXIT_ALLOW
    if not isinstance(payload, dict):
        return EXIT_ALLOW

    answer = _run_rtk(raw)
    if answer is None:
        return EXIT_ALLOW

    hook_output = answer.get("hookSpecificOutput")
    if not isinstance(hook_output, dict):
        return EXIT_ALLOW

    updated = hook_output.get("updatedInput")
    rewritten = updated.get("command") if isinstance(updated, dict) else None
    if (
        isinstance(rewritten, str)
        and _in_isolation_worktree(payload)
        and _is_vetoed_rewrite(rewritten)
    ):
        return EXIT_ALLOW  # emit nothing: the plain command runs

    if PERMISSION_DECISION_POLICY == "strip":
        hook_output.pop("permissionDecision", None)
        hook_output.pop("permissionDecisionReason", None)

    print(json.dumps(answer))
    return EXIT_ALLOW


if __name__ == "__main__":
    sys.exit(main())
