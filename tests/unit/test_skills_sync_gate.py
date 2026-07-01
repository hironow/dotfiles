"""Unit tests for the skills sync quality gate in sync_agents.

Two mechanisms keep junk out of agent homes (both directions):

- Structural gate: a `skills/` child that contains no SKILL.md anywhere
  (recursively) is not a skill (e.g. the skills repo's own docs/ dir, an
  empty leftover dir) and is skipped in both distribute and import.
- Denylist: skill names listed in `dump/harness/skills-sync-exclude.toml`
  (`exclude = [...]`) are skipped in both directions even if they contain
  a valid SKILL.md.

The gate applies only to `skills/`; commands/ and agents/ are untouched.
"""

from pathlib import Path

import pytest

# Import from scripts (add parent to path)
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (
    AgentTarget,
    _SyncManifest,
    _build_import_plan,
    _get_directory_items,
    _load_skills_sync_exclude,
    import_only_mode,
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


def _make_junk_dir(parent: Path, name: str, files: list[str]) -> Path:
    """Create a skills/ child directory WITHOUT any SKILL.md."""
    junk_dir = parent / "skills" / name
    junk_dir.mkdir(parents=True, exist_ok=True)
    for filename in files:
        (junk_dir / filename).write_text(f"# {filename}\n")
    return junk_dir


def _write_exclude_toml(dotfiles_dir: Path, body: str) -> Path:
    """Write dump/harness/skills-sync-exclude.toml with the given body."""
    exclude_file = dotfiles_dir / "dump" / "harness" / "skills-sync-exclude.toml"
    exclude_file.parent.mkdir(parents=True, exist_ok=True)
    exclude_file.write_text(body)
    return exclude_file


def _item_paths(dotfiles_dir: Path) -> list[str]:
    """Relative paths of all sync items discovered in dotfiles."""
    return [i.relative_path for i in _get_directory_items(dotfiles_dir)]


# --- Forward direction (dotfiles -> target) ---


def test_skills_dir_without_skill_md_not_synced(workspace: dict[str, Path]) -> None:
    """A skills/ child with no SKILL.md (e.g. repo docs/) is not distributed."""
    # given
    _make_junk_dir(workspace["dotfiles"], "docs", ["intent.md", "handover.md"])
    _make_skill(workspace["dotfiles"], "real-skill")

    # when
    paths = _item_paths(workspace["dotfiles"])

    # then
    assert "skills/docs" not in paths
    assert "skills/real-skill" in paths


def test_skills_dir_with_skill_md_synced(workspace: dict[str, Path]) -> None:
    """A normal skill directory keeps syncing as before."""
    # given
    _make_skill(workspace["dotfiles"], "my-skill")

    # when
    paths = _item_paths(workspace["dotfiles"])

    # then
    assert "skills/my-skill" in paths


def test_container_dir_with_nested_skill_md_synced(workspace: dict[str, Path]) -> None:
    """A container dir (learned/) whose descendants hold SKILL.md still syncs."""
    # given
    nested = workspace["dotfiles"] / "skills" / "learned" / "some-skill"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "SKILL.md").write_text("# nested\n")

    # when
    paths = _item_paths(workspace["dotfiles"])

    # then
    assert "skills/learned" in paths


def test_excluded_skill_not_synced(workspace: dict[str, Path]) -> None:
    """A skill named in the exclude TOML is not distributed even with SKILL.md."""
    # given
    _make_skill(workspace["dotfiles"], "banned-skill")
    _make_skill(workspace["dotfiles"], "kept-skill")
    _write_exclude_toml(workspace["dotfiles"], 'exclude = ["banned-skill"]\n')

    # when
    paths = _item_paths(workspace["dotfiles"])

    # then
    assert "skills/banned-skill" not in paths
    assert "skills/kept-skill" in paths


def test_stray_file_in_skills_not_synced(workspace: dict[str, Path]) -> None:
    """A plain file directly under skills/ is skipped without crashing."""
    # given
    skills_dir = workspace["dotfiles"] / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "README.md").write_text("# stray\n")
    _make_skill(workspace["dotfiles"], "real-skill")

    # when
    paths = _item_paths(workspace["dotfiles"])

    # then
    assert "skills/README.md" not in paths
    assert "skills/real-skill" in paths


