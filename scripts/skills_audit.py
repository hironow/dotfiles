#!/usr/bin/env python3
"""Structural audit of the skills submodule (the mechanical half of its conventions).

Checks every `<skill>/SKILL.md` and bundled markdown for:

- frontmatter: `name` equals the directory, `description` present and <= 1024 chars
- links: relative links and `#anchor`s resolve, across files of the same skill
  (`templates/` and `assets/` are output skeletons and may hold placeholders)
- code fences balance (a longer fence may enclose shorter ones)
- no emoji markers in SKILL.md; bundled files are checked too unless the skill
  is derived, whose references are upstream material (the same applies to the
  link check: a derived skill's bundled docs are not ours to fix)
- no Japanese instruction text outside the allowed places (the description,
  the Japanese-writing skills, `templates/` and `assets/`, `mcp-setup.md`,
  fenced code, inline code, and quoted phrases)
- provenance contract: `metadata.provenance` is `derived`, `original`, or
  `unknown` (absent counts as unknown); `derived` requires `metadata.upstream`,
  `metadata.upstream-license`, `metadata.changes`, and a bundled LICENSE file
  when the upstream is licensed; `metadata.upstream` without `derived` is an error

`--consumers` additionally compares every skill against the agent homes that
receive a copy (missing, drifted, dangling symlinks).
"""

from __future__ import annotations

import argparse
import filecmp
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from skills_frontmatter import FrontmatterError, read_skill, skill_dirs

JAPANESE_EXEMPT_SKILLS = frozenset(
    {"japanese-tech-writing", "argument-gap-edit", "fallacy-check"}
)
OUTPUT_DIRS = frozenset({"templates", "assets"})
EXEMPT_FILES = frozenset({"mcp-setup.md"})
MAX_DESCRIPTION = 1024
UNLICENSED = frozenset({"", "NOASSERTION", "none"})
PROVENANCE_STATES = frozenset({"derived", "original", "unknown"})

JAPANESE_RE = re.compile(r"[぀-ヿ一-鿿]")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF⭐⭕✅❌✔✖⚠★💡]")
FENCE_OPEN_RE = re.compile(r"^(`{3,})")
QUOTED_RE = re.compile(r"`[^`\n]*`|\"[^\"\n]*\"|「[^」\n]*」")
LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
IGNORED_NAMES = frozenset({".DS_Store", "__pycache__"})

CONSUMER_HOMES = (
    Path.home() / ".claude" / "skills",
    Path.home() / ".claude-work-a" / "skills",
    Path.home() / ".claude-work-b" / "skills",
    Path.home() / ".claude-work-c" / "skills",
    Path.home() / ".claude-work-d" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".gemini" / "skills",
    Path.home() / ".agents" / "skills",
)


@dataclass(frozen=True)
class Finding:
    skill: str
    path: str
    kind: str
    message: str


def slug(heading: str) -> str:
    """GitHub-style heading anchor."""
    cleaned = re.sub(r"[^\w\- ]", "", heading.strip().lower())
    return cleaned.replace(" ", "-")


def split_fences(text: str) -> tuple[str, bool]:
    """Return (text outside fenced code, balanced?).

    A fence opened with N backticks closes only at a line of >= N backticks, so
    a longer outer fence may enclose shorter ones (CommonMark).
    """
    outside: list[str] = []
    open_len = 0
    for line in text.splitlines():
        m = FENCE_OPEN_RE.match(line)
        if open_len:
            if (
                m
                and len(m.group(1)) >= open_len
                and not line[open_len:].strip("`").strip()
            ):
                open_len = 0
            continue
        if m:
            open_len = len(m.group(1))
            continue
        outside.append(line)
    return "\n".join(outside), open_len == 0


def strip_fences(text: str) -> str:
    return split_fences(text)[0]


def _markdown_files(skill_dir: Path) -> list[Path]:
    return sorted(p for p in skill_dir.rglob("*.md") if ".git" not in p.parts)


def _headings(files: list[Path]) -> dict[Path, set[str]]:
    return {
        p.resolve(): {
            slug(h) for h in HEADING_RE.findall(p.read_text(encoding="utf-8"))
        }
        for p in files
    }


def _is_output(rel: Path) -> bool:
    return bool(OUTPUT_DIRS & set(rel.parts))


def _metadata(fm: dict[str, object]) -> dict[str, str]:
    meta = fm.get("metadata")
    return {k: str(v) for k, v in meta.items()} if isinstance(meta, dict) else {}


def _provenance(fm: dict[str, object]) -> str:
    return _metadata(fm).get("provenance", "unknown")


def _check_frontmatter(skill: Path, fm: dict[str, object]) -> list[Finding]:
    findings: list[Finding] = []
    if fm.get("name") != skill.name:
        findings.append(
            Finding(
                skill.name,
                "SKILL.md",
                "frontmatter",
                f"name != directory ({fm.get('name')!r})",
            )
        )
    desc = str(fm.get("description", ""))
    if not desc:
        findings.append(
            Finding(skill.name, "SKILL.md", "frontmatter", "description is empty")
        )
    elif len(desc) > MAX_DESCRIPTION:
        findings.append(
            Finding(
                skill.name,
                "SKILL.md",
                "frontmatter",
                f"description is {len(desc)} chars (> {MAX_DESCRIPTION})",
            )
        )
    return findings


