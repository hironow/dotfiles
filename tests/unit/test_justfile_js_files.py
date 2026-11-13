"""`fmt`, `lint`, and `check` hand vp the same JS/TS files.

The three recipes used to spell the pathspec out on their own, so an exclusion
added to one (a vendored folder, say) could be missed in another and the gates
would disagree about which files are ours. One justfile variable holds the list.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"

_VP_LINE = re.compile(
    r"^\s+git ls-files -z (.+?) \| xargs -0 -r mise x -- vp (\w+)\s*$"
)


def _vp_lines() -> dict[str, str]:
    lines = {}
    for raw in JUSTFILE.read_text(encoding="utf-8").splitlines():
        match = _VP_LINE.match(raw)
        if match:
            lines[match.group(2)] = match.group(1)
    return lines


def test_every_vp_gate_reads_the_one_file_list() -> None:
    lines = _vp_lines()
    assert set(lines) == {"fmt", "lint", "check"}, lines
    assert all(spec == "{{ JS_FILES }}" for spec in lines.values()), lines


def test_the_file_list_is_declared_once() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    assert len(re.findall(r"^JS_FILES := ", text, re.MULTILINE)) == 1
    assert text.count("'*.mts' '*.cts'") == 1, "the pathspec is written out again"
