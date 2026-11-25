"""The root JS workspace gate delegates the Pi extension to a real Bun gate."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")


def _recipe_body(text: str, name: str) -> str:
    bodies = re.findall(
        rf"^{re.escape(name)}:\n((?:[ \t]+[^\n]*(?:\n|$)|\n)*)", text, re.MULTILINE
    )
    assert len(bodies) == 1, f"missing or ambiguous recipe: {name}"
    return bodies[0]


@pytest.mark.parametrize(
    ("name", "earlier"),
    [("check", "spec-check"), ("fmt", "pre-fmt"), ("lint", "pre-lint")],
)
def test_recipe_selection_uses_full_header(name: str, earlier: str) -> None:
    text = f"{earlier}:\n    wrong\n\n{name}:\n    expected\n"
    assert _recipe_body(text, name) == "    expected\n"


@pytest.mark.parametrize(
    "text", ["", "spec-check:\n    wrong\n", "check:\n    one\ncheck:\n    two\n"]
)
def test_recipe_selection_rejects_missing_or_duplicate_headers(text: str) -> None:
    with pytest.raises(AssertionError, match="missing or ambiguous recipe"):
        _recipe_body(text, "check")


def test_the_claude_live_verification_is_one_command() -> None:
    assert (
        "\njev-claude-verify:\n    {{ UV_RUN }} scripts/jev_claude_verify.py"
        in JUSTFILE
    )
