#!/usr/bin/env python3
"""Move a ruff or ty pin in every declaration at once (`just bump-tool <tool> <ver>`).

ruff and ty are pinned exactly in four places that must agree
(tests/unit/test_ruff_ty_pins.py): the justfile's `uvx ruff@<ver>` gate pin (ruff
only), the root and emulator dev groups (`"<tool>==<ver>"`), and the shared mise
config (`<tool> = "<ver>"`). Dependabot ignores both tools, so this script is the
one path a pin moves through. It rewrites all declarations (refusing, with no
writes, if any is missing or not an exact pin), re-locks both uv projects with
`uv lock --upgrade-package <tool>`, and prints the hironow/skills follow-up.

Usage: bump_tool.py {ruff,ty} VERSION [--repo DIR] [--no-lock] [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

TOOLS = ("ruff", "ty")
_VERSION = re.compile(r"^\d+(?:\.\d+)*(?:[a-zA-Z]+\d*)?$")


@dataclass(frozen=True)
class Edit:
    path: Path
    pattern: re.Pattern[str]
    replacement: str
    label: str

    def apply(self, text: str) -> tuple[str, int]:
        return self.pattern.subn(self.replacement, text)


def plan(repo: Path, tool: str, version: str) -> list[Edit]:
    """Every declaration of `tool` this repo carries, as substitution edits."""
    ver = r"[0-9][0-9A-Za-z.]*"
    edits = [
        Edit(
            repo / "pyproject.toml",
            re.compile(rf'"{tool}=={ver}"'),
            f'"{tool}=={version}"',
            "root dev group",
        ),
        Edit(
            repo / "emulator" / "pyproject.toml",
            re.compile(rf'"{tool}=={ver}"'),
            f'"{tool}=={version}"',
            "emulator dev group",
        ),
        Edit(
            repo / "config" / "mise" / "config.toml",
            re.compile(rf'^{tool} = "{ver}"$', re.MULTILINE),
            f'{tool} = "{version}"',
            "mise config",
        ),
    ]
    if tool == "ruff":
        edits.insert(
            0,
            Edit(
                repo / "justfile",
                re.compile(rf"uvx ruff@{ver}"),
                f"uvx ruff@{version}",
                "justfile uvx gate pin",
            ),
        )
    return edits


def _lock(repo: Path, tool: str, dry_run: bool) -> int:
    for project in (repo, repo / "emulator"):
        cmd = ["uv", "lock", "--upgrade-package", tool]
        print(f"$ (cd {project.relative_to(repo) or '.'} && {' '.join(cmd)})")
        if dry_run:
            continue
        done = subprocess.run(cmd, cwd=project, check=False)  # noqa: S603 - fixed argv
        if done.returncode != 0:
            print(f"bump-tool: uv lock failed in {project}", file=sys.stderr)
            return done.returncode
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("tool", choices=TOOLS)
    parser.add_argument(
        "version", help="exact version, e.g. 0.15.23 (no v prefix, no 'latest')"
    )
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--no-lock", action="store_true", help="skip `uv lock --upgrade-package`"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan, write nothing"
    )
    args = parser.parse_args(argv)
    if not _VERSION.match(args.version):
        parser.error(f"not an exact version: {args.version!r}")
    repo: Path = args.repo.resolve()

    # Phase 1: read everything and refuse before any write.
    staged: list[tuple[Edit, str, int]] = []
    problems: list[str] = []
    for edit in plan(repo, args.tool, args.version):
        rel = edit.path.relative_to(repo)
        try:
            text = edit.path.read_text(encoding="utf-8")
        except OSError as exc:
            problems.append(f"{rel}: cannot read ({exc})")
            continue
        new_text, n = edit.apply(text)
        if n == 0:
            problems.append(f"{rel}: no exact {args.tool} pin found ({edit.label})")
            continue
        staged.append((edit, new_text, n))
    if problems:
        for p in problems:
            print(f"bump-tool: {p}", file=sys.stderr)
        print("bump-tool: nothing written", file=sys.stderr)
        return 1

    # Phase 2: write (or print) every declaration.
    for edit, new_text, n in staged:
        rel = edit.path.relative_to(repo)
        print(
            f"{'would set' if args.dry_run else 'set'} {edit.label}: {rel} -> {args.tool} {args.version} ({n} site{'s' if n > 1 else ''})"
        )
        if not args.dry_run:
            edit.path.write_text(new_text, encoding="utf-8")

    rc = 0 if args.no_lock else _lock(repo, args.tool, args.dry_run)
    if rc:
        return rc
    print(
        "\nnext: hironow/skills pins the same tools in its own pyproject --\n"
        f"  (cd <skills clone> && uv add --dev '{args.tool}=={args.version}' && just check)\n"
        "then: just check   # tests/unit/test_ruff_ty_pins.py must be green"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
