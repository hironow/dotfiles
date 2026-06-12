#!/usr/bin/env python3
"""Scan deployed agent-home instruction files for dead file references.

Verification gate for the distributed agent instruction set: after
`just sync-agents`, every file reference inside the deployed base/overlay/
spokes must resolve. Per agent home this checks that:

1. absolute `/Users/...` and `~/...` references to .md/.sh/.yaml files exist
   (glob-ish tokens like `*` are checked at their fixed directory prefix);
2. no bare `docs/agents/` reference survived the sync path-rewrite;
3. no reference to README-agents-setup.md (not distributed) remains.

Exit code: 0 = clean, 1 = dead references found (listed on stdout).

Usage: uv run scripts/check_agent_home_refs.py [AGENT_HOME ...]
       (default: ~/.claude)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_PATH_RE = re.compile(r"(?:/Users/|~/)[\w@./*-]+")
_SUFFIXES = {".md", ".sh", ".yaml"}
_TRAILING_PUNCT = ".,;:'\")"

# Explanatory strings exempt from existence checks (none needed today; add the
# exact matched token here if a doc must show a deliberately fictional path).
ALLOWLIST: frozenset[str] = frozenset()


def _expand(ref: str) -> Path:
    if ref.startswith("~/"):
        return Path.home() / ref[2:]
    return Path(ref)


def _glob_prefix_exists(ref: str) -> bool:
    fixed = ref.split("*", 1)[0]
    path = _expand(fixed)
    return path.is_dir() if fixed.endswith("/") else path.parent.is_dir()


def _iter_instruction_files(home: Path) -> list[Path]:
    files = [home / "AGENTS.md", home / "CLAUDE.md"]
    files.extend(sorted((home / "docs" / "agents").glob("*.md")))
    return [f for f in files if f.is_file()]


def _scan_file(path: Path) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")

    spans: list[tuple[int, int]] = []
    for match in _PATH_RE.finditer(text):
        spans.append(match.span())
        ref = match.group(0).rstrip(_TRAILING_PUNCT)
        if ref in ALLOWLIST:
            continue
        if "*" in ref:
            ok = _glob_prefix_exists(ref)
        elif Path(ref).suffix in _SUFFIXES:
            ok = _expand(ref).exists()
        else:
            continue  # directory or extensionless mention — not checked
        if not ok:
            problems.append(f"{path.name}: dead path reference '{ref}'")

    for bare in re.finditer(r"docs/agents/", text):
        inside_abs = any(start <= bare.start() < end for start, end in spans)
        if not inside_abs:
            line = text.count("\n", 0, bare.start()) + 1
            problems.append(
                f"{path.name}:{line}: bare 'docs/agents/' reference "
                "(sync path-rewrite miss?)"
            )

    if "README-agents-setup" in text:
        problems.append(
            f"{path.name}: references README-agents-setup.md (not distributed)"
        )

    return problems


def main(argv: list[str]) -> int:
    homes = [Path(arg).expanduser() for arg in argv] or [Path.home() / ".claude"]
    problems: list[str] = []
    for home in homes:
        files = _iter_instruction_files(home)
        if not files:
            problems.append(f"{home}: no instruction files found (wrong home?)")
            continue
        for file in files:
            problems.extend(_scan_file(file))

    if problems:
        print("DEAD REFERENCES FOUND:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    homes_label = ", ".join(str(h) for h in homes)
    print(f"OK: all instruction-file references resolve in {homes_label}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
