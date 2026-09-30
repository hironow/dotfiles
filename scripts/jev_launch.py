#!/usr/bin/env python3
"""Opt-in Jev routing for a new Claude Code or Pi session (imperative shell)."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

from jev_core import (
    JEV_URL,
    PI_ROUTES,
    SONNET,
    build_command,
    build_env,
    build_request_body,
    claude_session_args,
    effort_from_answers,
    parse_args,
    windows_acl_is_private,
)

# Prints the user's SID, the file owner's SID, then the SID of each Allow ACE.
# Uses the .NET API, not Get-Acl: its module fails to autoload in Windows
# PowerShell when pwsh 7's PSModulePath is inherited.
_WINDOWS_ACL_SCRIPT = (
    "$s = [Security.Principal.SecurityIdentifier]; "
    "$a = [IO.File]::GetAccessControl($env:JEV_ACL_PATH); "
    "[Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
    "$a.GetOwner($s).Value; "
    "$a.GetAccessRules($true, $true, $s)"
    " | Where-Object { $_.AccessControlType -eq 'Allow' }"
    " | ForEach-Object { $_.IdentityReference.Value }"
)


def env_file_is_private(path: Path) -> bool:
    """~/.env may hold the key only if no one else can read or rewrite it."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                [
                    shutil.which("powershell") or "powershell.exe",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    _WINDOWS_ACL_SCRIPT,
                ],
                env={**os.environ, "JEV_ACL_PATH": str(path)},
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
        except (OSError, subprocess.SubprocessError):
            return False  # an unreadable ACL is not a private one
        sids = result.stdout.split()
        return len(sids) >= 2 and windows_acl_is_private(sids[0], sids[1], sids[2:])
    stat = path.stat()
    return stat.st_uid == os.getuid() and not stat.st_mode & 0o077


def jev_key() -> str | None:
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_AI_API_KEY")
    if key:
        return key
    # A local private file is convenient for interactive shell functions. Do
    # not source it: arbitrary shell content must never run during routing.
    path = Path.home() / ".env"
    if not path.is_file():
        return None
    if not env_file_is_private(path):
        rule = (
            "no ACL entry for other users" if sys.platform == "win32" else "mode 0600"
        )
        print(f"Jev: ~/.env must be owned by you and {rule}", file=sys.stderr)
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            if name.removeprefix("export ").strip() == "TYPESAFE_API_KEY":
                return value.strip().strip("\"'") or None
    return None


def choose_effort(task: str, key: str | None) -> str:
    """One bounded Jev call; a failed or unusable answer keeps the host profile."""
    if not key:
        print("Jev: no TYPESAFE_API_KEY; using Sonnet 5.5 medium", file=sys.stderr)
        return "medium"
    body = build_request_body(task)
    request = urllib.request.Request(
        JEV_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            answers = json.load(response)["answers"]
        if not isinstance(answers, dict):
            raise TypeError("answers is not an object")
        return effort_from_answers(answers)
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        # Never print exception bodies/headers: upstream errors may echo the key.
        print(
            f"Jev: no valid selection ({type(error).__name__}); using Sonnet 5.5 medium",
            file=sys.stderr,
        )
        return "medium"


def extension_installed() -> bool:
    """The worker-effort extension consumes the key handoff; without it, hand off nothing."""
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent")
    return (agent / "extensions/jev-sonnet-fallback.ts").is_file()


def pi_route() -> str:
    env = build_env(os.environ, "pi", None, False)
    for provider, model in PI_ROUTES:
        try:
            check = subprocess.run(
                [shutil.which("pi") or "pi", "auth", "check", "--provider", provider],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if check.returncode == 0 and check.stdout.strip() == "ready":
            return f"{provider}/{model}"
    raise SystemExit("Jev: no authenticated Pi Sonnet 5.5 provider (run pi /login)")


def hook_command() -> str:
    """The shell command Claude Code runs for the worker hook, with absolute paths."""
    # Claude Code runs hooks with bash on every OS (Git Bash on Windows), which
    # eats backslashes: C:/ paths quoted for a POSIX shell work everywhere.
    parts = [Path(sys.executable), Path(__file__).with_name("jev_claude_hook.py")]
    return " ".join(shlex.quote(part.as_posix()) for part in parts)


def main() -> None:
    try:
        host, task = parse_args(sys.argv[1:])
    except ValueError as error:
        raise SystemExit(str(error)) from error
    key = jev_key()
    effort = choose_effort(task, key)
    print(f"Jev: {host} Sonnet 5.5 / {effort}", file=sys.stderr)
    model = SONNET
    if host == "pi":
        model = pi_route()
        print(f"Pi route: {model}", file=sys.stderr)
    extra = claude_session_args(hook_command()) if host == "claude" else []
    command = build_command(host, task, effort, model, extra)
    env = build_env(os.environ, host, key, extension_installed())
    if os.name == "nt":
        # Resolve mise's .cmd/.exe shim via PATHEXT before CreateProcess.
        command[0] = shutil.which(command[0]) or command[0]
        raise SystemExit(subprocess.run(command, env=env, check=False).returncode)
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
