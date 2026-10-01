#!/usr/bin/env python3
"""Codex PreToolUse wrapper around `rtk hook codex` — stdlib only.

Invoked by the thin rtk-hook-codex.sh. Reads Codex's tool input JSON on stdin
and answers with rtk's own answer, the rewrite naming rtk's real binary.

Why the real binary: the rewritten command runs inside Codex's sandbox. On
Windows its PATH can reach rtk only through mise's shim, and the shim reads
~/.config/mise/config.toml, which the sandbox may not read (Codex skips
~/.config): "No version is set for shim: rtk". This hook runs as the user,
outside the sandbox, so it asks `mise which rtk` for the install itself (whose
directory the sandbox can read: scripts/codex_sandbox_tools.py) and names it.

What is forwarded: only a rewrite of the plain shape `rtk <command>` (the
leading launcher being its only `rtk`, the rule the Claude wrapper keeps too;
tests/unit/test_rtk_hook_codex.py checks they agree), and only with a path that
needs no quoting, since Codex runs commands through pwsh on Windows. Codex reads
permissionDecision:"allow" only as the carrier of updatedInput (it grants no
approval; codex-rs hooks/src/engine/output_parser.rs), so nothing is stripped.

FAILS OPEN everywhere: any doubt prints nothing and the typed command runs.
Not `rtk init --codex`: dotfiles owns this hook (ADR 0047; docs/agents/rtk.md).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys

EXIT_ALLOW = 0
RTK_LAUNCHER = "rtk"
# A path pwsh and sh both run as a command without quoting
UNQUOTED_PATH = re.compile(r"[A-Za-z0-9_./:-]+")
WINDOWS_PATH = re.compile(r"[A-Za-z]:[\\/]")
_TIMEOUT_SECONDS = 10


# ---- Functional core ----


def choose_launcher(mise_answer: str | None, on_path: str | None) -> str | None:
    """rtk's real binary: mise's answer, else PATH's copy unless it is a shim."""
    if mise_answer:
        return mise_answer
    if on_path and [part.lower() for part in _posix(on_path).split("/")[-2:-1]] != [
        "shims"  # a Windows path ignores case
    ]:
        return on_path
    return None


def _posix(path: str) -> str:
    """A Windows path (drive letter) with forward slashes; any other path as
    it is, since a backslash there is part of a name, not a separator."""
    return path.replace("\\", "/") if WINDOWS_PATH.match(path) else path


def named(command: str, launcher: str) -> str | None:
    """`<launcher> <args>` for a rewrite of the plain shape `rtk <args>`, else None."""
    prefix = RTK_LAUNCHER + " "
    if not command.startswith(prefix) or RTK_LAUNCHER in command[len(prefix) :]:
        return None
    path = _posix(launcher)
    if not UNQUOTED_PATH.fullmatch(path):
        return None
    return path + command[len(RTK_LAUNCHER) :]


def respond(answer: dict, launcher: str) -> dict | None:
    """rtk's answer with the rewrite naming launcher, or None to print nothing."""
    output = answer.get("hookSpecificOutput")
    if not isinstance(output, dict):
        return None
    updated = output.get("updatedInput")
    command = updated.get("command") if isinstance(updated, dict) else None
    if not isinstance(updated, dict) or not isinstance(command, str):
        return None
    rewrite = named(command, launcher)
    if rewrite is None:
        return None
    return {
        **answer,
        "hookSpecificOutput": {
            **output,
            "updatedInput": {**updated, "command": rewrite},
        },
    }


# ---- Imperative shell ----


def _run(argv: list[str], stdin: str | None = None) -> str | None:
    try:
        proc = subprocess.run(  # noqa: S603 - resolved argv, no shell
            argv,
            input=stdin,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def main() -> int:
    raw = sys.stdin.read()
    mise = shutil.which("mise")
    launcher = choose_launcher(
        _run([mise, "which", RTK_LAUNCHER]) if mise else None,
        shutil.which(RTK_LAUNCHER),
    )
    if launcher is None:
        return EXIT_ALLOW
    out = _run([launcher, "hook", "codex"], raw)
    try:
        answer = json.loads(out or "")
    except ValueError:
        return EXIT_ALLOW
    response = respond(answer, launcher) if isinstance(answer, dict) else None
    if response is not None:
        print(json.dumps(response))
    return EXIT_ALLOW


if __name__ == "__main__":
    sys.exit(main())
