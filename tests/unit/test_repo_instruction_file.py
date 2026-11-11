"""The repository's own CLAUDE.md is a regular file that imports AGENTS.md.

AGENTS.md holds the repo-side rules for every agent. Claude Code reads
CLAUDE.md, so CLAUDE.md imports AGENTS.md with Claude's `@` syntax, the same
way the global ROOT_CLAUDE.md imports ROOT_AGENTS.md.

It must not be a symlink. A Windows checkout without core.symlinks (Git for
Windows' default) writes a symlink as a small text file holding the target's
name, so Claude would read "AGENTS.md" instead of the rules; and the sandbox
tests refuse to copy a tracked symlink (tests/test_just_sandbox.py).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _tracked_modes() -> dict[str, str]:
    out = subprocess.run(
        ["git", "ls-files", "-s"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    return {line.split("\t", 1)[1]: line.split()[0] for line in out.splitlines()}


def test_no_tracked_file_is_a_symlink():
    links = sorted(path for path, mode in _tracked_modes().items() if mode == "120000")
    assert not links, (
        f"tracked symlinks break Windows checkouts and the sandbox: {links}"
    )


def test_claude_md_imports_the_repo_rules():
    lines = (ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    assert "@AGENTS.md" in lines
    assert (ROOT / "AGENTS.md").is_file()
