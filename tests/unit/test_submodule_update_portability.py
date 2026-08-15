"""update-all-submodules must run on the fresh-WSL baseline git (static-parse guard).

Ubuntu 24.04 — the fresh-WSL provisioning baseline (README "fresh WSL
provisioning") — ships git 2.43, which does not accept
`git submodule update --no-recurse-submodules`. The grandchild-drift guard the
flag provided (keep nested submodules pinned even if a user's global gitconfig
sets `submodule.recurse=true`) must instead use the version-portable
`git -c submodule.recurse=false submodule update ...` form.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

JUSTFILE = Path(__file__).resolve().parents[2] / "justfile"


@pytest.fixture(scope="module")
def recipe_body() -> str:
    """Lines of the update-all-submodules recipe (up to the next top-level line)."""
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^update-all-submodules[^:\n]*:", line):
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                if nxt and not nxt.startswith((" ", "\t")):
                    break
                body.append(nxt)
            return "\n".join(body)
    pytest.fail("recipe 'update-all-submodules' not found in justfile")


def test_no_flag_unsupported_by_baseline_git(recipe_body: str) -> None:
    assert "--no-recurse-submodules" not in recipe_body, (
        "git submodule update --no-recurse-submodules is not accepted by "
        "git 2.43 (Ubuntu 24.04, the fresh-WSL baseline); use "
        "`git -c submodule.recurse=false submodule update ...` instead"
    )


def test_recursion_guard_is_preserved(recipe_body: str) -> None:
    assert re.search(
        r"git\s+-c\s+submodule\.recurse=false\s+submodule\s+update\s+--remote",
        recipe_body,
    ), (
        "the grandchild-drift guard must survive the portability fix: the "
        "--remote update needs `-c submodule.recurse=false` so a user gitconfig "
        "with submodule.recurse=true cannot drag nested submodules off their "
        "parents' pinned SHAs"
    )
