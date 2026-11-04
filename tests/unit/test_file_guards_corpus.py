"""The file and secrets guard corpora still say what the shell guards do.

tools/agent-hooks/internal/guardcorpus/files-guard.jsonl and secrets-guard.jsonl
are what the agent-hook Go port of the two guards is tested against
(docs/plan/agent-hooks-go.md). scripts/file_guards_corpus.py writes them by
running the shell guards, so they drift apart only when someone changes a guard
or its tests and forgets `just file-guards-corpus`. These tests catch that.

The files corpus holds the guard's results under BSD and under GNU basename(1).
A machine checks the flavors it has: macOS both (with gbasename), Linux GNU's.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import file_guards_corpus
import old_script_fixes

pytestmark = pytest.mark.skipif(
    sys.platform == "win32"
    or shutil.which("bash") is None
    or shutil.which("jq") is None,
    reason="the shell guards need bash and jq (POSIX)",
)


def _entries(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _input(entry: dict) -> tuple[str, str]:
    """The (kind, text) an entry was made from, long inputs joined back."""
    return file_guards_corpus.unstored(entry)


def test_the_corpora_are_what_the_shell_guards_say_now() -> None:
    # given what the guards do now, under each basename flavor this machine has
    flavors = file_guards_corpus.basename_flavors()
    assert flavors, "no basename(1) found"
    files, secrets = file_guards_corpus.render(flavors)
    committed_files = _entries(file_guards_corpus.FILES_CORPUS)
    # then the files corpus has the same inputs and, for each flavor here, results
    assert [_input(e) for e in committed_files] == [_input(e) for e in files], (
        "run `just file-guards-corpus`"
    )
    for written, now in zip(committed_files, files, strict=True):
        for flavor in flavors:
            assert written[flavor] == now[flavor], (
                f"files-guard.jsonl: stale {flavor} result for {_input(now)!r}: "
                "run `just file-guards-corpus`"
            )
        # and the fixed guard's answer, which no flavor changes
        assert written.get("fixed") == now.get("fixed"), (
            f"files-guard.jsonl: stale fixed result for {_input(now)!r}: "
            "run `just file-guards-corpus`"
        )
    # and the secrets corpus is what the secrets guard says
    committed_secrets = _entries(file_guards_corpus.SECRETS_CORPUS)
    for written, now in zip(committed_secrets, secrets, strict=False):
        assert written == now, (
            f"secrets-guard.jsonl: stale entry {now!r}: run `just file-guards-corpus`"
        )
    assert len(committed_secrets) == len(secrets), "run `just file-guards-corpus`"


def test_every_input_the_guard_tests_use_is_in_the_corpora() -> None:
    # given the inputs the guards' own tests are parametrized with
    tests = file_guards_corpus.fixtures()
    assert len(tests["patch"]) >= 10 and len(tests["content"]) >= 20, (
        "the guard tests changed shape: update file_guards_corpus.fixtures"
    )
    files = _entries(file_guards_corpus.FILES_CORPUS)
    secrets = _entries(file_guards_corpus.SECRETS_CORPUS)
    # then each guard's corpus holds them
    file_inputs = {_input(e) for e in files}
    secret_inputs = {_input(e) for e in secrets}
    assert {("patch", text) for text in tests["patch"]} <= file_inputs
    assert {("patch", text) for text in tests["patch"]} <= secret_inputs
    assert {("content", text) for text in tests["content"]} <= secret_inputs


def test_the_large_writes_are_in_the_secrets_corpus() -> None:
    # given the 1 MiB writes the secrets guard's tests pin (#536)
    large = [
        text for text in file_guards_corpus.fixtures()["content"] if len(text) > 1 << 20
    ]
    assert len(large) == 3, "expected the three 1 MiB writes of test_block_secrets_hook"
    # then the corpus holds each, stored as runs, with the guard blocking it
    secrets = {_input(e): e for e in _entries(file_guards_corpus.SECRETS_CORPUS)}
    for text in large:
        entry = secrets[("content", text)]
        assert "contentRuns" in entry
        assert entry["exit"] == 2


def test_the_corpora_hold_every_kind_of_result() -> None:
    files = _entries(file_guards_corpus.FILES_CORPUS)
    secrets = _entries(file_guards_corpus.SECRETS_CORPUS)
    for flavor in ("bsd", "gnu"):
        reasons = [e[flavor]["reason"] for e in files if e[flavor]["reason"]]
        assert any("is the deprecated Compose v1 name" in r for r in reasons)
        assert any("uses '.yml'" in r for r in reasons)
        # the guard also passes, and fails without blocking (exit 1), somewhere
        assert {e[flavor]["exit"] for e in files} >= {0, 1, 2}
    # where the flavors part: GNU reads on past --help, BSD stops there
    assert any(e["bsd"] != e["gnu"] for e in files)
    assert any(e["reason"] for e in secrets)
    assert {e["exit"] for e in secrets} >= {0, 2}


def test_a_reason_that_holds_blocked_is_kept_whole() -> None:
    # The reason names the file, so it can hold "BLOCKED: " itself; it is read
    # from the first one, after any known diagnostic, and kept whole.
    result = file_guards_corpus.run_guard(
        file_guards_corpus.FILES_GUARD, "filePath", "BLOCKED: x.yml"
    )
    assert result == {
        "exit": 2,
        "reason": "'BLOCKED: x.yml' uses '.yml'. This project uses '.yaml' exclusively. "
        "Rename to 'BLOCKED: x.yaml'.",
    }


def test_the_files_corpus_records_the_old_guards_bugs_and_their_fixes() -> None:
    # A line that starts with "-" stopped the old guard under both flavors;
    # fixed, the line after it, or the line itself, blocks.
    entries = {_input(e): e for e in _entries(file_guards_corpus.FILES_CORPUS)}
    for kind, text in [
        ("filePath", "ok\n--bogus\nbad.yml"),
        ("filePath", "--x.yml"),
        ("patch", file_guards_corpus.patch("*** Add File: --x.yml\n+a: 1\n")),
    ]:
        entry = entries[(kind, text)]
        assert entry["fixed"]["exit"] == 2, entry
        for flavor in ("bsd", "gnu"):
            assert entry[flavor]["exit"] == 1, (flavor, entry)
            assert entry[flavor]["difference"] == "fixed-dash-line", (flavor, entry)


def test_every_difference_names_fixes_of_the_files_guard() -> None:
    # An entry holds the fixed guard's answer exactly when some flavor's old
    # answer differs from it, and each difference names fixes of this guard.
    names = {
        f"fixed-{name}"
        for name, fix in old_script_fixes.FIXES.items()
        if fix.script == old_script_fixes.FILES_GUARD
    }
    for entry in _entries(file_guards_corpus.FILES_CORPUS):
        differences = {entry[flavor].get("difference", "") for flavor in ("bsd", "gnu")}
        assert ("fixed" in entry) == (differences != {""}), entry
        for difference in differences - {""}:
            assert set(difference.split("+")) <= names, difference
