"""Every skill the agent instructions name is declared, so every home has it.

The hub and its spokes send agents to skills by name ("follow the `ui-sdk`
skill"). A name that no declaration installs works on the machine where someone
added it by hand and nowhere else. A store skill must be in
dump/harness/skill-lock.json (ADR 0043); a plugin's skill, written
`plugin:skill`, must come from a plugin in dump/harness/claude-plugins.json.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = sorted([*ROOT.glob("ROOT_AGENTS*.md"), ROOT / "ROOT_CLAUDE.md"])
_NAMED = re.compile(r"\bthe `([a-z0-9][a-z0-9:-]*)` skill\b")


def _named_skills() -> dict[str, str]:
    named = {}
    for source in SOURCES:
        text = " ".join(source.read_text(encoding="utf-8").split())
        for name in _NAMED.findall(text):
            named.setdefault(name, source.name)
    return named


def _store_skills() -> set[str]:
    lock = json.loads(
        (ROOT / "dump/harness/skill-lock.json").read_text(encoding="utf-8")
    )
    return {skill["installed_dir"] for skill in lock["skills"]}


def _plugins() -> set[str]:
    plugins = json.loads(
        (ROOT / "dump/harness/claude-plugins.json").read_text(encoding="utf-8")
    )
    return {plugin_id.partition("@")[0] for plugin_id in plugins["plugins"]}


def test_every_named_skill_is_declared() -> None:
    named = _named_skills()
    assert named, "expected the instructions to name a skill"
    store, plugins = _store_skills(), _plugins()
    missing = [
        f"{name} ({source})"
        for name, source in named.items()
        if (name.partition(":")[0] not in plugins if ":" in name else name not in store)
    ]
    assert missing == [], f"named in the instructions but never installed: {missing}"


def test_the_pattern_reads_store_and_plugin_skills() -> None:
    text = "Follow the `ui-sdk` skill, or the `grilling:grit-grill` skill."
    assert _NAMED.findall(text) == ["ui-sdk", "grilling:grit-grill"]
