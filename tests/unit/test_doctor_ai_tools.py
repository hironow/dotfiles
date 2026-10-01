"""doctor's AI tooling section warns when the check itself cannot run.

The section runs scripts/ai_tools_check.py through `uv run --frozen` and counts
its OK/WARN lines. When uv failed (offline, a missing cache, a crash) the
section printed nothing and doctor looked clean (found in review). The block
is cut out of doctor.sh and run with doctor's own helpers and a fake uv.
"""

import re
import shutil
from pathlib import Path

import pytest
from _bash_hook import bash_path, run_bash

ROOT = Path(__file__).resolve().parents[2]
DOCTOR = ROOT / "scripts" / "doctor.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _section() -> str:
    text = DOCTOR.read_text(encoding="utf-8")
    helpers = re.search(r"(?ms)^log_ok\(\).*?^has\(\).*?$", text)
    block = re.search(r"(?ms)^# AI tooling:.*?^fi$", text)
    assert helpers and block
    return (
        helpers[0]
        + "\nok=0; warn=0; err=0\n"
        + block[0]
        + '\necho "counts $ok $warn $err"\n'
    )


def _run(tmp_path: Path, fake_uv: str) -> str:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(f"#!/bin/sh\n{fake_uv}\n", encoding="utf-8", newline="\n")
    uv.chmod(0o755)
    # doctor.sh locates the script next to itself
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    harness = scripts / "doctor.sh"
    harness.write_text(_section(), encoding="utf-8", newline="\n")
    done = run_bash(
        harness,
        cwd=tmp_path,
        env={"PATH": f"{bash_path(bin_dir)}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout


def test_a_check_that_cannot_run_warns(tmp_path: Path) -> None:
    out = _run(tmp_path, "echo 'error: Failed to fetch' >&2\nexit 2")
    assert "WARN ai-tools" in out
    assert "counts 0 1 0" in out


def test_the_checks_lines_are_counted(tmp_path: Path) -> None:
    out = _run(
        tmp_path, "echo 'OK   rtk - 0.50.0 via mise'\necho 'WARN jev-key - none'"
    )
    assert "WARN ai-tools" not in out
    assert "counts 1 1 0" in out
