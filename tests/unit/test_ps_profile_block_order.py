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
    found = shutil.which("bash")
    if found is None or "system32" in found.lower():
        return None  # WSL's System32 bash cannot read drive-lettered paths
    return found


BASH = _bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="needs a POSIX bash")


def _lib(call: str) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    return subprocess.run(
        [BASH, "-c", f'set -euo pipefail; . "{LIB.as_posix()}"; {call}'],
        capture_output=True,
        text=True,
        encoding="utf-8",
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
