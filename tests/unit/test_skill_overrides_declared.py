"""skillOverrides only names skills this repo declares.

A skill dropped from dump/harness/skill-lock.json leaves the stores once
each machine removes it, so an override naming it tunes nothing. Plugin
skills (`plugin:skill`) come from marketplaces this repo does not pin, so
only bare names are checked.
"""

import json
from pathlib import Path

DOTFILES = Path(__file__).resolve().parents[2]


def _declared_skills() -> set[str]:
    lock = json.loads(
        (DOTFILES / "dump/harness/skill-lock.json").read_text(encoding="utf-8")
    )
    return {record["installed_dir"] for record in lock["skills"]}


def _override_keys() -> dict[str, set[str]]:
    fragments = sorted((DOTFILES / ".claude").glob("settings.shared*.json"))
    fragments += sorted((DOTFILES / ".claude/settings.profiles").glob("*.json"))
    keys: dict[str, set[str]] = {}
    for fragment in fragments:
        settings = json.loads(fragment.read_text(encoding="utf-8")).get("settings", {})
        keys[fragment.relative_to(DOTFILES).as_posix()] = set(
            settings.get("skillOverrides", {})
        )
    return keys


def test_every_bare_skill_override_is_declared() -> None:
    declared = _declared_skills()
    stale = {
        fragment: sorted(
            name for name in names if ":" not in name and name not in declared
        )
        for fragment, names in _override_keys().items()
    }
    assert not {fragment: names for fragment, names in stale.items() if names}, (
        "skillOverrides names skills missing from dump/harness/skill-lock.json"
    )


def test_the_check_sees_the_shared_overrides() -> None:
    # Guard the guard: the shared layer carries overrides today
    assert _override_keys()[".claude/settings.shared.json"]
