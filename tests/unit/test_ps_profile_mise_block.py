"""The PowerShell mise block skips activation inside a GitHub Actions job (ADR 0086).

GitHub Actions starts a `shell: pwsh` step without -NoProfile, so the user's
profile loads, and an activated mise put its tools ahead of the job's
GITHUB_PATH: a job that pinned a tool ran mise's version instead. The block now
activates mise only when GITHUB_ACTIONS is not "true". deploy rewrites an
existing block in place whenever it differs from the current text, keeping
every other line and its place; a block whose end marker is missing is left
alone and reported. The library functions are tested directly, and the block
itself runs in PowerShell where one is installed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from _ps_profile import needs_bash, run_lib, write_profile
from _pwsh import resolve_pwsh

BEGIN = "# >>> dotfiles managed block: mise activate >>>\n"
END = "# <<< end dotfiles managed block <<<\n"
OLD = (
    BEGIN
    + "# Managed by `just deploy` (see ADR 0024). Edits inside this block are overwritten on next deploy.\n"
    + "if (Get-Command mise -ErrorAction SilentlyContinue) {\n"
    + "    Invoke-Expression (&mise activate pwsh | Out-String)\n"
    + "}\n"
    + END
)
GUARD = "if ($env:GITHUB_ACTIONS -ne 'true' -and (Get-Command mise -ErrorAction SilentlyContinue)) {\n"
NEW = (
    BEGIN
    + "# Managed by `just deploy` (see ADR 0024, ADR 0086). Edits inside this block are overwritten on next deploy.\n"
    + "# Not inside a GitHub Actions job: there the job's GITHUB_PATH must come first (ADR 0086).\n"
    + GUARD
    + "    Invoke-Expression (&mise activate pwsh | Out-String)\n"
    + "}\n"
    + END
)
STARSHIP = (
    "# >>> dotfiles managed block: starship init >>>\n"
    "if (Get-Command starship -ErrorAction SilentlyContinue) {\n"
    "    Invoke-Expression (&starship init powershell)\n"
    "}\n" + END
)
USER_A = "Set-Alias ll Get-ChildItem\n"
USER_B = "$env:EDITOR = 'code'\n"
EOLS = pytest.mark.parametrize("eol", ["\n", "\r\n"], ids=["lf", "crlf"])


def _write(tmp_path: Path, text: str, eol: str = "\n") -> Path:
    path = tmp_path / "profile.ps1"
    path.write_bytes(text.replace("\n", eol).encode("utf-8"))
    return path


def _is(function: str, profile: Path) -> bool:
    result = run_lib(f'{function} "{profile.as_posix()}"')
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


@needs_bash
def test_the_library_prints_the_new_block() -> None:
    result = run_lib("ps_profile_mise_block")
    assert result.returncode == 0, result.stderr
    assert result.stdout == NEW


@needs_bash
@EOLS
def test_an_old_block_is_stale(tmp_path: Path, eol: str) -> None:
    profile = _write(tmp_path, USER_A + OLD, eol)
    assert _is("ps_profile_mise_stale", profile)
    assert not _is("ps_profile_mise_unclosed", profile)


@needs_bash
@EOLS
def test_the_new_block_is_current(tmp_path: Path, eol: str) -> None:
    profile = _write(tmp_path, USER_A + NEW + STARSHIP, eol)
    assert not _is("ps_profile_mise_stale", profile)
    assert not _is("ps_profile_mise_unclosed", profile)


@needs_bash
@pytest.mark.parametrize(
    "text", ["", USER_A + STARSHIP], ids=["empty", "no-mise-block"]
)
def test_a_profile_without_the_block_is_neither(tmp_path: Path, text: str) -> None:
    profile = write_profile(tmp_path, text)
    assert not _is("ps_profile_mise_stale", profile)
    assert not _is("ps_profile_mise_unclosed", profile)


@needs_bash
@pytest.mark.parametrize("text", [GUARD + OLD, OLD + GUARD], ids=["before", "after"])
def test_a_guard_line_outside_the_block_does_not_count(
    tmp_path: Path, text: str
) -> None:
    assert _is("ps_profile_mise_stale", write_profile(tmp_path, text))


@needs_bash
def test_a_block_with_its_guard_commented_out_is_stale(tmp_path: Path) -> None:
    edited = NEW.replace(GUARD, "# " + GUARD)
    assert _is("ps_profile_mise_stale", write_profile(tmp_path, edited))


@needs_bash
@EOLS
@pytest.mark.parametrize(
    "text",
    [
        USER_A + BEGIN + "if ($true) {\n",
        USER_A + BEGIN + "if ($true) {\n" + USER_B + STARSHIP,
    ],
    ids=["at-end-of-file", "before-another-block"],
)
def test_an_unclosed_block_is_reported_and_left_alone(
    tmp_path: Path, eol: str, text: str
) -> None:
    profile = _write(tmp_path, text, eol)
    before = profile.read_bytes()
    assert _is("ps_profile_mise_unclosed", profile)
    assert not _is("ps_profile_mise_stale", profile)
    result = run_lib(f'ps_profile_mise_upgrade "{profile.as_posix()}"')
    assert result.returncode != 0
    assert profile.read_bytes() == before


@needs_bash
@EOLS
def test_the_upgrade_rewrites_the_block_in_place(tmp_path: Path, eol: str) -> None:
    profile = _write(tmp_path, USER_A + "\n" + OLD + STARSHIP + USER_B, eol)
    result = run_lib(f'ps_profile_mise_upgrade "{profile.as_posix()}"')
    assert result.returncode == 0, result.stderr
    raw = profile.read_bytes().decode("utf-8")
    assert raw.replace("\r\n", "\n") == USER_A + "\n" + NEW + STARSHIP + USER_B
    if eol == "\r\n" and sys.platform != "win32":
        # MSYS tools may normalize line endings, which PowerShell does not
        # mind; elsewhere a CRLF profile stays CRLF.
        assert raw.count("\r\n") == raw.count("\n")
    assert not _is("ps_profile_mise_stale", profile)


@needs_bash
def test_a_second_upgrade_changes_nothing(tmp_path: Path) -> None:
    profile = write_profile(tmp_path, USER_A + OLD + STARSHIP)
    assert run_lib(f'ps_profile_mise_upgrade "{profile.as_posix()}"').returncode == 0
    first = profile.read_bytes()
    assert run_lib(f'ps_profile_mise_upgrade "{profile.as_posix()}"').returncode == 0
    assert profile.read_bytes() == first


PWSH = resolve_pwsh(os.environ)
needs_pwsh = pytest.mark.skipif(PWSH is None, reason="needs PowerShell")


def _run_block(tmp_path: Path, *, actions: str | None, with_mise: bool) -> str:
    """Run the new block in a PowerShell whose PATH holds only a temp dir."""
    block = run_lib("ps_profile_mise_block")
    assert block.returncode == 0, block.stderr
    tools = tmp_path / "bin"
    tools.mkdir()
    if with_mise:
        line = "$env:DOTFILES_TEST_MISE = 'activated'"
        if sys.platform == "win32":
            (tools / "mise.cmd").write_text(f"@echo {line}\r\n", encoding="utf-8")
        else:
            fake = tools / "mise"
            fake.write_text(
                f'#!/bin/sh\necho "{line.replace("$", chr(92) + "$")}"\n',
                encoding="utf-8",
            )
            fake.chmod(0o755)
    script = tmp_path / "check.ps1"
    script.write_text(
        block.stdout + 'Write-Output "mise=$env:DOTFILES_TEST_MISE"\n', encoding="utf-8"
    )
    path = [str(tools)]
    env = {"PATH": "", "HOME": str(tmp_path)}
    if sys.platform == "win32":
        system_root = os.environ["SYSTEMROOT"]
        path.append(str(Path(system_root) / "System32"))
        for name in ("SYSTEMROOT", "COMSPEC", "PATHEXT", "TEMP", "TMP", "USERPROFILE"):
            if name in os.environ:
                env[name] = os.environ[name]
    env["PATH"] = os.pathsep.join(path)
    if actions is not None:
        env["GITHUB_ACTIONS"] = actions
    assert PWSH is not None
    import subprocess

    done = subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout.strip().splitlines()[-1]


@needs_bash
@needs_pwsh
@pytest.mark.parametrize(
    ("actions", "activated"),
    [(None, True), ("false", True), ("true", False)],
    ids=["unset", "false", "true"],
)
def test_the_block_activates_mise_only_outside_actions(
    tmp_path: Path, actions: str | None, activated: bool
) -> None:
    result = _run_block(tmp_path, actions=actions, with_mise=True)
    assert result == ("mise=activated" if activated else "mise=")


@needs_bash
@needs_pwsh
def test_the_block_is_quiet_without_mise(tmp_path: Path) -> None:
    assert _run_block(tmp_path, actions=None, with_mise=False) == "mise="
