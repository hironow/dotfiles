"""Hook scripts run under macOS's /bin/bash 3.2, so they use no bash 4 syntax.

Claude Code and Codex start a hook with the first `bash` (or `sh`) on PATH; on
a Mac without Homebrew's bash that is 3.2. A bash 4 builtin there exits 127,
which no agent reads as a block, so a guard using one fails open: the command
guard's `mapfile` did (found in review).
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKS = sorted(ROOT.glob("ROOT_AGENTS_hooks_*.sh"))
BASH4 = {
    "mapfile": r"\bmapfile\b",
    "readarray": r"\breadarray\b",
    "associative array": r"\bdeclare\s+-A\b",
    "case conversion": r"\$\{\w+(,,|\^\^)",
    "&>> redirection": r"&>>",
    "|& pipe": r"\|&",
}


def test_there_are_hooks_to_check() -> None:
    assert HOOKS


@pytest.mark.parametrize("hook", HOOKS, ids=lambda path: path.name)
def test_a_hook_uses_no_bash4_syntax(hook: Path) -> None:
    code = [
        line
        for line in hook.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    ]
    found = [
        f"{name}: {line.strip()}"
        for line in code
        for name, pattern in BASH4.items()
        if re.search(pattern, line)
    ]
    assert not found
