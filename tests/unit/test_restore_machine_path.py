"""scripts/restore_machine_path.ps1 — guarded repair for a wiped HKLM
Machine PATH (ADR-less operational tool; found live: len=0, every fresh
shell born without System32).

Why static: no CI runner can (or should) exercise an HKLM write; these pin
the safety wiring at PR-review time (same approach as test_runner_gc.py's
ps1 checks).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from _pwsh import resolve_pwsh

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "restore_machine_path.ps1"


def test_parses_as_valid_powershell() -> None:
    pwsh = resolve_pwsh(os.environ) or shutil.which("powershell")
    if pwsh is None:
        pytest.skip("no PowerShell available to parse-check")
    check = (
        "$t=$null;$e=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{SCRIPT}',[ref]$t,[ref]$e)|Out-Null;"
        "if($e.Count -gt 0){$e|ForEach-Object{$_.ToString()};exit 1}"
    )
    proc = subprocess.run(
        [pwsh, "-NoProfile", "-Command", check],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode == 0, (
        "restore_machine_path.ps1 has syntax errors:\n" + proc.stdout
    )
