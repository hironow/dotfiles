"""Minimal SKILL.md frontmatter reader shared by the skills maintenance scripts.

Only the YAML subset the skills actually use is supported, so the scripts stay
stdlib-only (the unit-test workflow runs them under `uvx pytest`, without the
project's dependencies): `key: value`, quoted scalars, trailing `# comments`,
block scalars (`>`, `>-`, `|`, `|-`), and one level of nested mapping
(`metadata:`). Anything outside that subset raises FrontmatterError instead of
being skipped, because a silently dropped key is exactly how a broken
description or a lost provenance block would slip through the audit.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
KEY_RE = re.compile(r"^([A-Za-z][\w-]*):(?:[ \t]+(.*))?$")
BLOCK_INDICATORS = frozenset({">", ">-", "|", "|-"})


class FrontmatterError(ValueError):
    """The frontmatter is not valid YAML, or uses syntax outside the supported subset."""


def _strip_comment(raw: str) -> str:
    """Drop a trailing ` # comment`; a `#` inside a quoted scalar is kept."""
    if raw and raw[0] in "\"'":
        quote = raw[0]
        end = raw.find(quote, 1)
        if end < 0:
            raise FrontmatterError(f"unterminated quoted value: {raw!r}")
        return raw[: end + 1]
    if raw.startswith("#"):
        return ""
    return re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()


def _scalar(raw: str, key: str) -> str:
    raw = _strip_comment(raw.strip())
    if raw and raw[0] in "\"'":
        return raw[1:-1]
    if ": " in raw or raw.endswith(":"):
        raise FrontmatterError(
            f"{key}: a bare value must not contain ': ' (quote it): {raw!r}"
        )
    # flow sequences such as `argument-hint: [message]` are kept as text; the
    # remaining indicators (anchors, tags, directives) are not used in skills
    if raw and raw[0] in "&*!%@`":
        raise FrontmatterError(f"{key}: unsupported YAML syntax: {raw!r}")
    return raw


def _block(lines: list[str], i: int, indicator: str) -> tuple[str, int]:
    block: list[str] = []
    while i < len(lines) and (lines[i].startswith(" ") or not lines[i].strip()):
        block.append(lines[i].strip())
        i += 1
    joiner = "\n" if indicator.startswith("|") else " "
    return joiner.join(part for part in block if part).strip(), i


def _nested(lines: list[str], i: int, key: str) -> tuple[dict[str, str], int]:
    nested: dict[str, str] = {}
    while i < len(lines) and lines[i].startswith(" "):
        nm = KEY_RE.match(lines[i].strip())
        if not nm:
            raise FrontmatterError(
                f"{key}: unsupported nested syntax: {lines[i].strip()!r}"
            )
        nested[nm.group(1)] = _scalar(nm.group(2) or "", f"{key}.{nm.group(1)}")
        i += 1
    return nested, i


def parse_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter mapping, body). Missing frontmatter -> ({}, text)."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    lines = m.group(1).splitlines()
    result: dict[str, object] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        km = KEY_RE.match(line)
        if not km:
            raise FrontmatterError(f"unsupported frontmatter line: {line!r}")
        key, raw = km.group(1), _strip_comment((km.group(2) or "").strip())
        i += 1
        if raw in BLOCK_INDICATORS:
            result[key], i = _block(lines, i, raw)
        elif raw == "" and i < len(lines) and lines[i].startswith(" "):
            result[key], i = _nested(lines, i, key)
        else:
            result[key] = _scalar(raw, key)
    return result, text[m.end() :]


def read_skill(skill_dir: Path) -> tuple[dict[str, object], str]:
    """Parse `<skill_dir>/SKILL.md`."""
    return parse_frontmatter((skill_dir / "SKILL.md").read_text(encoding="utf-8"))


def skill_dirs(root: Path) -> list[Path]:
    """Every direct child of `root` that carries a SKILL.md, sorted by name."""
    return sorted(
        d for d in root.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()
    )
