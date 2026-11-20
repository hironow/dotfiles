"""Unit tests for scripts/instruction_budget.py.

The always-loaded instruction files (ROOT_AGENTS.md base + ROOT_CLAUDE.md
overlay) are kept short because adherence — not token cost — is the
constraint. The budget script counts list items outside fenced code blocks
and HTML comments as a proxy for instruction count, and fails above a cap
so the set cannot grow unnoticed (raising the cap is a visible edit).
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Import from scripts (add parent to path)
sys.path.insert(0, str(REPO / "scripts"))

from instruction_budget import count_instructions, main


def test_counts_dash_star_and_numbered_items() -> None:
    text = "- one\n* two\n1. three\n12. four\nprose line\n# heading\n"
    assert count_instructions(text) == 4


def test_indented_list_items_count() -> None:
    text = "- top\n  - nested\n"
    assert count_instructions(text) == 2


def test_fenced_code_blocks_are_excluded() -> None:
    text = "- real\n```sh\n- not an instruction\n```\n- real too\n"
    assert count_instructions(text) == 2


def test_html_comments_are_excluded() -> None:
    text = "<!--\n- commented out\n-->\n- real\n- also <!-- inline note -->\n"
    assert count_instructions(text) == 2


def test_tables_and_prose_are_not_counted() -> None:
    text = "| a | b |\n|---|---|\n| x | y |\nplain prose\n"
    assert count_instructions(text) == 0


def test_main_reports_and_passes_under_max(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    f = tmp_path / "doc.md"
    f.write_text("- one\n- two\n", encoding="utf-8")
    assert main(["--max", "5", str(f)]) == 0
    out = capsys.readouterr().out
    assert "doc.md" in out
    assert "2" in out


def test_main_fails_over_max(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("- one\n- two\n- three\n", encoding="utf-8")
    assert main(["--max", "2", str(f)]) == 1


def test_main_without_max_only_reports(tmp_path: Path) -> None:
    f = tmp_path / "doc.md"
    f.write_text("- one\n" * 100, encoding="utf-8")
    assert main([str(f)]) == 0
