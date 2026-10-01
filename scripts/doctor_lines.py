#!/usr/bin/env python3
"""The doctor line protocol: how a checker prints a finding and doctor reads it.

Every checker (codex_hooks_trust, codex_sandbox_tools, claude_plugins,
headroom_mcp, ai_tools_check) prints `LEVEL name - detail` lines, LEVEL padded
to four (OK, WARN, ERR), and exits 1 on a WARN. scripts/doctor.sh counts the
lines; ai_tools_check reads a checker's output back with parse(). Defining both
sides here keeps the writers and the readers in step.
"""

from collections.abc import Iterable

Line = tuple[str, str, str]  # (level, name, detail)
FAILING = ("WARN", "ERR")


def fmt(line: Line) -> str:
    level, name, detail = line
    return f"{level:<4} {name} - {detail}"


def parse(text: str) -> list[Line]:
    """Lines as a checker printed them; an odd line is read, never rejected."""
    lines: list[Line] = []
    for raw in text.splitlines():
        level, _, rest = raw.partition(" ")
        name, _, detail = rest.strip().partition(" - ")
        lines.append((level.strip(), name, detail))
    return lines


def failed(lines: Iterable[Line]) -> bool:
    return any(level in FAILING for level, _name, _detail in lines)
