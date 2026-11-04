"""The tool-hooks corpora still say what the old rtk and formatter scripts do.

tools/agent-hooks/internal/toolhookcorpus/{rtk,formatter}.jsonl are what the
agent-hook binary's rtk and formatter hooks are tested against
(docs/plan/agent-hooks-go.md). scripts/tool_hooks_corpus.py writes them by
running the old scripts with fake programs in a root built from scratch.

These tests catch a stale corpus, a run whose difference ID or expected
behavior does not follow from its legacy run, and a test of the old scripts
that no scenario (or Go test) mirrors. Rerunning the scripts needs bash 5,
jq, and Python 3.14; CI makes that check on 3.14 with
COMMAND_GUARD_CORPUS_STRICT set, where a skip would hide a failure.
"""

import ast
import dataclasses
import json
import os
import shutil
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import command_guard_corpus
import tool_hooks_corpus

UNIT = Path(__file__).resolve().parent
GO_RTK_TESTS = (
    tool_hooks_corpus.ROOT / "tools/agent-hooks/internal/rtkpolicy/policy_test.go"
)
# The tests of the old scripts. A subprocess test is mirrored by a scenario;
# a test of the rtk scripts' Python functions by a scenario or a Go test that
# names it.
MIRRORED_BY_SCENARIOS = ("test_rtk_hook_wrapper.py", "test_format_after_edit_hook.py")
MIRRORED_BY_GO = ("test_rtk_hook_respond.py", "test_rtk_hook_codex.py")
NOT_PORTED = {
    "test_permission_decision_is_kept_when_policy_is_keep": "the RTK_HOOK_PERMISSION_DECISION=keep test seam: the strip is the policy",
    "test_keep_forwards_rtks_answer_as_it_is": "the same keep seam",
}

needs_the_scripts = pytest.mark.skipif(
    sys.platform == "win32"
    or shutil.which("bash") is None
    or shutil.which("jq") is None,
    reason="the old hook scripts need bash and jq (POSIX)",
)


def _entries(hook: str) -> list[dict]:
    lines = tool_hooks_corpus.CORPORA[hook].read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def _require_the_pinned_python() -> None:
    have = unicodedata.unidata_version
    if have == command_guard_corpus.PYTHON_UNICODE:
        return
    message = (
        f"this Python has Unicode {have}; the corpus follows "
        f"{command_guard_corpus.PYTHON_UNICODE} (Python 3.14)"
    )
    if os.environ.get("COMMAND_GUARD_CORPUS_STRICT"):
        pytest.fail(message)
    pytest.skip(message)


def _scenarios() -> dict[str, tool_hooks_corpus.Scenario]:
    return {
        s.name: s
        for s in tool_hooks_corpus.rtk_scenarios()
        + tool_hooks_corpus.formatter_scenarios()
    }


@needs_the_scripts
def test_the_corpora_are_what_the_scripts_do_now() -> None:
    _require_the_pinned_python()
    # given what the scripts do now
    now = tool_hooks_corpus.render()
    for hook, entries in now.items():
        committed = _entries(hook)
        # then each corpus holds the same scenarios with the same runs
        assert [e["name"] for e in committed] == [e["name"] for e in entries], (
            f"{hook}.jsonl: run `just tool-hooks-corpus`"
        )
        for written, current in zip(committed, entries, strict=True):
            assert written == current, (
                f"{hook}.jsonl: stale scenario {current['name']}: run `just tool-hooks-corpus`"
            )


def test_every_run_follows_from_its_legacy_run() -> None:
    scenarios = _scenarios()
    for hook in tool_hooks_corpus.CORPORA:
        entries = {e["name"]: e for e in _entries(hook)}
        for entry in entries.values():
            scenario = scenarios[entry["name"]]
            for run in entry["runs"]:
                base = None
                if entry["base"]:
                    base = next(
                        r
                        for r in entries[entry["base"]]["runs"]
                        if r["harness"] == run["harness"]
                    )
                legacy = dict(run["legacy"])
                if legacy["stderr"] == "<diagnostic>":
                    legacy["stderr"] = (
                        "x"  # the rtk scripts' own stderr, kept as a flag
                    )
                difference, expected = tool_hooks_corpus.classify(
                    scenario, run["harness"], legacy, base
                )
                assert (run["difference"], run["expectedGo"]) == (
                    difference,
                    expected,
                ), (
                    f"{hook}.jsonl {entry['name']} {run['harness']}: the difference or "
                    "expectedGo does not follow from the legacy run: run `just tool-hooks-corpus`"
                )


