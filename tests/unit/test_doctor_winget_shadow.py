"""doctor must flag WinGet copies that shadow mise-managed CLIs.

Why this exists
---------------
The npm-rogue check covers one way a stray copy of a mise-managed AI CLI ends
up ahead of mise on PATH (`npm install -g` into a node version's global).
`winget install` is a second route, and it lands in
`AppData/Local/Microsoft/WinGet/Links/`, which sits ahead of mise on PATH just
the same.

The failure mode is worse than npm-rogue's because it hides: while an
npm-global copy exists, *it* wins the PATH race and the WinGet copy is
invisible. On this host `claude` was served by an npm-global copy for weeks;
only after `just prune-rogue-npm-globals` removed it did a WinGet-installed
2.1.198 surface — six patch releases behind the 2.1.215 mise had. Nothing had
reported the duplicate, because nothing looked.

Static-parse only: the check reads a Windows user profile path and mise's own
resolution, neither reproducible on the Linux CI runner.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
DOCTOR_SH = ROOT / "scripts" / "doctor.sh"


@pytest.fixture(scope="module")
def doctor_text() -> str:
    return DOCTOR_SH.read_text(encoding="utf-8")


def test_doctor_checks_the_winget_links_dir(doctor_text: str) -> None:
    """WinGet's shim dir is the thing that outranks mise on PATH."""
    assert "WinGet/Links" in doctor_text or "WinGet\\Links" in doctor_text, (
        "doctor must inspect AppData/Local/Microsoft/WinGet/Links, where a "
        "`winget install` puts the shim that shadows mise."
    )


def test_doctor_covers_every_mise_managed_ai_cli(doctor_text: str) -> None:
    """Same set the npm-rogue check guards; a gap here is a silent duplicate."""
    section = doctor_text[doctor_text.find("WinGet") :]
    for cli in ("codex", "claude", "copilot", "pi"):
        assert re.search(rf"\b{cli}\b", section), (
            f"{cli} is managed by mise's npm backend but is not checked for a "
            "WinGet copy; that copy would win on PATH unnoticed."
        )


def test_doctor_reports_winget_shadow_with_a_fix(doctor_text: str) -> None:
    """A finding the reader cannot act on just grows the list."""
    assert "winget-shadow" in doctor_text, (
        "the check needs its own label so it can be grepped and read in the "
        "doctor output."
    )
    assert "winget uninstall" in doctor_text, (
        "the warning must name the command that resolves it, like the "
        "npm-rogue check names `just prune-rogue-npm-globals`."
    )
