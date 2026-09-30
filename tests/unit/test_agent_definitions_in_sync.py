"""Each subagent ships twice: Markdown for Claude/Gemini, TOML for Codex.

Codex reads only ~/.codex/agents/*.toml (name, description and
developer_instructions are required), so the Codex copy must say exactly what
the Markdown one does. This pins the two together so an edit to one cannot
silently leave the other behind.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

AGENTS = Path(__file__).resolve().parents[2] / "agents"
MARKDOWN = sorted(AGENTS.glob("*.md"))


def _frontmatter_and_body(path: Path) -> tuple[dict[str, str], str]:
    """Split `---` frontmatter from the body; read `key: value` and `key: |` blocks."""
    text = path.read_text(encoding="utf-8")
    _, header, body = text.split("---\n", 2)
    fields: dict[str, str] = {}
    key = ""
    for line in header.splitlines():
        if line.startswith("  ") and key:
            fields[key] += line.removeprefix("  ") + "\n"
        elif ":" in line:
            key, value = (part.strip() for part in line.split(":", 1))
            fields[key] = "" if value == "|" else value
    return fields, body


def test_there_are_agents_to_compare() -> None:
    assert MARKDOWN


@pytest.mark.parametrize("markdown", MARKDOWN, ids=lambda path: path.stem)
def test_codex_toml_matches_markdown(markdown: Path) -> None:
    # given the Markdown definition and its Codex twin
    fields, body = _frontmatter_and_body(markdown)
    toml_path = markdown.with_suffix(".toml")
    assert toml_path.is_file(), f"{toml_path.name} is missing: Codex cannot load it"

    # when the TOML is parsed
    codex = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    # then both describe the same agent with the same instructions
    assert codex["name"] == fields["name"]
    assert codex["description"].strip() == fields["description"].strip()
    assert codex["developer_instructions"].strip() == body.strip()
