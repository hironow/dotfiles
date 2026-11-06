"""Value calculations for hook registration and shared settings."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import sync_agents as sync


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for key, name in (
        ("HOME", "home"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_DATA_HOME", "data"),
    ):
        monkeypatch.setenv(key, str(tmp_path / name))


def test_hook_value_merge_preserves_user_blocks_and_does_not_mutate_inputs() -> None:
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "user"}]}
    owned = {"matcher": "Bash", "hooks": [{"type": "command", "command": "old"}]}
    new = {"matcher": "Bash", "hooks": [{"type": "command", "command": "new"}]}
    target = {"hooks": {"PreToolUse": [owned, user]}, "keep": {"a": 1}}
    before = deepcopy(target)
    merged, changed = sync.merge_hook_values(
        target, {"PreToolUse": [new]}, {"PreToolUse": {0}}
    )
    assert changed and merged == {
        "hooks": {"PreToolUse": [user, new]},
        "keep": {"a": 1},
    }
    assert target == before
    merged["keep"]["a"] = 2
    assert target == before


def test_settings_value_merge_records_evaluated_absent_migrations() -> None:
    target = {"hooks": {}, "keep": 1}
    fragment = {"env": {"A": "1"}, "retired": {"retire-old": {"old": [False]}}}
    state = {"other": "kept"}
    before = deepcopy((target, fragment, state))
    merged, next_state, changed, state_changed = sync.merge_settings_values(
        target, fragment, state
    )
    assert changed and state_changed
    assert merged == {"hooks": {}, "keep": 1, "env": {"A": "1"}}
    assert next_state == {"other": "kept", "retired": ["retire-old"]}
    assert (target, fragment, state) == before
    assert json.dumps(next_state)
