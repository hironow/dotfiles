"""Jev PowerShell launchers are installed for the native Windows bootstrap."""

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")


def test_powershell_launchers_are_in_native_deploy() -> None:
    windows_branch = DEPLOY.split("    exit 0", 1)[0]
    assert (
        'ps_jev_marker_begin="# >>> dotfiles managed block: Jev launchers >>>"'
        in windows_branch
    )
    # the Pi extensions come with the agent steps (test_deploy_pi_extensions)
    assert "(export MISE_NODE_COREPACK=0 && run_agent_steps)" in windows_branch
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
        encoding="utf-8",
        errors="replace",
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
        encoding="utf-8",
        errors="replace",
    )
    assert called.returncode == 0, called.stderr


@pytest.mark.parametrize(
    ("call", "forwarded"),
    [
        ("j-cc -r abc 'next step'", ["claude", "-r", "abc", "next step"]),
        ("j-pi --continue", ["pi", "--continue"]),
        ("j-cc --resume=abc", ["claude", "--resume=abc"]),
    ],
)
def test_powershell_forwards_the_resume_flags(call: str, forwarded: list[str]) -> None:
    # A function without a param block leaves -r / --continue in $args, so
    # they reach jev_launch.py as the hosts would read them
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell unavailable; Windows CI runs this")
    env = os.environ.copy()
    env["JEV_FUNCTIONS"] = DEPLOY.split("cat <<'POWERSHELL'\n", 1)[1].split(
        "\nPOWERSHELL", 1
    )[0]
    invoke = (
        "function mise { $global:seen = @($args) }; "
        "Invoke-Expression $env:JEV_FUNCTIONS; "
        f"{call}; "
        f"($global:seen | Select-Object -Last {len(forwarded)}) -join '|'"
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
    assert called.stdout.strip() == "|".join(forwarded)


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
        encoding="utf-8",
        errors="replace",
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
    # ps_profile_drop_block (scripts/ps_profile_lib.sh) runs drop_managed_block.awk.
    assert "ps_profile_drop_block \"$ps_profile\" 'Jev launchers'" in windows_branch


@pytest.mark.parametrize("fail_at", ["just", "uvx", ""])
def test_windows_ci_cannot_mask_a_native_failure(tmp_path: Path, fail_at: str) -> None:
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell unavailable; Windows CI runs this")
    workflow = (ROOT / ".github/workflows/unit-test.yaml").read_text(encoding="utf-8")
    matches = re.findall(
        r"^      - name: Check PowerShell launchers and HOME-less justfile\n"
        r"        shell: pwsh\n        run: \|\n((?:          [^\n]*\n)+)",
        workflow,
        re.MULTILINE,
    )
    assert len(matches) == 1, "missing or ambiguous Windows check step"
    body = textwrap.dedent(matches[0])
    guard = "$PSNativeCommandUseErrorActionPreference = $true"
    assert body.count(guard) == 1
    trace = tmp_path / "calls.txt"
    script = tmp_path / "ci-check.ps1"
    env = os.environ | {
        "JEV_CI_CALLS": str(trace),
        "JEV_CI_PYTHON": sys.executable,
        "JEV_CI_FAIL": fail_at,
    }
    # Each fake command invokes a real native process; no throw/exit in the
    # functions can accidentally make the old workflow pass this regression.
    functions = "\n".join(
        f"function {command} {{\n"
        f"  Add-Content -LiteralPath $env:JEV_CI_CALLS -Value '{command}'\n"
        "  & $env:JEV_CI_PYTHON -c "
        f'\'import os, sys; sys.exit(23 if os.environ["JEV_CI_FAIL"] == "{command}" else 0)\'\n'
        "}\n"
        for command in ("just", "uvx", "bun")
    )
    for hardened in [True, False] if fail_at else [True]:
        trace.unlink(missing_ok=True)
        tested = body if hardened else body.replace(guard, "")
        # Match GitHub's pwsh wrapper; the extracted body alone must enable
        # native fail-fast. Removing its guard is the negative control.
        script.write_text(
            "$ErrorActionPreference = 'Stop'\n"
            + functions
            + tested
            + "\nif (Test-Path variable:\\LASTEXITCODE) { exit $LASTEXITCODE }\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            [pwsh, "-NoProfile", "-NonInteractive", "-File", str(script)],
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        calls = trace.read_text(encoding="utf-8").splitlines()
        if hardened and fail_at:
            assert result.returncode != 0, result.stdout + result.stderr
            assert calls == (["just"] if fail_at == "just" else ["just", "uvx"])
        else:
            assert result.returncode == 0, result.stdout + result.stderr
            assert calls == ["just", "uvx", "bun"]
