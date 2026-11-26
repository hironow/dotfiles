"""Static-parse guards wiring the rogue-npm-global check into doctor + just.

The behaviour of scripts/rogue_npm_globals.sh is covered by
test_rogue_npm_globals.py; here we only guard that it stays wired in:

- `just doctor` (scripts/doctor.sh) runs the detector CROSS-PLATFORM (outside
  the Windows `uname` case — the shadow risk exists on any OS) and, crucially,
  warns rather than reporting OK when the scan cannot resolve (non-zero exit).
- `just prune-rogue-npm-globals` exists as a linewise plain-bash wrapper (no
  shebang, so it runs from PowerShell without cygpath, like `doctor`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
DOCTOR_SH = ROOT / "scripts" / "doctor.sh"


@pytest.fixture(scope="module")
def doctor_text() -> str:
    return DOCTOR_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def justfile_text() -> str:
    return JUSTFILE.read_text(encoding="utf-8")


def test_doctor_runs_rogue_detector(doctor_text: str) -> None:
    assert "rogue_npm_globals.sh detect" in doctor_text, (
        "doctor must run scripts/rogue_npm_globals.sh detect"
    )
    assert "npm-rogue" in doctor_text, "doctor must label the check 'npm-rogue'"
    assert "just prune-rogue-npm-globals" in doctor_text, (
        "doctor must hint the fix recipe on a finding"
    )


def test_doctor_rogue_check_is_cross_platform(doctor_text: str) -> None:
    """The detector call must be OUTSIDE the Windows-only `uname` case — the
    shadow risk (a `codex update` on any OS) is not Windows-specific."""
    idx_call = doctor_text.index("rogue_npm_globals.sh detect")
    idx_wincase = doctor_text.index('case "$(uname -s)" in')
    assert idx_call < idx_wincase, (
        "the npm-rogue check must run before/outside the Windows uname case"
    )


def test_doctor_warns_not_ok_on_scan_error(doctor_text: str) -> None:
    """A non-zero detector exit (installs dir unresolvable) must WARN, never
    fall through to log_ok — otherwise a broken scan reads as 'clean'."""
    seg = doctor_text[doctor_text.index("npm-rogue") - 400 :]
    assert re.search(r'rc"?\s*-ne\s+0.*\n.*log_warn', seg, re.DOTALL) or re.search(
        r'\[ "\$rc" -ne 0 \]', doctor_text
    ), "doctor must branch on the detector's non-zero exit and warn"
