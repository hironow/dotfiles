"""The unit-test session guard: a run must not leave files in the checkout."""

from __future__ import annotations

import subprocess
from pathlib import Path

from _checkout_guard import checkout_changes


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )


def test_checkout_changes_lists_untracked_and_modified_paths(tmp_path):
    _git(tmp_path, "init", "-q")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    _git(tmp_path, "add", "tracked.txt")
    assert checkout_changes(tmp_path) == frozenset()

    tracked.write_text("after\n", encoding="utf-8")
    (tmp_path / "%SystemDrive%").mkdir()
    (tmp_path / "%SystemDrive%" / "cache.db").write_text("x", encoding="utf-8")
    assert checkout_changes(tmp_path) == {"tracked.txt", "%SystemDrive%/cache.db"}


def test_checkout_changes_skips_ignored_paths(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("*.log\n", encoding="utf-8")
    (tmp_path / "run.log").write_text("x", encoding="utf-8")
    assert checkout_changes(tmp_path) == {".gitignore"}


def test_checkout_changes_is_none_outside_a_work_tree(tmp_path):
    assert checkout_changes(tmp_path / "not-a-checkout") is None
