"""The doctor line protocol, written and read in one place.

Every checker prints `LEVEL name - detail` (LEVEL padded to four) and exits 1
on a WARN; scripts/doctor.sh counts the lines and ai_tools_check reads a
checker's output back. The format and the parse were spelled out in each
script; doctor_lines holds them, and these pin the exact bytes and the parse's
leniency (an odd line is read, never rejected).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import doctor_lines  # noqa: E402


@pytest.mark.parametrize(
    ("line", "text"),
    [
        (("OK", "rtk", "0.50.0 via mise"), "OK   rtk - 0.50.0 via mise"),
        (("WARN", "codex-hooks", "x - y"), "WARN codex-hooks - x - y"),
        (("ERR", "a", ""), "ERR  a - "),
    ],
)
def test_a_line_prints_as_doctor_counts_it(line: doctor_lines.Line, text: str) -> None:
    assert doctor_lines.fmt(line) == text


def test_printed_lines_read_back_as_written() -> None:
    lines = [("OK", "a", "b"), ("WARN", "c", "d - e")]
    text = "\n".join(doctor_lines.fmt(line) for line in lines)
    assert doctor_lines.parse(text) == lines


def test_an_odd_line_is_read_not_rejected() -> None:
    assert doctor_lines.parse("something else") == [("something", "else", "")]
    assert doctor_lines.parse("") == []


@pytest.mark.parametrize(
    ("levels", "failed"),
    [(["OK", "OK"], False), (["OK", "WARN"], True), (["ERR"], True), ([], False)],
)
def test_a_warn_or_err_is_a_failure(levels: list[str], failed: bool) -> None:
    assert doctor_lines.failed([(level, "n", "d") for level in levels]) is failed
