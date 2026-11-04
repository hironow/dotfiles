"""The payload corpus still says what the old hook scripts do.

tools/agent-hooks/internal/guardcorpus/payloads.jsonl is what the agent-hook
binary is tested against (docs/plan/agent-hooks-go.md):
every payload run through every old hook script as Claude Code and Codex run
them, with the answer the binary must give (expectedGo) and a difference ID
that says why the two may differ. scripts/hook_payload_corpus.py writes it.

These tests catch a stale corpus, and an entry whose difference ID or
expected answer does not follow from its legacy run: no run can be moved into
a tolerance by hand. Rerunning the scripts needs Python 3.14 (the command
guard's Unicode tables); CI makes that check on 3.14 with
COMMAND_GUARD_CORPUS_STRICT set, where a skip would hide a failure.
"""

import json
import os
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import command_guard_corpus
import hook_payload_corpus
import old_script_fixes

needs_the_scripts = pytest.mark.skipif(
    sys.platform == "win32"
    or shutil.which("bash") is None
    or shutil.which("jq") is None,
    reason="the old hook scripts need bash and jq (POSIX)",
)


def _entries() -> list[dict]:
    lines = hook_payload_corpus.CORPUS.read_text(encoding="utf-8").splitlines()
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


def _key(run: dict) -> tuple[str, str, str]:
    return run["harness"], run["hook"], run.get("basename", "")


@needs_the_scripts
def test_the_corpus_is_what_the_scripts_say_now() -> None:
    _require_the_pinned_python()
    # given what the scripts do now, under each basename flavor this machine has
    flavors = hook_payload_corpus.file_guards_corpus.basename_flavors()
    assert flavors, "no basename(1) found"
    now = hook_payload_corpus.render(flavors)
    committed = _entries()
    # then the corpus has the same payloads, in the same order
    assert [(e["name"], hook_payload_corpus.unstored_stdin(e)) for e in committed] == [
        (e["name"], hook_payload_corpus.unstored_stdin(e)) for e in now
    ], "run `just hook-payload-corpus`"
    # and, for each run this machine can make, the same record
    for written, current in zip(committed, now, strict=True):
        runs = {_key(run): run for run in written["runs"]}
        for run in current["runs"]:
            assert runs.get(_key(run)) == run, (
                f"payloads.jsonl: stale run {_key(run)} of {current['name']}: "
                "run `just hook-payload-corpus`"
            )


@needs_the_scripts
def test_the_callers_python_settings_do_not_reach_the_scripts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # given a caller whose PYTHONPATH shadows json, and whose Python reads
    # integers of any length or of fewer digits
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    (shadow / "json.py").write_text("raise SystemExit(7)\n", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(shadow))
    payload = next(
        p
        for p in hook_payload_corpus.limit_payloads()
        if p.name == "integer-4301-digits-block-all"
    )
    tools = hook_payload_corpus.make_tools(tmp_path / "tools", None)
    exits = set()
    for digits in ("0", "640", "4300"):
        monkeypatch.setenv("PYTHONINTMAXSTRDIGITS", digits)
        run = hook_payload_corpus.run_script(
            "claude", "command-guard", payload.stdin, tools
        )
        exits.add(run["exit"])
    # then the command guard's script raises on the 4,301 digits every time
    assert exits == {1}


def test_every_run_follows_from_its_legacy_run() -> None:
    # given each run's legacy record, its payload, and its base's run, if any
    entries = _entries()
    by_name = {entry["name"]: entry for entry in entries}
    for entry in entries:
        stdin = hook_payload_corpus.unstored_stdin(entry)
        base_runs = {}
        if "base" in entry:
            base_runs = {_key(run): run for run in by_name[entry["base"]]["runs"]}
        for run in entry["runs"]:
            base = base_runs.get(_key(run)) if base_runs else None
            # then the difference ID and the binary's answer follow from them
            difference, expected = hook_payload_corpus.classify(
                run["harness"], stdin, run["legacy"], base
            )
            if "fixed" not in run:
                assert (run["difference"], run["expectedGo"]) == (
                    difference,
                    expected,
                ), (
                    f"{entry['name']} {_key(run)}: the difference or expectedGo does not "
                    "follow from the legacy run: run `just hook-payload-corpus`"
                )
                continue
            # or, where the fixed script answers apart from the old one, from
            # the run of the fixed script, the reference: its noise always,
            # and fixes exactly when its answer differs from the old one
            full_difference, full_expected = hook_payload_corpus.classify(
                run["harness"], stdin, run["fixed"], None
            )
            fixes = [
                part.removeprefix("fixed-")
                for part in run["difference"].split("+")
                if part.startswith("fixed-")
            ]
            where = f"{entry['name']} {_key(run)}"
            if fixes:
                assert full_expected != expected, f"{where}: the fixes change nothing"
            else:
                assert full_expected == expected, (
                    f"{where}: an answer changed with no fix named"
                )
            assert run["expectedGo"] == full_expected, where
            assert run["difference"] == old_script_fixes.difference(
                fixes, full_difference
            ), where


def test_the_reference_is_the_fixed_script_even_where_only_noise_differs() -> None:
    # file_path "-1": the old guard's basename failed, so it passed with a
    # diagnostic; the fixed guard passes silently. The answers agree, so no
    # fix is needed, but the noise is the fixed script's: none.
    entry = next(e for e in _entries() if e["name"] == "field-file-path-negative")
    runs = [run for run in entry["runs"] if run["hook"] == "files-guard"]
    assert runs
    for run in runs:
        assert run["legacy"]["exit"] == 1, _key(run)
        assert "fixed" in run, _key(run)
        assert run["difference"] == "", _key(run)


