"""Codex's two shell routes, derived as Codex 0.166 does, and probed.

Codex runs a hook in the session's shell with its non-login arguments, or
with `$SHELL -lc` when the session has no shell. Doctor and sync both need to
know which shells those are, and whether each reads agent-hook's sh launcher
cleanly: a startup file that prints, or reads stdin, lets a guard fail open.
This module holds no doctor or sync logic, so both can import it.
"""

import os
import secrets
import shutil
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_hook_release import Outcome, run

try:
    import pwd
except ImportError:  # Windows has no passwd database or shell probes.
    pwd = None

SHELL_TIMEOUT = 10


@dataclass(frozen=True)
class ShellChoice:
    route: str
    executable: str | None
    kind: str
    reason: str


@dataclass(frozen=True)
class Shell:
    choice: ShellChoice
    argv: tuple[str, ...]
    outcome: Outcome
    token: str

    @property
    def clean(self) -> bool:
        return self.outcome.ok and self.outcome.stdout == self.token


SHELL_FALLBACKS = {
    "zsh": ("/bin/zsh",),
    "bash": ("/bin/bash", "/usr/bin/bash"),
    "sh": ("/bin/sh",),
    "pwsh": ("/usr/local/bin/pwsh",),
    "powershell": (),
    "cmd": (),
}
POSIX_SHELLS = {"zsh", "bash", "sh", "dash", "ksh"}


def shell_kind(path: str) -> str:
    name = Path(path).name
    while name not in SHELL_FALLBACKS and Path(name).stem != name:
        name = Path(name).stem
    if name in {"pwsh", "powershell"}:
        return "powershell"
    return name if name in POSIX_SHELLS or name in {"cmd", "fish"} else "other"


def derive_session_shell(
    login_shell: str | None,
    system: str,
    executables: Mapping[str, str],
    files: frozenset[str],
) -> ShellChoice:
    """Codex 0.166 shell_detect.rs, POSIX: passwd, PATH, fixed fallbacks.

    All discovery is passed in. dash/ksh/fish are not recognised session
    types, although dash and ksh can read the launcher's sh syntax.
    """
    login_kind = shell_kind(login_shell or "")
    recognised = {"zsh", "bash", "sh", "powershell", "cmd"}

    def find(kind: str) -> str | None:
        if login_kind == kind and login_shell in files:
            return login_shell
        names = ("pwsh", "powershell") if kind == "powershell" else (kind,)
        for name in names:
            if name in executables:
                return executables[name]
            for path in SHELL_FALLBACKS[name]:
                if path in files:
                    return path
        return None

    if login_kind in recognised and (executable := find(login_kind)):
        return ShellChoice(
            "session",
            executable,
            login_kind,
            f"login shell {Path(login_shell or '').name}",
        )
    fallback = ("zsh", "bash") if system == "darwin" else ("bash", "zsh")
    if not login_shell:
        reason = "login shell unavailable"
    elif login_kind in recognised:
        reason = f"login shell {Path(login_shell).name} not found"
    else:
        reason = f"login shell {Path(login_shell).name} is not one Codex runs"
    for kind in fallback:
        if executable := find(kind):
            return ShellChoice(
                "session", executable, kind, f"{reason}; it falls back to {kind}"
            )
    if "/bin/sh" in files:
        return ShellChoice(
            "session", "/bin/sh", "sh", f"{reason}; it falls back to fixed /bin/sh"
        )
    return ShellChoice(
        "session", None, "none", f"{reason}; no shell found (fixed /bin/sh missing)"
    )


def derive_login_shell(
    shell: str | None, executables: Mapping[str, str], files: frozenset[str]
) -> ShellChoice:
    if shell == "":
        return ShellChoice("$SHELL -lc", None, "none", "SHELL is empty")
    path = "/bin/sh" if shell is None else shell
    executable = path if path in files else executables.get(path)
    return ShellChoice(
        "$SHELL -lc",
        executable,
        shell_kind(path) if executable else "none",
        f"SHELL={path}" if shell is not None else "SHELL unset; /bin/sh -lc",
    )


def probe_argv(choice: ShellChoice, token: str) -> tuple[str, ...]:
    if choice.executable is None:
        return ()
    if choice.kind == "powershell":
        command = f"$l = [Console]::In.ReadLine(); if ($l -ceq '{token}') {{ [Console]::Out.Write('{token}') }} else {{ [Console]::Out.Write('{token}:stdin') }}"
    elif choice.kind in POSIX_SHELLS:
        command = f'IFS= read -r line; if [ "$line" = {token} ]; then printf %s {token}; else printf %s {token}:stdin; fi'
    elif choice.kind == "fish":
        # fish cannot parse sh's `if`, yet runs today's script hooks.
        command = f'read -l line; if test "$line" = {token}; printf %s {token}; else; printf %s {token}:stdin; end'
    else:
        # A shell whose syntax doctor does not know: the token alone, with
        # stdin unchecked (3d never wires Codex under it).
        command = f"printf %s {token}"
    if choice.route != "session":
        flags = ("-lc",)
    elif choice.kind == "powershell":
        flags = ("-NoProfile", "-Command")
    elif choice.kind == "cmd":
        flags = ("/c",)
    else:
        flags = ("-c",)
    return choice.executable, *flags, command


def unready_reason(shells: Sequence[Shell]) -> str:
    """Why Codex's two shells cannot run agent-hook's sh launcher cleanly, or
    "" when both are POSIX shells that do. Doctor says more about each."""
    if not shells:
        return "no POSIX shell to check"
    for shell in shells:
        choice = shell.choice
        if choice.executable is None:
            return f"{choice.route}: no shell found"
        if choice.kind not in POSIX_SHELLS:
            return f"{choice.route} {choice.executable} is {choice.kind}, not a POSIX shell"
        if not shell.clean:
            return (
                f"{choice.route} {choice.executable} does not run a command "
                "cleanly (run just doctor)"
            )
    return ""


def _login_shell() -> str | None:
    # sys.platform lets the type checker see that pwd and os.getuid are
    # POSIX's; at run time pwd is already None on Windows.
    if sys.platform == "win32" or pwd is None:
        return None
    try:
        return pwd.getpwuid(os.getuid()).pw_shell
    except (KeyError, OSError):
        return None


def gather_shells(system: str, env: Mapping[str, str]) -> tuple[Shell, ...]:
    if system == "windows":
        return ()
    login = _login_shell()
    names = {*SHELL_FALLBACKS, env.get("SHELL", "")}
    executables = {
        name: found
        for name in names
        if name and (found := shutil.which(name, path=env.get("PATH", "")))
    }
    candidates = {path for paths in SHELL_FALLBACKS.values() for path in paths}
    candidates.update(path for path in (login, env.get("SHELL")) if path)
    files = frozenset(path for path in candidates if Path(path).is_file())
    choices = (
        derive_session_shell(login, system, executables, files),
        derive_login_shell(env.get("SHELL"), executables, files),
    )
    probes = []
    for choice in choices:
        token = "agent-hook-probe-" + secrets.token_hex(8)
        argv = probe_argv(choice, token)
        outcome = (
            run(
                argv,
                env=env,
                timeout=SHELL_TIMEOUT,
                input=(token + "\n").encode("utf-8"),
            )
            if argv
            else Outcome(None, reason="missing shell")
        )
        probes.append(Shell(choice, argv, outcome, token))
    return tuple(probes)