def _test_functions(name: str) -> list[str]:
    tree = ast.parse((UNIT / name).read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def test_every_test_of_the_old_scripts_is_mirrored() -> None:
    mirrored = {
        m
        for hook in tool_hooks_corpus.CORPORA
        for e in _entries(hook)
        for m in e["mirrors"]
    }
    go_tests = GO_RTK_TESTS.read_text(encoding="utf-8")
    missing = []
    for name in MIRRORED_BY_SCENARIOS:
        missing += [
            t
            for t in _test_functions(name)
            if t not in mirrored and t not in NOT_PORTED
        ]
    for name in MIRRORED_BY_GO:
        missing += [
            t
            for t in _test_functions(name)
            if t not in mirrored
            and f'"{t}"' not in go_tests
            and f"// {t}" not in go_tests
            and t not in NOT_PORTED
        ]
    assert not missing, f"tests no scenario or Go test mirrors: {missing}"
    assert set(NOT_PORTED) <= {
        t
        for name in MIRRORED_BY_SCENARIOS + MIRRORED_BY_GO
        for t in _test_functions(name)
    }, "NOT_PORTED names a test that is gone"


def test_the_corpora_hold_every_difference() -> None:
    differences = {
        run["difference"]
        for hook in tool_hooks_corpus.CORPORA
        for entry in _entries(hook)
        for run in entry["runs"]
    }
    assert differences == set(tool_hooks_corpus.DIFFERENCES)


def test_a_rtk_deny_stays_a_deny_for_codex() -> None:
    # The Codex script forwards rtk's whole answer; only the command changes.
    entry = next(e for e in _entries("rtk") if e["name"] == "rtk-deny")
    codex = next(r for r in entry["runs"] if r["harness"] == "codex")
    answer = json.loads(codex["expectedGo"]["stdout"])
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_formatter_reports_bodies_whole_even_where_bash_rebuilt_the_warning() -> (
    None
):
    entry = next(
        e
        for e in _entries("formatter")
        if e["name"] == "py-nul-rebuilds-the-warning-text"
    )
    for run in entry["runs"]:
        assert run["difference"] == "nul-warning"
        assert "ignored null byte in input\nreal issue\n" in run["expectedGo"]["stderr"]


def test_a_derived_scenario_is_its_base_plus_one_unused_integer() -> None:
    scenarios = _scenarios()
    derived = [s for s in scenarios.values() if s.base]
    assert derived, "no derived scenario"
    for scenario in derived:
        tool_hooks_corpus.check_derived(scenario, scenarios[scenario.base])
    # A scenario that is not its base plus an integer cannot take its base's
    # expected behavior: here the veto would have become the base's rewrite.
    veto = dataclasses.replace(scenarios["veto"], base="rewrite")
    with pytest.raises(ValueError, match="not its base"):
        tool_hooks_corpus.check_derived(veto, scenarios["rewrite"])
    limit = scenarios["integer-4301-digits"]
    for payload in (
        limit.payload.replace(b'"x":9', b'"x":"9'),
        limit.payload.replace(b'"x":9', b'"y":9'),
        limit.payload + b" ",
    ):
        with pytest.raises(ValueError, match="not its base"):
            tool_hooks_corpus.check_derived(
                dataclasses.replace(limit, payload=payload), scenarios[limit.base]
            )
    with pytest.raises(ValueError, match="not its base"):
        tool_hooks_corpus.check_derived(
            dataclasses.replace(limit, cwd=tool_hooks_corpus.WORKTREE),
            scenarios[limit.base],
        )


def test_a_notice_body_that_looks_like_jq_is_kept_whole() -> None:
    entry = next(
        e for e in _entries("formatter") if e["name"] == "py-notice-body-looks-like-jq"
    )
    for run in entry["runs"]:
        assert "jq: ordinary notice body\n" in run["legacy"]["stderr"]
        assert run["expectedGo"]["stderr"].endswith("jq: ordinary notice body\n")
