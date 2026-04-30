"""Unit tests for import-only mode.

Tests that:
1. import_only_mode runs Phase 1 (target -> dotfiles) and skips Phase 2-3.
2. The is_import_source filter is dropped when running import-only:
   ALL selected agents become import candidates.
"""

from pathlib import Path

import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (  # noqa: E402
    AgentTarget,
    _build_import_plan,
    _SyncManifest,
    import_only_mode,
)


def _make_skill(parent: Path, name: str, content: str = "skill") -> Path:
    """Create a minimal skill directory with SKILL.md."""
    skill_dir = parent / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"# {name}\n{content}\n")
    return skill_dir


@pytest.fixture()
def workspace(tmp_path: Path) -> dict[str, Path]:
    """Create dotfiles + two target dirs."""
    dotfiles = tmp_path / "dotfiles"
    target_a = tmp_path / "target-a"
    target_b = tmp_path / "target-b"
    dotfiles.mkdir()
    target_a.mkdir()
    target_b.mkdir()
    (dotfiles / "ROOT_AGENTS.md").write_text("# base\n")
    return {"dotfiles": dotfiles, "target_a": target_a, "target_b": target_b}


def test_import_only_imports_from_non_import_source_agent(
    workspace: dict[str, Path],
) -> None:
    """Selected agent without is_import_source should still be imported from
    in import-only mode (the flag is dropped)."""
    # given: target-a has a unique skill, but its agent has is_import_source=False
    _make_skill(workspace["target_a"], "from-a")
    agent = AgentTarget(
        directory=workspace["target_a"],
        name="A",
        key="a",
        is_import_source=False,
    )
    manifest = _SyncManifest()

    # when: build import plan ignoring is_import_source flag
    plan = _build_import_plan(workspace["dotfiles"], agent, manifest)

    # then: the new skill is detected as importable regardless of the flag
    importable = [a for a in plan.items if a.status == "import"]
    assert any(a.relative_path == "skills/from-a" for a in importable)


def test_import_only_mode_does_not_create_target_files(
    workspace: dict[str, Path],
) -> None:
    """import_only_mode runs Phase 1 only — no forward sync, no orphan removal."""
    # given: dotfiles has a skill that is NOT in target-a
    _make_skill(workspace["dotfiles"], "only-in-dotfiles")
    # given: target-a has its own unique skill to import
    _make_skill(workspace["target_a"], "only-in-target")

    agent = AgentTarget(
        directory=workspace["target_a"],
        name="A",
        key="a",
    )

    # when: run import-only mode
    import_only_mode(workspace["dotfiles"], agents=[agent])

    # then: target-a's unique skill landed in dotfiles
    assert (workspace["dotfiles"] / "skills" / "only-in-target" / "SKILL.md").exists()

    # then: dotfiles' unique skill was NOT pushed into target-a
    assert not (workspace["target_a"] / "skills" / "only-in-dotfiles").exists()
