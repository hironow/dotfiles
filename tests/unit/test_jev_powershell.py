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
    assert "function j-cc" in windows_branch
    assert "function j-pi" in windows_branch
    assert "function jev-claude" not in windows_branch
    assert "function jev-pi" not in windows_branch


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
    )
    assert result.returncode == 0, result.stderr
    invoke = (
        "function mise { $global:seen = @($args) }; "
        "Invoke-Expression $env:JEV_FUNCTIONS; "
        "j-pi 'hello world'; "
        "if ($global:seen[-1] -ne 'hello world' -or $global:seen[0] -ne 'exec') { exit 1 }"
    )
    called = subprocess.run(
        [pwsh, "-NoProfile", "-Command", invoke],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert called.returncode == 0, called.stderr


def test_the_zsh_launchers_are_short_names() -> None:
    zshrc = (ROOT / ".zshrc").read_text(encoding="utf-8")
    assert (
        'j-cc() { python3 "$HOME/dotfiles/scripts/jev_launch.py" claude "$@"; }'
        in zshrc
    )
    assert 'j-pi() { python3 "$HOME/dotfiles/scripts/jev_launch.py" pi "$@"; }' in zshrc
    assert "jev-claude()" not in zshrc and "jev-pi()" not in zshrc


BEGIN = "# >>> dotfiles managed block: Jev launchers >>>"
END = "# <<< end dotfiles managed block <<<"
OTHER = "# >>> dotfiles managed block: mise activate >>>\nactivate\n" + END
STALE = f"{BEGIN}\nfunction jev-claude {{ }}\n{END}"


def _refresh(profile: str) -> str:
    awk = shutil.which("awk")
    if not awk:
        pytest.skip("awk unavailable")
    result = subprocess.run(
        [
            awk,
            "-v",
            f"b={BEGIN}",
            "-v",
            f"e={END}",
            "-f",
            str(ROOT / "scripts/drop_managed_block.awk"),
        ],
        input=profile,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_the_stale_block_is_dropped_and_other_blocks_are_kept() -> None:
    profile = f"$x = 1\n\n{OTHER}\n\n{STALE}\n"
    out = _refresh(profile)
    assert "jev-claude" not in out and BEGIN not in out
    assert "$x = 1" in out and OTHER in out


def test_refreshing_does_not_pile_up_blank_lines() -> None:
    block = f"\n{BEGIN}\nfunction j-cc {{ }}\n{END}\n"
    profile = f"$x = 1\n{block}"
    for _ in range(3):
        profile = _refresh(profile) + block
    assert profile.count("function j-cc") == 1
    assert "\n\n\n" not in profile


def test_the_native_deploy_refreshes_the_block_instead_of_skipping_it() -> None:
    windows_branch = DEPLOY.split("    exit 0", 1)[0]
    assert "drop_managed_block.awk" in windows_branch
