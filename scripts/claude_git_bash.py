#!/usr/bin/env python3
"""Which Git Bash Claude Code runs on native Windows, by its own lookup.

Claude Code 2.1.285 takes CLAUDE_CODE_GIT_BASH_PATH when it names an existing
bash/sh, else Git's default install, else <git>\\..\\..\\bin\\bash.exe for the
first git on PATH (which a scoop shim defeats). Without one its Bash tool is
off and j-cc fails. This is that contract, in one place: `just doctor` reports
from it, and `just harden-env` uses it to fill the variable where it is needed.
"""

from collections.abc import Callable
import ntpath
from pathlib import Path
import shutil
import sys

CLAUDE_BASH_DEFAULTS = (
    r"C:\Program Files\Git\bin\bash.exe",
    r"C:\Program Files (x86)\Git\bin\bash.exe",
)


def claude_git_bash(
    configured: str | None, git: str | None, exists: Callable[[str], bool]
) -> str | None:
    """The bash.exe Claude Code would run, by its own lookup."""
    names = {"bash.exe", "sh.exe", "bash", "sh"}
    if (
        configured
        and ntpath.basename(configured).lower() in names
        and exists(configured)
    ):
        return configured
    for default in CLAUDE_BASH_DEFAULTS:
        if exists(default):
            return default
    if git:
        derived = ntpath.normpath(ntpath.join(git, "..", "..", "bin", "bash.exe"))
        if exists(derived):
            return derived
    return None


def candidates(sh: str | None, home: str) -> list[str]:
    """Git Bash installs to point Claude Code at: the Git this shell's sh comes
    from (<Git>\\usr\\bin or <Git>\\bin), then scoop's Git. Windows paths on
    any OS (ntpath), so the rule is testable everywhere."""
    roots = [ntpath.join(home, "scoop", "apps", "git", "current")]
    if sh:
        up = ntpath.dirname(ntpath.dirname(sh))
        roots.insert(
            0, ntpath.dirname(up) if ntpath.basename(up).lower() == "usr" else up
        )
    return [ntpath.join(root, "bin", "bash.exe") for root in roots]


def to_set(
    user_value: str | None, found: str | None, candidate: str | None
) -> str | None:
    """What harden-env writes to the User env: the candidate, only while no
    value is set there (one set by hand, even a broken one, is never replaced;
    doctor reports it) and Claude Code's own lookup finds no Git Bash."""
    if user_value or found or not candidate:
        return None
    return candidate


# ---- Imperative shell ----


def _user_value() -> str | None:
    import winreg  # noqa: PLC0415 - Windows only

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        try:
            return str(winreg.QueryValueEx(key, "CLAUDE_CODE_GIT_BASH_PATH")[0]) or None
        except OSError:
            return None


def main(argv: list[str]) -> int:
    """`--to-set`: print the Git Bash harden-env should set, or nothing."""
    if "--to-set" not in argv or sys.platform != "win32":
        return 0
    exists = lambda path: Path(path).exists()  # noqa: E731
    found = claude_git_bash(None, shutil.which("git"), exists)
    candidate = next(
        (c for c in candidates(shutil.which("sh"), str(Path.home())) if exists(c)), None
    )
    if value := to_set(_user_value(), found, candidate):
        print(value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
