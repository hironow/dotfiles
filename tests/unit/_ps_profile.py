"""Run scripts/ps_profile_lib.sh functions from a test, on any OS.

The library runs under a POSIX bash: Git Bash on Windows, the system bash
elsewhere. Shared by the tests of the PowerShell profile's managed blocks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "ps_profile_lib.sh"


def _find_bash() -> str | None:
    """A POSIX bash, chosen like test_ps_profile_path's ``_unwrapped_bash``:
    never WSL's System32 launcher (it cannot read drive-lettered paths), and
    behind Git for Windows' ``<git>/bin/bash.exe`` launcher the real
    ``<git>/usr/bin/bash.exe``. ``run_lib`` puts that bash's own directory first
    on PATH, so the lib's sed/grep/cut come from the same toolset whether the
    suite runs from Git Bash or PowerShell."""
    found = shutil.which("bash")
    if found is None or "system32" in found.lower():
        return None
    exe = Path(found)
    real = exe.parent.parent / "usr" / "bin" / exe.name
    return str(real) if exe.parent.name.lower() == "bin" and real.is_file() else found


BASH = _find_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="needs a POSIX bash")


def run_lib(
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


def write_profile(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "profile.ps1"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
