"""On native Windows the POSIX disk adapter and the switch lock refuse plainly.

Windows imports agent_hook_wiring only for Roots (doctor, Codex trust). The
writers below are POSIX's; reached on Windows they must say so, not fail on
whatever POSIX call happens to be missing there.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import agent_hook_wiring as wiring

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="checks the native Windows refusal"
)


def test_real_disk_refuses_to_create_a_file(tmp_path):
    with pytest.raises(NotImplementedError, match="POSIX"):
        wiring.RealDisk().create(tmp_path / "file", 0o600)
    assert not (tmp_path / "file").exists()


def test_real_disk_refuses_to_flush_a_directory(tmp_path):
    with pytest.raises(NotImplementedError, match="POSIX"):
        wiring.RealDisk().fsync_directory(tmp_path)


def test_switch_lock_refuses_before_it_makes_anything(tmp_path):
    roots = wiring.Roots(data=tmp_path / "data", state=tmp_path / "state")
    with (
        pytest.raises(NotImplementedError, match="POSIX"),
        wiring.switch_lock(roots, wait_limit=0),
    ):
        pytest.fail("the lock was taken")
    assert not (tmp_path / "state").exists()
