"""sync-agents prints emoji; a native Windows console is cp932 by default.

main() reconfigures stdout and stderr to UTF-8 before it prints anything, so
`just sync-agents*` survives whatever the console's code page is. The run
starts a child Python with cp932 streams (PYTHONIOENCODING) and no bytecode
writes (-B), runs main() with `--help` (argparse prints the help and exits
before any sync touches a home), then prints emoji to both streams.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
EMOJI = "🔄 ⬅️ ⚠️"

PROGRAM = f"""
import sys
sys.path.insert(0, {str(SCRIPTS)!r})
import sync_agents
sys.argv = ["sync_agents.py", "--help"]
try:
    sync_agents.main()
except SystemExit as done:
    assert done.code == 0, done.code
print({EMOJI!r})
print({EMOJI!r}, file=sys.stderr)
"""


def test_main_reconfigures_stdout_to_utf8() -> None:
    env = {**os.environ, "PYTHONIOENCODING": "cp932"}
    done = subprocess.run(
        [sys.executable, "-B", "-c", PROGRAM],
        capture_output=True,
        env=env,
        check=False,
        timeout=60,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
    assert done.stdout.decode("utf-8").rstrip().endswith(EMOJI)
    assert done.stderr.decode("utf-8").rstrip().endswith(EMOJI)