def _check_links(
    skill: Path, md: Path, text: str, headings: dict[Path, set[str]]
) -> list[Finding]:
    rel = md.relative_to(skill)
    if _is_output(rel):
        return []
    findings: list[Finding] = []
    for target in LINK_RE.findall(strip_fences(text)):
        if re.match(r"^[a-z]+:", target):
            continue
        path, _, anchor = target.partition("#")
        resolved = (md.parent / path).resolve() if path else md.resolve()
        if path and not resolved.exists():
            findings.append(
                Finding(skill.name, str(rel), "link", f"file not found: {target}")
            )
            continue
        if anchor and anchor not in headings.get(resolved, set()):
            findings.append(
                Finding(skill.name, str(rel), "link", f"anchor not found: {target}")
            )
    return findings


def _check_language(skill: Path, md: Path, body: str) -> list[Finding]:
    rel = md.relative_to(skill)
    if (
        skill.name in JAPANESE_EXEMPT_SKILLS
        or _is_output(rel)
        or rel.name in EXEMPT_FILES
    ):
        return []
    prose = QUOTED_RE.sub("", strip_fences(body))
    lines = [
        i for i, line in enumerate(prose.splitlines(), 1) if JAPANESE_RE.search(line)
    ]
    if not lines:
        return []
    return [
        Finding(
            skill.name,
            str(rel),
            "language",
            f"Japanese outside quoted/fenced text on {len(lines)} line(s), "
            f"first at line {lines[0]}",
        )
    ]


def _check_provenance(skill: Path, fm: dict[str, object]) -> list[Finding]:
    meta = _metadata(fm)
    state = _provenance(fm)

    def mk(msg: str) -> Finding:
        return Finding(skill.name, "SKILL.md", "provenance", msg)

    if state not in PROVENANCE_STATES:
        return [mk(f"metadata.provenance must be one of {sorted(PROVENANCE_STATES)}")]
    if state != "derived":
        return (
            [mk("metadata.upstream is only allowed with metadata.provenance: derived")]
            if meta.get("upstream")
            else []
        )
    findings = [
        mk(f"metadata.{key} is required for a derived skill")
        for key in ("upstream", "upstream-license", "changes")
        if not meta.get(key)
    ]
    licensed = meta.get("upstream-license", "") not in UNLICENSED
    has_license_file = any(
        p.name.upper().startswith("LICENSE") for p in skill.iterdir()
    )
    if licensed and not has_license_file:
        findings.append(mk("upstream is licensed but no LICENSE file is bundled"))
    return findings


def audit_skill(skill: Path) -> list[Finding]:
    try:
        fm, skill_body = read_skill(skill)
    except FrontmatterError as e:
        return [Finding(skill.name, "SKILL.md", "frontmatter", f"not valid YAML: {e}")]
    findings = _check_frontmatter(skill, fm) + _check_provenance(skill, fm)
    files = _markdown_files(skill)
    headings = _headings(files)
    derived = _provenance(fm) == "derived"
    for md in files:
        text = md.read_text(encoding="utf-8")
        rel = md.relative_to(skill)
        is_skill_md = md.parent == skill and md.name == "SKILL.md"
        # the description may carry trigger phrases in the user's language
        body = skill_body if is_skill_md else text
        if not split_fences(text)[1]:
            findings.append(
                Finding(skill.name, str(rel), "fence", "unbalanced code fences")
            )
        if (is_skill_md or not derived) and EMOJI_RE.search(text):
            findings.append(
                Finding(
                    skill.name, str(rel), "emoji", "emoji marker; use a word instead"
                )
            )
        if is_skill_md or not derived:
            findings += _check_links(skill, md, text, headings)
        findings += _check_language(skill, md, body)
    return findings


def audit_tree(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for skill in skill_dirs(root):
        findings += audit_skill(skill)
    return findings


def _tree_matches(src: Path, dst: Path) -> bool:
    """True when every file matches byte for byte (not filecmp's shallow default)."""
    cmp = filecmp.dircmp(src, dst, ignore=list(IGNORED_NAMES))
    if cmp.left_only or cmp.right_only or cmp.common_funny or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(src, dst, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(_tree_matches(src / sub, dst / sub) for sub in cmp.common_dirs)


def check_consumers(root: Path, homes: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    skills = skill_dirs(root)
    for home in homes:
        if not home.is_dir():
            findings.append(
                Finding(
                    home.parent.name,
                    str(home),
                    "missing-home",
                    "agent home has no skills directory",
                )
            )
            continue
        for entry in sorted(home.iterdir()):
            if entry.is_symlink() and not entry.exists():
                findings.append(
                    Finding(entry.name, str(entry), "dangling", "dangling symlink")
                )
        for skill in skills:
            target = home / skill.name
            if not target.exists():
                findings.append(
                    Finding(
                        skill.name, str(target), "missing", "not present in agent home"
                    )
                )
            elif not _tree_matches(skill, target):
                findings.append(
                    Finding(
                        skill.name, str(target), "drift", "differs from the submodule"
                    )
                )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "skills",
    )
    parser.add_argument(
        "--consumers", action="store_true", help="also compare against the agent homes"
    )
    args = parser.parse_args(argv)
    findings = audit_tree(args.skills_dir)
    if args.consumers:
        findings += check_consumers(args.skills_dir, list(CONSUMER_HOMES))
    for f in findings:
        sys.stdout.write(f"{f.kind:11s} {f.skill}/{f.path}: {f.message}\n")
    n = len(skill_dirs(args.skills_dir))
    status = "❌" if findings else "✅"
    sys.stdout.write(f"{status} skills-audit: {n} skills, {len(findings)} finding(s)\n")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
