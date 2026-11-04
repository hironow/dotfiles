"""Every difference the corpora record between the old scripts and the
agent-hook binary has a kind and a reason.

The owner decided (2026-11-04) that the binary fixes the old scripts' bugs, and
that the tests keep those fixes apart from the faithful port. So every ID a
corpus uses is in REGISTRY, and the "fixed" kind holds exactly the places where
the binary differs from the old scripts on purpose, because they had a bug:

- fixed-<name>: a named edit to an old script (scripts/old_script_fixes.py);
- path-relative, rtk-answer-unreadable: fixes the binary made before the
  edits existed (PR 2c), still recorded under their own IDs;
- BINARY_ONLY: fixes with no old-script counterpart, so no corpus holds them;
  each is tested in the Go test named beside it.

The Go corpus tests name each subtest by the same IDs ("parity" for none), so
`go test -run '/fixed-'` lists the fixed places.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import old_script_fixes

CORPORA = ROOT / "tools/agent-hooks/internal"

# Each ID, by kind: "fixed" (an old bug the binary fixes), "policy" (a decided
# change), "limit" (the reference's own limits), "noise" (diagnostics the
# binary does not reproduce).
REGISTRY: dict[str, tuple[str, str]] = {
    "unreadable": (
        "policy",
        "input that is not one JSON value: the guards block it, rtk and the formatter pass (PR 2b)",
    ),
    "reference-limit": (
        "limit",
        "past a reference's own limit (jq's nesting, Python's 4,300-digit integers): answered as the base",
    ),
    "pass-diagnostic": (
        "noise",
        "the script passed while printing diagnostics: the binary passes silently",
    ),
    "nul-warning": ("noise", "bash warned that it dropped a NUL: the binary does not"),
    "path-relative": (
        "fixed",
        "a program found through a relative PATH entry is not run (PR 2c)",
    ),
    "rtk-answer-unreadable": (
        "fixed",
        "rtk's answer that is not one JSON value is not forwarded (PR 2c)",
    ),
} | {
    f"fixed-{name}": ("fixed", fix.bug) for name, fix in old_script_fixes.FIXES.items()
}

# The binary's fixes that no old script can show: each ID, its bug, and the Go
# test that holds it (its file and function).
BINARY_ONLY: dict[str, tuple[str, str, str]] = {
    "fixed-guard-failure": (
        (
            "a guard that panicked let the call go on, as the old Python guard's own "
            "exceptions did (exit 1, which Claude and Codex let through)"
        ),
        "tools/agent-hooks/internal/launch/panic_test.go",
        "TestFixedGuardFailureBlocks",
    ),
}
REGISTRY |= {name: ("fixed", bug) for name, (bug, _, _) in BINARY_ONLY.items()}


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _differences() -> dict[str, set[str]]:
    """Every difference each corpus records, by corpus."""
    found: dict[str, set[str]] = {}
    commands = _lines(CORPORA / "guardcorpus/command-guard.jsonl")
    found["command-guard.jsonl"] = {entry["difference"] for entry in commands}
    files = _lines(CORPORA / "guardcorpus/files-guard.jsonl")
    found["files-guard.jsonl"] = {
        entry[flavor].get("difference", "")
        for entry in files
        for flavor in ("bsd", "gnu")
    }
    payloads = _lines(CORPORA / "guardcorpus/payloads.jsonl")
    found["payloads.jsonl"] = {
        run["difference"] for entry in payloads for run in entry["runs"]
    }
    for name in ("rtk.jsonl", "formatter.jsonl"):
        scenarios = _lines(CORPORA / "toolhookcorpus" / name)
        found[name] = {
            run["difference"] for scenario in scenarios for run in scenario["runs"]
        }
    return found


def test_every_difference_in_every_corpus_is_registered() -> None:
    for corpus, differences in _differences().items():
        for difference in differences - {""}:
            for part in difference.split("+"):
                assert part in REGISTRY, f"{corpus}: {part!r} is not in REGISTRY"


def test_the_fixed_kind_holds_every_fix_and_nothing_else() -> None:
    fixed = {name for name, (kind, _) in REGISTRY.items() if kind == "fixed"}
    named = {f"fixed-{name}" for name in old_script_fixes.FIXES}
    assert named <= fixed
    assert (
        fixed - named == {"path-relative", "rtk-answer-unreadable"} | BINARY_ONLY.keys()
    )
    for name, (kind, reason) in REGISTRY.items():
        assert kind in {"fixed", "policy", "limit", "noise"}, name
        assert reason, name


def test_every_named_fix_is_earned_somewhere() -> None:
    # A fix no corpus input needs would be a fix nothing tests.
    used = {
        part
        for differences in _differences().values()
        for difference in differences
        for part in difference.split("+")
    }
    for name in old_script_fixes.FIXES:
        assert f"fixed-{name}" in used, f"no corpus input needs fixed-{name}"


def test_every_named_fix_has_a_witness_of_its_own() -> None:
    # A run names the smallest set of fixes that gives its answer, the first
    # by name; a fix that only ever came with another would test nothing alone.
    alone = {
        part
        for differences in _differences().values()
        for difference in differences
        if len(parts := [p for p in difference.split("+") if p.startswith("fixed-")])
        == 1
        for part in parts
    }
    for name in old_script_fixes.FIXES:
        assert f"fixed-{name}" in alone, f"no corpus input needs fixed-{name} alone"


def _go_test_body(path: Path, function: str) -> str | None:
    """The body of a Go test function, if the file has it as one Go runs:
    `func TestXxx(t *testing.T) {` in a _test.go file, up to its closing }."""
    if not path.name.endswith("_test.go") or not re.fullmatch(
        r"Test[A-Z]\w*", function
    ):
        return None
    match = re.search(
        rf"^func {function}\(t \*testing\.T\) {{\n(.*?)^}}\n",
        path.read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else None


def test_every_binary_only_fix_is_in_its_go_test_and_in_no_corpus() -> None:
    used = {
        part
        for differences in _differences().values()
        for difference in differences
        for part in difference.split("+")
    }
    for name, (_, test, function) in BINARY_ONLY.items():
        body = _go_test_body(ROOT / test, function)
        assert body is not None, f"{test} has no test {function} that Go runs"
        assert name in body, f"{function} never names {name}"
        assert name not in used, f"{name} is binary-only, but a corpus holds it"


def test_a_go_test_counts_only_as_one_go_runs(tmp_path: Path) -> None:
    test = tmp_path / "x_test.go"
    test.write_text(
        "func TestA(t *testing.T) {\n\t// fixed-a\n}\n"
        "func B(t *testing.T) {\n\t// fixed-b\n}\n"
        "func TestC(t *testing.T) {\n}\n// fixed-c\n",
        encoding="utf-8",
    )
    assert "fixed-a" in (_go_test_body(test, "TestA") or "")
    assert _go_test_body(test, "B") is None  # Go does not run it
    assert "fixed-c" not in (_go_test_body(test, "TestC") or "")
    assert _go_test_body(tmp_path / "x.go", "TestA") is None
