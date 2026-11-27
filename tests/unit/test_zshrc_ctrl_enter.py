"""Ctrl+Enter edits the current buffer without accepting the line."""

import shutil
import subprocess
from pathlib import Path

import pytest
from _zsh_startup import ROOT, run_zsh


@pytest.mark.skipif(shutil.which("zsh") is None, reason="needs zsh")
def test_zshrc_parses() -> None:
    result = subprocess.run(
        ["zsh", "-n", str(ROOT / ".zshrc")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_ctrl_enter_edits_buffer(tmp_path: Path) -> None:
    output = run_zsh(
        tmp_path,
        r"""
source "$1"
LBUFFER=left
RBUFFER=right
_ctrl_enter_newline
[[ "$LBUFFER" == $'left\n' && "$RBUFFER" == right ]] || exit 41
print -r -- edited
""",
    )
    assert output.splitlines() == ["edited"]
    calls = (tmp_path / "widgets").read_text(encoding="utf-8").splitlines()
    assert not [line for line in calls if line.split("\t")[0] == "accept-line"]
