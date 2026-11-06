"""Pure decisions for Claude hook registration. No environment or filesystem I/O."""

import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class _Unchanged(Enum):
    VALUE = "unchanged"


class _Absent(Enum):
    HOOKS = "absent hooks"


UNCHANGED = _Unchanged.VALUE
ABSENT_HOOKS = _Absent.HOOKS
FileBytes = bytes | None | _Unchanged


@dataclass(frozen=True)
class ReleaseEvidence:
    path: Path
    id: str
    sha256: str


@dataclass(frozen=True)
class HomeFacts:
    key: str
    settings: bytes | None
    state: bytes | None
    managed: dict
    wired: bool
    target: str | None
    marked: bool
    release: ReleaseEvidence | None
    rendered: dict | None
    scripts: dict | None
    hook_merge: Callable[[dict, dict], dict]
    shared_merge: Callable[[dict, dict], tuple[dict, dict]]
    managed_from: Callable[[dict], dict]
    reason: str = ""


@dataclass(frozen=True)
class HomePlan:
    action: str
    hooks: object
    settings: FileBytes
    state: FileBytes
    old_target: str | None
    new_target: str | None
    old_mark: bool
    new_mark: bool
    reason: str = ""

    @property
    def changed(self) -> bool:
        return (
            self.settings is not UNCHANGED
            or self.state is not UNCHANGED
            or self.old_target != self.new_target
            or self.old_mark != self.new_mark
        )


class PlanInvalid(ValueError):
    pass


def settings_value(raw: bytes | None) -> dict:
    value = {} if raw is None else json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise PlanInvalid("settings must be a JSON object")
    return value


def _bytes_if_changed(before: bytes | None, after: dict) -> FileBytes:
    if settings_value(before) == after:
        return UNCHANGED
    return (json.dumps(after, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _decision(operation: str, facts: HomeFacts) -> tuple[str, str]:
    available = facts.release is not None and facts.rendered is not None
    if operation == "uninstall":
        return (
            ("nothing", "") if facts.marked and not facts.wired else ("unregister", "")
        )
    if operation == "install":
        if not available:
            return "stop", f"no release: {facts.reason}"
        if facts.marked:
            return "install", ""
    elif operation != "sync":
        raise ValueError(f"unknown operation: {operation}")
    if facts.marked:
        if facts.wired:
            return (
                "stop",
                f"uninstalled, yet wired; run just agent-hooks-uninstall {facts.key} or just agent-hooks-install {facts.key}",
            )
        return "uninstalled", ""
    if available:
        assert facts.rendered is not None and facts.release is not None
        if facts.managed == facts.rendered.get("hooks", {}):
            return (
                ("nothing", "")
                if facts.target == str(facts.release.path)
                else ("link", "")
            )
        return "register", ""
    if facts.wired:
        reason = facts.reason
        if facts.target is None:
            reason += f"; every hook of {facts.key} blocks until a release is ready or the home is uninstalled"
        return "keep", reason
    return "scripts", facts.reason


def _stopped(facts: HomeFacts, reason: str) -> HomePlan:
    return HomePlan(
        "stop",
        UNCHANGED,
        UNCHANGED,
        UNCHANGED,
        facts.target,
        facts.target,
        facts.marked,
        facts.marked,
        reason,
    )


def plan_home(operation: str, facts: HomeFacts) -> HomePlan:
    """Apply the sync/install/uninstall tables and check the hook invariants."""
    action, reason = _decision(operation, facts)
    if action == "stop" and operation == "install":
        return _stopped(facts, reason)
    settings = settings_value(facts.settings)
    state = settings_value(facts.state)
    original_hooks = deepcopy(settings.get("hooks", ABSENT_HOOKS))
    desired = (
        facts.rendered
        if action in {"register", "install"}
        else facts.scripts
        if action in {"scripts", "uninstalled", "unregister"}
        else None
    )
    if action == "unregister" and facts.wired and desired is None:
        return _stopped(facts, "missing scripts fragment; cannot uninstall")
    hook_part: object = UNCHANGED
    if desired is not None:
        settings = facts.hook_merge(deepcopy(settings), deepcopy(desired))
        hook_part = deepcopy(settings.get("hooks", ABSENT_HOOKS))
        if facts.managed_from(settings) != facts.managed_from(desired):
            return _stopped(
                facts,
                "hook merge invariant: managed hooks differ from the desired registration",
            )
    expected_hooks = original_hooks if hook_part is UNCHANGED else hook_part
    if operation == "sync":
        settings, state = facts.shared_merge(deepcopy(settings), deepcopy(state))
    if settings.get("hooks", ABSENT_HOOKS) != expected_hooks:
        return _stopped(facts, "shared merge invariant: hooks changed")
    new_target = facts.target
    if action in {"register", "install", "link"}:
        assert facts.release is not None
        new_target = str(facts.release.path)
    new_mark = (
        True
        if action == "unregister"
        else False
        if action == "install"
        else facts.marked
    )
    return HomePlan(
        action,
        hook_part,
        _bytes_if_changed(facts.settings, settings),
        _bytes_if_changed(facts.state, state) if operation == "sync" else UNCHANGED,
        facts.target,
        new_target,
        facts.marked,
        new_mark,
        reason,
    )
