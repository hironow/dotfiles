"""Value calculations for hook registration and shared settings."""

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from dataclasses import replace

import agent_hook_plan as plan
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


def block(command: str) -> dict:
    return {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]}


def managed(settings: dict) -> dict:
    return {
        event: owned
        for event, blocks in settings.get("hooks", {}).items()
        if (
            owned := [
                b
                for b in blocks
                if all(h["command"].startswith("/managed/") for h in b["hooks"])
            ]
        )
    }


def merge_hooks(settings: dict, desired: dict) -> dict:
    indexes = {
        event: {
            i for i, b in enumerate(blocks) if b in managed(settings).get(event, [])
        }
        for event, blocks in settings.get("hooks", {}).items()
    }
    return sync.merge_hook_values(settings, desired.get("hooks", {}), indexes)[0]


def facts(
    *,
    marked: bool = False,
    wired: bool = False,
    available: bool = True,
    equal: bool = False,
    linked: bool = True,
    retired: bool = False,
) -> plan.HomeFacts:
    release = plan.ReleaseEvidence(
        Path("/data/dotfiles/agent-hooks/releases/0123456789abcdef/agent-hook"),
        "0123456789abcdef",
        "0" * 64,
    )
    current = block("/managed/binary" if wired or equal else "/managed/scripts")
    settings = {"hooks": {"PreToolUse": [current, block("user")]}, "keep": 1}
    return plan.HomeFacts(
        key="claude",
        settings=json.dumps(settings).encode(),
        state=None,
        managed=managed(settings),
        wired=wired or equal,
        target=str(release.path) if linked else None,
        marked=marked,
        release=release if available else None,
        rendered={"hooks": {"PreToolUse": [block("/managed/binary")]}}
        if available
        else None,
        scripts={"hooks": {"PreToolUse": [block("/managed/scripts")]}},
        hook_merge=merge_hooks,
        shared_merge=lambda s, y: (deepcopy(s), deepcopy(y)),
        managed_from=managed,
        reason="no Go",
        retired=retired,
    )


@pytest.mark.parametrize(
    "operation,options,action",
    [
        ("sync", {"marked": True}, "uninstalled"),
        ("sync", {"marked": True, "wired": True}, "stop"),
        ("sync", {"equal": True}, "nothing"),
        ("sync", {"equal": True, "linked": False}, "link"),
        ("sync", {}, "register"),
        ("sync", {"wired": True, "available": False}, "keep"),
        ("sync", {"available": False}, "scripts"),
        ("install", {"available": False}, "stop"),
        ("install", {"marked": True, "available": False}, "stop"),
        ("install", {"marked": True}, "install"),
        ("install", {"marked": True, "wired": True}, "install"),
        ("install", {"equal": True}, "nothing"),
        ("install", {"equal": True, "linked": False}, "link"),
        ("install", {}, "register"),
        ("uninstall", {}, "unregister"),
        ("uninstall", {"wired": True}, "unregister"),
        ("uninstall", {"marked": True, "wired": True}, "unregister"),
        ("uninstall", {"marked": True}, "nothing"),
    ],
)
def test_every_decision_table_row(operation: str, options: dict, action: str) -> None:
    observed = plan.plan_home(operation, facts(**options))
    assert observed.action == action
    assert observed.new_mark == (
        True
        if action == "unregister"
        else False
        if action == "install"
        else options.get("marked", False)
    )


def test_keep_preserves_bytes_and_user_block_positions() -> None:
    before = facts(wired=True, available=False)
    observed = plan.plan_home("sync", before)
    assert observed.hooks is plan.UNCHANGED
    assert observed.settings is plan.UNCHANGED
    assert not observed.changed


def test_shared_merge_that_changes_hooks_stops_before_any_write() -> None:
    before = replace(facts(), shared_merge=lambda s, y: ({**s, "hooks": {}}, y))
    observed = plan.plan_home("sync", before)
    assert observed.action == "stop" and "hooks" in observed.reason
    assert not observed.changed


@pytest.mark.parametrize("operation", ["install", "uninstall"])
def test_install_and_uninstall_never_call_the_shared_merge(operation: str) -> None:
    def forbidden(s: dict, y: dict) -> tuple[dict, dict]:
        pytest.fail("shared merge called outside sync")

    before = replace(facts(marked=True, wired=True), shared_merge=forbidden)
    observed = plan.plan_home(operation, before)
    assert observed.state is plan.UNCHANGED
    assert isinstance(observed.settings, bytes)
    assert json.loads(observed.settings)["keep"] == 1


def test_state_only_change_is_not_nothing_to_do() -> None:
    before = replace(
        facts(equal=True), shared_merge=lambda s, y: (s, {"retired": ["migration"]})
    )
    observed = plan.plan_home("sync", before)
    assert observed.action == "nothing" and observed.changed
    assert observed.settings is plan.UNCHANGED
    assert isinstance(observed.state, bytes)
    assert json.loads(observed.state) == {"retired": ["migration"]}


def test_a_retired_block_turns_an_equal_registration_into_register() -> None:
    # given a home wired as the release renders it, with rtk's own hook back
    observed = plan.plan_home("sync", facts(equal=True, retired=True))
    # then sync registers again, and its merge drops that block
    assert observed.action == "register"


def test_keep_without_a_link_says_every_hook_blocks() -> None:
    observed = plan.plan_home("sync", facts(wired=True, available=False, linked=False))
    assert observed.action == "keep"
    assert (
        "every hook of claude blocks until a release is ready or the home is uninstalled"
        in observed.reason
    )
