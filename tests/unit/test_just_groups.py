"""Every public recipe is listed in a group, with a doc comment.

`just --list` is how a person finds a recipe: recipes are listed by group
(the manual's Groups section) with their doc comments (Documentation
Comments). The root justfile uses one fixed set of groups, by purpose; the
template's recipes are grouped and documented the same way. A bare `just`
lists the recipes through `set default-list`, the manual's setting for it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
TEMPLATE = ROOT / "templates/agent-baseline/justfile"
# The root justfile's groups, by purpose. AGENTS.md (Task runner) names what
# goes in each.
GROUPS = {
    "gate",
    "lint",
    "test",
    "setup",
    "doctor",
    "agents",
    "runner",
    "emulator",
    "telemetry",
    "tailnet",
    "cloud",
    "dns",
    "site",
    "debug",
    "meta",
}
SKIP = re.compile(
    r"^(#|\[|set |alias |export |import |mod |\s|\}|$)"
    r"|^[A-Za-z_][\w-]*\s*:="
    r"|^[A-Za-z_][\w-]*\([^)]*\)\s*:="
)


def _recipes(path: Path) -> list[tuple[str, list[str], str | None]]:
    """(name, attribute lines, doc) of every recipe header, every OS's variant.

    The doc is the comment right above the recipe's attributes, or the value
    of a `[doc('...')]` attribute, as `just --list` shows it.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    found = []
    for i, line in enumerate(lines):
        if SKIP.match(line):
            continue
        m = re.match(r"^@?([A-Za-z_][\w-]*)", line)
        if not m:
            continue
        j, attrs = i - 1, []
        while j >= 0 and lines[j].startswith("["):
            attrs.insert(0, lines[j])
            j -= 1
        doc = None
        docattr = re.findall(r"^\[doc\('([^']*)'\)\]$", "\n".join(attrs), re.MULTILINE)
        if docattr:
            doc = docattr[0]
        elif j >= 0 and lines[j].startswith("#") and not lines[j].startswith("#!"):
            doc = lines[j][1:].strip()
        found.append((m.group(1), attrs, doc))
    return found


def _public(path: Path) -> list[tuple[str, list[str], str | None]]:
    return [
        r
        for r in _recipes(path)
        if not r[0].startswith("_") and "[private]" not in r[1]
    ]


def _groups(attrs: list[str]) -> list[str]:
    return re.findall(r"^\[group\('([^']*)'\)\]$", "\n".join(attrs), re.MULTILINE)


def test_the_parser_sees_every_recipe_just_sees() -> None:
    just = shutil.which("just")
    if just is None:
        pytest.skip("needs just")
    dumped = json.loads(
        subprocess.run(
            [just, "--justfile", str(JUSTFILE), "--dump", "--dump-format", "json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        ).stdout
    )["recipes"]
    parsed = {name for name, _, _ in _recipes(JUSTFILE)}
    assert set(dumped) <= parsed, sorted(set(dumped) - parsed)


def test_every_public_recipe_is_in_exactly_one_known_group() -> None:
    wrong = [
        (name, _groups(attrs))
        for name, attrs, _ in _public(JUSTFILE)
        if len(_groups(attrs)) != 1 or _groups(attrs)[0] not in GROUPS
    ]
    assert not wrong, wrong


def test_every_group_holds_a_recipe() -> None:
    used = {g for _, attrs, _ in _public(JUSTFILE) for g in _groups(attrs)}
    assert used == GROUPS, (sorted(GROUPS - used), sorted(used - GROUPS))


@pytest.mark.parametrize("path", [JUSTFILE, TEMPLATE], ids=["justfile", "template"])
def test_every_public_recipe_has_a_doc(path: Path) -> None:
    missing = [name for name, _, doc in _public(path) if not doc]
    assert not missing, missing


def test_the_template_groups_every_public_recipe() -> None:
    wrong = [name for name, attrs, _ in _public(TEMPLATE) if len(_groups(attrs)) != 1]
    assert not wrong, wrong


@pytest.mark.parametrize("path", [JUSTFILE, TEMPLATE], ids=["justfile", "template"])
def test_a_bare_just_lists_the_recipes(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^set default-list$", text, re.MULTILINE)
    # the setting replaces the old `default: help` recipe
    assert not re.search(r"^default:", text, re.MULTILINE)


@pytest.mark.parametrize("path", [JUSTFILE, TEMPLATE], ids=["justfile", "template"])
def test_a_recipe_under_a_comment_block_names_its_summary_with_doc(path: Path) -> None:
    # `just --list` shows only the comment line right above a recipe. Under a
    # block of explanation that line is a fragment ("is a conscious,
    # reviewable edit of this line."), so such a recipe gives its one-line
    # summary with `[doc('...')]` (the manual's attribute for this) and the
    # block stays as the explanation.
    lines = path.read_text(encoding="utf-8").splitlines()
    fragments = []
    for i, line in enumerate(lines):
        if SKIP.match(line):
            continue
        m = re.match(r"^@?([A-Za-z_][\w-]*)", line)
        if not m or m.group(1).startswith("_"):
            continue
        j, attrs = i - 1, []
        while j >= 0 and lines[j].startswith("["):
            attrs.append(lines[j])
            j -= 1
        if "[private]" in attrs or any(a.startswith("[doc(") for a in attrs):
            continue
        if j >= 1 and lines[j].startswith("#") and lines[j - 1].startswith("#"):
            fragments.append(m.group(1))
    assert not fragments, fragments
