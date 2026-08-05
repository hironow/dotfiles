"""Unit tests for scripts/check_agent_home_refs.py.

The deployed-reference checker must understand every path shape the sync
actually writes. On Windows the sync rewrites `docs/agents/` references to
the agent home's native absolute path (e.g. `C:\\Users\\me\\.claude/docs/
agents/x.md`, mixed separators); a checker that only recognizes `/Users/`
and `~/` prefixes mis-flags every such rewritten reference as a "bare
docs/agents/ reference" — a Windows-only false positive that turns
`just check-agent-refs` permanently red there.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(REPO / "scripts"))

from check_agent_home_refs import _scan_file  # noqa: E402


def _scan_text(tmp_path: Path, text: str) -> list[str]:
    f = tmp_path / "AGENTS.md"
    f.write_text(text, encoding="utf-8")
    return _scan_file(f)


def test_windows_drive_ref_is_recognized_not_bare(tmp_path: Path) -> None:
    """A sync-rewritten Windows ref (backslash home + forward-slash tail) must
    be treated as an absolute reference: existence-checked ("dead path"), never
    mis-flagged as a bare docs/agents/ rewrite miss."""
    problems = _scan_text(
        tmp_path,
        "see C:\\Users\\nobody\\.claude/docs/agents/tdd-workflow.md for more\n",
    )
    assert not any("bare 'docs/agents/'" in p for p in problems), problems
    assert any("dead path reference" in p for p in problems), problems


def test_windows_drive_glob_ref_is_recognized_not_bare(tmp_path: Path) -> None:
    """Glob-form Windows refs (`...\\.claude/docs/agents/*.md`) get the same
    treatment as their /Users/ counterparts: prefix-checked, not bare-flagged."""
    problems = _scan_text(
        tmp_path,
        "exclude C:\\Users\\nobody\\.claude/docs/agents/*.md from scans\n",
    )
    assert not any("bare 'docs/agents/'" in p for p in problems), problems


def test_linux_home_ref_is_recognized_not_bare(tmp_path: Path) -> None:
    """A sync-rewritten Linux ref (`/home/<user>/.claude/docs/agents/x.md`,
    as written on WSL/Linux homes) must be treated as an absolute reference:
    existence-checked ("dead path"), never mis-flagged as a bare
    docs/agents/ rewrite miss."""
    problems = _scan_text(
        tmp_path,
        "see /home/nobody/.claude/docs/agents/tdd-workflow.md for more\n",
    )
    assert not any("bare 'docs/agents/'" in p for p in problems), problems
    assert any("dead path reference" in p for p in problems), problems


def test_linux_home_glob_ref_is_recognized_not_bare(tmp_path: Path) -> None:
    """Glob-form Linux refs (`/home/<user>/.claude/docs/agents/*.md`) get the
    same treatment as their /Users/ counterparts: prefix-checked, not
    bare-flagged."""
    problems = _scan_text(
        tmp_path,
        "exclude /home/nobody/.claude/docs/agents/*.md from scans\n",
    )
    assert not any("bare 'docs/agents/'" in p for p in problems), problems


def test_bare_reference_is_still_flagged(tmp_path: Path) -> None:
    problems = _scan_text(tmp_path, "see docs/agents/testing.md\n")
    assert any("bare 'docs/agents/'" in p for p in problems), problems


@pytest.mark.skipif(sys.platform != "win32", reason="real drive paths need Windows")
def test_existing_windows_drive_ref_resolves(tmp_path: Path) -> None:
    spoke = tmp_path / "docs" / "agents" / "spoke.md"
    spoke.parent.mkdir(parents=True)
    spoke.write_text("x\n", encoding="utf-8")
    ref = str(tmp_path).replace("/", "\\") + "/docs/agents/spoke.md"
    problems = _scan_text(tmp_path, f"see {ref} here\n")
    assert problems == []
