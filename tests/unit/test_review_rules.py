"""Reviews are judged against the requirements, and they end (ADR-0091).

A reviewer asked to "review critically" finds something every round, and an
author who adopts every finding lets the review, not the requirement, set the
scope. The rules: brief the reviewer with the requirements, accept only a bug
or a broken requirement, decline the rest with a reason, stop after three
rounds, and settle what a test can settle with a test.

Each assertion is scoped to the paragraph, bullet, or command that carries the
rule: moving or dropping the rule fails the test.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPOKE = ROOT / "ROOT_AGENTS_docs_agents_plan-review.md"
OVERLAY = ROOT / "ROOT_CLAUDE.md"


def _blocks(path: Path) -> list[str]:
    """Paragraphs and list items, each on one line."""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)", text)
    return [" ".join(block.split()) for block in blocks if block.strip()]


def _block_with(path: Path, needle: str) -> str:
    matching = [block for block in _blocks(path) if needle in block]
    assert len(matching) == 1, f"expected one block with {needle!r}: {matching}"
    return matching[0]


def _codex_prompts() -> list[str]:
    text = SPOKE.read_text(encoding="utf-8")
    return re.findall(r'^codex exec[^\n]*\\\n\s+"([^"\n]+)"$', text, re.MULTILINE)


def test_the_guide_covers_code_review_too() -> None:
    first = SPOKE.read_text(encoding="utf-8").splitlines()[0]
    assert first == "# Plan and code review"


def test_the_reviewer_gets_the_requirements() -> None:
    block = _block_with(SPOKE, "Brief the reviewer with the requirements")
    for source in ("request", "done", "rules"):
        assert source in block, source


def test_every_codex_prompt_is_neutral_and_allows_no_findings() -> None:
    prompts = _codex_prompts()
    assert len(prompts) == 2, prompts
    for prompt in prompts:
        assert "批判的" not in prompt, prompt
        assert "致命的" not in prompt, prompt
        assert "指摘なし" in prompt, prompt
        assert "要件" in prompt, prompt


def test_only_a_bug_or_a_broken_requirement_is_accepted() -> None:
    block = _block_with(SPOKE, "Accept a finding only when")
    assert "bug" in block
    assert "requirement" in block
    assert "Declining every finding is a valid outcome" in block


def test_reviews_stop_after_three_rounds_with_no_exception() -> None:
    block = _block_with(SPOKE, "At most three rounds")
    assert "fourth" in block and "No fourth round" in block


def test_a_test_settles_what_a_test_can_settle() -> None:
    assert "instead of another round" in _block_with(SPOKE, "settle by a test")


def test_conflicting_requirements_are_decided_and_recorded() -> None:
    block = _block_with(SPOKE, "two requirements conflict")
    assert "record" in block


def test_relayed_findings_leave_room_to_decline() -> None:
    block = _block_with(SPOKE, "When you pass findings to an author")
    assert "decline" in block and "all" in block


def test_a_request_for_improvements_allows_no_change() -> None:
    assert "no change is needed" in _block_with(SPOKE, "improve your own work")


def test_the_overlay_states_the_three_rules_in_one_sentence() -> None:
    block = _block_with(OVERLAY, "Every plan that changes behavior")
    assert "requirements" in block
    assert "three rounds" in block
