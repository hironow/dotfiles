"""Native-Windows guards on justfile recipes that would otherwise hang or error.

Static-parse guards (the Linux sandbox can't exercise a `uname`=MINGW branch, so
a regression would only surface on a real Windows host):

- `validate-path-duplicates`: its role() classifier only knows Unix structural
  paths and it globs every file in every PATH dir (System32/Program Files), so
  on native Windows it is slow + all false positives — `doctor`/`self-check`
  hang on it. Must skip on Windows.
- `update-brew` / `update-gcloud`: no brew/gcloud/sudo on Windows. Must skip so
  `update-all` (which calls them) does not abort before its guarded mise/gh/tldr
  tail.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

JUSTFILE = Path(__file__).resolve().parents[2] / "justfile"


@pytest.fixture(scope="module")
def justfile_text() -> str:
    return JUSTFILE.read_text(encoding="utf-8")


def _recipe_body(text: str, name: str) -> str:
    m = re.search(
        rf"(?ms)^{re.escape(name)}\s*:.*?\n(.*?)(?=^[A-Za-z_][\w-]*\s*:|\Z)",
        text,
    )
    assert m is not None, f"recipe {name!r} not found in justfile"
    return m.group(1)


def _windows_branch(body: str) -> str:
    m = re.search(
        r"(?:MINGW\*\|MSYS\*\|CYGWIN\*|MSYS\*\|MINGW\*\|CYGWIN\*)\)([\s\S]*?);;",
        body,
    )
    assert m is not None, "no MINGW/MSYS/CYGWIN case branch"
    return m.group(1)


@pytest.mark.parametrize(
    "recipe",
    ["validate-path-duplicates", "update-brew", "update-gcloud"],
)
def test_recipe_skips_on_native_windows(justfile_text: str, recipe: str) -> None:
    body = _recipe_body(justfile_text, recipe)
    assert re.search(r'case\s+"\$\(uname\s+-s\)"\s+in', body), (
        f"{recipe} must dispatch on `uname -s` so it can skip native Windows"
    )
    win = _windows_branch(body)
    assert re.search(r"\bexit\s+0\b", win), (
        f"{recipe} windows branch must `exit 0` (skip cleanly, not hang/error)"
    )
