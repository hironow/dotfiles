"""Guard: every text file I/O in sync_agents.py pins an explicit encoding.

`Path.read_text()` / `Path.write_text()` default to the platform's preferred
encoding. On Linux/macOS/CI that is UTF-8, so unencoded calls work there and
the bug is invisible; on native Windows it is cp932, so reading a UTF-8
instruction file with non-ASCII bytes raises
`UnicodeDecodeError: 'cp932' codec can't decode ...` and `just sync-agents*`
dies mid-run. This static (AST) guard catches a missing `encoding=` on ANY
platform, so the regression cannot slip back through Linux CI.
"""

from __future__ import annotations

import ast
from pathlib import Path

SYNC = Path(__file__).resolve().parents[2] / "scripts" / "sync_agents.py"
TEXT_IO = {"read_text", "write_text"}


def _unencoded_calls() -> list[tuple[int, str]]:
    tree = ast.parse(SYNC.read_text(encoding="utf-8"))
    bad: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in TEXT_IO:
            continue
        if not any(kw.arg == "encoding" for kw in node.keywords):
            bad.append((node.lineno, func.attr))
    return bad


def test_all_text_io_pins_encoding() -> None:
    bad = _unencoded_calls()
    assert not bad, (
        "sync_agents.py has read_text()/write_text() calls without an explicit "
        "encoding= (breaks on native Windows cp932): "
        + ", ".join(f"{attr}@L{line}" for line, attr in bad)
    )


def test_main_reconfigures_stdout_to_utf8() -> None:
    """main() prints emoji; native Windows stdout is cp932 and raises
    UnicodeEncodeError on them. main() must reconfigure stdout/stderr to
    UTF-8 so `just sync-agents*` survives regardless of console code page."""
    src = SYNC.read_text(encoding="utf-8")
    assert 'reconfigure(encoding="utf-8")' in src, (
        "main() must reconfigure stdout/stderr to UTF-8 (emoji prints break on "
        "native Windows cp932 otherwise)"
    )
