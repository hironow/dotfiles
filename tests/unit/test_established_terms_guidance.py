"""The agent instructions keep private terms out and send new terms to the human.

ADR-0080: the owner's three rules are (1) do not use private terms of our own,
(2) take a special term from the industry or open source, and ask on the spot
before defining a private one, and (3) when many terms need deciding, or the
thing being built is a field of its own, find a glossary skill first. Each
assertion is scoped to the paragraph or bullet that carries the rule: moving or
dropping the rule fails the test, a stray mention elsewhere does not pass it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "ROOT_AGENTS.md"
NAMING = ROOT / "ROOT_AGENTS_docs_agents_naming.md"
PLAIN = ROOT / "ROOT_AGENTS_docs_agents_plain-language.md"

GLOSSARY_SKILLS = ("domain-modeling", "ubiquitous-language", "provable-glossary")


def _blocks(path: Path) -> list[str]:
    """Paragraphs and list items, each on one line."""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)", text)
    return [" ".join(block.split()) for block in blocks if block.strip()]


def _block_with(path: Path, needle: str) -> str:
    matching = [block for block in _blocks(path) if needle in block]
    assert len(matching) == 1, f"expected one block in {path.name} with {needle!r}"
    return matching[0]


def test_the_hub_rule_bans_private_terms_and_points_to_the_guide() -> None:
    rule = _block_with(HUB, "**Name things specifically")
    assert "Do not coin a private term" in rule
    assert "industry or open source" in rule
    assert "ask the human" in rule
    assert "docs/agents/naming.md" in rule


def test_the_hub_sends_term_choices_to_the_naming_guide() -> None:
    rows = [
        line
        for line in HUB.read_text(encoding="utf-8").splitlines()
        if "docs/agents/naming.md" in line and line.startswith("|")
    ]
    assert len(rows) == 1, rows
    assert "choosing a term" in rows[0]


def test_the_guide_opens_for_terms_as_well_as_names() -> None:
    assert "choose a term" in _block_with(NAMING, "Read this when")


def test_private_terms_are_not_used() -> None:
    rule = _block_with(NAMING, "Do not coin a private term.")
    assert "only this team" in rule


def test_a_special_term_comes_from_the_industry_or_open_source() -> None:
    rule = _block_with(NAMING, "Take the term from the field.")
    assert "industry" in rule
    assert "open-source" in rule
    for source in ("standard", "documentation"):
        assert source in rule, source


def test_a_new_private_term_needs_the_human_on_the_spot() -> None:
    rule = _block_with(NAMING, "When no established term fits")
    assert "stop and ask the human" in rule
    assert "before" in rule
    for part in ("which established terms you checked", "the term you propose"):
        assert part in rule, part
    assert "only after the human agrees" in rule


def test_many_terms_or_a_new_field_start_with_a_glossary_skill() -> None:
    rule = _block_with(NAMING, "build a glossary first")
    assert "many terms" in rule
    assert "a field of its own" in rule
    assert "before you define" in rule
    for skill in GLOSSARY_SKILLS:
        assert f"the `{skill}` skill" in rule, skill
    assert "the `find-skills` skill" in rule


def test_an_existing_private_term_is_not_exempt() -> None:
    # "It is already in the code" must not let a private term spread.
    rule = _block_with(NAMING, "An existing term is not exempt.")
    assert "only when it is an established term, or one the human approved" in rule
    assert "ask the human then and there" in rule
    assert "do not spread it into new names, docs, or answers" in rule
    assert "Leave existing identifiers and APIs as they are" in rule


def test_plain_language_points_to_the_term_rule() -> None:
    rule = _block_with(PLAIN, "Explain a technical term the first time")
    assert "docs/agents/naming.md" in rule


def test_a_term_in_doubt_is_written_in_english() -> None:
    rule = _block_with(NAMING, "write the term in English")
    assert "unsure" in rule
    for avoided in ("coined", "katakana", "forced Japanese"):
        assert avoided in rule, avoided
    assert "Japanese prose with ordinary English terms in it is fine" in rule


def test_the_hub_rule_keeps_a_doubtful_term_in_english() -> None:
    rule = _block_with(HUB, "**Name things specifically")
    assert "In Japanese text" in rule
    assert "in English" in rule


def test_plain_japanese_words_and_technical_terms_are_told_apart() -> None:
    rule = _block_with(PLAIN, "prefer plain words over kango and katakana")
    assert "ordinary words" in rule
    assert "technical term" in rule
    assert "English" in rule
    assert "docs/agents/naming.md" in rule
