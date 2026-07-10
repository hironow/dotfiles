"""`just doctor` as the native-Windows environment doctor (static-parse guards).

Why static: the Linux sandbox can't exercise a `uname`=MINGW branch and no CI
runner reproduces a stock native-Windows PowerShell PATH, so these guard the
Windows assurance wiring at PR-review time (same approach as
test_windows_setup_recipes.py).

Context: on native Windows, `just` translates the interpreter path of every
shebang recipe through `cygpath`. A stock persisted PATH carries Git\\bin
(bash) but not Git\\usr\\bin (cygpath), so from PowerShell every shebang
recipe dies with "could not find cygpath executable ..." while linewise
recipes keep working. Git Bash is immune (it prepends /usr/bin itself).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
DOCTOR_SH = ROOT / "scripts" / "doctor.sh"


@pytest.fixture(scope="module")
def justfile_text() -> str:
    return JUSTFILE.read_text(encoding="utf-8")


def _recipe_body(text: str, name: str) -> str:
    m = re.search(
        rf"(?ms)^{re.escape(name)}[^:\n]*:.*?\n(.*?)(?=^[A-Za-z_][\w-]*[^:\n]*:|\Z)",
        text,
    )
    assert m is not None, f"recipe {name!r} not found in justfile"
    return m.group(1)


def test_doctor_recipe_is_plain_bash_wrapper(justfile_text: str) -> None:
    """A shebang doctor cannot even start from PowerShell on a stock Windows
    PATH (no cygpath) — the diagnostics tool would die of the exact disease
    it exists to diagnose. It must stay a linewise plain-bash wrapper, which
    works from any shell and under any just version."""
    body = _recipe_body(justfile_text, "doctor")
    assert "#!" not in body, (
        "doctor must not be a shebang recipe: shebang recipes need cygpath on "
        "native Windows, which a stock PowerShell persisted PATH cannot reach"
    )
    assert re.search(r"@?bash scripts/doctor\.sh", body), (
        "doctor must delegate to scripts/doctor.sh via plain `bash` "
        "(linewise recipe, no shebang)"
    )
