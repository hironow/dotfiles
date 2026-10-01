"""Claude Code's own Git Bash lookup on Windows, mirrored for doctor and
harden-env (scripts/claude_git_bash.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import claude_git_bash as lookup  # noqa: E402

GIT = r"C:\Program Files\Git"
SCOOP_GIT = r"C:\Users\u\scoop\apps\git\current"


def _exists(*paths: str):
    return lambda path: path in paths


@pytest.mark.parametrize(
    ("configured", "git", "present", "found"),
    [
        (None, None, (GIT + r"\bin\bash.exe",), GIT + r"\bin\bash.exe"),
        # git through a scoop shim: <shims>\..\..\bin\bash.exe is no Git Bash
        (
            None,
            r"C:\Users\u\scoop\shims\git.exe",
            (SCOOP_GIT + r"\bin\bash.exe",),
            None,
        ),
        (
            None,
            SCOOP_GIT + r"\cmd\git.exe",
            (SCOOP_GIT + r"\bin\bash.exe",),
            SCOOP_GIT + r"\bin\bash.exe",
        ),
        (
            SCOOP_GIT + r"\bin\bash.exe",
            None,
            (SCOOP_GIT + r"\bin\bash.exe",),
            SCOOP_GIT + r"\bin\bash.exe",
        ),
        # a configured path that is not a bash, or not there, falls back
        (SCOOP_GIT + r"\bin\git.exe", None, (SCOOP_GIT + r"\bin\git.exe",), None),
        (
            r"D:\nowhere\bash.exe",
            None,
            (GIT + r"\bin\bash.exe",),
            GIT + r"\bin\bash.exe",
        ),
    ],
)
def test_claude_codes_git_bash_lookup_is_mirrored(
    configured: str | None, git: str | None, present: tuple[str, ...], found: str | None
) -> None:
    assert lookup.claude_git_bash(configured, git, _exists(*present)) == found


@pytest.mark.parametrize(
    ("sh", "first"),
    [
        (r"C:\Program Files\Git\usr\bin\sh.exe", r"C:\Program Files\Git"),
        (r"C:\Program Files\Git\bin\sh.exe", r"C:\Program Files\Git"),
    ],
)
def test_candidates_start_from_the_git_this_shell_runs(sh: str, first: str) -> None:
    assert lookup.candidates(sh, r"C:\Users\u") == [
        first + r"\bin\bash.exe",
        SCOOP_GIT + r"\bin\bash.exe",
    ]
