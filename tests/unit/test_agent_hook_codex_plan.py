"""The Codex home's plan (PR 3d.2): pure values, no I/O.

Codex keys a user hook's trust by its position in ~/.codex/hooks.json, so the
merge keeps every script group and user group where it is, and adds
agent-hook's guards (G) beside the scripts, in empty groups or past the end
(design section 7.2).
"""

import json
import random
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import agent_hook_codex_plan as codex
import agent_hook_plan as plan

HOME = "/h/.codex/hooks/"
LINK = "/d/current/codex/agent-hook"


def script(*names: str, matcher: str | None = "Bash") -> dict:
    return {
        "matcher": matcher,
        "hooks": [
            {"type": "command", "command": f'bash "{HOME}{name}"', "timeout": 30}
            for name in names
        ],
    }


def binary(*ids: str, matcher: str | None = "Bash", event: str = "pre") -> dict:
    return {
        "matcher": matcher,
        "hooks": [
            {
                "type": "command",
                "command": f"'{LINK}' codex {event} --hook {hook}"
                + (
                    " || { printf '%s\\n' 'agent-hook failed' >&2; exit 2; }"
                    if hook.endswith("guard")
                    else ""
                ),
                "timeout": 30,
            }
            for hook in ids
        ],
    }


def user(name: str, matcher: str | None = "Bash") -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": name}]}


def empty(matcher: str | None = "Bash") -> dict:
    return {"matcher": matcher, "hooks": []}


def _all(group: dict, test) -> bool:
    handlers = group.get("hooks", [])
    return bool(handlers) and all(test(h["command"]) for h in handlers)


CLASSES = codex.Classes(
    is_script=lambda g: _all(g, lambda c: HOME in c),
    is_binary=lambda g: _all(g, lambda c: c.startswith(f"'{LINK}'")),
    is_retired=lambda g: _all(g, lambda c: c == "rtk hook codex"),
)

# Today's scripts on this Mac (F), and agent-hook's render (R).
FILES = "Write|Edit|NotebookEdit"
F = {
    "PreToolUse": [
        script(
            "guard-codex.sh block-prohibited-files.sh",
            "guard-codex.sh block-secrets.sh",
            matcher=FILES,
        ),
        script("guard-codex.sh block-prohibited-commands.sh"),
        script("rtk-hook-codex.sh"),
    ],
    "PostToolUse": [script("format-after-edit.sh", matcher="Write|Edit")],
}
R = {
    "PreToolUse": [
        binary("files-guard", "secrets-guard", matcher=FILES),
        binary("command-guard"),
        binary("rtk"),
    ],
    "PostToolUse": [binary("formatter", matcher="Write|Edit", event="post")],
}
G = {
    "PreToolUse": [
        binary("files-guard", "secrets-guard", matcher=FILES),
        binary("command-guard"),
    ]
}
HERDR = user("bash '/x/herdr-agent-state.sh' session", matcher=None)


def this_mac() -> dict:
    return {"SessionStart": [deepcopy(HERDR)], **deepcopy(F)}


# ---- codex_guards ----


def test_codex_guards_keeps_the_guard_groups_of_the_render_in_order() -> None:
    assert codex.codex_guards(R) == G


def test_codex_guards_wants_every_handler_of_a_group_to_be_a_guard() -> None:
    mixed = {"PreToolUse": [binary("command-guard", "rtk")]}
    assert codex.codex_guards(mixed) == {}


# ---- merge and check ----


def test_wiring_this_mac_adds_g_after_the_scripts_and_moves_nothing() -> None:
    merged = codex.merge(this_mac(), F, G, CLASSES)
    assert merged.hooks == {
        "SessionStart": [HERDR],
        "PreToolUse": [*F["PreToolUse"], *G["PreToolUse"]],
        "PostToolUse": F["PostToolUse"],
    }
    assert merged.changed == frozenset({"binary"})
    codex.check(this_mac(), merged.hooks, CLASSES, merged.changed)


def test_an_unchanged_home_merges_to_itself() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    again = codex.merge(wired, F, G, CLASSES)
    assert again.hooks == wired
    assert again.changed == frozenset()


def test_uninstall_leaves_empty_groups_and_install_reuses_their_keys() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    uninstalled = codex.merge(wired, F, {}, CLASSES)
    assert uninstalled.hooks["PreToolUse"][3:] == [empty(FILES), empty()]
    assert uninstalled.changed == frozenset({"binary"})
    codex.check(wired, uninstalled.hooks, CLASSES, uninstalled.changed)
    reinstalled = codex.merge(uninstalled.hooks, F, G, CLASSES)
    assert reinstalled.hooks == wired


