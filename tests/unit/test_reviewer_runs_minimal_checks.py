"""A reviewer never runs the whole gate: only the checks its findings need.

The owner's rule (2026-11-18): do not let Codex run `just check`, `just ci`, or
another command that runs all of CI at once. It may run the smallest test or
check that covers the diff it was given. The full gate is slow, and in the
reviewer's read-only sandbox it fails for reasons that say nothing about the
change. The caller runs the full gate.

Each assertion is scoped to the paragraph, bullet, or command that carries the
rule: moving or dropping the rule fails the test.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPOKE = ROOT / "ROOT_AGENTS_docs_agents_plan-review.md"

FULL_GATES = ("just check", "just ci", "just test")


def _blocks() -> list[str]:
    """Paragraphs and list items, each on one line."""
    text = SPOKE.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)", text)
    return [" ".join(block.split()) for block in blocks if block.strip()]


def _block_with(needle: str) -> str:
    matching = [block for block in _blocks() if needle in block]
    assert len(matching) == 1, f"expected one block with {needle!r}"
    return matching[0]


def _codex_prompts() -> list[str]:
    """The quoted prompt of every `codex exec` command in the guide."""
    text = SPOKE.read_text(encoding="utf-8")
    return re.findall(r'^codex exec[^\n]*\\\n\s+"([^"\n]+)"$', text, re.MULTILINE)


def test_the_guide_says_a_reviewer_runs_only_what_a_finding_needs() -> None:
    rule = _block_with("never runs the whole gate")
    for gate in FULL_GATES:
        assert f"`{gate}`" in rule, gate
    assert "smallest test or check" in rule
    assert "You run the full gate yourself" in rule


def test_every_codex_prompt_carries_the_limit() -> None:
    prompts = _codex_prompts()
    assert len(prompts) == 2, prompts  # the first review, and the resumed one
    for prompt in prompts:
        for gate in FULL_GATES:
            assert gate in prompt, (gate, prompt)
        assert "実行しない" in prompt
        assert "最小" in prompt


def test_no_codex_prompt_lets_the_shell_run_a_command() -> None:
    # The prompt sits in double quotes. A backtick or `$(` there is a command
    # substitution: the shell would run `just ci` before Codex ever started.
    for prompt in _codex_prompts():
        assert "`" not in prompt, prompt
        assert "$(" not in prompt, prompt
    assert "without backticks" in _block_with("never runs the whole gate")


def test_the_fallback_reviewer_gets_the_same_limit() -> None:
    step = _block_with("the same instruction you give Codex")
    assert "the limit on what it may run" in step
