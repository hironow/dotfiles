"""Unit tests for sync_agents directory comparison.

Found live (2026-08-31): `_compare_directories` relied on
`filecmp.dircmp.diff_files`, which compares SHALLOWLY (size + mtime stat
signature). A changed file with the same byte length whose mtime collides at
the filesystem's timestamp granularity (observed on podman's virtiofs during
the e2e suite) was reported identical, so sync silently skipped the update.
`_compare_files` already used shallow=False; directories must too.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import _compare_directories


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_same_size_same_mtime_different_content_is_a_difference(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write(source / "SKILL.md", "# My Real Skill v2\n")
    _write(target / "SKILL.md", "# My Real Skill v1\n")
    # Force the shallow-comparison trap: identical size AND stat times.
    stamp = (1_700_000_000, 1_700_000_000)
    os.utime(source / "SKILL.md", stamp)
    os.utime(target / "SKILL.md", stamp)

    assert _compare_directories(source, target) is False


def test_identical_directories_compare_equal(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    for root in (source, target):
        _write(root / "SKILL.md", "# Same\n")
        _write(root / "nested" / "ref.md", "ref\n")

    assert _compare_directories(source, target) is True


def test_nested_same_size_change_is_detected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    target = tmp_path / "target"
    for root, marker in ((source, "aa"), (target, "bb")):
        _write(root / "SKILL.md", "# Same\n")
        _write(root / "nested" / "ref.md", f"{marker}\n")
    stamp = (1_700_000_000, 1_700_000_000)
    os.utime(source / "nested" / "ref.md", stamp)
    os.utime(target / "nested" / "ref.md", stamp)

    assert _compare_directories(source, target) is False
