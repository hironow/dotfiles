#!/usr/bin/env python3
"""Regenerate the generated tables of the skills submodule README from frontmatter.

The README's prose is written by hand; the blocks between marker comments are
generated so they cannot drift from the skills:

    <!-- skills-index:start --> ... <!-- skills-index:end -->
    <!-- credits:start -->      ... <!-- credits:end -->

The index lists every skill with the first sentence of its description and
flags (`user-invoked`, `fork of <repo>`). The credits block lists every
derived skill with its upstream repository (linked at the compared revision),
the upstream license, and what changed here, followed by the skills whose
origin is not yet confirmed and the confirmed originals — all read from the
provenance contract in frontmatter (`metadata.provenance`,
`metadata.upstream`, `metadata.upstream-license`, `metadata.changes`). A
derived skill missing part of the contract is an error, never a blank cell.

`--check` compares the regenerated README with the file and exits 1 on drift.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from skills_frontmatter import read_skill, skill_dirs

MAX_SUMMARY = 140
UPSTREAM_RE = re.compile(
    r"^(?P<repo>[\w.-]+/[\w.-]+)@(?P<sha>[0-9a-f]{7,40}):(?P<path>.+)$"
)


class MissingProvenanceError(ValueError):
    """A derived skill lacks part of the provenance contract."""


@dataclass(frozen=True)
class SkillEntry:
    name: str
    summary: str
    user_invoked: bool
    provenance: str
    upstream: str | None
    upstream_license: str | None
    changes: str | None


def first_sentence(description: str) -> str:
    text = " ".join(description.split())
    m = re.search(r"(?:\.\s|。)", text)
    sentence = text[: m.end()].strip() if m else text
    if len(sentence) > MAX_SUMMARY:
        sentence = sentence[: MAX_SUMMARY - 3].rstrip() + "…"
    return sentence


def collect(root: Path) -> list[SkillEntry]:
    entries: list[SkillEntry] = []
    for skill in skill_dirs(root):
        fm, _ = read_skill(skill)
        meta = fm.get("metadata")
        meta = meta if isinstance(meta, dict) else {}
        entries.append(
            SkillEntry(
                name=skill.name,
                summary=first_sentence(str(fm.get("description", ""))),
                user_invoked=str(fm.get("disable-model-invocation", "")).lower()
                == "true",
                provenance=str(meta.get("provenance") or "unknown"),
                upstream=str(meta["upstream"]) if meta.get("upstream") else None,
                upstream_license=str(meta["upstream-license"])
                if meta.get("upstream-license")
                else None,
                changes=str(meta["changes"]) if meta.get("changes") else None,
            )
        )
    return entries


def _flags(entry: SkillEntry) -> str:
    flags: list[str] = []
    if entry.user_invoked:
        flags.append("user-invoked")
    if entry.provenance == "derived":
        m = UPSTREAM_RE.match(entry.upstream or "")
        flags.append(f"fork of {m.group('repo')}" if m else "derived (origin unknown)")
    return ", ".join(flags)


def _cell(text: str) -> str:
    return text.replace("|", "\\|")


def render_index(entries: list[SkillEntry]) -> str:
    rows = [
        f"| [`{e.name}`]({e.name}/SKILL.md) | {_cell(e.summary)} | {_flags(e)} |"
        for e in entries
    ]
    return "| skill | what it does | notes |\n|---|---|---|\n" + "\n".join(rows)


def _upstream_cell(upstream: str) -> str:
    m = UPSTREAM_RE.match(upstream)
    if not m:
        return "unknown"
    repo, sha, path = m.group("repo"), m.group("sha"), m.group("path")
    return f"[{repo}](https://github.com/{repo}/tree/{sha}/{path})"


def render_credits(entries: list[SkillEntry]) -> str:
    rows: list[str] = []
    for e in entries:
        if e.provenance != "derived":
            continue
        if not (e.upstream and e.upstream_license and e.changes):
            raise MissingProvenanceError(
                f"{e.name}: a derived skill needs metadata.upstream, "
                "metadata.upstream-license, and metadata.changes"
            )
        rows.append(
            f"| [`{e.name}`]({e.name}/SKILL.md) | {_upstream_cell(e.upstream)} "
            f"| {e.upstream_license} | {_cell(e.changes)} |"
        )
    table = (
        "| skill | upstream | upstream license | what changed here |\n"
        "|---|---|---|---|\n" + "\n".join(rows)
    )
    unknown = ", ".join(f"`{e.name}`" for e in entries if e.provenance == "unknown")
    original = ", ".join(f"`{e.name}`" for e in entries if e.provenance == "original")
    return (
        f"{table}\n\n"
        f"Origin not yet confirmed (no upstream found; confirm before publishing): {unknown or 'none'}\n\n"
        f"Original (confirmed): {original or 'none'}"
    )


def replace_between_markers(doc: str, marker: str, content: str) -> str:
    start, end = f"<!-- {marker}:start -->\n", f"<!-- {marker}:end -->"
    i, j = doc.find(start), doc.find(end)
    if i < 0 or j < 0 or j < i:
        raise ValueError(f"README is missing the {marker} markers")
    return doc[: i + len(start)] + content.rstrip("\n") + "\n" + doc[j:]


def render_readme(doc: str, entries: list[SkillEntry]) -> str:
    doc = replace_between_markers(doc, "skills-index", render_index(entries))
    return replace_between_markers(doc, "credits", render_credits(entries))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    root = Path(__file__).resolve().parents[1] / "skills"
    parser.add_argument("--skills-dir", type=Path, default=root)
    parser.add_argument(
        "--readme", type=Path, default=None, help="defaults to <skills-dir>/README.md"
    )
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if the README would change"
    )
    args = parser.parse_args(argv)
    readme: Path = args.readme or args.skills_dir / "README.md"
    current = readme.read_text(encoding="utf-8")
    rendered = render_readme(current, collect(args.skills_dir))
    if args.check:
        if rendered != current:
            sys.stdout.write(
                f"❌ {readme} is out of date; run `just skills-readme-index`\n"
            )
            return 1
        sys.stdout.write(f"✅ {readme} matches the skills frontmatter\n")
        return 0
    if rendered != current:
        readme.write_text(rendered, encoding="utf-8")
    sys.stdout.write(f"✅ regenerated tables in {readme}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
