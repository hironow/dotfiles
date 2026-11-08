"""The Codex home's plan (PR 3d.2): pure values, no environment or file I/O.

Codex runs a user hook only while the thread's config snapshot trusts it, and
keys that trust by the hook's position in ~/.codex/hooks.json and a hash of
its declaration. So a group whose declaration is still wanted never moves,
and agent-hook's guards (G) go beside the scripts: in an empty group with the
same matcher, or past the end of the list. A thread that does not trust G yet
still runs the scripts. PR 5 removes the scripts later.

Every `hooks` value here is the `hooks` member of hooks.json: event name to
a list of groups, each `{"matcher": ..., "hooks": [handlers]}`.
"""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass

from agent_hook_plan import (
    UNCHANGED,
    FileBytes,
    HomePlan,
    ReleaseEvidence,
    settings_value,
)

Hooks = dict[str, list[dict]]

_GUARD = re.compile(r"--hook (files-guard|secrets-guard|command-guard)(\s|$)")
# G is whole when it runs each of these once (PR 5 removes the scripts on it)
GUARDS = ("files-guard", "secrets-guard", "command-guard")
SCRIPT, BINARY = "script", "binary"


class PlacementInvalid(ValueError):
    """A merge would move or overwrite what it must keep; the home stops."""


@dataclass(frozen=True)
class Classes:
    """How sync's ownership rule reads a group. Each family needs at least
    one handler, so an empty group belongs to none; a group that mixes the
    two families is a user's."""

    is_script: Callable[[dict], bool]
    is_binary: Callable[[dict], bool]
    is_retired: Callable[[dict], bool]

    def family(self, group: dict) -> str | None:
        if self.is_binary(group):
            return BINARY
        if self.is_script(group):
            return SCRIPT
        return None


@dataclass(frozen=True)
class Merged:
    hooks: Hooks
    changed: frozenset[str]


def _handlers(group: dict) -> list:
    handlers = group.get("hooks", [])
    return handlers if isinstance(handlers, list) else []


def _emptied(group: dict) -> dict:
    return {**{k: v for k, v in group.items() if k != "hooks"}, "hooks": []}


def _is_user(group: dict, classes: Classes) -> bool:
    return (
        bool(_handlers(group))
        and classes.family(group) is None
        and not classes.is_retired(group)
    )


def codex_guards(rendered: Mapping[str, Sequence[dict]]) -> Hooks:
    """G: the render's groups whose every handler runs one of agent-hook's
    three guards, in the render's order (rtk and the formatter wait for PR 5)."""
    guards: Hooks = {}
    for event, groups in rendered.items():
        for group in groups:
            handlers = _handlers(group)
            if handlers and all(
                _GUARD.search(str(h.get("command", ""))) for h in handlers
            ):
                guards.setdefault(event, []).append(deepcopy(group))
    return guards


def _guard_ids(guards: Mapping[str, Sequence[dict]]) -> list[str]:
    return [
        found[1]
        for groups in guards.values()
        for group in groups
        for handler in _handlers(group)
        if (found := _GUARD.search(str(handler.get("command", ""))))
    ]


def family_groups(
    hooks: Mapping[str, Sequence[dict]], classes: Classes, family: str
) -> Hooks:
    """The family's groups, per event, in index order."""
    found: Hooks = {}
    for event, groups in hooks.items():
        for group in groups:
            if classes.family(group) == family:
                found.setdefault(event, []).append(deepcopy(group))
    return found


def _reconcile(
    groups: list[dict], desired: Sequence[dict], is_member: Callable[[dict], bool]
) -> None:
    """Make one event's groups of a family hold `desired`. A group whose
    declaration equals a desired one stays where it is, so Codex keeps
    trusting it; every other group of the family is emptied in place. Each
    desired group left over fills, with its matcher, a group of the family it
    just emptied, else any empty group (another family's after an uninstall),
    else goes past the end. Order does not matter to Codex: it runs every
    matching handler."""
    members = [index for index, group in enumerate(groups) if is_member(group)]
    kept: set[int] = set()
    leftover: list[dict] = []
    for wanted in desired:
        index = next(
            (i for i in members if i not in kept and groups[i] == wanted), None
        )
        if index is None:
            leftover.append(wanted)
        else:
            kept.add(index)
    freed = [index for index in members if index not in kept]
    for index in freed:
        groups[index] = _emptied(groups[index])
    for wanted in leftover:

        def fits(index: int, wanted: dict = wanted) -> bool:
            group = groups[index]
            return not _handlers(group) and group.get("matcher") == wanted.get(
                "matcher"
            )

        slot = next(
            (i for i in freed if fits(i)),
            next((i for i in range(len(groups)) if fits(i)), None),
        )
        if slot is None:
            groups.append(deepcopy(wanted))
        else:
            groups[slot] = deepcopy(wanted)


