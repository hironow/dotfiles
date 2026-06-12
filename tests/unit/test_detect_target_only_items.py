"""Unit tests for _detect_target_only_items in sync_agents.

Tests the orphan detection logic that identifies items existing
only in the target directory (not in dotfiles source or manifest).

`skills` is an ADDITIVE directory (see ADDITIVE_DIRECTORIES in sync_agents):
target-only skills are never flagged as orphans because the `bunx skills`
CLI owns installs there. Orphan detection still applies to the non-additive
sync directories (`commands`, `agents`).
"""

from pathlib import Path

import pytest

# Import from scripts (add parent to path)
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (
    AgentTarget,
    _SyncManifest,
    _detect_target_only_items,
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


def _make_skill(parent: Path, name: str) -> Path:
    """Create a minimal skill directory with SKILL.md."""
    skill_dir = parent / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n")
    return skill_dir


def _make_command(parent: Path, name: str) -> Path:
    """Create a minimal command file under commands/."""
    cmd_dir = parent / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    cmd_file = cmd_dir / f"{name}.md"
    cmd_file.write_text(f"# {name}\n")
    return cmd_file


def test_additive_skills_orphan_not_detected(workspace: dict[str, Path]) -> None:
    """Target-only skill is NOT an orphan — skills/ is additive (CLI-owned)."""
    # given
    _make_skill(workspace["dotfiles"], "my-skill")
    _make_skill(workspace["target"], "my-skill")
    _make_skill(workspace["target"], "cli-installed-skill")
    manifest = _SyncManifest(items={"skills": ["my-skill"]})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_detects_orphan_command_in_target(workspace: dict[str, Path]) -> None:
    """Target-only item in a non-additive dir (commands/) is detected as orphan."""
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
    """Target-only directory in a non-additive dir is detected with is_directory."""
    # given
    orphan_dir = workspace["target"] / "agents" / "orphan-agent"
    orphan_dir.mkdir(parents=True, exist_ok=True)
    (orphan_dir / "agent.md").write_text("# orphan\n")
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
    _make_skill(workspace["dotfiles"], "skill-a")
    _make_skill(workspace["dotfiles"], "skill-b")
    _make_skill(workspace["target"], "skill-a")
    _make_skill(workspace["target"], "skill-b")
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
    _make_skill(workspace["dotfiles"], "active-skill")
    _make_skill(workspace["target"], "active-skill")
    _make_skill(workspace["target"], "removed-skill")
    manifest = _SyncManifest(items={"skills": ["active-skill", "removed-skill"]})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_skips_hidden_directories(workspace: dict[str, Path]) -> None:
    """Hidden directories (starting with .) are ignored."""
    # given
    _make_skill(workspace["dotfiles"], "my-skill")
    _make_skill(workspace["target"], "my-skill")
    hidden = workspace["target"] / "skills" / ".hidden-dir"
    hidden.mkdir(parents=True, exist_ok=True)
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_skips_internal_symlinks(workspace: dict[str, Path]) -> None:
    """Internal symlinks (e.g., learned skill links) are ignored."""
    # given
    _make_skill(workspace["dotfiles"], "real-skill")
    _make_skill(workspace["target"], "real-skill")
    # Create learned/ with a skill and a symlink to it
    learned_skill = workspace["target"] / "skills" / "learned" / "linked-skill"
    learned_skill.mkdir(parents=True, exist_ok=True)
    (learned_skill / "SKILL.md").write_text("# linked\n")
    link = workspace["target"] / "skills" / "linked-skill"
    link.symlink_to(Path("learned") / "linked-skill")
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    orphan_paths = [o.relative_path for o in orphans]
    assert "skills/linked-skill" not in orphan_paths


def test_source_symlinks_count_as_valid_names(workspace: dict[str, Path]) -> None:
    """Symlinks in dotfiles source are included in valid names.

    e.g., skills/gcp-serverless-appdev -> learned/gcp-serverless-appdev
    should prevent that name from being flagged as orphan in target.
    """
    # given
    dotfiles_skills = workspace["dotfiles"] / "skills"
    dotfiles_skills.mkdir(parents=True, exist_ok=True)
    # Real skill
    _make_skill(workspace["dotfiles"], "real-skill")
    # Symlink in source (like learned skill links)
    learned = dotfiles_skills / "learned" / "symlinked-skill"
    learned.mkdir(parents=True, exist_ok=True)
    (learned / "SKILL.md").write_text("# symlinked\n")
    (dotfiles_skills / "symlinked-skill").symlink_to(
        Path("learned") / "symlinked-skill"
    )
    # Target has matching items
    _make_skill(workspace["target"], "real-skill")
    _make_skill(workspace["target"], "symlinked-skill")
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


def test_no_target_skills_dir(workspace: dict[str, Path]) -> None:
    """No crash when target has no skills/ directory."""
    # given
    _make_skill(workspace["dotfiles"], "my-skill")
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_no_source_skills_dir(workspace: dict[str, Path]) -> None:
    """Target-only skills survive even when source has no skills/ — additive."""
    # given
    _make_skill(workspace["target"], "lonely-skill")
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_no_source_commands_dir(workspace: dict[str, Path]) -> None:
    """All target items are orphans when source lacks a non-additive dir."""
    # given
    _make_command(workspace["target"], "lonely-cmd")
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert len(orphans) == 1
    assert orphans[0].relative_path == "commands/lonely-cmd.md"
    assert orphans[0].reason == "orphan"


def test_respects_agent_sync_directories(workspace: dict[str, Path]) -> None:
    """Only checks directories listed in agent's sync_directories."""
    # given
    _make_skill(workspace["dotfiles"], "my-skill")
    _make_skill(workspace["target"], "my-skill")
    # Create orphan in commands/ (not in sync_directories for this agent)
    cmd_dir = workspace["target"] / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    (cmd_dir / "orphan-cmd.md").write_text("# orphan\n")
    manifest = _SyncManifest(items={})
    agent = AgentTarget(
        directory=workspace["target"],
        name="SkillsOnly",
        sync_directories=["skills"],
    )

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert orphans == []


def test_orphan_file_not_directory(workspace: dict[str, Path]) -> None:
    """Non-directory orphan items are detected with is_directory=False."""
    # given
    commands_dir = workspace["target"] / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    (commands_dir / "stray-file.md").write_text("# stray\n")
    (workspace["dotfiles"] / "commands").mkdir(parents=True, exist_ok=True)
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    orphans = _detect_target_only_items(workspace["dotfiles"], agent, manifest)

    # then
    assert len(orphans) == 1
    assert orphans[0].relative_path == "commands/stray-file.md"
    assert orphans[0].is_directory is False
