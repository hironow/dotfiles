#!/usr/bin/env python3
"""Declarative management of third-party agent skills.

The bunx skills CLI owns ~/.agents/skills and records installs in
~/.agents/.skill-lock.json. That lock is not usable raw (display-name keys,
duplicate registrations, frontmatter-name installs whose dir differs from the
repo path), so this script normalizes it into a committed declaration:

    dump/harness/skill-lock.json

Subcommands:
    dump     normalize the machine lock into the committed declaration
    restore  install every declared skill via the pinned bunx skills CLI
    check    fail when a lock-managed skill reappears in the skills submodule
             (the CI barrier against re-vendoring; hironow/skills is exempt)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

# Pinned like every bunx-run CLI here: an unpinned CLI would make restore
# behavior drift between machines.
SKILLS_CLI_VERSION = "1.5.22"

# Skills sourced from this repo are the submodule's own content; their presence
# in the submodule is by design, never re-vendoring.
SELF_SOURCE = "hironow/skills"

MACHINE_LOCK = Path.home() / ".agents" / ".skill-lock.json"
AGENTS_STORE = Path.home() / ".agents" / "skills"
DUMP_RELATIVE = Path("dump/harness/skill-lock.json")
SKILLS_DIR_RELATIVE = Path("skills")


class UnresolvedSkillError(RuntimeError):
    """A lock entry could not be mapped to an installed dir but overlaps the
    submodule — resolving it wrongly would corrupt the delete/overlap sets."""


@dataclass(frozen=True)
class SkillRecord:
    """One declared third-party skill (normalized from the machine lock)."""

    installed_dir: str
    upstream_name: str
    lock_key: str
    source: str
    skill_path: str
    skill_folder_hash: str
    resolved_by: str  # "installed" | "skillPath"


def _upstream_name(skill_path: str) -> str:
    parts = skill_path.rstrip("/").split("/")
    return parts[-2] if len(parts) >= 2 else parts[-1]


def normalize_lock(
    raw_skills: dict[str, dict[str, str]],
    installed_dirs: set[str],
    submodule_dirs: set[str],
) -> list[SkillRecord]:
    """Two-stage resolution: lock key if it is an installed dir (frontmatter-name
    installs land under the key), else the skillPath parent. Deduped by
    installed_dir; unresolved entries are dropped with a warning unless either
    of their names overlaps the submodule, which is a hard error."""
    by_dir: dict[str, SkillRecord] = {}
    for key, entry in raw_skills.items():
        upstream = _upstream_name(entry["skillPath"])
        if key in installed_dirs:
            installed, resolved_by = key, "installed"
        elif upstream in installed_dirs:
            installed, resolved_by = upstream, "skillPath"
        else:
            if key in submodule_dirs or upstream in submodule_dirs:
                raise UnresolvedSkillError(
                    f"lock entry {key!r} is not installed but overlaps the "
                    f"skills submodule — refusing to guess its installed dir"
                )
            print(f"⚠️  skipping unresolved lock entry: {key!r}", file=sys.stderr)
            continue
        record = SkillRecord(
            installed_dir=installed,
            upstream_name=upstream,
            lock_key=key,
            source=entry["source"],
            skill_path=entry["skillPath"],
            skill_folder_hash=entry.get("skillFolderHash", ""),
            resolved_by=resolved_by,
        )
        # Duplicate registrations (display-name + dir-name keys): prefer the
        # entry whose key is the installed dir itself.
        existing = by_dir.get(installed)
        if existing is None or record.resolved_by == "installed":
            by_dir[installed] = record
    return sorted(by_dir.values(), key=lambda r: r.installed_dir)


def check_overlap(records: list[SkillRecord], submodule_dirs: set[str]) -> list[str]:
    """Names (installed or upstream) of lock-managed third-party skills that
    are present in the skills submodule. Non-empty means re-vendoring."""
    overlap: set[str] = set()
    for rec in records:
        if rec.source == SELF_SOURCE:
            continue
        for name in (rec.installed_dir, rec.upstream_name):
            if name in submodule_dirs:
                overlap.add(name)
    return sorted(overlap)


def build_restore_command(record: SkillRecord) -> list[str]:
    """The CLI accepts the frontmatter name it recorded as the lock key
    (spike-verified: `-s composition-patterns` fails, the listed and accepted
    name is `vercel-composition-patterns`)."""
    return [
        "bunx",
        f"skills@{SKILLS_CLI_VERSION}",
        "add",
        record.source,
        "-g",
        "-s",
        record.lock_key,
        "-y",
    ]


def _list_dirs(path: Path) -> set[str]:
    if not path.is_dir():
        return set()
    return {c.name for c in path.iterdir() if c.is_dir() and not c.name.startswith(".")}


def _load_dump(dotfiles_dir: Path) -> list[SkillRecord]:
    data = json.loads((dotfiles_dir / DUMP_RELATIVE).read_text())
    return [SkillRecord(**item) for item in data["skills"]]


def _cmd_dump(dotfiles_dir: Path) -> int:
    raw = json.loads(MACHINE_LOCK.read_text())["skills"]
    submodule_dirs = _list_dirs(dotfiles_dir / SKILLS_DIR_RELATIVE)
    records = normalize_lock(raw, _list_dirs(AGENTS_STORE), submodule_dirs)
    dump_path = dotfiles_dir / DUMP_RELATIVE
    dump_path.write_text(
        json.dumps(
            {"version": 1, "skills": [asdict(r) for r in records]},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    overlap = check_overlap(records, submodule_dirs)
    print(f"✅ dumped {len(records)} skills -> {dump_path}")
    print(f"   submodule overlap (expected delete set): {len(overlap)}")
    return 0


def _configure_output() -> None:
    # Windows Git Bash hands Python a cp932 stdout; the emoji progress lines
    # then raise UnicodeEncodeError and kill the whole command. Re-encode to
    # UTF-8 where supported, degrade to replacement characters elsewhere.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _cmd_restore(dotfiles_dir: Path) -> int:
    records = _load_dump(dotfiles_dir)
    installed = _list_dirs(AGENTS_STORE)
    failures = 0
    for rec in records:
        if rec.installed_dir in installed:
            continue
        cmd = build_restore_command(rec)
        print(f"⬇️  {rec.installed_dir} <- {rec.source}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            failures += 1
            print(f"❌ restore failed: {rec.installed_dir}", file=sys.stderr)
    print(f"{'⚠️' if failures else '✅'} restore done ({failures} failures)")
    return 1 if failures else 0


def _cmd_check(dotfiles_dir: Path) -> int:
    records = _load_dump(dotfiles_dir)
    overlap = check_overlap(records, _list_dirs(dotfiles_dir / SKILLS_DIR_RELATIVE))
    if overlap:
        print(
            "❌ lock-managed third-party skills present in the skills submodule "
            f"(re-vendoring): {', '.join(overlap)}",
            file=sys.stderr,
        )
        return 1
    print("✅ no lock-managed skills in the submodule")
    return 0


def main() -> int:
    _configure_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["dump", "restore", "check"])
    args = parser.parse_args()
    dotfiles_dir = Path(__file__).resolve().parent.parent
    if args.command == "dump":
        return _cmd_dump(dotfiles_dir)
    if args.command == "restore":
        return _cmd_restore(dotfiles_dir)
    return _cmd_check(dotfiles_dir)


if __name__ == "__main__":
    sys.exit(main())