def merge(
    hooks: Mapping[str, Sequence[dict]],
    scripts: Mapping[str, Sequence[dict]],
    binary: Mapping[str, Sequence[dict]],
    classes: Classes,
) -> Merged:
    """The new hooks value: retired groups emptied in place, then each family
    (the scripts, then agent-hook's) reconciled with what is desired, event by
    event (_reconcile). An event the file lacks comes after its events. No
    group is removed. `changed` names each family whose groups changed."""
    result: Hooks = {event: deepcopy(list(groups)) for event, groups in hooks.items()}
    for groups in result.values():
        for index, group in enumerate(groups):
            if classes.is_retired(group):
                groups[index] = _emptied(group)
    changed: set[str] = set()
    for family, desired in ((SCRIPT, scripts), (BINARY, binary)):
        before = family_groups(result, classes, family)
        events = [*result, *(event for event in desired if event not in result)]
        for event in events:
            wanted = list(desired.get(event, []))
            if event not in result and not wanted:
                continue
            _reconcile(
                result.setdefault(event, []),
                wanted,
                lambda group, family=family: classes.family(group) == family,
            )
        if family_groups(result, classes, family) != before:
            changed.add(family)
    return Merged(result, frozenset(changed))


def check(
    old: Mapping[str, Sequence[dict]],
    new: Mapping[str, Sequence[dict]],
    classes: Classes,
    changed: frozenset[str],
) -> None:
    """Raise PlacementInvalid unless the merge kept what it must keep."""
    for event, groups in old.items():
        after = new.get(event)
        if after is None or len(after) < len(groups):
            raise PlacementInvalid(f"a group of {event} was removed")
        for index, group in enumerate(groups):
            family = classes.family(group)
            if _is_user(group, classes) and after[index] != group:
                raise PlacementInvalid(f"user group {event}[{index}] moved or changed")
            if family is not None and family not in changed and after[index] != group:
                raise PlacementInvalid(
                    f"{family} group {event}[{index}] changed, but its family did not"
                )
    # A handler written where a kept one was is caught above: a group that had
    # handlers is a user's, a retired one, or a family's, and the first two
    # rules keep every user group and every unchanged family as it was.


@dataclass(frozen=True)
class CodexFacts:
    """What sync read for the Codex home. `settings`, `state`, `target`, and
    `marked` carry the names the session's checked writes compare."""

    key: str
    settings: bytes | None  # hooks.json
    state: None
    target: str | None  # the stable link's target
    marked: bool
    release: ReleaseEvidence | None
    rendered: Hooks | None  # R's hooks value
    reason: str  # why there is no release or no R
    scripts: Hooks | None  # F's hooks value; None: no scripts fragment
    shells_ok: bool
    shells_reason: str
    classes: Classes


def _stop(facts: CodexFacts, reason: str) -> HomePlan:
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


def _settings_bytes(before: bytes | None, value: dict) -> FileBytes:
    if before is not None and settings_value(before) == value:
        return UNCHANGED
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def plan_codex(operation: str, facts: CodexFacts) -> HomePlan:
    """The first row whose condition holds decides (design section 7.2)."""
    if operation not in {"sync", "install", "uninstall"}:
        raise ValueError(f"unknown operation: {operation}")
    if facts.scripts is None:
        return _stop(facts, "missing scripts fragment")
    guards = {} if facts.rendered is None else codex_guards(facts.rendered)
    ids = _guard_ids(guards)
    if facts.release is None or facts.rendered is None:
        missing = facts.reason  # why there is no release, or no render
    elif sorted(ids) != sorted(GUARDS):
        missing = (
            f"render: agent-hook's guards are {', '.join(ids) or 'none'}, "
            f"not {', '.join(GUARDS)}"
        )
    else:
        missing = ""
    available = not missing
    if operation == "install" and not (available and facts.shells_ok):
        if available:
            return _stop(facts, facts.shells_reason)
        return _stop(
            facts,
            missing if missing.startswith("no release") else f"no release: {missing}",
        )
    value = settings_value(facts.settings)
    hooks = value.get("hooks", {})
    classes = facts.classes
    if operation == "uninstall" or (facts.marked and operation != "install"):
        action, binary, mark, target = "unregister", {}, True, facts.target
    elif available and facts.shells_ok:
        assert facts.release is not None
        action = "install" if operation == "install" else "register"
        binary, mark = guards, False if operation == "install" else facts.marked
        target = str(facts.release.path)
    elif family_groups(hooks, classes, BINARY):
        action, binary, mark, target = (
            "keep",
            family_groups(hooks, classes, BINARY),
            facts.marked,
            facts.target,
        )
    else:
        action, binary, mark, target = "scripts", {}, facts.marked, facts.target
    merged = merge(hooks, facts.scripts, binary, classes)
    try:
        check(hooks, merged.hooks, classes, merged.changed)
    except PlacementInvalid as exc:
        return _stop(facts, f"placement: {exc}")
    new_value = {**value, "hooks": merged.hooks}
    if not merged.hooks:
        new_value.pop("hooks")
    settings = _settings_bytes(facts.settings, new_value)
    if action == "unregister" and settings is UNCHANGED and facts.marked:
        action = "uninstalled"
    # nothing to journal when hooks.json and the mark stay (an install too)
    if (
        action in {"register", "install"}
        and settings is UNCHANGED
        and mark == facts.marked
    ):
        action = "link" if facts.target != target else "nothing"
    # keep and scripts name the reason as 3d.1 does: the source's own words
    reason = (missing or facts.shells_reason) if action in {"keep", "scripts"} else ""
    return HomePlan(
        action,
        merged.hooks if settings is not UNCHANGED else UNCHANGED,
        settings,
        UNCHANGED,
        facts.target,
        target,
        facts.marked,
        mark,
        reason,
    )
