"""Unit tests for scripts/skills_lock.py (declarative skills, store + consumers).

The bunx skills CLI owns the store ~/.agents/skills and records installs in
~/.agents/.skill-lock.json. That lock is NOT usable raw:

- keys mix display names ("Create MCP App") and dir names ("create-mcp-app"),
  with duplicate registrations for the same skill,
- some skills land under their SKILL.md frontmatter name, which differs from
  the repo path ("vercel-composition-patterns" <- skills/composition-patterns/).

skills_lock normalizes it into a committed declaration
(dump/harness/skill-lock.json) used by restore, by the collision check
(hironow/skills wins a name collision), and by `place`, which makes every
consumer home (`~/.claude`, `~/.claude-work-*`, `~/.codex`, `~/.gemini`)
carry each declared skill as a relative symlink into the store (or a copy
where symlinks are unavailable).
"""

import os
import sys
from pathlib import Path

import pytest
from _symlinks import requires_symlinks

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from skills_lock import (
    CONSUMER_HOMES,
    SELF_SOURCE,
    SKILLS_CLI_VERSION,
    SkillRecord,
    build_restore_command,
    check_collisions,
    normalize_lock,
    place,
    restore_order,
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


def _rec(
    installed_dir: str,
    upstream_name: str | None = None,
    source: str = "mattpocock/skills",
) -> SkillRecord:
    upstream_name = upstream_name or installed_dir
    return SkillRecord(
        installed_dir=installed_dir,
        upstream_name=upstream_name,
        lock_key=installed_dir,
        source=source,
        skill_path=f"skills/{upstream_name}/SKILL.md",
        skill_folder_hash="deadbeef",
        resolved_by="installed",
    )


# --- normalize_lock: two-stage resolution ---


def test_lock_key_matching_installed_dir_wins() -> None:
    raw = {"tdd": _entry("mattpocock/skills", "skills/tdd/SKILL.md")}
    records = normalize_lock(raw, installed_dirs={"tdd"})
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
    records = normalize_lock(raw, installed_dirs={"create-mcp-app"})
    assert records[0].installed_dir == "create-mcp-app"
    assert records[0].resolved_by == "skillPath"


def test_renamed_install_resolves_via_lock_key() -> None:
    """Frontmatter-name installs: key is the installed dir, path parent differs."""
    raw = {
        "vercel-composition-patterns": _entry(
            "vercel-labs/agent-skills", "skills/composition-patterns/SKILL.md"
        )
    }
    records = normalize_lock(raw, installed_dirs={"vercel-composition-patterns"})
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
    records = normalize_lock(raw, installed_dirs={"create-mcp-app"})
    assert len(records) == 1
    assert records[0].installed_dir == "create-mcp-app"


def test_unresolved_entry_is_dropped_with_warning() -> None:
    raw = {"ghost-skill": _entry("someone/skills", "skills/ghost-skill/SKILL.md")}
    assert normalize_lock(raw, installed_dirs=set()) == []


def test_self_source_wins_a_name_collision_on_dump() -> None:
    """Requester's rule: when two sources resolve to the same installed dir,
    the hironow/skills record is kept, whatever the registration order."""
    raw = {
        "review": _entry("mattpocock/skills", "skills/engineering/review/SKILL.md"),
        "review (self)": _entry(SELF_SOURCE, "review/SKILL.md"),
    }
    records = normalize_lock(raw, installed_dirs={"review"})
    assert [r.source for r in records] == [SELF_SOURCE]
    raw_reversed = dict(reversed(list(raw.items())))
    assert [r.source for r in normalize_lock(raw_reversed, {"review"})] == [SELF_SOURCE]


# --- check_collisions: the committed lock never shadows a hironow/skills name ---


def test_collision_on_installed_dir_is_reported() -> None:
    records = [_rec("review", source=SELF_SOURCE), _rec("review")]
    assert check_collisions(records) == ["review"]


def test_collision_on_upstream_name_is_reported() -> None:
    records = [
        _rec("zoom-out", source=SELF_SOURCE),
        _rec("mp-zoom-out", upstream_name="zoom-out"),
    ]
    assert check_collisions(records) == ["zoom-out"]


def test_no_collision_returns_empty() -> None:
    records = [_rec("review", source=SELF_SOURCE), _rec("tdd")]
    assert check_collisions(records) == []


# --- restore: self-source records go last so they win in the store ---


def test_restore_order_puts_self_source_last() -> None:
    records = [_rec("review", source=SELF_SOURCE), _rec("tdd"), _rec("qa")]
    ordered = [r.installed_dir for r in restore_order(records)]
    assert ordered[-1] == "review"
    assert set(ordered[:-1]) == {"tdd", "qa"}


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


# --- place: consumer homes mirror the store ---


def _store_skill(home: Path, name: str, body: str = "# skill\n") -> Path:
    d = home / ".agents" / "skills" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(body, encoding="utf-8")
    return d


def _homes(home: Path) -> list[Path]:
    out = []
    for rel in CONSUMER_HOMES:
        (home / rel / "skills").mkdir(parents=True, exist_ok=True)
        out.append(home / rel / "skills")
    return out


@requires_symlinks
def test_place_links_every_consumer_home_relatively(tmp_path: Path) -> None:
    _store_skill(tmp_path, "review")
    homes = _homes(tmp_path)
    result = place([_rec("review", source=SELF_SOURCE)], tmp_path)
    for skills_dir in homes:
        link = skills_dir / "review"
        assert link.is_symlink()
        assert os.readlink(link) == os.path.join(
            "..", "..", ".agents", "skills", "review"
        )
        assert (link / "SKILL.md").read_text(encoding="utf-8") == "# skill\n"
    assert sorted(result.linked) == sorted(f"{h.parent.name}/review" for h in homes)
    # idempotent
    again = place([_rec("review", source=SELF_SOURCE)], tmp_path)
    assert again.linked == [] and again.replaced == [] and again.kept == []


@requires_symlinks
def test_place_replaces_an_identical_real_dir_and_keeps_a_different_one(
    tmp_path: Path,
) -> None:
    _store_skill(tmp_path, "review", "# v2\n")
    homes = _homes(tmp_path)
    same = homes[0] / "review"
    same.mkdir()
    (same / "SKILL.md").write_text("# v2\n", encoding="utf-8")
    edited = homes[1] / "review"
    edited.mkdir()
    (edited / "SKILL.md").write_text("# local edit\n", encoding="utf-8")
    result = place([_rec("review", source=SELF_SOURCE)], tmp_path)
    assert same.is_symlink()
    assert not edited.is_symlink()
    assert (edited / "SKILL.md").read_text(encoding="utf-8") == "# local edit\n"
    assert result.kept == [f"{homes[1].parent.name}/review"]
    forced = place([_rec("review", source=SELF_SOURCE)], tmp_path, force=True)
    assert edited.is_symlink()
    assert forced.replaced == [f"{homes[1].parent.name}/review"]


def test_place_copy_mode_refreshes_stale_copies(tmp_path: Path) -> None:
    """Where symlinks are unavailable (Windows without Developer Mode) the
    consumer holds a copy; `place` refreshes it whenever the store differs."""
    _store_skill(tmp_path, "review", "# v1\n")
    homes = _homes(tmp_path)
    first = place([_rec("review", source=SELF_SOURCE)], tmp_path, link=False)
    assert len(first.copied) == len(homes)
    assert not (homes[0] / "review").is_symlink()
    _store_skill(tmp_path, "review", "# v2\n")
    second = place([_rec("review", source=SELF_SOURCE)], tmp_path, link=False)
    assert len(second.refreshed) == len(homes)
    assert (homes[-1] / "review" / "SKILL.md").read_text(encoding="utf-8") == "# v2\n"
    third = place([_rec("review", source=SELF_SOURCE)], tmp_path, link=False)
    assert third.copied == [] and third.refreshed == []


def test_place_skips_a_record_missing_from_the_store(tmp_path: Path) -> None:
    _homes(tmp_path)
    result = place([_rec("ghost")], tmp_path)
    assert result.missing == ["ghost"]
    assert result.linked == [] and result.copied == []


def test_place_only_touches_homes_that_exist(tmp_path: Path) -> None:
    """A machine without ~/.claude-work-c must not get one created."""
    _store_skill(tmp_path, "review")
    (tmp_path / ".claude" / "skills").mkdir(parents=True)
    place([_rec("review", source=SELF_SOURCE)], tmp_path, link=False)
    assert (tmp_path / ".claude" / "skills" / "review" / "SKILL.md").exists()
    assert not (tmp_path / ".claude-work-c").exists()


def test_restore_command_writes_the_store_only() -> None:
    """`-a universal`: the CLI must never touch a consumer home itself (it
    would delete a same-named directory without comparing it)."""
    cmd = build_restore_command(_rec("review", source=SELF_SOURCE))
    assert cmd[cmd.index("-a") + 1] == "universal"


def test_place_symlink_fallback_keeps_refreshing_its_own_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows without Developer Mode: symlink creation fails, the consumer gets
    a copy, and later runs (still in the default link mode) refresh that copy
    as long as it is unedited; an edited copy is kept and reported."""
    import skills_lock

    monkeypatch.setattr(skills_lock, "_try_symlink", lambda *_: False)
    _store_skill(tmp_path, "review", "# v1\n")
    homes = _homes(tmp_path)
    first = place([_rec("review", source=SELF_SOURCE)], tmp_path)
    assert first.symlinks_unavailable and len(first.copied) == len(homes)
    _store_skill(tmp_path, "review", "# v2\n")
    second = place([_rec("review", source=SELF_SOURCE)], tmp_path)
    assert len(second.refreshed) == len(homes) and second.kept == []
    assert (homes[0] / "review" / "SKILL.md").read_text(encoding="utf-8") == "# v2\n"
    (homes[0] / "review" / "SKILL.md").write_text("# local edit\n", encoding="utf-8")
    _store_skill(tmp_path, "review", "# v3\n")
    third = place([_rec("review", source=SELF_SOURCE)], tmp_path)
    assert third.kept == [f"{homes[0].parent.name}/review"]
    assert len(third.refreshed) == len(homes) - 1


@requires_symlinks
def test_place_never_removes_the_store_through_a_linked_skills_dir(
    tmp_path: Path,
) -> None:
    """If a consumer's whole skills/ dir is a symlink to the store, source and
    target are the same entity: never delete, never replace."""
    store = _store_skill(tmp_path, "review")
    (tmp_path / ".codex").mkdir()
    os.symlink(os.path.join("..", ".agents", "skills"), tmp_path / ".codex" / "skills")
    result = place([_rec("review", source=SELF_SOURCE)], tmp_path)
    assert store.is_dir() and (store / "SKILL.md").exists()
    assert result.linked == [] and result.replaced == [] and result.kept == []


def test_place_keeps_a_real_dir_whose_entry_types_differ(tmp_path: Path) -> None:
    """A type mismatch (file vs directory) is a difference, not a match."""
    store = _store_skill(tmp_path, "review")
    (store / "notes").write_text("file in the store\n", encoding="utf-8")
    homes = _homes(tmp_path)
    consumer = homes[0] / "review"
    consumer.mkdir()
    (consumer / "SKILL.md").write_text("# skill\n", encoding="utf-8")
    (consumer / "notes").mkdir()
    (consumer / "notes" / "local.md").write_text("local\n", encoding="utf-8")
    result = place([_rec("review", source=SELF_SOURCE)], tmp_path, link=False)
    assert result.kept == [f"{homes[0].parent.name}/review"]
    assert (consumer / "notes" / "local.md").exists()


def test_place_creates_skills_dir_for_an_existing_profile_home(tmp_path: Path) -> None:
    _store_skill(tmp_path, "review")
    (tmp_path / ".claude-work-c").mkdir()  # profile exists, no skills/ yet
    place([_rec("review", source=SELF_SOURCE)], tmp_path, link=False)
    assert (tmp_path / ".claude-work-c" / "skills" / "review" / "SKILL.md").exists()
    assert not (tmp_path / ".claude-work-d").exists()


def test_dropped_self_records_are_detected_on_dump() -> None:
    """The CLI's machine lock replaces a same-named key: installing a
    third-party `review` after ours silently drops our record. dump must
    notice that a previously declared hironow/skills record is gone or
    re-sourced instead of committing the loss."""
    from skills_lock import find_dropped_self_records

    previous = [
        _rec("review", source=SELF_SOURCE),
        _rec("zoom-out", source=SELF_SOURCE),
        _rec("tdd"),
    ]
    current = [_rec("review"), _rec("tdd")]
    assert find_dropped_self_records(previous, current) == ["review", "zoom-out"]
    assert find_dropped_self_records(previous, previous) == []


def test_restore_reinstalls_a_self_record_the_machine_lock_lost() -> None:
    from skills_lock import needs_reinstall

    ours = _rec("review", source=SELF_SOURCE)
    assert needs_reinstall(ours, installed=True, machine_source="mattpocock/skills")
    assert needs_reinstall(ours, installed=False, machine_source=None)
    assert not needs_reinstall(ours, installed=True, machine_source=SELF_SOURCE)
    theirs = _rec("tdd")
    assert not needs_reinstall(theirs, installed=True, machine_source="other/skills")


def test_cli_env_is_isolated_under_skills_lock_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skills_lock import cli_env

    monkeypatch.setenv("SKILLS_LOCK_HOME", "/tmp/rehearsal-home")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", "/Users/x/.claude-work-b")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/Users/x/.config")
    env = cli_env()
    assert env["HOME"] == "/tmp/rehearsal-home"
    assert "CLAUDE_CONFIG_DIR" not in env and "XDG_CONFIG_HOME" not in env
    monkeypatch.delenv("SKILLS_LOCK_HOME")
    assert "CLAUDE_CONFIG_DIR" in cli_env()


def test_update_command_uses_the_pinned_cli_globally() -> None:
    from skills_lock import build_update_command

    cmd = build_update_command()
    assert cmd[:2] == ["bunx", f"skills@{SKILLS_CLI_VERSION}"]
    assert cmd[2:] == ["update", "-g", "-y"]


def test_update_still_places_when_the_cli_update_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One third-party skill failing to update must not leave the homes
    unplaced: the store refresh failure is reported and the exit code is 1,
    but `place` still runs on whatever the store holds."""
    import subprocess

    import skills_lock

    (tmp_path / "dump" / "harness").mkdir(parents=True)
    (tmp_path / "dump" / "harness" / "skill-lock.json").write_text(
        json_dumps_records([_rec("review", source=SELF_SOURCE)]), encoding="utf-8"
    )
    home = tmp_path / "home"
    _store_skill(home, "review")
    (home / ".claude").mkdir()
    monkeypatch.setenv("SKILLS_LOCK_HOME", str(home))
    monkeypatch.setattr(
        skills_lock.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1),
    )
    rc = skills_lock._cmd_update(tmp_path, force=False, copy=True)
    assert rc == 1
    assert (home / ".claude" / "skills" / "review" / "SKILL.md").exists()


def json_dumps_records(records: list[SkillRecord]) -> str:
    import json
    from dataclasses import asdict

    return json.dumps({"version": 1, "skills": [asdict(r) for r in records]})


def test_output_survives_cp932_stdout() -> None:
    # Windows Git Bash gives Python a cp932 stdout; restore's progress lines
    # use emoji (下矢印 U+2B07) and crashed with UnicodeEncodeError, killing
    # the whole restore. _configure_output() must make printing safe.
    import subprocess

    script = (
        "import sys; sys.path.insert(0, r'{scripts}');"
        "import skills_lock; skills_lock._configure_output();"
        "print('⬇️  ok')"
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
