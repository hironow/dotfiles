"""Unit tests for _detect_target_only_items in sync_agents.

Tests the orphan detection logic that identifies items existing
only in the target directory (not in dotfiles source or manifest).

Orphan detection applies to the synced directories (`commands`, `agents`).
`skills` is not synced at all since ADR 0043 (the bunx skills CLI and
scripts/skills_lock.py own it); see test_sync_ignores_skills.py.
"""

import sys
from pathlib import Path

import pytest
from _symlinks import requires_symlinks

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (
    AgentTarget,
    _detect_target_only_items,
    _SyncManifest,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> dict[str, Path]:
    """Create dotfiles and target directory structure."""
    dotfiles_dir = tmp_path / "dotfiles"
    target_dir = tmp_path / "target"
    dotfiles_dir.mkdir()
    target_dir.mkdir()
    return {"dotfiles": dotfiles_dir, "target": target_dir}


def _make_agent(target_dir: Path) -> AgentTarget:
    """Create an AgentTarget pointing to target_dir."""
    return AgentTarget(directory=target_dir, name="Test")


def _make_subagent(parent: Path, name: str) -> Path:
    """Create a minimal subagent directory under agents/."""
    agent_dir = parent / "agents" / name
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "agent.md").write_text(f"# {name}\n")
    return agent_dir


def _make_command(parent: Path, name: str) -> Path:
    """Create a minimal command file under commands/."""
    cmd_dir = parent / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    cmd_file = cmd_dir / f"{name}.md"
    cmd_file.write_text(f"# {name}\n")
    return cmd_file


def test_detects_orphan_command_in_target(workspace: dict[str, Path]) -> None:
    """Target-only item in commands/ is detected as orphan."""
    # given
    _make_command(workspace["dotfiles"], "my-cmd")
    _make_command(workspace["target"], "my-cmd")
    _make_command(workspace["target"], "orphan-cmd")
    manifest = _SyncManifest(items={"commands": ["my-cmd.md"]})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert len(orphans) == 1
    assert orphans[0].relative_path == "commands/orphan-cmd.md"
    assert orphans[0].reason == "orphan"
    assert orphans[0].is_directory is False


def test_detects_orphan_directory_in_target(workspace: dict[str, Path]) -> None:
    """Target-only directory in agents/ is detected with is_directory."""
    # given
    _make_subagent(workspace["target"], "orphan-agent")
    (workspace["dotfiles"] / "agents").mkdir(parents=True, exist_ok=True)
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert len(orphans) == 1
    assert orphans[0].relative_path == "agents/orphan-agent"
    assert orphans[0].is_directory is True


def test_no_orphans_when_all_in_source(workspace: dict[str, Path]) -> None:
    """No orphans detected when all target items exist in source."""
    # given
    _make_subagent(workspace["dotfiles"], "agent-a")
    _make_subagent(workspace["dotfiles"], "agent-b")
    _make_subagent(workspace["target"], "agent-a")
    _make_subagent(workspace["target"], "agent-b")
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_skips_manifest_tracked_items(workspace: dict[str, Path]) -> None:
    """Items in manifest but not in source are NOT flagged as orphan.

    These are handled by _build_deletion_plan instead.
    """
    # given
    _make_subagent(workspace["dotfiles"], "active-agent")
    _make_subagent(workspace["target"], "active-agent")
    _make_subagent(workspace["target"], "removed-agent")
    manifest = _SyncManifest(items={"agents": ["active-agent", "removed-agent"]})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_skips_hidden_directories(workspace: dict[str, Path]) -> None:
    """Hidden directories (starting with .) are ignored."""
    # given
    _make_subagent(workspace["dotfiles"], "my-agent")
    _make_subagent(workspace["target"], "my-agent")
    hidden = workspace["target"] / "agents" / ".hidden-dir"
    hidden.mkdir(parents=True, exist_ok=True)
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


@requires_symlinks
def test_source_symlinks_count_as_valid_names(workspace: dict[str, Path]) -> None:
    """Symlinks in dotfiles source are included in valid names, so the same
    name in the target is not flagged as orphan."""
    # given
    dotfiles_agents = workspace["dotfiles"] / "agents"
    _make_subagent(workspace["dotfiles"], "real-agent")
    shared = workspace["dotfiles"] / "shared" / "linked-agent"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "agent.md").write_text("# linked\n")
    (dotfiles_agents / "linked-agent").symlink_to(
        Path("..") / "shared" / "linked-agent"
    )
    _make_subagent(workspace["target"], "real-agent")
    _make_subagent(workspace["target"], "linked-agent")
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_multiple_orphans_sorted_by_name(workspace: dict[str, Path]) -> None:
    """Multiple orphans are returned sorted by directory iteration order."""
    # given
    _make_command(workspace["dotfiles"], "keep-me")
    _make_command(workspace["target"], "keep-me")
    _make_command(workspace["target"], "zebra-orphan")
    _make_command(workspace["target"], "alpha-orphan")
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert len(orphans) == 2
    paths = [o.relative_path for o in orphans]
    assert paths == ["commands/alpha-orphan.md", "commands/zebra-orphan.md"]
