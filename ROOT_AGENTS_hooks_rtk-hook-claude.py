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
   the permission posture. Under PERMISSION_DECISION_POLICY "strip" the
   wrapper forwards the rewrite (the token saving) and nothing else, so
   Claude Code still decides, whatever approving field a later rtk adds.

FAILS OPEN everywhere: any error exits 0 with no stdout, leaving the command
untouched. This is NOT a guard — block-prohibited-commands.py is, it runs
independently, and it sees the original command (hooks are not chained).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

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
_MISE_TIMEOUT_SECONDS = 10


def _basename(token: str) -> str:
    return token.replace("\\", "/").rsplit("/", 1)[-1]


def _rtk_executable() -> str | None:
    """Where to find rtk: PATH first, then mise. None when there is no rtk.

    PATH first, always. Whatever the operator put in front wins, and mise's
    answer is not reliably the better one -- a live mise config that does not
    declare rtk makes `mise x -- rtk` fall through to PATH and resolve the very
    copy the pruning is meant to retire (measured 2026-10-01).

    mise second, because a Claude Code session's environment is a snapshot taken
    when the session started: a tool mise installed afterwards is invisible to
    it, and once the hand-placed ~/.local/bin/rtk is pruned such a session has
    no rtk on PATH at all. `mise which` answers from mise's own configuration,
    so it reaches the pinned copy without the session being restarted. The
    subprocess is paid only when PATH has no rtk, which is the case where the
    hook would otherwise do nothing.
    """
    found = shutil.which(RTK_LAUNCHER)
    if found:
        return found
    if not shutil.which("mise"):
        return None
    try:
        proc = subprocess.run(  # noqa: S603,S607 - fixed argv, PATH lookup intended
            ["mise", "which", RTK_LAUNCHER],
            capture_output=True,
            text=True,
            timeout=_MISE_TIMEOUT_SECONDS,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None  # the tool is not active here: a stale or absent config
    candidate = proc.stdout.strip()
    if not candidate or not os.access(candidate, os.X_OK):
        return None
    return candidate


def _in_isolation_worktree(payload: dict) -> bool:
    """True when this tool call runs inside a Claude Code isolation worktree."""
    cwd = payload.get("cwd") or str(Path.cwd())
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


_ASSIGNMENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=[^\s;&|()]*")
_LAUNCHER_WORD = re.compile(re.escape(RTK_LAUNCHER) + r"(?=[\s;&|)]|$)")
_COMMAND_START = set(";&|(\n")


def _with_launcher(command: str, launcher: str) -> str:
    """command, with each `rtk` in command position replaced by launcher.

    Used when rtk came from mise: the shell that runs the rewrite has the same
    PATH as this hook, without rtk, so a bare `rtk` there is "command not
    found". Command position means unquoted, at the start or after `;` `&` `|`
    `(` or a newline, past any NAME=value prefixes; an `rtk` anywhere else (an
    argument, a quoted commit message, a heredoc body) stays as it is.
    """
    quoted = shlex.quote(launcher)
    out: list[str] = []
    i, at_start, quote = 0, True, ""
    while i < len(command):
        char = command[i]
        if quote:
            if char == "\\" and quote == '"':
                out.append(command[i : i + 2])
                i += 2
                continue
            quote = "" if char == quote else quote
            out.append(char)
            i += 1
            continue
        if command.startswith("<<", i):  # a heredoc body is data: leave the rest
            out.append(command[i:])
            break
        if char in "'\"":
            quote, at_start = char, False
        elif char == "\\":
            out.append(command[i : i + 2])
            i, at_start = i + 2, False
            continue
        elif char in _COMMAND_START:
            at_start = True
        elif char.isspace():
            pass
        elif at_start and (word := _LAUNCHER_WORD.match(command, i)):
            out.append(quoted)
            i, at_start = word.end(), False
            continue
        elif at_start and (assignment := _ASSIGNMENT.match(command, i)):
            out.append(assignment[0])
            i = assignment.end()
            continue
        else:
            at_start = False
        out.append(char)
        i += 1
    return "".join(out)


def _run_rtk(raw: str) -> tuple[dict, str | None] | None:
    """rtk's hook answer and, when rtk came from mise rather than PATH, the
    launcher a rewrite must name; None when rtk declines / is absent /
    misbehaves."""
    launcher = _rtk_executable()
    if launcher is None:
        return None
    off_path = None if shutil.which(RTK_LAUNCHER) else Path(launcher).as_posix()
    try:
        proc = subprocess.run(  # noqa: S603 - resolved argv, no shell
            [launcher, "hook", "claude"],
            input=raw,
            capture_output=True,
            text=True,
            timeout=_RTK_TIMEOUT_SECONDS,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        answer = json.loads(proc.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return (answer, off_path) if isinstance(answer, dict) else None


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return EXIT_ALLOW
    if not isinstance(payload, dict):
        return EXIT_ALLOW

    ran = _run_rtk(raw)
    if ran is None:
        return EXIT_ALLOW
    answer, off_path = ran

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

    if off_path and isinstance(rewritten, str) and isinstance(updated, dict):
        updated["command"] = _with_launcher(rewritten, off_path)

    if PERMISSION_DECISION_POLICY == "strip":
        # Forward the rewrite and nothing else, so no approving field rtk
        # emits, today's or a later release's, reaches Claude Code
        if not isinstance(updated, dict):
            return EXIT_ALLOW
        answer = {
            "hookSpecificOutput": {
                "hookEventName": hook_output.get("hookEventName", "PreToolUse"),
                "updatedInput": updated,
            }
        }

    print(json.dumps(answer))
    return EXIT_ALLOW


if __name__ == "__main__":
    sys.exit(main())
