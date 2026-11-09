"""Choosing the PowerShell that the PowerShell tests run."""

from __future__ import annotations

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
