"""Hold exe/spec/lease.qnt's constants equal to exe/lease-constants.json.

The lease auto-sleep numbers exist in three places by necessity: the JSON is the
declared source of truth, the Go reaper mirrors it, and the Quint model mirrors it
because Quint cannot read JSON. A mirror nothing checks is a mirror that will
disagree -- and the disagreement is silent in the worst possible way: the model
keeps proving a property about numbers the running code no longer uses, so the
gate stays green while the guarantee quietly stops applying.

This is that check. It reads the .qnt as TEXT rather than importing anything:
`quint` is a Node CLI with no Python binding, and a regex over `pure val <key> =
<int>` is both sufficient and honest about what it verifies.

Three checks, in increasing strength:

1.  Every numeric constant in the JSON either appears in the model with the same
    value, or is on NOT_MODELLED -- an explicit, commented allowlist. Adding a
    number to the JSON therefore forces a decision about the model instead of
    drifting past it.
2.  Every mirrored `pure val` in the model that shares a name with a JSON key
    agrees with it, and the model invents no fourth copy of a JSON key under a
    different value.
3.  The cap formula is re-derived here, in Python, from the other constants:

        nightly_cap_local_hour
            == l3_daily_stop_local_hour
               - (l1_tick + drain_ceiling + l2_tick + slack) / 60

    The model re-derives the same formula in its L3NeverHitsAwakeActor
    invariant, and the Go guard re-derives it again. Three independent
    derivations of one number is the point: none of them may read the stored 3
    and call it verified.

Stdlib + pytest only, no fixtures on disk, and no `uv` in its invocation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
CONSTANTS_JSON: Final = _REPO_ROOT / "exe" / "lease-constants.json"
LEASE_QNT: Final = _REPO_ROOT / "exe" / "spec" / "lease.qnt"

#: JSON keys that are deliberately absent from the model, with the reason. The
#: model's header says the same thing in prose; this is the mechanical half.
NOT_MODELLED: Final[dict[str, str]] = {
    # The model's clock is abstract minutes, not wall-clock time in any zone.
    "timezone": "the model has no dates and no zone; the clock is minutes",
    # Task retention is the same reaper binary but a different job, with its own
    # retention argument. Out of scope for the lease state machine.
    "task_ttl_days": "task retention is a separate job (plan section 3.3)",
    "task_ttl_warning_days": "task retention is a separate job (plan section 3.3)",
}

#: `pure val name = 123` in a Quint module. Only integer literals: a mirrored
#: constant that needed an expression would not be a mirror.
_PURE_VAL_INT: Final = re.compile(
    r"^\s*pure val\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<value>-?\d+)\s*$",
    re.MULTILINE,
)


def _json_constants() -> dict[str, object]:
    """The declared source of truth, prose keys (`_`-prefixed) dropped."""
    document = json.loads(CONSTANTS_JSON.read_text(encoding="utf-8"))
    return {key: value for key, value in document.items() if not key.startswith("_")}


def _json_int(key: str) -> int:
    """One numeric constant from the source of truth.

    Narrowing rather than coercing: a key that stopped being a plain integer is
    a change to the shape of the source of truth, and this test's job is to say
    so loudly rather than to `int()` whatever turned up.
    """
    value = _json_constants()[key]
    assert isinstance(value, int) and not isinstance(value, bool), (key, value)
    return value


def _model_int_constants() -> dict[str, int]:
    """Every `pure val <name> = <int>` in exe/spec/lease.qnt."""
    text = LEASE_QNT.read_text(encoding="utf-8")
    return {
        match.group("name"): int(match.group("value"))
        for match in _PURE_VAL_INT.finditer(text)
    }


# --- the two files exist and parse ------------------------------------------


def test_both_files_are_present() -> None:
    assert CONSTANTS_JSON.is_file(), CONSTANTS_JSON
    assert LEASE_QNT.is_file(), LEASE_QNT


def test_the_model_declares_integer_constants_the_regex_can_see() -> None:
    """A guard on the guard: a reformat that hid every constant would otherwise
    turn this whole module into a set of vacuous passes."""
    assert len(_model_int_constants()) >= 12


# --- check 1: every JSON constant is mirrored or explicitly excused ----------


def test_every_json_constant_is_mirrored_or_listed_as_not_modelled() -> None:
    model = _model_int_constants()
    unaccounted = [
        key for key in _json_constants() if key not in model and key not in NOT_MODELLED
    ]
    assert unaccounted == [], (
        "exe/lease-constants.json declares constants that exe/spec/lease.qnt "
        "neither mirrors nor excuses. Mirror them as `pure val <key> = <n>`, or "
        f"add them to NOT_MODELLED with a reason: {unaccounted}"
    )


def test_not_modelled_only_lists_keys_that_really_are_absent() -> None:
    """A stale excuse is worse than none: it hides a constant that IS mirrored
    and therefore IS subject to the equality check below."""
    model = _model_int_constants()
    stale = sorted(key for key in NOT_MODELLED if key in model)
    assert stale == [], f"NOT_MODELLED excuses constants the model does mirror: {stale}"


def test_not_modelled_only_lists_keys_the_json_actually_has() -> None:
    declared = _json_constants()
    unknown = sorted(key for key in NOT_MODELLED if key not in declared)
    assert unknown == [], f"NOT_MODELLED names keys the JSON does not have: {unknown}"


def test_every_not_modelled_key_carries_a_reason() -> None:
    assert all(reason.strip() for reason in NOT_MODELLED.values())


# --- check 2: the mirrored values are equal ---------------------------------


def test_mirrored_constants_have_equal_values() -> None:
    declared = _json_constants()
    model = _model_int_constants()
    mismatches = {
        key: (declared[key], model[key])
        for key in declared
        if key in model and declared[key] != model[key]
    }
    assert mismatches == {}, (
        "exe/spec/lease.qnt disagrees with exe/lease-constants.json "
        f"(key: (json, qnt)): {mismatches}"
    )


def test_the_mirror_covers_every_number_the_json_declares() -> None:
    """Spelled out as an exact set, so a new constant cannot slip in as 'covered
    by the loop above' while nothing in the model reads it."""
    declared = _json_constants()
    model = _model_int_constants()
    mirrored = {key for key in declared if key in model}
    assert mirrored == set(declared) - set(NOT_MODELLED)


