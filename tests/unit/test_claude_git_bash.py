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


BASH = SCOOP_GIT + r"\bin\bash.exe"


@pytest.mark.parametrize(
    ("user_value", "found", "candidate", "written"),
    [
        # Claude's lookup misses and a Git Bash exists: harden-env points it there
        (None, None, BASH, BASH),
        # it finds one by itself: nothing to write
        (None, GIT + r"\bin\bash.exe", BASH, None),
        # a value set for the User, even a broken one, is never replaced
        (r"D:\old\bash.exe", None, BASH, None),
        # no Git Bash to point at: doctor tells the user instead
        (None, None, None, None),
    ],
)
def test_harden_env_fills_the_variable_only_where_it_is_needed(
    user_value: str | None,
    found: str | None,
    candidate: str | None,
    written: str | None,
) -> None:
    assert lookup.to_set(user_value, found, candidate) == written


@pytest.mark.parametrize(
    ("user_value", "printed"), [(None, True), ("set by hand", False)]
)
def test_to_set_prints_the_git_bash_for_harden_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    user_value: str | None,
    printed: bool,
) -> None:
    git_bash = tmp_path / "bash.exe"
    git_bash.write_text("", encoding="utf-8")
    monkeypatch.setattr(lookup.sys, "platform", "win32")
    monkeypatch.setattr(lookup, "claude_git_bash", lambda *_: None)
    monkeypatch.setattr(lookup, "candidates", lambda *_: [str(git_bash)])
    monkeypatch.setattr(lookup, "_user_value", lambda: user_value)
    assert lookup.main(["--to-set"]) == 0
    assert capsys.readouterr().out == (f"{git_bash}\n" if printed else "")


@pytest.mark.parametrize(("machine", "printed"), [("M:/bash.exe", False), (None, True)])
def test_a_machine_wide_value_counts_as_claudes_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    machine: str | None,
    printed: bool,
) -> None:
    # Claude Code sees the Machine scope too: a working value there needs no
    # User value on top (which would override it)
    git_bash = tmp_path / "bash.exe"
    git_bash.write_text("", encoding="utf-8")
    monkeypatch.setattr(lookup.sys, "platform", "win32")
    monkeypatch.setattr(lookup, "claude_git_bash", lambda configured, *_: configured)
    monkeypatch.setattr(lookup, "candidates", lambda *_: [str(git_bash)])
    monkeypatch.setattr(lookup, "_user_value", lambda: None)
    monkeypatch.setattr(lookup, "_machine_value", lambda: machine)
    assert lookup.main(["--to-set"]) == 0
    assert bool(capsys.readouterr().out) is printed
