#!/usr/bin/env python3
"""The Claude homes dotfiles manages, and what a per-home script shares.

claude_plugins and headroom_mcp visit every existing home and drive Claude
Code's own CLI there; ai_tools_check reads each home's settings. The home
names live here once, in the order the scripts report them.
"""

from collections.abc import Callable, Sequence
import os
from pathlib import Path
import shutil
import subprocess
import time

from doctor_lines import Line, failed, fmt

NAMES = (
    ".claude",
    ".claude-work-a",
    ".claude-work-b",
    ".claude-work-c",
    ".claude-work-d",
)


def existing(home: Path) -> list[Path]:
    """The managed homes under `home` that exist; a missing one is never made."""
    return [home / name for name in NAMES if (home / name).is_dir()]


# ---- Visiting a home through Claude Code's CLI ----

CALL_TIMEOUT = 180.0  # one claude call
# A --check run as a whole: below doctor's wait for a checker (ai_tools_check),
# so a hanging home costs its own lines, never the report of the others
CHECK_BUDGET = 240.0

Run = Callable[[list[str]], str | None]  # claude argv -> stdout, None on failure


def call_timeout(deadline: float | None, now: float) -> float | None:
    """How long the next claude call may take; None when the budget is spent."""
    if deadline is None:
        return CALL_TIMEOUT
    if now >= deadline:
        return None
    return min(CALL_TIMEOUT, deadline - now)


def runner(
    claude: str,
    home: Path,
    deadline: float | None,
    *,
    cwd: Path | None = None,
    no_stdin: bool = False,
) -> Run:
    """`claude <args>` against one home: CLAUDE_CONFIG_DIR set to its native
    path in a copied environment, within what is left of `deadline`."""
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(home)}

    def run(args: list[str]) -> str | None:
        timeout = call_timeout(deadline, time.monotonic())
        if timeout is None:
            return None
        try:
            done = subprocess.run(  # noqa: S603 - resolved argv, no shell
                [claude, *args],
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL if no_stdin else None,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout if done.returncode == 0 else None

    return run


# ---- Reporting a visit, as doctor lines ----

Visit = Callable[[str, Path, float | None], tuple[Sequence[str], Sequence[str]]]


def home_lines(
    name: str, home: Path, fixed: Sequence[str], problems: Sequence[str], fix: str
) -> list[Line]:
    """One home's lines: what was fixed there, then what is still wrong."""
    return [("OK", name, f"~/{home.name}: fixed: {item}") for item in fixed] + [
        ("WARN", name, f"~/{home.name}: {problem}: {fix}") for problem in problems
    ]


def visit(
    name: str,
    homes: Sequence[Path],
    one: Visit,
    *,
    check: bool,
    recipe: str,
    summary: Callable[[int], str],
) -> int:
    """Run `one(claude, home, deadline)` for each home, printing each home's
    lines as it goes (a later failure cannot swallow them), then the summary
    when nothing is wrong. Exit 1 on a WARN, as a checker does."""
    claude = shutil.which("claude")
    if not claude:
        print(fmt(("WARN", name, "claude not on PATH: mise install")))
        return 1
    deadline = time.monotonic() + CHECK_BUDGET if check else None
    fix = recipe if check else "see the line above"
    found = False
    for home in homes:
        lines = home_lines(name, home, *one(claude, home, deadline), fix)
        for line in lines:
            print(fmt(line))
        found = found or failed(lines)
    if not found:
        print(fmt(("OK", name, summary(len(homes)))))
    return 1 if found else 0
