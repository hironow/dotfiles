"""The dotfiles sync is out of the skills business (ADR 0043).

Skills — self-authored ones included — reach the agent homes through the
bunx skills CLI and `scripts/skills_lock.py`; `just sync-agents` distributes
instructions, hooks, settings, commands and agents only. These tests pin the
contract: no target syncs a `skills` directory, and a stale manifest that
still lists `skills` items (every machine that synced before the retirement
has one) produces neither deletions nor imports under any mode.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (
    AGENTS,
    SYNC_DIRECTORIES,
    AgentTarget,
    _build_deletion_plan,
    _build_import_plan,
    _detect_target_only_items,
    _SyncManifest,
)


def test_skills_is_not_a_sync_directory_anywhere() -> None:
    assert "skills" not in SYNC_DIRECTORIES
    for agent in AGENTS:
        assert "skills" not in agent.get_sync_directories(), agent.name


def test_no_target_exists_only_for_skills() -> None:
    """The ~/.agents target (skills-only) is gone with the submodule."""
    assert all(agent.directory.name != ".agents" for agent in AGENTS)


@pytest.fixture()
def workspace(tmp_path: Path) -> dict[str, Path]:
    dotfiles = tmp_path / "dotfiles"
    target = tmp_path / "target"
    (dotfiles / "commands").mkdir(parents=True)
    (target / "commands").mkdir(parents=True)
    skills = target / "skills"
    (skills / "cli-managed").mkdir(parents=True)
    (skills / "cli-managed" / "SKILL.md").write_text("# cli\n")
    (skills / "stale-copy").mkdir()
    (skills / "stale-copy" / "SKILL.md").write_text("# stale\n")
    return {"dotfiles": dotfiles, "target": target, "skills": skills}


def _agent(target: Path) -> AgentTarget:
    return AgentTarget(directory=target, name="Test")


def _stale_manifest() -> _SyncManifest:
    # What every pre-retirement machine still carries: skills items that the
    # submodule used to distribute.
    return _SyncManifest(items={"skills": ["stale-copy", "gone-skill"], "commands": []})


def test_stale_manifest_skills_items_yield_no_deletions(
    workspace: dict[str, Path],
) -> None:
    plan = _build_deletion_plan(
        workspace["dotfiles"], _agent(workspace["target"]), _stale_manifest()
    )
    assert [d.relative_path for d in plan] == []


def test_target_only_skills_are_never_orphans(workspace: dict[str, Path]) -> None:
    orphans = _detect_target_only_items(
        workspace["dotfiles"], _agent(workspace["target"]), _stale_manifest()
    )
    assert [o.relative_path for o in orphans] == []


def test_skills_never_import_back(workspace: dict[str, Path]) -> None:
    plan = _build_import_plan(
        workspace["dotfiles"], _agent(workspace["target"]), _stale_manifest()
    )
    assert [
        a.relative_path for a in plan.items if a.relative_path.startswith("skills/")
    ] == []