def test_a_user_group_after_the_empty_groups_does_not_stop_their_reuse() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    uninstalled = codex.merge(wired, F, {}, CLASSES).hooks
    uninstalled["PreToolUse"].append(user("later"))
    reinstalled = codex.merge(uninstalled, F, G, CLASSES)
    assert reinstalled.hooks["PreToolUse"][3:5] == G["PreToolUse"]
    assert reinstalled.hooks["PreToolUse"][5] == user("later")


def test_user_groups_before_between_and_after_keep_their_indices() -> None:
    hooks = {
        "PreToolUse": [
            user("a"),
            *deepcopy(F["PreToolUse"][:2]),
            user("b"),
            deepcopy(F["PreToolUse"][2]),
            user("c"),
        ]
    }
    merged = codex.merge(hooks, {"PreToolUse": F["PreToolUse"]}, G, CLASSES)
    assert merged.hooks["PreToolUse"][:6] == hooks["PreToolUse"]
    assert merged.hooks["PreToolUse"][6:] == G["PreToolUse"]
    codex.check(hooks, merged.hooks, CLASSES, merged.changed)


def test_a_retired_group_is_emptied_in_place() -> None:
    hooks = {"PreToolUse": [user("rtk hook codex"), *deepcopy(F["PreToolUse"])]}
    merged = codex.merge(hooks, {"PreToolUse": F["PreToolUse"]}, {}, CLASSES)
    assert merged.hooks["PreToolUse"][0] == empty()
    assert merged.hooks["PreToolUse"][1:] == F["PreToolUse"]
    codex.check(hooks, merged.hooks, CLASSES, merged.changed)


def test_a_scripts_update_and_a_template_change_both_pass_the_check() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    f2 = deepcopy(F)
    f2["PreToolUse"][1]["hooks"][0]["timeout"] = 45
    updated = codex.merge(wired, f2, G, CLASSES)
    assert updated.changed == frozenset({"script"})
    assert updated.hooks["PreToolUse"][1] == f2["PreToolUse"][1]
    codex.check(wired, updated.hooks, CLASSES, updated.changed)
    g2 = deepcopy(G)
    g2["PreToolUse"][1]["hooks"][0]["timeout"] = 20
    template = codex.merge(wired, F, g2, CLASSES)
    assert template.changed == frozenset({"binary"})
    assert template.hooks["PreToolUse"][4] == g2["PreToolUse"][1]
    codex.check(wired, template.hooks, CLASSES, template.changed)


def test_scripts_that_grow_while_uninstalled_take_an_empty_group() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    uninstalled = codex.merge(wired, F, {}, CLASSES).hooks
    f2 = deepcopy(F)
    f2["PreToolUse"].append(script("another.sh"))
    grown = codex.merge(uninstalled, f2, {}, CLASSES)
    assert grown.hooks["PreToolUse"][4] == script("another.sh")
    codex.check(uninstalled, grown.hooks, CLASSES, grown.changed)
    # G's files group gets its own empty group back, at the key Codex trusts;
    # its Bash group finds none left, so it goes past the end, at a new key
    reinstalled = codex.merge(grown.hooks, f2, G, CLASSES)
    assert reinstalled.hooks["PreToolUse"][3] == G["PreToolUse"][0]
    assert reinstalled.hooks["PreToolUse"][-1] == G["PreToolUse"][1]
    codex.check(grown.hooks, reinstalled.hooks, CLASSES, reinstalled.changed)


def _kept(before: dict, after: dict, desired: dict, is_member) -> list:
    """The groups of before, in the family, whose declaration is one of
    desired's but which no longer sit at their index in after."""
    return [
        (event, index)
        for event, groups in before.items()
        for index, group in enumerate(groups)
        if is_member(group)
        and group in desired.get(event, [])
        and after.get(event, [])[index : index + 1] != [group]
    ]


