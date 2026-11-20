"""The template's commit hook runs only fast checks (ADR 0083).

A commit must not wait minutes for what CI runs anyway. The agent-baseline
template's `.githooks/pre-commit` runs `just pre-commit`, which runs ruff alone.
ty, the tests and Semgrep stay in `just check`, which the template's CI runs on
every pull request that is ready for review, so nothing the hook used to run is
lost. These tests read files and run no shell, so they pass on Windows too.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "templates/agent-baseline"
HOOK = TEMPLATE / ".githooks/pre-commit"
JUSTFILE = TEMPLATE / "justfile"
CI = TEMPLATE / ".github/workflows/quality-gate.yaml"
RUFF = [
    "uv run --locked --only-group lint ruff format --check .",
    "uv run --locked --only-group lint ruff check .",
]
# The hook's lines other than its last command: the shebang, errexit, the
# check that `just` exists, and one line saying what it runs.
HOOK_SCAFFOLD = re.compile(
    r"set -euo pipefail"
    r"|if ! command -v just >/dev/null 2>&1; then"
    r'|echo "pre-commit: .*"( >&2)?'
    r"|exit 1"
    r"|fi"
)


def _recipe(name: str) -> tuple[list[str], list[str]]:
    """The dependencies and the command lines of the template recipe `name`."""
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
    for start, line in enumerate(lines):
        header = re.match(rf"^{re.escape(name)}\s*:(?!=)(?P<deps>.*)$", line)
        if header:
            break
    else:
        raise AssertionError(f"no recipe {name} in {JUSTFILE}")
    deps = header.group("deps").split("#", 1)[0].split()
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        if line.strip() and not line.strip().startswith("#"):
            body.append(line.strip())
    return deps, body


def test_the_hook_runs_just_pre_commit_and_nothing_else():
    lines = HOOK.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    commands = [line.strip() for line in lines[1:] if line.strip()]
    commands = [line for line in commands if not line.startswith("#")]
    # errexit is set, and the last command decides the hook's exit status.
    assert "set -euo pipefail" in commands
    assert commands[-1] == "just pre-commit"
    for line in commands[:-1]:
        assert HOOK_SCAFFOLD.fullmatch(line), f"unexpected hook command: {line}"


def test_the_pre_commit_recipe_runs_only_ruff():
    deps, body = _recipe("pre-commit")
    assert deps == [], "pre-commit must not depend on another recipe"
    assert body == RUFF


def test_ci_runs_what_the_hook_does_not():
    workflow = CI.read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s+run: just check\s*$", workflow)
    deps, _ = _recipe("check")
    assert {"lint", "semgrep", "test"} <= set(deps)
