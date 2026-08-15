"""Unit tests for scripts/skills_lock.py (declarative third-party skills).

The bunx skills CLI owns ~/.agents/skills and records installs in
~/.agents/.skill-lock.json. That lock is NOT usable raw:

- keys mix display names ("Create MCP App") and dir names ("create-mcp-app"),
  with duplicate registrations for the same skill,
- some skills land under their SKILL.md frontmatter name, which differs from
  the repo path ("vercel-composition-patterns" <- skills/composition-patterns/).

skills_lock normalizes it into a committed declaration
(dump/harness/skill-lock.json) used by restore and by the CI overlap check.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from skills_lock import (
    SkillRecord,
    UnresolvedSkillError,
    build_restore_command,
    check_overlap,
    normalize_lock,
)


def _entry(source: str, skill_path: str) -> dict[str, str]:
    return {
        "source": source,
        "sourceType": "github",
        "sourceUrl": f"https://github.com/{source}.git",
        "skillPath": skill_path,
        "skillFolderHash": "deadbeef",
        "installedAt": "2026-08-01T00:00:00Z",
        "updatedAt": "2026-08-01T00:00:00Z",
    }


# --- normalize_lock: two-stage resolution ---


def test_lock_key_matching_installed_dir_wins() -> None:
    raw = {"tdd": _entry("mattpocock/skills", "skills/tdd/SKILL.md")}
    records = normalize_lock(raw, installed_dirs={"tdd"}, submodule_dirs=set())
    assert len(records) == 1
    rec = records[0]
    assert rec.installed_dir == "tdd"
    assert rec.upstream_name == "tdd"
    assert rec.resolved_by == "installed"


def test_display_name_key_falls_back_to_skill_path_parent() -> None:
    raw = {
        "Create MCP App": _entry(
            "modelcontextprotocol/ext-apps",
            "plugins/mcp-apps/skills/create-mcp-app/SKILL.md",
        )
    }
    records = normalize_lock(
        raw, installed_dirs={"create-mcp-app"}, submodule_dirs=set()
    )
    assert records[0].installed_dir == "create-mcp-app"
    assert records[0].resolved_by == "skillPath"


def test_renamed_install_resolves_via_lock_key() -> None:
    """Frontmatter-name installs: key is the installed dir, path parent differs."""
    raw = {
        "vercel-composition-patterns": _entry(
            "vercel-labs/agent-skills", "skills/composition-patterns/SKILL.md"
        )
    }
    records = normalize_lock(
        raw, installed_dirs={"vercel-composition-patterns"}, submodule_dirs=set()
    )
    rec = records[0]
    assert rec.installed_dir == "vercel-composition-patterns"
    assert rec.upstream_name == "composition-patterns"


def test_duplicate_registrations_dedupe_to_one_record() -> None:
    raw = {
        "Create MCP App": _entry(
            "modelcontextprotocol/ext-apps",
            "plugins/mcp-apps/skills/create-mcp-app/SKILL.md",
        ),
        "create-mcp-app": _entry(
            "modelcontextprotocol/ext-apps",
            "plugins/mcp-apps/skills/create-mcp-app/SKILL.md",
        ),
    }
    records = normalize_lock(
        raw, installed_dirs={"create-mcp-app"}, submodule_dirs=set()
    )
    assert len(records) == 1
    assert records[0].installed_dir == "create-mcp-app"


def test_unresolved_entry_outside_submodule_is_dropped_with_warning() -> None:
    raw = {"ghost-skill": _entry("someone/skills", "skills/ghost-skill/SKILL.md")}
    records = normalize_lock(raw, installed_dirs=set(), submodule_dirs=set())
    assert records == []


def test_unresolved_entry_overlapping_submodule_fails_loud() -> None:
    """A silently mis-resolved entry would corrupt the delete set: fail."""
    raw = {"tdd": _entry("mattpocock/skills", "skills/tdd/SKILL.md")}
    with pytest.raises(UnresolvedSkillError):
        normalize_lock(raw, installed_dirs=set(), submodule_dirs={"tdd"})


# --- check_overlap: CI barrier against re-vendoring ---


def _rec(
    installed_dir: str,
    upstream_name: str,
    source: str = "mattpocock/skills",
) -> SkillRecord:
    return SkillRecord(
        installed_dir=installed_dir,
        upstream_name=upstream_name,
        lock_key=installed_dir,
        source=source,
        skill_path=f"skills/{upstream_name}/SKILL.md",
        skill_folder_hash="deadbeef",
        resolved_by="installed",
    )


def test_overlap_matches_installed_dir() -> None:
    records = [_rec("tdd", "tdd")]
    assert check_overlap(records, submodule_dirs={"tdd", "my-own"}) == ["tdd"]


def test_overlap_matches_upstream_name_union() -> None:
    """Either name reappearing in the submodule must trip the barrier."""
    records = [_rec("vercel-composition-patterns", "composition-patterns")]
    assert check_overlap(records, submodule_dirs={"composition-patterns"}) == [
        "composition-patterns"
    ]


def test_overlap_ignores_hironow_sourced_records() -> None:
    """Self-authored skills live in the submodule by design."""
    records = [_rec("sibyl", "sibyl", source="hironow/skills")]
    assert check_overlap(records, submodule_dirs={"sibyl"}) == []


def test_no_overlap_returns_empty() -> None:
    records = [_rec("tdd", "tdd")]
    assert check_overlap(records, submodule_dirs={"my-own"}) == []


# --- build_restore_command ---


def test_restore_command_uses_lock_key_and_pinned_cli() -> None:
    rec = SkillRecord(
        installed_dir="vercel-composition-patterns",
        upstream_name="composition-patterns",
        lock_key="vercel-composition-patterns",
        source="vercel-labs/agent-skills",
        skill_path="skills/composition-patterns/SKILL.md",
        skill_folder_hash="deadbeef",
        resolved_by="installed",
    )
    cmd = build_restore_command(rec)
    assert cmd[0] == "bunx"
    assert cmd[1].startswith("skills@")  # pinned CLI version
    assert "add" in cmd
    assert "vercel-labs/agent-skills" in cmd
    assert "-s" in cmd
    # -s takes the frontmatter name the CLI recorded (spike-verified), which
    # is the lock key — NOT the repo path name.
    assert cmd[cmd.index("-s") + 1] == "vercel-composition-patterns"
    assert "-g" in cmd
    assert "-y" in cmd


def test_output_survives_cp932_stdout() -> None:
    # Windows Git Bash gives Python a cp932 stdout; restore's progress lines
    # use emoji (下矢印 U+2B07) and crashed with UnicodeEncodeError, killing
    # the whole restore. _configure_output() must make printing safe.
    import os
    import subprocess

    script = (
        "import sys; sys.path.insert(0, r'{scripts}');"
        "import skills_lock; skills_lock._configure_output();"
        "print('\u2b07\ufe0f  ok')"
    ).format(scripts=Path(__file__).resolve().parents[2] / "scripts")
    env = dict(os.environ, PYTHONIOENCODING="cp932")
    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, (
        "skills_lock output must not crash on a cp932 stdout:\n" + proc.stderr
    )
