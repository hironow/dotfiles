#!/usr/bin/env python3
"""Opt-in Jev routing for a new Claude Code or Pi session (imperative shell)."""

from collections.abc import Mapping
import io
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
    build_codex_request_body,
    build_command,
    build_env,
    build_request_body,
    codex_from_answers,
    claude_session_args,
    effort_from_answers,
    parse_args,
    windows_acl_is_private,
)
from jev_headroom import claude_env, ensure_proxy, proxy_port

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


KEY_FILES = (Path(".config/jev/env"), Path(".env"))  # relative to home, preferred first


def env_file_is_private(path: Path) -> bool:
    """A key file may hold the key only if no one else can read or rewrite it."""
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
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError):
            return False  # an unreadable ACL is not a private one
        sids = result.stdout.split()
        return len(sids) >= 2 and windows_acl_is_private(sids[0], sids[1], sids[2:])
    stat = path.stat()
    return stat.st_uid == os.getuid() and not stat.st_mode & 0o077


def use_utf8_stdio() -> None:
    """Claude Code and Pi speak UTF-8 over stdin/stdout; the locale may not.

    On Japanese Windows piped stdio defaults to cp932, which garbles a Japanese
    prompt before Jev sees it and cannot write every character of the answer.
    """
    for stream in (sys.stdin, sys.stdout):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding="utf-8")


def jev_key() -> str | None:
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_AI_API_KEY")
    if key:
        return key
    # A local private file is convenient for interactive shell functions, and the only
    # source for children whose environment is scrubbed. Do not source it: arbitrary
    # shell content must never run during routing.
    try:
        home = Path.home()
    except (RuntimeError, OSError):  # a scrubbed environment may not name a home
        return None
    # ~/.config/jev/env first: Codex's Windows sandbox grants itself read access to
    # every entry directly under the profile except a fixed list that includes
    # .config. ~/.env is read only while the new file does not exist.
    for name in KEY_FILES:
        path = home / name
        if path.is_file():
            break
    else:
        return None
    if not env_file_is_private(path):
        shown = f"~/{name.as_posix()}"
        rule = (
            f"no ACL entry for other accounts (list them: icacls {shown})"
            if sys.platform == "win32"
            else "mode 0600"
        )
        print(
            f"Jev: {shown} must be owned by you and {rule}; "
            "see docs/runbook/jev-launchers.md",
            file=sys.stderr,
        )
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            if name.removeprefix("export ").strip() == "TYPESAFE_API_KEY":
                return value.strip().strip("\"'") or None
    return None


def ask_jev(body: dict[str, object], key: str) -> dict[str, object] | None:
    """Imperative shell: one bounded call. None means there was no usable answer."""
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
        return answers
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        # Never print exception bodies/headers: upstream errors may echo the key.
        print(f"Jev: no valid selection ({type(error).__name__})", file=sys.stderr)
        return None


def choose_effort(task: str, key: str | None) -> str:
    """One Jev call; no key, no answer or an unusable one keeps the host profile."""
    if not key:
        print("Jev: no TYPESAFE_API_KEY; using Sonnet 5.5 medium", file=sys.stderr)
        return "medium"
    answers = ask_jev(build_request_body(task), key)
    return effort_from_answers(answers) if answers is not None else "medium"


def choose_codex(task: str, key: str | None) -> tuple[str, str]:
    """(model, effort) for a Codex worker; without an answer, Sol at medium."""
    if not key:
        print("Jev: no TYPESAFE_API_KEY; using gpt-6.1-sol medium", file=sys.stderr)
        return codex_from_answers({})
    return codex_from_answers(ask_jev(build_codex_request_body(task), key) or {})


def extension_installed() -> bool:
    """The worker-effort extension consumes the key handoff; without it, hand off nothing."""
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent")
    return (agent / "extensions/jev-sonnet-fallback.ts").is_file()


def codex_agents_installed() -> bool:
    """The Jev-aware Codex agents exist; the extension only redirects to agents that do."""
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent")
    return all(
        (agent / "agents" / name).is_file()
        for name in ("codex-jev.md", "codex-jev-writer.md")
    )


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
                encoding="utf-8",
                errors="replace",
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


def headroom_env(host: str, environ: Mapping[str, str]) -> dict[str, str]:
    """j-cc's Claude goes through a headroom proxy when one can be had.

    Only this process and its workers: a custom base URL turns Remote Control
    off, so plain `claude` stays direct. JEV_HEADROOM=off opts out. Any failure
    launches without headroom; it never stops j-cc.
    """
    env = dict(environ)
    if host != "claude":
        return env
    port = proxy_port(environ, Path.home(), ensure=ensure_proxy)
    return env if port is None else claude_env(env, port)


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
    env = headroom_env(
        host,
        build_env(
            os.environ, host, key, extension_installed(), codex_agents_installed()
        ),
    )
    if os.name == "nt":
        # Resolve mise's .cmd/.exe shim via PATHEXT before CreateProcess.
        command[0] = shutil.which(command[0]) or command[0]
        raise SystemExit(subprocess.run(command, env=env, check=False).returncode)
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