def test_a_reason_that_quotes_bashs_warning_is_kept_whole() -> None:
    # given the command guard's blocks whose reason quotes bash's NUL warning
    entries = {entry["name"]: entry for entry in _entries()}
    for name in (
        "order-warning-quoted-in-reason",
        "order-script-warning-quoted-in-reason",
    ):
        for run in entries[name]["runs"]:
            if run["hook"] != "command-guard":
                continue
            # then nothing is taken off it: the binary must give the whole answer
            assert hook_payload_corpus.blocks(run["harness"], run["legacy"])
            assert run["difference"] == "", (name, run["harness"])
            legacy = {key: run["legacy"][key] for key in ("exit", "stdout", "stderr")}
            assert run["expectedGo"] == legacy, (name, run["harness"])


def test_a_derived_payload_is_its_base_and_one_unused_member() -> None:
    entries = _entries()
    by_name = {entry["name"]: entry for entry in entries}
    derived = [entry for entry in entries if "base" in entry]
    assert len(derived) >= 6
    for entry in derived:
        stdin = hook_payload_corpus.unstored_stdin(entry)
        base = hook_payload_corpus.unstored_stdin(by_name[entry["base"]])
        assert "base" not in by_name[entry["base"]]
        assert stdin.startswith(base[:-1]), entry["name"]
        assert re.fullmatch(rb',"x":[\[\]0-9]+\}', stdin[len(base) - 1 :]), entry[
            "name"
        ]


def test_every_input_the_guard_tests_use_is_in_the_corpus() -> None:
    # given the payloads the guards' own tests feed them, wrapped as they wrap them
    tests = hook_payload_corpus.test_payloads()
    # (the minimums of the command and file guard corpora's own checks)
    for kind, least in (("command", 80), ("patch", 10), ("content", 20)):
        found = [p for p in tests if p.name.startswith(f"test-{kind}-")]
        assert len(found) >= least, f"the guard tests changed shape: {kind} inputs"
    # then the corpus holds each one
    stdins = {hook_payload_corpus.unstored_stdin(entry) for entry in _entries()}
    missing = [payload.name for payload in tests if payload.stdin not in stdins]
    assert not missing, f"not in the corpus: {missing}: run `just hook-payload-corpus`"


def test_the_corpus_holds_every_difference_and_the_flavors_apart() -> None:
    entries = _entries()
    parts = {
        part
        for entry in entries
        for run in entry["runs"]
        for part in run["difference"].split("+")
    }
    fixes = {
        f"fixed-{name}"
        for names in hook_payload_corpus.HOOK_FIXES.values()
        for name in names
    }
    assert parts == set(hook_payload_corpus.DIFFERENCES) | fixes
    # where BSD's and GNU's basename(1) part ways, the old guard's answers
    # differ; fixed (fixed-dash-line), the guard needs no basename, and the
    # binary's answer is the same under both
    help_then_yml = next(e for e in entries if e["name"] == "dash-path-0")
    runs = {
        run["basename"]: run
        for run in help_then_yml["runs"]
        if run["harness"] == "claude" and run["hook"] == "files-guard"
    }
    assert {flavor: run["legacy"]["exit"] for flavor, run in runs.items()} == {
        "bsd": 1,
        "gnu": 2,
    }
    assert {flavor: run["expectedGo"]["exit"] for flavor, run in runs.items()} == {
        "bsd": 2,
        "gnu": 2,
    }
    assert {flavor: run["difference"] for flavor, run in runs.items()} == {
        "bsd": "fixed-dash-line",
        "gnu": "",
    }
    # and a blocking payload made unreadable blocks today in every script
    nan = next(e for e in entries if e["name"] == "unreadable-nan-block-all")
    assert all(
        hook_payload_corpus.blocks(r["harness"], r["legacy"]) for r in nan["runs"]
    )


def _nested(levels: int) -> bytes:
    """A payload with this many levels of nesting in all."""
    return b'{"x":' + b"[" * (levels - 1) + b"1" + b"]" * (levels - 1) + b"}"


def test_the_strict_reader_reads_as_deep_as_the_binary() -> None:
    # Python 3.12's json stops near 1,500 levels; 3.14's reads past 20,000.
    _require_the_pinned_python()
    assert hook_payload_corpus.readable(_nested(10_000))
    assert not hook_payload_corpus.readable(_nested(10_001))


@pytest.mark.parametrize(
    ("stdin", "readable"),
    [
        (b'{"tool_input":{"command":"ls"}}', True),
        (b'{"x":' + b"9" * 4301 + b"}", True),
        (b'{"x":1e400}', True),
        (b'{"x":"\\ud83d\\ude00"}', True),
        (b'{"x":"\\uffff"}', True),
        (b"[1]", True),
        (_nested(255), True),
        (b"", False),
        (b" ", False),
        (b'{"x":NaN}', False),
        (b'{"x":-Infinity}', False),
        (b"\xef\xbb\xbf{}", False),
        (b'{"x":1,"x":2}', False),
        (b'{"x":1,"\\u0078":2}', False),
        (b'{"x":[{"y":1,"y":2}]}', False),
        (b'{"x":"\\ud800"}', False),
        (b'{"\\udc00":1}', False),
        (b'{"x":"\xff"}', False),
        (b'{"x":"\x00"}', False),
        (b'{"x":1} x', False),
        (b"{}{}", False),
    ],
)
def test_the_strict_reader_reads_what_the_binary_reads(
    stdin: bytes, readable: bool
) -> None:
    assert hook_payload_corpus.readable(stdin) is readable
