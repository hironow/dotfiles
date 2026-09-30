"""The starship block must come after `mise activate` in the pwsh $PROFILE.

starship is a mise-managed tool. `Get-Command starship` in the starship block
finds it only once `mise activate` has put mise's tool dirs on PATH, or when
mise's shims are on the persisted PATH anyway (true on the self-hosted runner
hosts, which add them for their jobs). deploy wrote the starship block first,
so on every other Windows host the block silently skipped and the prompt stayed
plain. deploy only appends missing blocks, so fixing the write order alone
leaves existing profiles misordered: deploy must also move the block, and
doctor must say when the order is wrong.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "ps_profile_lib.sh"
DEPLOY = ROOT / "scripts" / "deploy.sh"
DOCTOR = ROOT / "scripts" / "doctor.sh"

STARSHIP = (
    "# >>> dotfiles managed block: starship init >>>\n"
    "if (Get-Command starship -ErrorAction SilentlyContinue) {\n"
    "    Invoke-Expression (&starship init powershell)\n"
    "}\n"
    "# <<< end dotfiles managed block <<<\n"
)
MISE = (
    "# >>> dotfiles managed block: mise activate >>>\n"
    "if (Get-Command mise -ErrorAction SilentlyContinue) {\n"
    "    Invoke-Expression (&mise activate pwsh | Out-String)\n"
    "}\n"
    "# <<< end dotfiles managed block <<<\n"
)
USER_LINE = "Set-Alias ll Get-ChildItem\n"


def _bash() -> str | None:
    """A POSIX bash, chosen like test_ps_profile_path's ``_unwrapped_bash``:
    never WSL's System32 launcher (it cannot read drive-lettered paths), and
    behind Git for Windows' ``<git>/bin/bash.exe`` launcher the real
    ``<git>/usr/bin/bash.exe``. ``_lib`` puts that bash's own directory first
    on PATH, so the lib's sed/grep/cut come from the same toolset whether the
    suite runs from Git Bash or PowerShell."""
    found = shutil.which("bash")
    if found is None or "system32" in found.lower():
        return None
    exe = Path(found)
    real = exe.parent.parent / "usr" / "bin" / exe.name
    return str(real) if exe.parent.name.lower() == "bin" and real.is_file() else found


BASH = _bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="needs a POSIX bash")


def _lib(
    call: str, path_prefix: list[Path] | None = None
) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    entries = [*(path_prefix or []), Path(BASH).parent]
    path = os.pathsep.join([*map(str, entries), os.environ.get("PATH", "")])
    return subprocess.run(
        [BASH, "-c", f'set -euo pipefail; . "{LIB.as_posix()}"; {call}'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PATH": path},
        check=False,
    )


def _profile(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "profile.ps1"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


@needs_bash
@pytest.mark.parametrize(
    ("text", "misordered"),
    [
        (STARSHIP + MISE, True),
        (MISE + STARSHIP, False),
        (STARSHIP, False),  # nothing to order against
        (MISE, False),
        ("", False),
    ],
    ids=["starship-first", "mise-first", "starship-only", "mise-only", "empty"],
)
def test_detects_starship_before_mise(
    tmp_path: Path, text: str, misordered: bool
) -> None:
    profile = _profile(tmp_path, text)
    result = _lib(f'ps_profile_starship_before_mise "{profile.as_posix()}"')
    assert (result.returncode == 0) is misordered, result.stderr


@needs_bash
def test_drop_block_removes_only_that_block(tmp_path: Path) -> None:
    # given a misordered profile with a user line between the blocks
    profile = _profile(tmp_path, STARSHIP + USER_LINE + MISE)

    # when the starship block is dropped
    result = _lib(f'ps_profile_drop_block "{profile.as_posix()}" "starship init"')

    # then the user's line and the mise block are untouched
    assert result.returncode == 0, result.stderr
    assert profile.read_text(encoding="utf-8") == USER_LINE + MISE


@needs_bash
def test_drop_block_does_not_depend_on_gnu_sed_in_place(tmp_path: Path) -> None:
    """`sed -i` differs between GNU and BSD (macOS wants `-i ''`), so the lib
    must not use it: a sed that rejects -i stands in for BSD's here."""
    # given a sed that refuses -i, first on PATH
    real = shutil.which("sed", path=str(Path(BASH or "").parent)) or shutil.which("sed")
    assert real is not None
    fake = tmp_path / "bin"
    fake.mkdir()
    script = [
        "#!/bin/sh",
        'for a in "$@"; do case "$a" in -i*) echo "sed: no -i" >&2; exit 1;; esac; done',
        f'exec "{Path(real).as_posix()}" "$@"',
    ]
    (fake / "sed").write_text(
        "".join(line + chr(10) for line in script), encoding="utf-8", newline=chr(10)
    )
    (fake / "sed").chmod(0o755)
    profile = _profile(tmp_path, STARSHIP + USER_LINE + MISE)

    # when the starship block is dropped
    result = _lib(
        f'ps_profile_drop_block "{profile.as_posix()}" "starship init"', [fake]
    )

    # then it still works
    assert result.returncode == 0, result.stderr
    assert profile.read_text(encoding="utf-8") == USER_LINE + MISE


def _marker_pos(text: str, name: str) -> int:
    return text.index(f'"# >>> dotfiles managed block: {name} >>>"')


def test_deploy_writes_mise_activate_before_starship() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    assert _marker_pos(text, "mise activate") < _marker_pos(text, "starship init")


def test_deploy_moves_a_misordered_starship_block() -> None:
    text = DEPLOY.read_text(encoding="utf-8")
    move = text.index("ps_profile_starship_before_mise")
    assert move < _marker_pos(text, "starship init")
    assert "ps_profile_drop_block" in text[move : _marker_pos(text, "starship init")]


def test_doctor_reports_a_misordered_profile() -> None:
    assert "ps_profile_starship_before_mise" in DOCTOR.read_text(encoding="utf-8")
