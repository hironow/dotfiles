"""Every anchored `.semgrepignore` entry must still name something.

An entry for a path that was deleted or never existed keeps reading as if
that path were exempt from the scan. If the path comes back, it inherits an
exemption nobody chose. An anchored entry (`/name`) must match a tracked file
or a gitignored path; an ignored directory pattern such as `/private/` only
matches with the trailing slash, so both forms are tried.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(),
    reason="needs git and a real checkout to resolve tracked and ignored paths",
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _anchored_entries() -> list[str]:
    lines = (ROOT / ".semgrepignore").read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip().startswith("/")]


def _names_something(entry: str) -> bool:
    path = entry.lstrip("/").rstrip("/")
    if _git("ls-files", "--", path).stdout.strip():
        return True
    # One path per call: with two paths, check-ignore exits 1 here even when
    # the second one is ignored.
    return any(
        _git("check-ignore", "-q", "--no-index", "--", form).returncode == 0
        for form in (path, f"{path}/")
    )


def test_every_anchored_semgrepignore_entry_names_something() -> None:
    entries = _anchored_entries()
    assert entries, ".semgrepignore has no anchored entry; the check would be empty"
    dead = [entry for entry in entries if not _names_something(entry)]
    assert not dead, (
        f".semgrepignore names paths that are neither tracked nor gitignored: {dead}. "
        "Remove the entries for paths that are gone."
    )
