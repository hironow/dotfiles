"""run_bash runs a script that is not under cwd, even on another drive."""

from __future__ import annotations

import os
from pathlib import Path

import _bash_hook
from _bash_hook import run_bash


def test_a_script_on_another_drive_is_staged_under_cwd(tmp_path, monkeypatch):
    # On Windows, os.path.relpath raises ValueError across drives: on the
    # windows-latest runner the checkout is on D: and the temp dir on C:.
    script = tmp_path / "elsewhere" / "hello.sh"
    script.parent.mkdir()
    script.write_text("echo hello\n", encoding="utf-8", newline="\n")
    cwd = tmp_path / "work"
    cwd.mkdir()
    relpath = os.path.relpath

    def across_drives(path, start=None):
        if Path(path) == script:
            raise ValueError("path is on mount 'D:', start on mount 'C:'")
        return relpath(path, start)

    monkeypatch.setattr(_bash_hook.os.path, "relpath", across_drives)
    result = run_bash(script, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "hello\n"
