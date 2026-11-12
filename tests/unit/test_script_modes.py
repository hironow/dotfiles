"""A tracked Python file that starts with a shebang is tracked as executable.

Native Windows has no executable bit, so a script written there lands as
100644. Linux CI then fails ruff's EXE001 inside the sandbox suite, twenty
minutes in (PR #604). This test catches it in the fast unit gate on every OS.
Shell scripts are left out: many are run as `bash script.sh` and stay 100644.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _tracked_modes() -> dict[str, str]:
    out = subprocess.run(
        ["git", "ls-files", "-s", "--", "*.py"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    return {line.split("\t", 1)[1]: line.split()[0] for line in out.splitlines()}


def test_every_python_file_with_a_shebang_is_executable() -> None:
    missing = [
        path
        for path, mode in _tracked_modes().items()
        if mode == "100644" and (ROOT / path).read_bytes()[:2] == b"#!"
    ]
    assert not missing, (
        "shebang without the executable bit (git update-index --chmod=+x): "
        f"{sorted(missing)}"
    )
