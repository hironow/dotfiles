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