@pytest.mark.parametrize("with_g", [True, False], ids=["with G", "without G"])
def test_scripts_that_grow_by_one_group_keep_every_other_group_in_place(
    with_g: bool,
) -> None:
    wired = codex.merge(this_mac(), F, G if with_g else {}, CLASSES).hooks
    f2 = deepcopy(F)
    f2["PreToolUse"].append(script("another.sh"))
    grown = codex.merge(wired, f2, G if with_g else {}, CLASSES)
    assert _kept(wired, grown.hooks, f2, CLASSES.is_script) == []
    assert grown.hooks["PreToolUse"][:3] == wired["PreToolUse"][:3]
    assert grown.hooks["PreToolUse"][-1] == script("another.sh")
    codex.check(wired, grown.hooks, CLASSES, grown.changed)


def test_a_changed_first_group_moves_no_other_script_group() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    f2 = deepcopy(F)
    f2["PreToolUse"][0]["matcher"] = "Write|Edit"
    changed = codex.merge(wired, f2, G, CLASSES)
    assert _kept(wired, changed.hooks, f2, CLASSES.is_script) == []
    assert changed.hooks["PreToolUse"][1:3] == F["PreToolUse"][1:3]
    assert changed.hooks["PreToolUse"][0] == empty(FILES)
    assert changed.hooks["PreToolUse"][-1] == f2["PreToolUse"][0]


def test_a_script_group_past_g_keeps_its_place_through_uninstall_and_updates() -> None:
    # given a script group sync appended after G, and then an uninstall
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    f2 = deepcopy(F)
    f2["PreToolUse"].append(script("another.sh"))
    grown = codex.merge(wired, f2, G, CLASSES).hooks
    uninstalled = codex.merge(grown, f2, {}, CLASSES).hooks
    # when another scripts update changes only the first group
    f3 = deepcopy(f2)
    f3["PreToolUse"][0]["hooks"][0]["timeout"] = 45
    updated = codex.merge(uninstalled, f3, {}, CLASSES)
    # then the appended group stays where it was, and G's empty groups stay free
    assert _kept(uninstalled, updated.hooks, f3, CLASSES.is_script) == []
    assert updated.hooks["PreToolUse"][3:5] == [empty(FILES), empty()]
    # and an install puts G back at its own keys
    reinstalled = codex.merge(updated.hooks, f3, G, CLASSES).hooks
    assert reinstalled["PreToolUse"][3:5] == G["PreToolUse"]


def test_a_template_change_of_one_guard_group_keeps_the_other_in_place() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    g2 = deepcopy(G)
    g2["PreToolUse"][0]["hooks"][0]["timeout"] = 20
    template = codex.merge(wired, F, g2, CLASSES)
    assert template.hooks["PreToolUse"][4] == G["PreToolUse"][1]
    assert template.hooks["PreToolUse"][3] == g2["PreToolUse"][0]


def test_a_mixed_group_and_a_user_group_are_never_touched() -> None:
    mixed = {
        "matcher": "Bash",
        "hooks": [*script("x.sh")["hooks"], *binary("command-guard")["hooks"]],
    }
    hooks = {"PreToolUse": [deepcopy(mixed), *deepcopy(F["PreToolUse"])]}
    merged = codex.merge(hooks, {"PreToolUse": F["PreToolUse"]}, G, CLASSES)
    assert merged.hooks["PreToolUse"][0] == mixed


def test_other_keys_of_a_group_and_new_events_are_kept_in_order() -> None:
    hooks = {"SessionStart": [deepcopy(HERDR)]}
    merged = codex.merge(hooks, F, G, CLASSES)
    assert list(merged.hooks) == ["SessionStart", "PreToolUse", "PostToolUse"]


def test_check_refuses_a_moved_user_group() -> None:
    old = {"PreToolUse": [deepcopy(F["PreToolUse"][1]), user("u")]}
    new = {"PreToolUse": [user("u"), empty()]}
    with pytest.raises(codex.PlacementInvalid, match="user group"):
        codex.check(old, new, CLASSES, frozenset({"script"}))


def test_check_refuses_a_changed_family_that_was_not_named() -> None:
    old = {"PreToolUse": [deepcopy(F["PreToolUse"][1])]}
    new = {"PreToolUse": [empty()]}
    with pytest.raises(codex.PlacementInvalid, match="script group"):
        codex.check(old, new, CLASSES, frozenset({"binary"}))


def test_check_refuses_a_handler_written_over_a_user_handler() -> None:
    old = {"PreToolUse": [user("u")]}
    new = {"PreToolUse": [binary("command-guard")]}
    with pytest.raises(codex.PlacementInvalid):
        codex.check(old, new, CLASSES, frozenset({"binary"}))


