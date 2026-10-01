"""What every per-home Claude script shares: which homes, and how to visit them.

claude_plugins and headroom_mcp (and doctor's settings checks) each carried
their own copy of the five home names; claude_homes holds them, in the order
the scripts report them, and only existing homes are visited.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import claude_homes  # noqa: E402


def test_the_homes_in_report_order() -> None:
    assert claude_homes.NAMES == (
        ".claude",
        ".claude-work-a",
        ".claude-work-b",
        ".claude-work-c",
        ".claude-work-d",
    )


def test_only_existing_homes_are_visited(tmp_path: Path) -> None:
    for name in (".claude-work-c", ".claude"):
        (tmp_path / name).mkdir()
    (tmp_path / ".claude-work-a").write_text("not a dir", encoding="utf-8")
    assert claude_homes.existing(tmp_path) == [
        tmp_path / ".claude",
        tmp_path / ".claude-work-c",
    ]
