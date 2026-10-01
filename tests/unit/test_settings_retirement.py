"""Retiring a top-level settings key that the fragments used to write.

Sync upserts the composed top-level settings keys into each claude-family
home's settings.json and never deletes one on its own, so a key dropped from
the fragments would linger in every home already synced. A fragment names
such keys under `retired`: a migration id mapping each key to every value
the fragments ever wrote for it. Each home evaluates a migration once
(recorded in `<home>/settings.sync-state.json`): the key is deleted when it
still holds one of those values, and a value set afterwards is left alone.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import AgentTarget, _merge_settings_fragment  # noqa: E402

DOTFILES = Path(__file__).resolve().parents[2]
MIGRATION = "2026-10-test-migration"


def _write_profile(dotfiles: Path, key: str, data: dict) -> None:
    path = dotfiles / ".claude" / "settings.profiles" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_target(home: Path, data: dict) -> None:
    (home / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def _read_target(home: Path) -> dict:
    return json.loads((home / "settings.json").read_text(encoding="utf-8"))


@pytest.fixture()
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    dotfiles, home = tmp_path / "dotfiles", tmp_path / "home"
    dotfiles.mkdir()
    home.mkdir()
    return dotfiles, home


def _agent(home: Path, key: str = "work-c") -> AgentTarget:
    return AgentTarget(directory=home, name="Test", key=key)


def test_a_retired_value_is_removed_and_other_keys_are_kept(
    dirs: tuple[Path, Path],
) -> None:
    dotfiles, home = dirs
    _write_profile(
        dotfiles,
        "work-c",
        {"settings": {}, "retired": {MIGRATION: {"tui": ["default"]}}},
    )
    _write_target(home, {"tui": "default", "enabledPlugins": {"p@m": True}})

    assert _merge_settings_fragment(dotfiles, _agent(home), system="Linux")

    assert _read_target(home) == {"enabledPlugins": {"p@m": True}}


def test_a_value_the_user_changed_is_kept(dirs: tuple[Path, Path]) -> None:
    dotfiles, home = dirs
    _write_profile(
        dotfiles,
        "work-c",
        {"settings": {}, "retired": {MIGRATION: {"tui": ["default"]}}},
    )
    _write_target(home, {"tui": "fullscreen"})

    _merge_settings_fragment(dotfiles, _agent(home), system="Linux")

    assert _read_target(home)["tui"] == "fullscreen"


def test_any_value_the_fragments_ever_wrote_matches(dirs: tuple[Path, Path]) -> None:
    dotfiles, home = dirs
    retired = {MIGRATION: {"tui": ["default", "fullscreen"]}}
    _write_profile(dotfiles, "work-c", {"settings": {}, "retired": retired})
    _write_target(home, {"tui": "fullscreen"})

    _merge_settings_fragment(dotfiles, _agent(home), system="Linux")

    assert "tui" not in _read_target(home)


def test_a_key_the_fragments_still_set_is_upserted_not_retired(
    dirs: tuple[Path, Path],
) -> None:
    dotfiles, home = dirs
    retired = {MIGRATION: {"tui": ["default"]}}
    _write_profile(
        dotfiles, "work-c", {"settings": {"tui": "default"}, "retired": retired}
    )
    _write_target(home, {"tui": "fullscreen"})

    _merge_settings_fragment(dotfiles, _agent(home), system="Linux")

    assert _read_target(home)["tui"] == "default"


def test_a_home_evaluates_a_migration_once(dirs: tuple[Path, Path]) -> None:
    dotfiles, home = dirs
    _write_profile(
        dotfiles,
        "work-c",
        {"settings": {}, "retired": {MIGRATION: {"tui": ["default"]}}},
    )
    _write_target(home, {"tui": "default"})
    _merge_settings_fragment(dotfiles, _agent(home), system="Linux")
    assert "tui" not in _read_target(home)

    # The user picks the classic renderer again (`/tui default`)
    _write_target(home, {**_read_target(home), "tui": "default"})

    assert not _merge_settings_fragment(dotfiles, _agent(home), system="Linux")
    assert _read_target(home)["tui"] == "default"
    state = json.loads((home / "settings.sync-state.json").read_text(encoding="utf-8"))
    assert state["retired"] == [MIGRATION]


def test_a_migration_that_matched_nothing_is_still_recorded(
    dirs: tuple[Path, Path],
) -> None:
    dotfiles, home = dirs
    _write_profile(
        dotfiles,
        "work-c",
        {"settings": {}, "retired": {MIGRATION: {"tui": ["default"]}}},
    )
    _write_target(home, {"theme": "dark"})

    _merge_settings_fragment(dotfiles, _agent(home), system="Linux")
    _write_target(home, {"theme": "dark", "tui": "default"})
    _merge_settings_fragment(dotfiles, _agent(home), system="Linux")

    assert _read_target(home)["tui"] == "default"


def test_dry_run_neither_writes_nor_records(dirs: tuple[Path, Path]) -> None:
    dotfiles, home = dirs
    _write_profile(
        dotfiles,
        "work-c",
        {"settings": {}, "retired": {MIGRATION: {"tui": ["default"]}}},
    )
    _write_target(home, {"tui": "default"})

    assert _merge_settings_fragment(
        dotfiles, _agent(home), dry_run=True, system="Linux"
    )

    assert _read_target(home) == {"tui": "default"}
    assert not (home / "settings.sync-state.json").exists()


def test_the_record_is_written_before_settings(
    dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    # A failure in between leaves the old value in place (today's behavior)
    # rather than retrying later over a value the user may have set again
    import sync_agents

    dotfiles, home = dirs
    _write_profile(
        dotfiles,
        "work-c",
        {"settings": {}, "retired": {MIGRATION: {"tui": ["default"]}}},
    )
    _write_target(home, {"tui": "default"})

    write = sync_agents._write_settings

    def fail_on_settings(path: Path, data: dict) -> None:
        if path.name == "settings.json":
            raise OSError("disk full")
        write(path, data)

    monkeypatch.setattr(sync_agents, "_write_settings", fail_on_settings)
    with pytest.raises(OSError):
        _merge_settings_fragment(dotfiles, _agent(home), system="Linux")
    monkeypatch.undo()

    assert not _merge_settings_fragment(dotfiles, _agent(home), system="Linux")
    assert _read_target(home)["tui"] == "default"


# ---- The repo's own fragments, applied to what earlier syncs deployed ----

DEPLOYED_BEFORE = {
    "work-a": {
        "effortLevel": "medium",
        "permissions": {"defaultMode": "auto"},
        "skipAutoPermissionPrompt": True,
        "teammateMode": "in-process",
        "askUserQuestionTimeout": "10m",
        "editorMode": "normal",
        "companyAnnouncements": ["Welcome to workspace - a -"],
    },
    "work-b": {
        "effortLevel": "medium",
        "permissions": {"defaultMode": "auto"},
        "skipAutoPermissionPrompt": True,
        "tui": "default",
    },
    "work-c": {"effortLevel": "xhigh", "tui": "default"},
    "work-d": {
        "effortLevel": "xhigh",
        "permissions": {"defaultMode": "default"},
        "tui": "default",
    },
}
RETIRED_KEYS = {"effortLevel", "tui", "teammateMode", "editorMode"}
USER_KEYS = {
    "enabledPlugins": {"p@m": True},
    "statusLine": {"type": "command", "command": "x"},
}


@pytest.mark.parametrize(
    "renderer", ["default", "fullscreen"]
)  # fullscreen: before #286
@pytest.mark.parametrize("key", sorted(DEPLOYED_BEFORE))
def test_repo_work_profiles_retire_what_they_dropped(
    tmp_path: Path, key: str, renderer: str
) -> None:
    deployed = dict(DEPLOYED_BEFORE[key])
    if "tui" in deployed:
        deployed["tui"] = renderer
    _write_target(tmp_path, {**deployed, **USER_KEYS})

    _merge_settings_fragment(DOTFILES, _agent(tmp_path, key), system="Linux")

    result = _read_target(tmp_path)
    assert not RETIRED_KEYS & set(result)
    assert result["permissions"]["defaultMode"] == "auto"
    assert result["skipAutoPermissionPrompt"] is True
    assert {name: result[name] for name in USER_KEYS} == USER_KEYS
    if key == "work-a":
        assert result["askUserQuestionTimeout"] == "10m"
        assert result["companyAnnouncements"] == ["Welcome to workspace - a -"]


def test_the_claude_profile_keeps_its_effective_settings(tmp_path: Path) -> None:
    # Moving defaultMode / skipAutoPermissionPrompt into the shared layer
    # must not change what the personal profile gets
    _merge_settings_fragment(DOTFILES, _agent(tmp_path, "claude"), system="Linux")

    result = _read_target(tmp_path)
    assert result["permissions"]["defaultMode"] == "auto"
    assert result["skipAutoPermissionPrompt"] is True
    assert result["effortLevel"] == "medium"
    assert result["teammateMode"] == "auto"
