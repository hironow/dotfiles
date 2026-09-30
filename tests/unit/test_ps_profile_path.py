"""The PowerShell 7 $PROFILE that deploy/clean/doctor edit must be the one
pwsh actually loads.

Found live (2026-09-30): deploy.sh / clean.sh / doctor.sh hardcoded
`$HOME/Documents/PowerShell/Microsoft.PowerShell_profile.ps1`. On a host whose
Documents folder is redirected to OneDrive, pwsh's real $PROFILE is
`C:\\Users\\<u>\\OneDrive\\ドキュメント\\PowerShell\\...`, so `just deploy` wrote
every managed block (starship, mise activate, corepack, Jev launchers) into a
file pwsh never reads, and `just doctor` reported the blocks "in sync" because
it checked the same wrong file.

The path now comes from scripts/ps_profile_lib.sh. These tests pin its
resolution order with fake `pwsh` / `powershell.exe` / `cygpath` executables
(the real ones exist only on Windows), including a non-ASCII path: without
forcing UTF-8 console output, pwsh returns the Japanese folder name as
mojibake.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "ps_profile_lib.sh"
SCRIPTS = {
    name: ROOT / "scripts" / f"{name}.sh" for name in ("deploy", "clean", "doctor")
}


def _unwrapped_bash() -> str | None:
    """Git for Windows' `<git>/bin/bash.exe` is a launcher that puts
    `<git>/usr/bin` on PATH before starting the real shell, so a real
    `cygpath` leaks into the fixture PATH (seen from PowerShell, where `bash`
    resolves to the launcher). Use the shell behind it when there is one."""
    found = shutil.which("bash")
    if found is None:
        return None
    exe = Path(found)
    real = exe.parent.parent / "usr" / "bin" / exe.name
    return str(real) if exe.parent.name.lower() == "bin" and real.is_file() else found


BASH = _unwrapped_bash()
LEGACY_TAIL = "Documents/PowerShell/Microsoft.PowerShell_profile.ps1"
ONEDRIVE_WIN = (
    "C:\\Users\\u\\OneDrive\\ドキュメント\\PowerShell\\Microsoft.PowerShell_profile.ps1"
)
ONEDRIVE_POSIX = (
    "/c/Users/u/OneDrive/ドキュメント/PowerShell/Microsoft.PowerShell_profile.ps1"
)

needs_posix_bash = pytest.mark.skipif(
    BASH is None or "system32" in BASH.lower(),
    reason=(
        "needs a POSIX bash that can run the fixture dir (WSL's System32 bash "
        "cannot read drive-lettered paths); runs on Linux CI and Git Bash"
    ),
)


def _fake(bin_dir: Path, name: str, body: str) -> None:
    exe = bin_dir / name
    exe.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8", newline="\n")
    exe.chmod(0o755)


# A cygpath stand-in for the two Windows paths these tests use; builtins only,
# so PATH can hold nothing but the fixture bin (a Git Bash host ships a real
# cygpath in /usr/bin, which would defeat the "no cygpath" case).
FAKE_CYGPATH = (
    'case "$2" in '
    f"'{ONEDRIVE_WIN}') echo '{ONEDRIVE_POSIX}' ;; "
    "'D:\\Docs') echo /d/Docs ;; "
    "*) exit 1 ;; esac"
)


def _resolve(
    tmp_path: Path, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    assert BASH is not None
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    env = {
        # Only the fixture bin: a real pwsh/powershell.exe/cygpath on the
        # host must not leak in (the lib and the fakes use builtins only).
        "PATH": str(bin_dir),
        "HOME": "/home/u",
        "SYSTEMROOT": str(tmp_path / "no-windows"),
        **(env_extra or {}),
    }
    return subprocess.run(
        [BASH, "-c", f'set -euo pipefail; . "{LIB.as_posix()}"; resolve_ps_profile'],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


@needs_posix_bash
def test_sourcing_the_lib_runs_no_external_command(tmp_path: Path) -> None:
    """The fixtures isolate PATH to their own bin (so a real pwsh or cygpath
    cannot leak in), so the lib must not need any external command just to be
    sourced; `dirname` there broke every test on macOS. A tool that fails when
    called stands in for "not on PATH" on hosts whose bash finds one anyway."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in ("dirname", "basename", "readlink", "realpath"):
        _fake(bin_dir, tool, f'echo "{tool} called" >&2; exit 97')
    assert BASH is not None
    r = subprocess.run(
        [
            BASH,
            "-c",
            f'set -euo pipefail; . "{LIB.as_posix()}"; echo "$_PS_PROFILE_LIB_DIR"',
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"PATH": str(bin_dir), "HOME": "/home/u"},
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert "called" not in r.stderr
    assert r.stdout.strip().endswith("/scripts")


@needs_posix_bash
def test_override_wins(tmp_path: Path) -> None:
    r = _resolve(tmp_path, {"DOTFILES_PS_PROFILE": "/x/profile.ps1"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "/x/profile.ps1"


@needs_posix_bash
def test_pwsh_profile_is_used_and_utf8_forced(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # The fake answers only when the command forces UTF-8 console output,
    # pinning the mojibake regression; it also prints a warning line first,
    # so the last non-empty line must be taken.
    _fake(
        bin_dir,
        "pwsh",
        'case "$*" in *OutputEncoding*UTF8*) '
        f"printf 'WARNING: noise\\r\\n{ONEDRIVE_WIN.replace(chr(92), chr(92) * 2)}\\r\\n' ;; "
        "*) exit 1 ;; esac",
    )
    _fake(bin_dir, "cygpath", FAKE_CYGPATH)
    r = _resolve(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == ONEDRIVE_POSIX


@needs_posix_bash
def test_windows_powershell_mydocuments_fallback(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake(bin_dir, "pwsh", "exit 1")
    _fake(bin_dir, "powershell.exe", "printf 'D:\\\\Docs\\r\\n'")
    _fake(bin_dir, "cygpath", FAKE_CYGPATH)
    r = _resolve(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "/d/Docs/PowerShell/Microsoft.PowerShell_profile.ps1"


@needs_posix_bash
@pytest.mark.parametrize("pwsh_out", ["", "not-a-path", "relative\\\\x.ps1"])
def test_unusable_probe_output_falls_back_to_legacy(
    tmp_path: Path, pwsh_out: str
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake(bin_dir, "pwsh", f"printf '{pwsh_out}\\r\\n'")
    _fake(bin_dir, "cygpath", FAKE_CYGPATH)
    r = _resolve(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"/home/u/{LEGACY_TAIL}"


@needs_posix_bash
def test_no_probes_available_falls_back_to_legacy(tmp_path: Path) -> None:
    r = _resolve(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"/home/u/{LEGACY_TAIL}"


@needs_posix_bash
def test_no_cygpath_falls_back_to_legacy(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake(
        bin_dir, "pwsh", f"printf '{ONEDRIVE_WIN.replace(chr(92), chr(92) * 2)}\\r\\n'"
    )
    r = _resolve(tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == f"/home/u/{LEGACY_TAIL}"


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_scripts_resolve_profile_instead_of_hardcoding(name: str) -> None:
    text = SCRIPTS[name].read_text(encoding="utf-8")
    assert 'ps_profile="$HOME/Documents/PowerShell' not in text, (
        f"{name}.sh hardcodes the legacy $PROFILE path; OneDrive-redirected "
        "Documents make pwsh load a different file"
    )
    assert "ps_profile_lib.sh" in text, (
        f"{name}.sh must source scripts/ps_profile_lib.sh"
    )
    assert "resolve_ps_profile" in text, f"{name}.sh must call resolve_ps_profile"


def test_clean_also_sweeps_legacy_profile() -> None:
    """Hosts deployed before the fix carry managed blocks in the legacy file;
    clean must still remove them there."""
    text = SCRIPTS["clean"].read_text(encoding="utf-8")
    assert "ps_profile_legacy" in text


def test_doctor_warns_on_stale_legacy_blocks() -> None:
    text = SCRIPTS["doctor"].read_text(encoding="utf-8")
    assert "ps_profile_legacy" in text
    assert "win-profile-legacy" in text


def test_clean_removes_every_block_deploy_writes() -> None:
    """Every managed block deploy.sh writes needs a sed range in clean.sh.

    Found live: #401's Jev launchers block had no removal, so clean left it in
    the legacy profile and doctor's `win-profile-legacy` advice (`just clean &&
    just deploy`) could never clear the warning."""
    marker = re.compile(r"# >>> dotfiles managed block: ([^>]+?) >>>")
    written = set(marker.findall(SCRIPTS["deploy"].read_text(encoding="utf-8")))
    removed = {
        name
        for line in SCRIPTS["clean"].read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("sed -i")
        for name in marker.findall(line)
    }
    assert written, "deploy.sh writes no managed blocks?"
    assert written <= removed, f"clean.sh never removes: {sorted(written - removed)}"
