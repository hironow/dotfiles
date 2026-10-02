"""The rtk 'run `rtk init -g`' notice is a documented false positive.

rtk only recognises its own installer's layout, so the dotfiles-managed hook
(`hooks/rtk-hook-claude.sh`) is invisible to it and every rtk run prints "No
hook installed — run `rtk init -g`". Acting on that notice would add the hook
block `just sync-agents` retires (`RETIRED_HOOK_COMMAND`), so the spoke has to
keep saying the notice is expected. The assertions below are scoped to the
paragraph that discusses the notice: a file-wide substring match would pass on
the older "`rtk init -g` is never needed" sentence alone.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPOKE = ROOT / "ROOT_AGENTS_docs_agents_rtk.md"

# One paragraph must carry all of these, so moving or dropping the note fails.
REQUIRED_IN_PARAGRAPH = (
    "No hook installed",
    "rtk init --show",
    "Hook: not found",
    "expected",
    "claude-rtk-hook",
)


def _paragraph_mentioning(needle: str) -> str:
    paragraphs = [
        " ".join(block.split())
        for block in SPOKE.read_text(encoding="utf-8").split("\n\n")
    ]
    matching = [p for p in paragraphs if needle in p]
    assert len(matching) == 1, f"expected exactly one {needle!r} paragraph"
    return matching[0]


def test_spoke_says_the_init_notice_is_expected() -> None:
    paragraph = _paragraph_mentioning("No hook installed")
    missing = [t for t in REQUIRED_IN_PARAGRAPH if t not in paragraph]
    assert not missing, f"notice paragraph lost: {missing}"
