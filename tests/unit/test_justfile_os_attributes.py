"""OS-limited justfile recipes must carry just's OS attributes (static-parse guards).

just's `[windows]` / `[macos]` attributes are the spec-level mark for
OS-limited recipes: the recipe is only defined on that OS, so `just --list`
elsewhere doesn't advertise commands that cannot run. These tests pin which
recipes are OS-limited:

- `add-scoop`   : scoop restore — Windows-only (ADR 0032; runtime uname guard stays)
- `wsl-compact` : WSL vhdx slack report — Windows host only (ADR 0035)
- `start-cdp` / `debug-cdp` : hardcoded /Applications Chrome Dev path — macOS-only
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

JUSTFILE = Path(__file__).resolve().parents[2] / "justfile"


@pytest.fixture(scope="module")
def justfile_lines() -> list[str]:
    return JUSTFILE.read_text(encoding="utf-8").splitlines()


def _recipe_attributes(lines: list[str], name: str) -> list[str]:
    """Contiguous attribute lines (`[...]`) directly above the recipe definition."""
    def_re = re.compile(rf"^{re.escape(name)}[^:\n]*:")
    for i, line in enumerate(lines):
        if def_re.match(line):
            attrs: list[str] = []
            for prev in reversed(lines[:i]):
                if re.fullmatch(r"\[.*\]", prev.strip()):
                    attrs.append(prev.strip())
                else:
                    break
            return attrs
    pytest.fail(f"recipe {name!r} not found in justfile")


def _has_os_attribute(attrs: list[str], os_name: str) -> bool:
    return any(re.search(rf"\b{os_name}\b", a) for a in attrs)


@pytest.mark.parametrize("recipe", ["add-scoop", "wsl-compact"])
def test_windows_only_recipes_carry_windows_attribute(
    justfile_lines: list[str], recipe: str
) -> None:
    attrs = _recipe_attributes(justfile_lines, recipe)
    assert _has_os_attribute(attrs, "windows"), (
        f"{recipe} is Windows-only and must carry just's [windows] attribute "
        f"so other OSes don't list a recipe that cannot run (found: {attrs})"
    )


@pytest.mark.parametrize("recipe", ["start-cdp", "debug-cdp"])
def test_macos_only_recipes_carry_macos_attribute(
    justfile_lines: list[str], recipe: str
) -> None:
    attrs = _recipe_attributes(justfile_lines, recipe)
    assert _has_os_attribute(attrs, "macos"), (
        f"{recipe} hardcodes /Applications (macOS) and must carry just's [macos] "
        f"attribute so other OSes don't list a recipe that cannot run "
        f"(found: {attrs})"
    )
