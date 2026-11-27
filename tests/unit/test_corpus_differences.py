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
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import old_script_fixes
from _agent_hooks_go import STRICT_GO, why_go_cannot_build_the_module

CORPORA = ROOT / "tools/agent-hooks/internal"
REAL_GO = shutil.which("go")

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


def test_no_corpus_claims_a_binary_only_fix() -> None:
    used = {
        part
        for differences in _differences().values()
        for difference in differences
        for part in difference.split("+")
    }
    for name in BINARY_ONLY:
        assert name not in used, f"{name} is binary-only, but a corpus holds it"


def _offline_go_env(home: Path) -> dict[str, str]:
    """Run Go with its own home and build cache, using cached modules only."""
    why = why_go_cannot_build_the_module(REAL_GO, home)
    if why:
        if STRICT_GO:
            pytest.fail(why)
        pytest.skip(why)
    assert REAL_GO is not None
    modules = os.environ.get("GOMODCACHE") or str(Path.home() / "go" / "pkg" / "mod")
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "APPDATA": str(home / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(home / "AppData" / "Local"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_STATE_HOME": str(home / "state"),
        "GOCACHE": str(home / ".cache" / "go-build"),
        "GOMODCACHE": modules,
        "GOTOOLCHAIN": "local",
        "GOPROXY": "off",
        "GONOPROXY": "none",
        "GOSUMDB": "off",
    }
    done = subprocess.run(
        [REAL_GO, "-C", str(ROOT / "tools/agent-hooks"), "mod", "download"],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    if done.returncode:
        errors = done.stderr.splitlines()
        if errors and all(
            "module lookup disabled by GOPROXY=off" in line for line in errors
        ):
            why = f"offline Go module cache is incomplete: {done.stderr.strip()}"
            if STRICT_GO:
                pytest.fail(why)
            pytest.skip(why)
        pytest.fail(f"Go dependency check failed:\n{done.stdout}\n{done.stderr}")
    return env


@pytest.fixture(scope="module")
def go_env(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    return _offline_go_env(tmp_path_factory.mktemp("corpus-go-home"))


@pytest.mark.parametrize("name", BINARY_ONLY)
def test_every_binary_only_fix_runs_its_go_test(
    name: str, go_env: dict[str, str]
) -> None:
    assert REAL_GO is not None
    _, test, function = BINARY_ONLY[name]
    module = ROOT / "tools/agent-hooks"
    package = "./" + (ROOT / test).parent.relative_to(module).as_posix()
    done = subprocess.run(
        [
            REAL_GO,
            "-C",
            str(module),
            "test",
            "-count=1",
            "-json",
            "-run",
            f"^{re.escape(function)}$",
            package,
        ],
        env=go_env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    diagnostic = f"{name}: {function}\n{done.stdout}\n{done.stderr}"
    assert done.returncode == 0, diagnostic
    actions = [
        event.get("Action")
        for line in done.stdout.splitlines()
        if (event := json.loads(line)).get("Test") == function
    ]
    assert actions.count("run") == 1, diagnostic
    assert actions.count("pass") == 1 and "skip" not in actions, diagnostic


@pytest.mark.parametrize("strict", [False, True])
def test_an_empty_module_cache_is_reported_before_running_go_tests(
    strict: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    why = why_go_cannot_build_the_module(REAL_GO, tmp_path)
    if why:
        pytest.skip(why)
    modules = tmp_path / "modules"
    modules.mkdir()
    assert not list(modules.iterdir())
    monkeypatch.setenv("GOMODCACHE", str(modules))
    monkeypatch.setattr(sys.modules[__name__], "STRICT_GO", strict)
    outcome = pytest.fail.Exception if strict else pytest.skip.Exception
    with pytest.raises(outcome, match="offline Go module cache is incomplete"):
        _offline_go_env(tmp_path)