def test_gate_does_not_apply_to_other_directories(
    workspace: dict[str, Path],
) -> None:
    """commands/ children have no SKILL.md and must keep syncing untouched."""
    # given
    cmd_dir = workspace["dotfiles"] / "commands"
    cmd_dir.mkdir(parents=True, exist_ok=True)
    (cmd_dir / "my-cmd.md").write_text("# cmd\n")

    # when
    paths = _item_paths(workspace["dotfiles"])

    # then
    assert "commands/my-cmd.md" in paths


# --- Exclude list loading ---


def test_missing_exclude_file_defaults_to_empty(workspace: dict[str, Path]) -> None:
    """No exclude TOML means an empty exclude set (fail-safe)."""
    assert _load_skills_sync_exclude(workspace["dotfiles"]) == frozenset()


def test_exclude_file_loads_names(workspace: dict[str, Path]) -> None:
    """The exclude TOML's `exclude` list is loaded as a frozenset."""
    # given
    _write_exclude_toml(workspace["dotfiles"], 'exclude = ["a-skill", "b-skill"]\n')

    # when / then
    assert _load_skills_sync_exclude(workspace["dotfiles"]) == frozenset(
        {"a-skill", "b-skill"}
    )


def test_malformed_exclude_file_fails_loud(workspace: dict[str, Path]) -> None:
    """Broken TOML syntax and a non-list `exclude` both raise."""
    # given: invalid syntax
    _write_exclude_toml(workspace["dotfiles"], "exclude = [unterminated\n")

    # when / then
    with pytest.raises(Exception):
        _load_skills_sync_exclude(workspace["dotfiles"])

    # given: wrong type
    _write_exclude_toml(workspace["dotfiles"], 'exclude = "not-a-list"\n')

    # when / then
    with pytest.raises(ValueError):
        _load_skills_sync_exclude(workspace["dotfiles"])


# --- Import direction (target -> dotfiles) ---


def test_junk_in_target_not_reimported(workspace: dict[str, Path]) -> None:
    """A target-only skills/ dir without SKILL.md never becomes an import."""
    # given
    _make_junk_dir(workspace["target"], "docs", ["intent.md", "handover.md"])
    _make_skill(workspace["target"], "genuine-skill")
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    plan = _build_import_plan(workspace["dotfiles"], agent, manifest)

    # then
    paths = [a.relative_path for a in plan.items]
    assert "skills/docs" not in paths
    assert "skills/genuine-skill" in paths


def test_excluded_skill_in_target_not_reimported(workspace: dict[str, Path]) -> None:
    """A denylisted skill with a valid SKILL.md in target is not reimported."""
    # given
    _make_skill(workspace["target"], "banned-skill")
    _write_exclude_toml(workspace["dotfiles"], 'exclude = ["banned-skill"]\n')
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    plan = _build_import_plan(workspace["dotfiles"], agent, manifest)

    # then
    assert [a.relative_path for a in plan.items] == []


def test_symlinked_skill_in_target_still_importable(
    workspace: dict[str, Path], tmp_path: Path
) -> None:
    """An external symlink to a real skill passes the gate via its resolved dir."""
    # given: real skill lives outside the target (like ~/.agents/skills/foo)
    real = tmp_path / "elsewhere" / "linked-skill"
    real.mkdir(parents=True, exist_ok=True)
    (real / "SKILL.md").write_text("# linked\n")
    skills_dir = workspace["target"] / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    (skills_dir / "linked-skill").symlink_to(real)
    manifest = _SyncManifest(items={})
    agent = _make_agent(workspace["target"])

    # when
    plan = _build_import_plan(workspace["dotfiles"], agent, manifest)

    # then
    paths = [a.relative_path for a in plan.items]
    assert "skills/linked-skill" in paths


def test_import_only_no_skills_imports_nothing(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    """import_only_mode honors exclude_dirs: skills never reach the plan."""
    # given
    _make_skill(workspace["target"], "target-skill")
    agent = _make_agent(workspace["target"])

    # when
    import_only_mode(
        workspace["dotfiles"],
        agents=[agent],
        preview=True,
        exclude_dirs=frozenset({"skills"}),
    )

    # then
    out = capsys.readouterr().out
    assert "skills/target-skill" not in out
