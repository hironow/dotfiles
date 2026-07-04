"""`just semgrep-test` must skip on native Windows.

semgrep's native-Windows engine does not fire some rules (verified: e.g.
`python-no-mutable-default-args` on `def f(x=[])` produces no finding while 25
sibling rules do), so `semgrep --test`'s annotation matching fails there even
though the rules are valid and pass on Linux/WSL/CI. The recipe therefore
uname-guards a clean skip on MINGW/MSYS/CYGWIN — mirroring the deploy/clean/dump
Windows branches (ADR 0018/0019) — so `just ci` does not hard-fail on a native
Windows host. This is a static-parse guard: the Linux sandbox cannot exercise a
`uname`=MINGW branch, so a regression would only surface on a real Windows box.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

JUSTFILE = Path(__file__).resolve().parents[2] / "justfile"


@pytest.fixture(scope="module")
def semgrep_test_recipe() -> str:
    text = JUSTFILE.read_text(encoding="utf-8")
    m = re.search(
        r"(?ms)^semgrep-test\s*:.*?\n(.*?)(?=^[A-Za-z_][\w-]*\s*:|\Z)",
        text,
    )
    assert m is not None, "semgrep-test recipe not found in justfile"
    return m.group(1)


def _windows_branch(recipe_body: str) -> str:
    m = re.search(
        r"(?:MINGW\*\|MSYS\*\|CYGWIN\*|MSYS\*\|MINGW\*\|CYGWIN\*)\)([\s\S]*?);;",
        recipe_body,
    )
    assert m is not None, "semgrep-test must have a MINGW/MSYS/CYGWIN case branch"
    return m.group(1)


def test_semgrep_test_dispatches_on_uname(semgrep_test_recipe: str) -> None:
    assert re.search(r'case\s+"\$\(uname\s+-s\)"\s+in', semgrep_test_recipe), (
        "semgrep-test must dispatch on `uname -s` so it can skip native Windows"
    )


def test_semgrep_test_windows_branch_skips_cleanly(semgrep_test_recipe: str) -> None:
    win = _windows_branch(semgrep_test_recipe)
    assert re.search(r"\bexit\s+0\b", win), (
        "semgrep-test windows branch must `exit 0` (skip cleanly, not fail)"
    )
    assert "uvx semgrep" not in win, (
        "semgrep-test windows branch must NOT invoke semgrep (`uvx semgrep …`): "
        "semgrep's native-Windows engine mis-fires rules, so it is skipped there "
        "(a descriptive mention of `semgrep --test` in the skip message is fine)"
    )
