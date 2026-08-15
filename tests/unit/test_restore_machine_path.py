"""scripts/restore_machine_path.ps1 — guarded repair for a wiped HKLM
Machine PATH (ADR-less operational tool; found live: len=0, every fresh
shell born without System32).

Why static: no CI runner can (or should) exercise an HKLM write; these pin
the safety wiring at PR-review time (same approach as test_runner_gc.py's
ps1 checks).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "restore_machine_path.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="ascii")


def _code() -> str:
    """Script minus full-line comments — execution assertions must not trip
    on comments explaining why an API is NOT used."""
    lines = _text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


def test_script_exists_and_is_ascii() -> None:
    assert SCRIPT.is_file(), "scripts/restore_machine_path.ps1 must exist"
    raw = SCRIPT.read_bytes()
    assert all(b < 128 for b in raw), (
        "must be ASCII-only: PowerShell 5.1 reads BOM-less UTF-8 as ANSI "
        "(same constraint as runner_gc_win.ps1 / bootstrap.ps1)"
    )


def test_writes_expandstring_never_setenvironmentvariable() -> None:
    text = _text()
    assert "ExpandString" in text, (
        "must write REG_EXPAND_SZ via Registry.SetValue — "
        "SetEnvironmentVariable/setx write REG_SZ and %SystemRoot% then "
        "never expands at logon"
    )
    assert "SetEnvironmentVariable" not in _code(), (
        "must not use SetEnvironmentVariable for the Machine scope at all"
    )


def test_merges_instead_of_clobbering() -> None:
    # If Machine PATH is NOT empty the script must append missing entries,
    # never replace wholesale — a partial wipe repair must not destroy
    # surviving machine-specific entries.
    assert re.search(r"-notin|NotContains|missing", _text(), re.IGNORECASE), (
        "must merge (append missing entries) into an existing Machine PATH, "
        "not overwrite it"
    )


def test_detects_optional_dirs_instead_of_hardcoding_users() -> None:
    text = _text()
    assert "Test-Path" in text, (
        "optional entries (PowerShell 7, LLVM, Docker, scoop/bun/mise shims) "
        "must be probed with Test-Path so the script ports across machines"
    )
    assert "USERPROFILE" in text, (
        "per-user shim dirs must derive from $env:USERPROFILE, not a "
        "hardcoded C:/Users/<name>"
    )
    assert not re.search(r"C:\\Users\\[A-Za-z]", text), (
        "no hardcoded user-profile paths"
    )


def test_requires_apply_switch_and_self_elevates() -> None:
    text = _text()
    assert "-Apply" in text or "$Apply" in text, (
        "default run must be a dry-run preview; the write happens only "
        "under an explicit -Apply switch"
    )
    assert "RunAs" in text, (
        "must self-elevate via Start-Process -Verb RunAs when not admin "
        "(HKLM write needs elevation; UAC keeps the human in the loop)"
    )


def test_parses_as_valid_powershell() -> None:
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    if pwsh is None:
        pytest.skip("no PowerShell available to parse-check")
    check = (
        "$t=$null;$e=$null;"
        "[System.Management.Automation.Language.Parser]::ParseFile("
        f"'{SCRIPT}',[ref]$t,[ref]$e)|Out-Null;"
        "if($e.Count -gt 0){$e|ForEach-Object{$_.ToString()};exit 1}"
    )
    proc = subprocess.run(
        [pwsh, "-NoProfile", "-Command", check],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, (
        "restore_machine_path.ps1 has syntax errors:\n" + proc.stdout
    )
