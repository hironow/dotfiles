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

from pathlib import Path

SYNC = Path(__file__).resolve().parents[2] / "scripts" / "sync_agents.py"


def test_main_reconfigures_stdout_to_utf8() -> None:
    """main() prints emoji; native Windows stdout is cp932 and raises
    UnicodeEncodeError on them. main() must reconfigure stdout/stderr to
    UTF-8 so `just sync-agents*` survives regardless of console code page."""
    src = SYNC.read_text(encoding="utf-8")
    assert 'reconfigure(encoding="utf-8")' in src, (
        "main() must reconfigure stdout/stderr to UTF-8 (emoji prints break on "
        "native Windows cp932 otherwise)"
    )
