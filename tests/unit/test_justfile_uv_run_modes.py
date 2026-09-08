"""uv has two run modes and the justfile must pick the right one per script.

Project mode (`UV_RUN` = `uv run --frozen ...`): the command runs in the root
project's environment (dev deps: pytest, ruff, ty) and `--frozen` installs from
the committed uv.lock without ever rewriting it. Script mode: a file with a
PEP 723 `# /// script` block runs in its own isolated environment, never touches
uv.lock -- and `--frozen` there demands a *script* lockfile that does not
exist (`error: Unable to find lockfile for Python script`), which is how
`just sync-agents` broke inside the devcontainer sandbox on 2026-09-08.
`UV_RUN_SCRIPT` (no `--frozen`) is for those scripts, and only those.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SCRIPT_REF = re.compile(r"\{\{\s*(UV_RUN_SCRIPT|UV_RUN)\s*\}\}\s+(scripts/\S+\.py)")


def _is_pep723(script: Path) -> bool:
    head = script.read_text(encoding="utf-8").splitlines()[:10]
    return any(line.startswith("# /// script") for line in head)


def _runner_uses() -> list[tuple[str, str, int]]:
    uses = []
    for n, line in enumerate(
        (REPO / "justfile").read_text(encoding="utf-8").splitlines(), 1
    ):
        m = _SCRIPT_REF.search(line)
        if m:
            uses.append((m.group(1), m.group(2), n))
    assert uses, "no script invocations found in the justfile"
    return uses


def test_frozen_runner_is_never_used_for_pep723_scripts() -> None:
    offenders = [
        f"justfile:{n}: {{{{UV_RUN}}}} {script} (PEP 723 script needs UV_RUN_SCRIPT)"
        for runner, script, n in _runner_uses()
        if runner == "UV_RUN" and _is_pep723(REPO / script)
    ]
    assert not offenders, "\n".join(offenders)


def test_script_runner_is_only_used_for_pep723_scripts() -> None:
    offenders = [
        f"justfile:{n}: {{{{UV_RUN_SCRIPT}}}} {script} (project-mode script needs UV_RUN)"
        for runner, script, n in _runner_uses()
        if runner == "UV_RUN_SCRIPT" and not _is_pep723(REPO / script)
    ]
    assert not offenders, "\n".join(offenders)


def test_runner_definitions_differ_only_by_frozen() -> None:
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    project = re.search(r'^UV_RUN := "(.*)"$', justfile, re.MULTILINE)
    script = re.search(r'^UV_RUN_SCRIPT := "(.*)"$', justfile, re.MULTILINE)
    assert project and script, "both UV_RUN and UV_RUN_SCRIPT must be defined"
    assert project.group(1).endswith(" --frozen")
    assert script.group(1) == project.group(1).removesuffix(" --frozen")
