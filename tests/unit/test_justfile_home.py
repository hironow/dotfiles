"""The justfile must evaluate in PowerShell environments with no HOME."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_exe_source_path_does_not_require_home_env(tmp_path: Path) -> None:
    just = shutil.which("just")
    if not just:
        pytest.skip("just unavailable")
    env = os.environ.copy()
    env.pop("HOME", None)
    env.pop("XDG_CACHE_HOME", None)
    env["USERPROFILE"] = str(tmp_path)
    result = subprocess.run(
        [just, "--evaluate", "_EXE_SRC_DIR"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("exe/src")
