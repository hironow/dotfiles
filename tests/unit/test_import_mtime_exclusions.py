"""Import conflict resolution must ignore excluded (workspace) children.

Found live (2026-08-31, via an instrumented e2e flake on podman): the
skills/learned import round-trip resolves "which side is newer" with
`_get_newest_mtime`, which walked EVERY file — including `-workspace`
directories that are excluded from content comparison and never synced.
Any workspace activity after editing the dotfiles-side skill made the
target look newer, so the import phase silently overwrote the fresher
dotfiles content with the target's stale copy (observed: v2 reverted to
v1, then the forward sync reported "already in sync").
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (
    AgentTarget,
    _build_import_plan,
    _get_newest_mtime,
    _SyncManifest,
)

_T0 = time.time() - 3600


def _stamp(path: Path, offset: int) -> None:
    os.utime(path, (_T0 + offset, _T0 + offset))


def test_newest_mtime_ignores_workspace_children_in_learned(
    tmp_path: Path,
) -> None:
    learned = tmp_path / "learned"
    skill = learned / "my-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# v1\n")
    _stamp(skill / "SKILL.md", 0)
    workspace = learned / "my-skill-workspace" / "iteration-1"
    workspace.mkdir(parents=True)
    (workspace / "results.md").write_text("data\n")
    _stamp(workspace / "results.md", 500)

    assert _get_newest_mtime(learned) == _T0


def test_target_workspace_activity_does_not_win_import_conflict(
    tmp_path: Path,
) -> None:
    """A fresher dotfiles-side skill must never lose to target workspace noise."""
    dotfiles = tmp_path / "dotfiles"
    target = tmp_path / "home"
    src_skill = dotfiles / "skills" / "learned" / "my-skill"
    src_skill.mkdir(parents=True)
    (src_skill / "SKILL.md").write_text("# v2\n")
    _stamp(src_skill / "SKILL.md", 100)

    tgt_skill = target / "skills" / "learned" / "my-skill"
    tgt_skill.mkdir(parents=True)
    (tgt_skill / "SKILL.md").write_text("# v1\n")
    _stamp(tgt_skill / "SKILL.md", 0)
    workspace = target / "skills" / "learned" / "my-skill-workspace"
    workspace.mkdir(parents=True)
    (workspace / "results.md").write_text("busy\n")
    _stamp(workspace / "results.md", 900)  # newer than everything

    agent = AgentTarget(directory=target, name="Test")
    plan = _build_import_plan(dotfiles, agent, _SyncManifest(items={}))

    learned_actions = [a for a in plan.items if a.relative_path == "skills/learned"]
    assert learned_actions, "skills/learned should be considered"
    # dotfiles is newer where it matters (the skill itself): the target copy
    # must NOT be imported over it.
    assert learned_actions[0].status != "import"
