"""Unit tests for Windows-aware hook command rendering in sync_agents.

On Windows a bare ``bash`` resolves to the System32 WSL bash before Git Bash
(documented hazard in repo CLAUDE.md), so hook commands render as
``sh "<posix path>"`` there — the same strategy as the justfile's
``set windows-shell := ["sh", ...]``. mac/linux output stays byte-identical to
the historical form. Managed-block detection normalizes ``\\`` to ``/`` so
legacy backslash-rendered blocks are replaced, not duplicated (ADR 0037).
"""

import json
import sys
from pathlib import Path, PureWindowsPath

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (
    AgentTarget,
    _is_managed_hook_block,
    _merge_hook_settings,
    _render_hook_command,
)

FRAGMENT_CMD = 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/block.sh"'


def test_render_hook_command_windows_uses_sh_and_posix_path() -> None:
    """Windows renders sh + forward-slash C:/ path (never bare bash)."""
    agent = AgentTarget(directory=PureWindowsPath(r"C:\Users\x\.claude"), name="Test")

    rendered = _render_hook_command(FRAGMENT_CMD, agent, system="Windows")

    assert rendered == 'sh "C:/Users/x/.claude/hooks/block.sh"'


def test_render_hook_command_posix_unchanged(tmp_path: Path) -> None:
    """mac/linux output is byte-identical to the historical form."""
    agent = AgentTarget(directory=tmp_path, name="Test")

    for system in ("Darwin", "Linux"):
        rendered = _render_hook_command(FRAGMENT_CMD, agent, system=system)
        assert rendered == f'bash "{tmp_path}/hooks/block.sh"'


def test_windows_rendered_command_is_recognized_as_managed() -> None:
    """Idempotency: the freshly rendered Windows command matches the marker."""
    agent = AgentTarget(directory=PureWindowsPath(r"C:\Users\x\.claude"), name="Test")
    rendered = _render_hook_command(FRAGMENT_CMD, agent, system="Windows")
    block = {"matcher": "Bash", "hooks": [{"type": "command", "command": rendered}]}

    assert _is_managed_hook_block(block, agent) is True


def test_legacy_backslash_block_is_recognized_as_managed(tmp_path: Path) -> None:
    """A pre-existing backslash-rendered block is managed, not a user block."""
    agent = AgentTarget(directory=tmp_path, name="Test")
    legacy_cmd = 'bash "' + str(tmp_path).replace("/", "\\") + '\\hooks\\block.sh"'
    block = {"matcher": "Bash", "hooks": [{"type": "command", "command": legacy_cmd}]}

    assert _is_managed_hook_block(block, agent) is True


@pytest.mark.parametrize("system", ["Windows"])
def test_merge_replaces_legacy_backslash_block_without_duplicate(
    tmp_path: Path, system: str
) -> None:
    """Sync after the strategy switch leaves exactly one sh command, zero bash."""
    dotfiles = tmp_path / "dotfiles"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    fragment = dotfiles / ".claude" / "settings.hooks.json"
    fragment.parent.mkdir(parents=True)
    fragment.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": FRAGMENT_CMD}],
                        }
                    ]
                }
            }
        )
    )
    agent = AgentTarget(directory=target_dir, name="Test")
    legacy_cmd = 'bash "' + str(target_dir).replace("/", "\\") + '\\hooks\\block.sh"'
    (target_dir / "settings.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": legacy_cmd}],
                        }
                    ]
                }
            }
        )
    )

    _merge_hook_settings(dotfiles, agent, system=system)

    blocks = json.loads((target_dir / "settings.json").read_text())["hooks"][
        "PreToolUse"
    ]
    commands = [h["command"] for b in blocks for h in b["hooks"]]
    assert commands == [f'sh "{target_dir.as_posix()}/hooks/block.sh"']
