"""Every difference the corpora record between the old scripts and the
agent-hook binary has a kind and a reason.

The owner decided (2026-11-04) that the binary fixes the old scripts' bugs, and
that the tests keep those fixes apart from the faithful port. So every ID a
corpus uses is in REGISTRY, and the "fixed" kind holds exactly the places where
the binary differs from the old scripts on purpose, because they had a bug:

- fixed-<name>: a named edit to an old script (scripts/old_script_fixes.py);
- path-relative, rtk-answer-unreadable: fixes the binary made before the
  edits existed (PR 2c), still recorded under their own IDs.

The Go corpus tests name each subtest by the same IDs ("parity" for none), so
`go test -run '/fixed-'` lists the fixed places.
"""

import json
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


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _differences() -> dict[str, set[str]]:
    """Every difference each corpus records, by corpus."""
    found: dict[str, set[str]] = {}
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
    assert fixed - named == {"path-relative", "rtk-answer-unreadable"}
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
