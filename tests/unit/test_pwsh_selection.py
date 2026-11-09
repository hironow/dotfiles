"""Choosing the PowerShell that the PowerShell tests run."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from _pwsh import resolve_pwsh


def test_dotfiles_test_pwsh_selects_the_runtime():
    chosen = resolve_pwsh({"DOTFILES_TEST_PWSH": sys.executable})
    assert chosen is not None and Path(chosen).samefile(sys.executable)


def test_dotfiles_test_pwsh_must_name_an_executable(tmp_path):
    for override in (str(tmp_path / "missing"), str(tmp_path), ""):
        with pytest.raises(RuntimeError, match="DOTFILES_TEST_PWSH"):
            resolve_pwsh({"DOTFILES_TEST_PWSH": override})


def test_dotfiles_test_pwsh_wins_over_the_gc_alias(tmp_path):
    environ = {
        "DOTFILES_TEST_PWSH": sys.executable,
        "PODMAN_GC_TEST_PWSH": str(tmp_path / "missing"),
    }
    chosen = resolve_pwsh(environ)
    assert chosen is not None and Path(chosen).samefile(sys.executable)


def test_every_powershell_test_takes_the_override():
    # A test that looks pwsh up itself ignores DOTFILES_TEST_PWSH, so a run
    # on Windows PowerShell 5.1 would quietly test pwsh 7 instead.
    tests = Path(__file__).resolve().parents[1]
    lookup = re.compile(r"""\bwhich\(\s*["']pwsh(?:\.exe)?["']""")
    found = [
        f"{path.relative_to(tests)}:{number}"
        for path in sorted(tests.rglob("*.py"))
        if path.name != "_pwsh.py"
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        )
        if lookup.search(line)
    ]
    assert not found, f"use _pwsh.resolve_pwsh(os.environ) instead: {found}"
