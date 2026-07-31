"""Symlink-capability probe for tests whose subject *is* symlink handling.

Windows grants symlink creation only to an elevated process or on a machine
with Developer Mode enabled; otherwise every attempt raises
``OSError: [WinError 1314] A required privilege is not held by the client``.

A test that asserts behaviour *about* symlinks cannot be rewritten to avoid
creating one, so on a host that withholds the privilege the honest outcome is
a skip, not a failure — the code under test is untested there, not broken.
Turning on Developer Mode (Settings > System > For developers) makes these
run for real. On POSIX the probe is always true.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest


def symlinks_available() -> bool:
    """True when this process may actually create a symlink."""
    if os.name != "nt":
        return True
    with tempfile.TemporaryDirectory() as d:
        target = Path(d) / "target"
        target.mkdir()
        try:
            (Path(d) / "link").symlink_to(target, target_is_directory=True)
        except (OSError, NotImplementedError):
            return False
    return True


requires_symlinks = pytest.mark.skipif(
    not symlinks_available(),
    reason="creating a symlink needs elevation or Developer Mode on Windows",
)
