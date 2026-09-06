"""Unit tests for scripts/skills_compare.py (fork vs upstream quantitative pass).

The comparison is deterministic and cheap: per-version size (lines, words,
estimated tokens, description length), frontmatter sanity, tooling-rule
violations in the body, and pairwise SKILL.md diff sizes. It is the first
step of the fork-dedup playbook, before any judge model reads the files.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from skills_compare import diff_lines, main, metrics


def _skill(root: Path, name: str, body: str, desc: str = "Use when asked.") -> Path:
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {desc}\n---\n{body}", encoding="utf-8"
    )
    return d


def test_metrics_reports_sizes_and_frontmatter(tmp_path: Path) -> None:
    d = _skill(tmp_path, "fork", "# Fork\n\nOne two three four five.\n")
    m = metrics(d)
    assert m["name==dir"] is True
    assert m["lines"] == 7
    assert m["words(body)"] == 6
    assert m["desc_chars"] == len("Use when asked.")
    assert m["violations"] == {}


def test_metrics_flags_tooling_violations_only_in_commands(tmp_path: Path) -> None:
    body = (
        "# F\n\nRun `npm install foo` then `pip install bar`.\n"
        "Please make sure the tests pass.\n"
    )
    m = metrics(_skill(tmp_path, "fork", body))
    assert m["violations"] == {"npm": 1, "pip/poetry": 1}


def test_diff_lines_counts_changed_lines(tmp_path: Path) -> None:
    a = _skill(tmp_path, "a", "# A\n\nline one\nline two\n")
    b = _skill(tmp_path, "b", "# A\n\nline one\nline changed\nline added\n")
    assert diff_lines(a, b) == 3


def test_main_prints_a_table_for_every_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _skill(tmp_path, "fork", "# A\n\nbody\n")
    b = _skill(tmp_path, "upstream", "# A\n\nbody more\n")
    assert main([str(a), str(b)]) == 0
    out = capsys.readouterr().out
    assert "fork" in out
    assert "upstream" in out
    assert "diff lines" in out
