#!/usr/bin/env python3
"""The Claude homes dotfiles manages, and what a per-home script shares.

claude_plugins and headroom_mcp visit every existing home and drive Claude
Code's own CLI there; ai_tools_check reads each home's settings. The home
names live here once, in the order the scripts report them.
"""

from pathlib import Path

NAMES = (
    ".claude",
    ".claude-work-a",
    ".claude-work-b",
    ".claude-work-c",
    ".claude-work-d",
)


def existing(home: Path) -> list[Path]:
    """The managed homes under `home` that exist; a missing one is never made."""
    return [home / name for name in NAMES if (home / name).is_dir()]
