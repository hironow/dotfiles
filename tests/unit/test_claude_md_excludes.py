"""Claude Code must not load the instruction files of other projects' submodules.

Claude loads a subdirectory's CLAUDE.md (and AGENTS.md) as soon as it reads a
file there. This repository pins dozens of third-party projects as submodules,
and many of them ship their own CLAUDE.md or AGENTS.md. Those files are data,
not instructions (AGENTS.md, "You follow three sources of instructions"), so
the project settings list them in `claudeMdExcludes`. These checks keep the
list complete when a submodule is added, and keep it from ever hiding an
instruction file this repository tracks itself.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Submodules whose instruction files the owner writes, so Claude may load them.
OWNER_WRITTEN = {"guardrails/semgrep"}

INSTRUCTION_FILE = re.compile(
    r"(^|/)(CLAUDE|CLAUDE\.local|AGENTS|GEMINI)\.md$|(^|/)\.claude/rules/"
)


def _excludes() -> list[str]:
    settings = json.loads(
        (ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
    )
    patterns = settings.get("claudeMdExcludes", [])
    assert isinstance(patterns, list)
    return patterns


def _glob_regex(pattern: str) -> re.Pattern[str]:
    """A glob as Claude applies it to absolute paths: `**` spans directories,
    `*` stays within one. (PurePath.full_match needs Python 3.13; the floor is 3.12.)"""
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pattern.startswith("**", i):
            out += ".*"
            i += 2
        elif pattern[i] == "*":
            out += "[^/]*"
            i += 1
        else:
            out += re.escape(pattern[i])
            i += 1
    return re.compile(out + r"\Z")


def _excluded(repo_path: str, patterns: list[str]) -> bool:
    absolute = f"/checkout/dotfiles/{repo_path}"
    return any(_glob_regex(pattern).match(absolute) for pattern in patterns)


def _submodule_paths() -> list[str]:
    text = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    return re.findall(r"^\s*path\s*=\s*(\S+)\s*$", text, re.MULTILINE)


def test_every_third_party_submodule_is_excluded() -> None:
    patterns = _excludes()
    submodules = _submodule_paths()
    assert submodules, ".gitmodules lists no submodule"
    missing = [
        path
        for path in submodules
        if path not in OWNER_WRITTEN and not _excluded(f"{path}/CLAUDE.md", patterns)
    ]
    assert not missing, (
        f"add claudeMdExcludes patterns for {missing} in .claude/settings.json, "
        "or list them in OWNER_WRITTEN if the owner writes their instructions"
    )


def test_owner_written_submodules_stay_loadable() -> None:
    patterns = _excludes()
    hidden = [
        path for path in OWNER_WRITTEN if _excluded(f"{path}/CLAUDE.md", patterns)
    ]
    assert not hidden, f"claudeMdExcludes hides owner-written instructions in {hidden}"


@pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(),
    reason="needs git and a real checkout to list tracked files",
)
def test_no_tracked_instruction_file_is_excluded() -> None:
    patterns = _excludes()
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.splitlines()
    instruction_files = [path for path in tracked if INSTRUCTION_FILE.search(path)]
    assert "CLAUDE.md" in instruction_files, "expected the repository's own CLAUDE.md"
    hidden = [path for path in instruction_files if _excluded(path, patterns)]
    assert not hidden, (
        f"claudeMdExcludes hides instruction files this repository tracks: {hidden}"
    )
