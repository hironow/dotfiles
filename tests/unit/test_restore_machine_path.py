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


def test_missing_comparison_expands_env_vars() -> None:
    # Seen live 2026-08-17: the wiped-PATH incident was first repaired with
    # LITERAL entries (C:\Windows\system32); a later run of this script
    # compared UNEXPANDED strings, saw %SystemRoot%\system32 as "missing",
    # and appended it — doubling every System32 binary on PATH (5786
    # duplicate names; `just doctor` looked hung enumerating them).
    assert "ExpandEnvironmentVariables" in _code(), (
        "missing-entry comparison must expand env vars so "
        "%SystemRoot%\\system32 and a literal C:\\Windows\\system32 count "
        "as the same entry"
    )


def test_dedupes_existing_entries_by_expanded_value() -> None:
    # The same incident left both spellings already IN the Machine PATH;
    # merging correctly next time is not enough — the script must also
    # collapse pre-existing duplicates (by expanded, case-insensitive value)
    # so a repaired machine converges instead of staying doubled.
    assert re.search(r"dedup", _text(), re.IGNORECASE), (
        "must dedupe current Machine PATH entries by expanded value "
        "(keep one spelling per real directory)"
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


def test_git_bin_is_prepended_ahead_of_system32() -> None:
    r"""A bare `bash` on Windows resolves through PATH order, and System32
    carries the WSL launcher. Found live (2026-08-21): the box's historical
    "Git\bin before System32" Machine PATH ordering was lost in the
    2026-08-16 rebuild (this script appends, so the repair itself dropped
    the ordering), and the first CI job with a `shell: bash` step on the
    interactive runner died inside a WSL distro ("uv not on PATH", E#544).
    Workflow-side self-defence exists (hub prefer-git-bash), but jobs that
    inject no steps (CodeQL default setup) only have the box — so the
    rebuild script itself must own the ordering, or the next rebuild loses
    it again.

    Git\bin is safe to front-load: it holds bash/sh/git only (unlike
    usr\bin, which would shadow find/sort — the reason blanket prepends
    are banned in CLAUDE.md stays valid).
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert re.search(r"Git\\bin", text), (
        r"restore_machine_path.ps1 must manage the Git\bin entry."
    )
    assert "prepend" in text.lower(), (
        r"Git\bin must be PREPENDED (ahead of System32), not appended — "
        "append order is exactly how the 2026-08-16 rebuild lost it."
    )
    assert re.search(r"usr\\+bin", text), (
        r"the script must document why Git\bin and NOT Git\usr\bin "
        r"(usr\bin shadows find/sort; see the blanket-prepend ban)."
    )


def test_nothing_to_do_honours_ordering() -> None:
    r"""'Machine PATH already complete' must also require the ordering to
    be right — otherwise a PATH with Git\bin trailing System32 reports
    healthy and the repair never fires."""
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(
        r"if \(([^)]*)\) \{\s*\n\s*Write-Host 'Machine PATH already complete",
        text,
    )
    assert m is not None, "the nothing-to-do gate should exist"
    assert "order" in m.group(1).lower() or "prepend" in m.group(1).lower(), (
        "the nothing-to-do gate must include the ordering check."
    )


def test_doctor_detects_the_bash_shadow() -> None:
    r"""doctor must warn when the Machine PATH would resolve a bare `bash`
    to System32's WSL launcher (Git\bin absent or trailing System32) and
    point at the repair."""
    text = (SCRIPT.parent / "doctor.sh").read_text(encoding="utf-8")
    assert "win-bash-shadow" in text, (
        "doctor.sh needs a win-bash-shadow check on the Machine PATH."
    )
    assert text.count("restore_machine_path.ps1") >= 3, (
        "the bash-shadow WARN must point at restore_machine_path.ps1 "
        "(alongside the existing win-machine-path pointers)."
    )
