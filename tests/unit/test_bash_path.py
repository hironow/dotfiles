"""bash_path spells a path the way bash reads it in a ':'-separated PATH."""

from __future__ import annotations

from pathlib import PurePath, PurePosixPath, PureWindowsPath

import pytest
from _bash_hook import bash_path


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (PureWindowsPath("C:/Users/x/bin"), "/c/Users/x/bin"),
        (PureWindowsPath("D:/tools"), "/d/tools"),
        (PureWindowsPath("//srv/share/bin"), "//srv/share/bin"),
        (PurePosixPath("/usr/local/bin"), "/usr/local/bin"),
    ],
    ids=["drive", "other-drive", "unc", "posix"],
)
def test_bash_path(path: PurePath, expected: str) -> None:
    assert bash_path(path) == expected
