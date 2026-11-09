"""What a test run left behind in the checkout.

A test that starts a process without its own working directory or environment
can write into the repository (a Windows PowerShell child without SystemDrive
created ``%SystemDrive%\\ProgramData\\...`` at the repo root). conftest.py
compares the checkout before and after the session.

``.pytest_cache`` is not reported: pytest writes a ``*`` .gitignore inside it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def checkout_changes(root: Path) -> frozenset[str] | None:
    """Untracked (not ignored) and modified paths, or None outside a work tree."""
    if not root.is_dir() or _git(root, "rev-parse", "--is-inside-work-tree").returncode:
        return None
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    modified = _git(root, "diff", "--name-only", "-z")
    if untracked.returncode or modified.returncode:
        return None
    return frozenset((untracked.stdout + modified.stdout).split("\0")) - {""}