def test_every_mirrored_constant_is_a_plain_integer_in_the_json() -> None:
    """`pure val x = 3` can only mirror a JSON integer. A key that became a
    string or an object must go through NOT_MODELLED, not through a silent
    type coercion."""
    declared = _json_constants()
    model = _model_int_constants()
    for key in model.keys() & declared.keys():
        value = declared[key]
        assert isinstance(value, int) and not isinstance(value, bool), (key, value)


# --- check 3: the cap formula, re-derived ------------------------------------


def test_the_cap_formula_holds_in_the_json() -> None:
    """nightly_cap = l3_stop_hour - (l1_tick + ceiling + l2_tick + slack) / 60.

    With the committed numbers: 04:00 - (1 + 30 + 10 + 19) minutes = 03:00.
    Recomputed here rather than compared against the stored 3.
    """
    gap_minutes = (
        _json_int("l1_tick_minutes")
        + _json_int("drain_ceiling_minutes")
        + _json_int("l2_tick_minutes")
        + _json_int("slack_minutes")
    )
    assert gap_minutes % 60 == 0, (
        "the cap gap must be a whole number of hours for the cap to be "
        f"expressible as a local hour, got {gap_minutes} minutes"
    )
    assert _json_int("nightly_cap_local_hour") == _json_int(
        "l3_daily_stop_local_hour"
    ) - (gap_minutes // 60)


def test_the_cap_formula_holds_in_the_model_too() -> None:
    """The same derivation over the model's own mirrored copies. If the mirror
    is equal (check 2) this cannot fail on its own -- which is the point: it
    fails only when the mirror has drifted, and then it says why.
    """
    m = _model_int_constants()
    gap_minutes = (
        m["l1_tick_minutes"]
        + m["drain_ceiling_minutes"]
        + m["l2_tick_minutes"]
        + m["slack_minutes"]
    )
    assert gap_minutes % m["minutes_per_hour"] == 0, gap_minutes
    assert m["nightly_cap_local_hour"] == m["l3_daily_stop_local_hour"] - (
        gap_minutes // m["minutes_per_hour"]
    )


def test_the_model_derives_the_cap_gap_rather_than_storing_it() -> None:
    """cap_gap_minutes and nightly_cap_from_formula must be expressions over the
    four latency terms, never integer literals -- an invariant that compares a
    stored 60 with a stored 3 proves nothing.
    """
    text = LEASE_QNT.read_text(encoding="utf-8")
    for name in ("cap_gap_minutes", "nightly_cap_from_formula"):
        literal = re.search(
            rf"^\s*pure val\s+{name}\s*=\s*-?\d+\s*$", text, re.MULTILINE
        )
        assert literal is None, f"{name} is a stored literal; it must be derived"
        derived = re.search(rf"^\s*pure val\s+{name}\s*=\s*$", text, re.MULTILINE)
        assert derived is not None, f"{name} is not declared as a derived pure val"


def test_the_stored_cap_hour_is_read_exactly_once_by_the_model() -> None:
    """nightly_cap_local_hour may appear twice: its own declaration, and the one
    invariant clause that checks the re-derived value against it. A third use
    would mean something downstream trusts the stored number.
    """
    text = LEASE_QNT.read_text(encoding="utf-8")
    code = "\n".join(
        line
        for line in text.splitlines()
        if not line.lstrip().startswith(("//", "///"))
    )
    assert code.count("nightly_cap_local_hour") == 3, (
        "expected exactly three code occurrences of nightly_cap_local_hour "
        "(the declaration, the invariant's comparison, and the cap-instant test)"
    )


# --- the bound NodesEventuallyZero uses -------------------------------------


#: The two bounds NodesEventuallyZero holds the pool to, as the model must
#: derive them. The first is the plan's worst case, deadline + force_grace +
#: l2_tick, which assumes L2 can read lease.json; the second adds the L2 ticks
#: the three-strike rule forbids a stop on when it cannot. The Go reaper derives
#: the same two (lease.AwakeBound, lease.BlindAwakeBound) and pins them against
#: the JSON in constants_test.go.
_BOUND_DERIVATIONS: Final[dict[str, str]] = {
    "awake_bound_minutes": "force_grace_minutes + l2_tick_minutes",
    "blind_awake_bound_minutes": (
        "awake_bound_minutes + l2_tick_minutes * (lease_read_failure_threshold - 1)"
    ),
}


def test_the_model_derives_the_plans_bound_and_the_blind_one() -> None:
    """Each bound is a pure val over the mirrored constants, spelled exactly as
    above: a stored number could drift from the JSON by itself, and a
    different formula is a different guarantee.
    """
    text = LEASE_QNT.read_text(encoding="utf-8")
    for name, derivation in _BOUND_DERIVATIONS.items():
        match = re.search(
            rf"^\s*pure val\s+{name}\s*=\s*\n\s*(?P<expr>[^\n]+?)\s*$",
            text,
            re.MULTILINE,
        )
        assert match is not None, f"{name} is not declared as a derived pure val"
        assert match.group("expr") == derivation, (name, match.group("expr"))


def test_nodes_eventually_zero_uses_both_bounds() -> None:
    """The readable bound alone is a property about a subset of the reachable
    states (those where L2 can read the lease); the blind bound alone is looser
    than the plan promises. The invariant needs both.
    """
    text = LEASE_QNT.read_text(encoding="utf-8")
    invariant = re.search(
        r"^\s*val NodesEventuallyZero = and \{(?P<body>.*?)^\s*\}",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert invariant is not None, "NodesEventuallyZero is not an and-block"
    for name in _BOUND_DERIVATIONS:
        assert name in invariant.group("body"), name
    assert "termination_bound_minutes" not in text, "the old, wider bound is back"


def test_the_awake_window_bound_fits_inside_the_cap_gap() -> None:
    """The readable-lease bound has to fit in the gap the cap reserves, or L3
    could land on a pool L2 was still entitled to be waiting on.
    """
    gap_minutes = (
        _json_int("l1_tick_minutes")
        + _json_int("drain_ceiling_minutes")
        + _json_int("l2_tick_minutes")
        + _json_int("slack_minutes")
    )
    assert (
        _json_int("force_grace_minutes") + _json_int("l2_tick_minutes") <= gap_minutes
    )


# --- shape of the source of truth -------------------------------------------


def test_the_json_names_one_writer_per_object() -> None:
    """The one-writer rule is what the model encodes structurally; the JSON is
    where the rule is declared, so a fourth object or a shared writer has to
    show up here first.
    """
    document = json.loads(CONSTANTS_JSON.read_text(encoding="utf-8"))
    writers = document["_writers"]
    assert set(writers) == {"lease.json", "drain.json", "enforce.json"}
    assert len(set(writers.values())) == len(writers), writers


def test_the_json_points_at_the_model_it_is_mirrored_into() -> None:
    document = json.loads(CONSTANTS_JSON.read_text(encoding="utf-8"))
    assert "exe/spec/lease.qnt" in document["_source_of_truth"]
