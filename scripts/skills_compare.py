#!/usr/bin/env python3
"""Quantitative comparison of skill versions (fork vs installed vs upstream HEAD).

First step of the fork-dedup playbook, before any judge model reads the files:
per-version sizes (lines, words, estimated tokens, description length),
frontmatter sanity, tooling-rule violations in the body (npm/npx, yarn/pnpm,
pip/poetry, make targets, .yml), and pairwise diff sizes of the SKILL.md
bodies.

    uv run scripts/skills_compare.py skills/review /path/to/upstream/code-review
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from pathlib import Path

from skills_frontmatter import read_skill

VIOLATIONS: dict[str, re.Pattern[str]] = {
    "npm": re.compile(r"\bnpm (install|i|run|x)\b|\bnpx\b"),
    "yarn/pnpm": re.compile(r"\b(yarn|pnpm)\b"),
    "pip/poetry": re.compile(r"\bpip (install|3)?\b|\bpoetry\b|\bpipenv\b"),
    "make": re.compile(
        r"(^|`|\$ )make\s+(?!(it|the|sure|a|an|this|that|them|your|skills?)\b)[a-z][\w-]*",
        re.MULTILINE,
    ),
    ".yml": re.compile(r"\.yml\b"),
}
WORD_RE = re.compile(r"[\w'-]+")


def est_tokens(text: str) -> int:
    return round(len(text) / 4)


def metrics(skill_dir: Path) -> dict[str, object]:
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    fm, body = read_skill(skill_dir)
    desc = str(fm.get("description", ""))
    files = [
        p
        for p in skill_dir.rglob("*")
        if p.is_file() and p.name != ".DS_Store" and ".git" not in p.parts
    ]
    violations = {
        k: len(v.findall(body)) for k, v in VIOLATIONS.items() if v.search(body)
    }
    return {
        "lines": len(text.splitlines()),
        "words(body)": len(WORD_RE.findall(body)),
        "tok(desc)": est_tokens(desc),
        "tok(body)": est_tokens(body),
        "desc_chars": len(desc),
        "name==dir": fm.get("name") == skill_dir.name,
        "headings": len(re.findall(r"^#{1,6}\s", body, re.MULTILINE)),
        "bundle_files": len(files),
        "bundle_bytes": sum(p.stat().st_size for p in files),
        "violations": violations,
    }


def diff_lines(a: Path, b: Path) -> int:
    """Changed (+/-) lines between the SKILL.md bodies of two skill directories."""
    _, body_a = read_skill(a)
    _, body_b = read_skill(b)
    diff = difflib.unified_diff(
        body_a.splitlines(), body_b.splitlines(), lineterm="", n=0
    )
    return sum(
        1 for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---"))
    )


def render(versions: list[Path]) -> str:
    rows = {v: metrics(v) for v in versions}
    keys = list(next(iter(rows.values())))
    width = max(len(k) for k in keys)
    labels = [v.name for v in versions]
    out = [" " * (width + 2) + " | ".join(f"{label[:28]:>28s}" for label in labels)]
    out += [
        f"{k:{width}s}  " + " | ".join(f"{str(rows[v][k])[:28]:>28s}" for v in versions)
        for k in keys
    ]
    out.append("-- pairwise SKILL.md body diff lines (+/-) --")
    for i, a in enumerate(versions):
        for b in versions[i + 1 :]:
            out.append(f"  {a.name} <-> {b.name}: {diff_lines(a, b)}")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "versions",
        nargs="+",
        type=Path,
        help="skill directories to compare (fork first)",
    )
    args = parser.parse_args(argv)
    for v in args.versions:
        if not (v / "SKILL.md").is_file():
            sys.stdout.write(f"❌ not a skill directory: {v}\n")
            return 2
    sys.stdout.write(render(args.versions))
    return 0


if __name__ == "__main__":
    sys.exit(main())