def test_check_refuses_a_removed_group_or_event() -> None:
    old = {"PreToolUse": [empty(), empty()], "PostToolUse": [empty()]}
    with pytest.raises(codex.PlacementInvalid, match="removed"):
        codex.check(
            old,
            {"PreToolUse": [empty()], "PostToolUse": [empty()]},
            CLASSES,
            frozenset(),
        )
    with pytest.raises(codex.PlacementInvalid, match="removed"):
        codex.check(old, {"PreToolUse": [empty(), empty()]}, CLASSES, frozenset())


def _random_hooks(rng: random.Random) -> dict:
    makers = [
        lambda i: user(f"u{i}", matcher=rng.choice(["Bash", FILES, None])),
        lambda i: script(f"s{i}.sh", matcher=rng.choice(["Bash", FILES])),
        lambda i: binary("command-guard"),
        lambda i: user("rtk hook codex"),
        lambda i: empty(rng.choice(["Bash", FILES])),
    ]
    return {
        event: [rng.choice(makers)(i) for i in range(rng.randint(0, 6))]
        for event in rng.sample(
            ["PreToolUse", "PostToolUse", "SessionStart"], rng.randint(1, 3)
        )
    }


@pytest.mark.parametrize("seed", range(300))
def test_merge_always_passes_check_on_random_layouts(seed: int) -> None:
    rng = random.Random(seed)
    hooks = _random_hooks(rng)
    for desired_binary in (G, {}):
        merged = codex.merge(hooks, F, desired_binary, CLASSES)
        codex.check(hooks, merged.hooks, CLASSES, merged.changed)
        assert (
            codex.merge(merged.hooks, F, desired_binary, CLASSES).changed == frozenset()
        )


@pytest.mark.parametrize("seed", range(100))
def test_script_groups_never_move_except_in_a_scripts_update(seed: int) -> None:
    """Design section 3.1's claim, over random sequences of changes."""
    rng = random.Random(1000 + seed)
    hooks = codex.merge(this_mac(), F, {}, CLASSES).hooks
    scripts = deepcopy(F)
    g = deepcopy(G)
    for _ in range(25):
        step = rng.choice(
            ["sync", "install", "uninstall", "release", "template", "scripts"]
        )
        before = deepcopy(hooks)
        if step == "template":
            g = deepcopy(g)
            g["PreToolUse"][rng.randrange(2)]["hooks"][0]["timeout"] = rng.randint(
                1, 60
            )
        if step == "scripts":
            scripts = deepcopy(scripts)
            groups = scripts["PreToolUse"]
            change = rng.choice(["timeout", "matcher", "grow", "shrink"])
            if change == "timeout":
                groups[rng.randrange(len(groups))]["hooks"][0]["timeout"] = rng.randint(
                    1, 60
                )
            elif change == "matcher":
                groups[rng.randrange(len(groups))]["matcher"] = rng.choice(
                    ["Bash", FILES, "Write|Edit"]
                )
            elif change == "grow":
                groups.append(script(f"n{rng.randrange(1000)}.sh"))
            elif len(groups) > 1:
                groups.pop()
        desired = {} if step == "uninstall" else g
        merged = codex.merge(hooks, scripts, desired, CLASSES)
        codex.check(before, merged.hooks, CLASSES, merged.changed)
        # a group whose declaration is still desired never moves: Codex keeps
        # trusting it, even in a scripts update or a template change
        assert _kept(before, merged.hooks, scripts, CLASSES.is_script) == []
        assert _kept(before, merged.hooks, desired, CLASSES.is_binary) == []
        if step != "scripts":
            assert [
                (event, i, group)
                for event, groups in before.items()
                for i, group in enumerate(groups)
                if CLASSES.is_script(group)
            ] == [
                (event, i, group)
                for event, groups in merged.hooks.items()
                for i, group in enumerate(groups)
                if CLASSES.is_script(group)
            ]
        hooks = merged.hooks


# ---- plan_codex ----


def _facts(**overrides: object) -> codex.CodexFacts:
    release = plan.ReleaseEvidence(
        Path("/d/releases/1111111111111111/agent-hook"), "1" * 16, "0" * 64
    )
    base = codex.CodexFacts(
        key="codex",
        settings=(json.dumps({"hooks": this_mac()}, indent=2) + "\n").encode(),
        state=None,
        target=None,
        marked=False,
        release=release,
        rendered=R,
        reason="",
        scripts=F,
        shells_ok=True,
        shells_reason="",
        classes=CLASSES,
    )
    return replace(base, **overrides)


