"""Jev PowerShell launchers are installed for the native Windows bootstrap."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")


def test_powershell_launchers_are_in_native_deploy() -> None:
    windows_branch = DEPLOY.split("    exit 0", 1)[0]
    assert (
        'ps_jev_marker_begin="# >>> dotfiles managed block: Jev launchers >>>"'
        in windows_branch
    )
    assert (
        "MISE_NODE_COREPACK=0 mise -C / exec -- python ~/dotfiles/scripts/install_pi_extensions.py"
        in windows_branch
    )
    assert "function jev-claude" in windows_branch
    assert "function jev-pi" in windows_branch


def test_powershell_function_syntax() -> None:
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell unavailable; Windows CI runs this")
    functions = DEPLOY.split("cat <<'POWERSHELL'\n", 1)[1].split("\nPOWERSHELL", 1)[0]
    parser = (
        "$tokens=$null; $errors=$null; "
        "[System.Management.Automation.Language.Parser]::ParseInput($env:JEV_FUNCTIONS, "
        "[ref]$tokens, [ref]$errors) | Out-Null; "
        "if ($errors.Count -ne 0) { $errors | Out-String | Write-Error; exit 1 }"
    )
    env = os.environ.copy()
    env["JEV_FUNCTIONS"] = functions
    result = subprocess.run(
        [pwsh, "-NoProfile", "-Command", parser],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    invoke = (
        "function mise { $global:seen = @($args) }; "
        "Invoke-Expression $env:JEV_FUNCTIONS; "
        "jev-pi 'hello world'; "
        "if ($global:seen[-1] -ne 'hello world' -or $global:seen[0] -ne 'exec') { exit 1 }"
    )
    called = subprocess.run(
        [pwsh, "-NoProfile", "-Command", invoke],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    assert called.returncode == 0, called.stderr
