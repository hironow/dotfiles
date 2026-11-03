"""The command guard corpus still says what the Python command guard does.

tools/agent-hooks/internal/guardcorpus/command-guard.jsonl is what the agent-hook Go port
is tested against (docs/plan/agent-hooks-go.md). It is written from the Python
guard by scripts/command_guard_corpus.py, so the two can only drift apart when
someone changes the guard or its tests and forgets `just command-guard-corpus`.
These tests catch that.
"""

import json
import os
import re
import sys
import unicodedata
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import command_guard_corpus


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _require_the_pinned_unicode() -> None:
    """Skip a check another Python cannot make. CI runs these on Python 3.14 with
    COMMAND_GUARD_CORPUS_STRICT set, where a skip would hide a failure."""
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


def test_the_corpus_is_what_the_python_guard_says_now() -> None:
    _require_the_pinned_unicode()
    # given the committed corpus and what the reference makes of the same inputs
    committed = _lines(command_guard_corpus.CORPUS.read_text(encoding="utf-8"))
    current = _lines(command_guard_corpus.render())
    # then they agree line by line (the first difference names its input)
    for written, expected in zip(committed, current, strict=False):
        assert written == expected, (
            f"stale entry for {json.loads(expected)['input']!r}: "
            "run `just command-guard-corpus`"
        )
    assert len(committed) == len(current), "run `just command-guard-corpus`"


def test_every_command_the_guard_tests_use_is_in_the_corpus() -> None:
    # given every command the guard's own tests feed it
    fixtures = command_guard_corpus.fixture_commands()
    # then the extraction still finds them, and the corpus holds each one
    assert len(fixtures) >= 80, "the guard tests changed shape: update the extractor"
    lines = command_guard_corpus.CORPUS.read_text(encoding="utf-8").splitlines()
    inputs = {json.loads(line)["input"] for line in lines}
    assert set(fixtures) <= inputs


def test_every_reason_the_guard_gives_is_in_the_corpus() -> None:
    # given every block reason the guard can give
    reference = command_guard_corpus.load_reference()
    reasons = {
        reference.MSG_PIP,
        reference.MSG_NODE,
        reference.MSG_MAKE,
        reference.MSG_FORCE_PUSH,
        *(reason for _, reason in reference.RAW_GUARDS),
    }
    # then each one is the verdict of at least one entry (.yml reasons vary)
    lines = command_guard_corpus.CORPUS.read_text(encoding="utf-8").splitlines()
    given = {json.loads(line)["reason"] for line in lines}
    assert reasons <= given
    assert any(reason and reason.endswith(reference.MSG_YML) for reason in given)


def test_the_word_table_is_for_the_pinned_unicode() -> None:
    # given the committed table of Python's \w
    committed = command_guard_corpus.WORD_TABLE.read_text(encoding="utf-8")
    version = re.search(r'const pythonUnicodeVersion = "([^"]+)"', committed)
    # then it is for the Unicode version the port follows, on every Python
    assert version is not None
    assert version[1] == command_guard_corpus.PYTHON_UNICODE


def test_the_word_table_is_pythons() -> None:
    _require_the_pinned_unicode()
    # given the committed table, then it is what Python 3.14's re says \w is
    committed = command_guard_corpus.WORD_TABLE.read_text(encoding="utf-8")
    assert committed == command_guard_corpus.render_word_table(), (
        "run `just command-guard-corpus`"
    )