def _hooks_of(result: plan.HomePlan) -> dict:
    assert isinstance(result.settings, bytes)
    return json.loads(result.settings)["hooks"]


def test_row0_a_missing_scripts_fragment_stops() -> None:
    result = codex.plan_codex("sync", _facts(scripts=None))
    assert (result.action, result.reason) == ("stop", "missing scripts fragment")


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        (
            {"release": None, "rendered": None, "reason": "missing Go"},
            "no release: missing Go",
        ),
        ({"shells_ok": False, "shells_reason": "session: fish"}, "session: fish"),
    ],
)
def test_row1_install_refuses_without_a_release_or_clean_shells(
    overrides: dict, reason: str
) -> None:
    result = codex.plan_codex("install", _facts(marked=True, **overrides))
    assert (result.action, result.reason) == ("stop", reason)
    assert result.settings is plan.UNCHANGED and result.new_mark is True


def test_row2_uninstall_empties_g_and_sets_the_mark() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    facts = _facts(settings=(json.dumps({"hooks": wired}) + "\n").encode())
    result = codex.plan_codex("uninstall", facts)
    assert result.action == "unregister"
    assert _hooks_of(result)["PreToolUse"][3:] == [empty(FILES), empty()]
    assert (result.old_mark, result.new_mark) == (False, True)
    assert result.new_target == result.old_target


def test_row2_a_marked_home_with_nothing_to_change_is_uninstalled() -> None:
    result = codex.plan_codex("sync", _facts(marked=True))
    assert result.action == "uninstalled"
    assert result.settings is plan.UNCHANGED


def test_row3_sync_wires_and_points_the_link_at_the_release() -> None:
    result = codex.plan_codex("sync", _facts())
    assert result.action == "register"
    assert _hooks_of(result)["PreToolUse"][3:] == G["PreToolUse"]
    assert result.new_target == "/d/releases/1111111111111111/agent-hook"


def test_row3_a_new_release_only_moves_the_link() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    facts = _facts(
        settings=(json.dumps({"hooks": wired}, indent=2) + "\n").encode(),
        target="/d/releases/0000000000000000/agent-hook",
    )
    assert codex.plan_codex("sync", facts).action == "link"
    current = replace(facts, target="/d/releases/1111111111111111/agent-hook")
    assert codex.plan_codex("sync", current).action == "nothing"


def test_row3_install_clears_the_mark() -> None:
    result = codex.plan_codex("install", _facts(marked=True))
    assert result.action == "install"
    assert (result.old_mark, result.new_mark) == (True, False)


def test_row4_a_wired_home_without_a_release_keeps_g() -> None:
    wired = codex.merge(this_mac(), F, G, CLASSES).hooks
    facts = _facts(
        settings=(json.dumps({"hooks": wired}, indent=2) + "\n").encode(),
        release=None,
        rendered=None,
        reason="missing Go",
    )
    result = codex.plan_codex("sync", facts)
    assert (result.action, result.reason) == ("keep", "missing Go")
    assert result.settings is plan.UNCHANGED


def test_row5_a_home_on_the_scripts_without_a_release_keeps_the_scripts() -> None:
    result = codex.plan_codex(
        "sync", _facts(release=None, rendered=None, reason="missing Go")
    )
    assert (result.action, result.reason) == ("scripts", "missing Go")
    assert result.settings is plan.UNCHANGED


def test_row5_writes_the_scripts_on_a_new_home() -> None:
    result = codex.plan_codex(
        "sync", _facts(settings=None, release=None, rendered=None, reason="missing Go")
    )
    assert result.action == "scripts"
    assert _hooks_of(result) == F


def test_a_placement_that_fails_its_check_stops_the_home(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # merge always passes check (the random-layout test); this pins what
    # plan_codex does if it ever did not
    def bad_merge(
        hooks: dict, scripts: dict, binary: dict, classes: codex.Classes
    ) -> codex.Merged:
        return codex.Merged({"PreToolUse": [user("moved")]}, frozenset({"binary"}))

    monkeypatch.setattr(codex, "merge", bad_merge)
    result = codex.plan_codex("sync", _facts())
    assert result.action == "stop"
    assert result.reason.startswith("placement: ")
    assert result.settings is plan.UNCHANGED
