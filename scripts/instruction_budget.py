#!/usr/bin/env python3
"""Count always-loaded agent instructions and gate their growth.

The hub-and-spoke design keeps ROOT_AGENTS.md (base) and ROOT_CLAUDE.md
(overlay) short because adherence — not token cost — is the constraint;
the ~150-200-instructions-followed figure behind that is a heuristic, not
a measured constant. This gate therefore does not validate the figure: it
counts Markdown list items (outside fenced code blocks and HTML comments)
as a *proxy* for instruction count and fails when the total exceeds a cap,
so the always-loaded set cannot grow unnoticed. Raising the cap means
editing the justfile — a visible, reviewable act.

Counted:   "- item", "* item", "1. item" (any indentation).
Excluded:  fenced code blocks, HTML comments, tables, headings, prose
           (prose can carry instructions too — hence "proxy").
"""

from __future__ import annotations

import argparse
import re
import sys

_LIST_ITEM = re.compile(r"^\s*(?:[-*]|\d+\.)\s+")
_INLINE_COMMENT = re.compile(r"<!--.*?-->")


def count_instructions(text: str) -> int:
    """Count list items outside fenced code blocks and HTML comments."""
    count = 0
    in_fence = False
    in_comment = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not in_comment and stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_comment:
            if "-->" in raw_line:
                in_comment = False
            continue
        line = _INLINE_COMMENT.sub("", raw_line)
        if "<!--" in line:
            in_comment = True
            line = line.split("<!--", 1)[0]
        if _LIST_ITEM.match(line):
            count += 1
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="Markdown files to count")
    parser.add_argument(
        "--max",
        type=int,
        default=None,
        help="fail (exit 1) when the total exceeds this cap",
    )
    args = parser.parse_args(argv)

    total = 0
    for name in args.files:
        with open(name, encoding="utf-8") as fh:
            n = count_instructions(fh.read())
        total += n
        print(f"{name}: {n}")
    cap = f" (cap {args.max})" if args.max is not None else ""
    print(f"total: {total}{cap}")

    if args.max is not None and total > args.max:
        print(
            f"instruction budget exceeded: {total} > {args.max} — trim the "
            "always-loaded files or consciously raise the cap in the justfile",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
