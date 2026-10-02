"""Reading the persisted Windows environment (User or Machine) in one place.

ai_tools_check reads the telemetry switches harden-env persisted, and
claude_git_bash reads CLAUDE_CODE_GIT_BASH_PATH at both scopes; each opened
the registry itself. windows_env.persisted() is that read: None off Windows,
the values that are set (a missing one left out) on Windows.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import windows_env


def test_off_windows_there_is_nothing_to_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows_env.sys, "platform", "linux")
    assert windows_env.persisted(["Path"]) is None
    assert windows_env.persisted(["Path"], machine=True) is None


@pytest.mark.skipif(sys.platform != "win32", reason="reads the real registry")
def test_on_windows_set_values_are_read_and_missing_ones_left_out() -> None:
    machine = windows_env.persisted(["Path", "DOTFILES_NO_SUCH_VARIABLE"], machine=True)
    assert machine is not None
    assert "DOTFILES_NO_SUCH_VARIABLE" not in machine
    assert "system32" in machine["Path"].lower()
