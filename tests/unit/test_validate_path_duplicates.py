"""Checks for the `validate-path-duplicates` justfile recipe.

Why this exists
---------------
Seen live 2026-08-17: with the Windows PATH leaking into WSL
(`appendWindowsPath=true` default) the duplicate scan globbed every
`/mnt/<drive>/...` directory over the 9p filesystem — thousands of
System32 files at network-share latency — and `just doctor` appeared to
hang (>2 min). The recipe already skips native Windows for exactly this
reason ("System32 glob too slow"); WSL reaches the same directories
through `/mnt` and must skip them too. Windows-leak detection is not
lost: the sibling `validate-path-windows` check owns that finding.

Host-side (tests/unit/, `just ci`), same harness as
test_validate_path_windows.py.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"


def _recipe_body() -> str:
    text = JUSTFILE.read_text(encoding="utf-8")
    match = re.search(
        r"^validate-path-duplicates:\n(.*?)(?=^\S)", text, re.MULTILINE | re.DOTALL
    )
    assert match, "recipe validate-path-duplicates not defined"
    return match.group(1)


def test_skips_windows_drive_mounts() -> None:
    """The scan loop must skip `/mnt/<drive>` dirs before globbing them:
    9p makes the glob minutes-slow, and validate-path-windows already owns
    the Windows-leak finding."""
    assert re.search(r"/mnt/\[a-zA-Z\]", _recipe_body()), (
        "validate-path-duplicates must skip /mnt/<drive> PATH entries "
        "(9p glob is minutes-slow; leak detection belongs to "
        "validate-path-windows)"
    )


@pytest.fixture
def just_binary() -> str:
    if sys.platform == "win32":
        pytest.skip("shebang recipes need a Unix-style PATH; runs on Linux/WSL/CI")
    just = shutil.which("just")
    if just is None:
        pytest.skip("just not on PATH")
    return just


def test_detects_duplicates_across_dirs(just_binary: str, tmp_path: Path) -> None:
    """Two dirs shipping the same executable name -> exit 2, name surfaced.
    Pins that the /mnt skip does not silence real (non-mnt) duplicates."""
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    for d in (dir_a, dir_b):
        d.mkdir()
        exe = d / "dupcmd"
        exe.write_text("#!/bin/sh\n", encoding="utf-8")
        exe.chmod(0o755)
    env = {
        "PATH": f"{os.path.dirname(just_binary)}:/usr/bin:/bin:/usr/local/bin",
        "HOME": os.environ.get("HOME", "/root"),
        "VALIDATE_PATH": f"{dir_a}:{dir_b}",
    }
    result = subprocess.run(
        [just_binary, "-f", str(JUSTFILE), "validate-path-duplicates"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode == 2, (
        f"expected exit 2 on a real duplicate, got {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "dupcmd" in combined, f"expected duplicate name in output:\n{combined}"
