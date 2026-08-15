"""`just doctor` as the native-Windows environment doctor (static-parse guards).

Why static: the Linux sandbox can't exercise a `uname`=MINGW branch and no CI
runner reproduces a stock native-Windows PowerShell PATH, so these guard the
Windows assurance wiring at PR-review time (same approach as
test_windows_setup_recipes.py).

Context: on native Windows, `just` translates the interpreter path of every
shebang recipe through `cygpath`. A stock persisted PATH carries Git\\bin
(bash) but not Git\\usr\\bin (cygpath), so from PowerShell every shebang
recipe dies with "could not find cygpath executable ..." while linewise
recipes keep working. Git Bash is immune (it prepends /usr/bin itself).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
DOCTOR_SH = ROOT / "scripts" / "doctor.sh"


@pytest.fixture(scope="module")
def justfile_text() -> str:
    return JUSTFILE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def doctor_text() -> str:
    return DOCTOR_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def doctor_windows_branch(doctor_text: str) -> str:
    m = re.search(
        r'case\s+"\$\(uname\s+-s\)"\s+in\s*\n\s*MINGW\*\|MSYS\*\|CYGWIN\*\)([\s\S]*?);;',
        doctor_text,
    )
    assert m is not None, (
        "doctor.sh has no uname-gated MINGW/MSYS/CYGWIN section; the Windows "
        "assurance checks must not run on Linux/macOS/WSL"
    )
    return m.group(1)


def _recipe_body(text: str, name: str) -> str:
    m = re.search(
        rf"(?ms)^{re.escape(name)}[^:\n]*:.*?\n(.*?)(?=^[A-Za-z_][\w-]*[^:\n]*:|\Z)",
        text,
    )
    assert m is not None, f"recipe {name!r} not found in justfile"
    return m.group(1)


def test_doctor_recipe_is_plain_bash_wrapper(justfile_text: str) -> None:
    """A shebang doctor cannot even start from PowerShell on a stock Windows
    PATH (no cygpath) — the diagnostics tool would die of the exact disease
    it exists to diagnose. It must stay a linewise plain-bash wrapper, which
    works from any shell and under any just version."""
    body = _recipe_body(justfile_text, "doctor")
    assert "#!" not in body, (
        "doctor must not be a shebang recipe: shebang recipes need cygpath on "
        "native Windows, which a stock PowerShell persisted PATH cannot reach"
    )
    assert re.search(r"@?bash scripts/doctor\.sh", body), (
        "doctor must delegate to scripts/doctor.sh via plain `bash` "
        "(linewise recipe, no shebang)"
    )


def test_doctor_checks_persisted_path_reaches_cygpath(
    doctor_windows_branch: str,
) -> None:
    """The doctor must check the persisted (registry) PATH — the current
    process PATH is useless because Git Bash always self-prepends /usr/bin —
    and teach the exact PowerShell one-liner fix."""
    win = doctor_windows_branch
    assert "cygpath -w /usr/bin" in win, (
        "must derive Git usr/bin dynamically via `cygpath -w /usr/bin` "
        "(install-location independent), not hardcode C:\\Program Files\\Git"
    )
    assert "GetEnvironmentVariable" in win, (
        "must read the persisted User+Machine PATH from the registry via "
        "powershell.exe — the in-process PATH always has /usr/bin under Git Bash"
    )
    assert "SetEnvironmentVariable" in win, (
        "on a miss it must print the copy-pasteable SetEnvironmentVariable "
        "fix, not just say 'PATH is wrong'"
    )


def test_doctor_checks_deploy_managed_state(doctor_windows_branch: str) -> None:
    """Stale deploy-managed state is the nastiest Windows gotcha (an ungated
    sheldon in ~/.config/mise/config.toml aborts every `mise exec` recipe).
    The doctor must diff the deployed artifacts and point at `just deploy`."""
    win = doctor_windows_branch
    assert "config/mise/config.toml" in win, (
        "must compare the deployed ~/.config/mise/config.toml against the "
        "repo copy (drift = e.g. missing sheldon os-gate)"
    )
    for marker in ("starship init", "mise activate", "mise node corepack"):
        assert marker in win, (
            f"must check the PowerShell profile managed block {marker!r} "
            "that `just deploy` owns"
        )
    assert "just deploy" in win, "the fix hint must name `just deploy`"


def test_doctor_checks_windows_uv_hardening(doctor_windows_branch: str) -> None:
    """Native Windows uv reads %APPDATA%\\uv\\uv.toml; without it the 7-day
    quarantine is off and any `uv run` rewrites committed uv.locks (this
    exact failure blocked commits via the pre-commit `just lint`)."""
    win = doctor_windows_branch
    assert (
        re.search(r"APPDATA.*uv[/\\]uv\.toml|uv[/\\]?uv\.toml", win)
        and "APPDATA" in win
    ), (
        "must check %APPDATA%/uv/uv.toml presence (the config uv actually "
        "reads on native Windows)"
    )
    assert "just harden-env" in win, "the fix hint must name `just harden-env`"


def test_doctor_checks_scoop_unix_clis(doctor_windows_branch: str) -> None:
    """Hooks and `just check` shell out to jq/shellcheck; on Windows they
    come from scoop and their absence fails with cryptic 'command not
    found's. The doctor must check and name the scoop install line."""
    win = doctor_windows_branch
    assert "jq" in win and "shellcheck" in win, "must check jq + shellcheck presence"
    assert "scoop install jq shellcheck" in win, (
        "the fix hint must be the exact scoop install command"
    )


def test_doctor_checks_persisted_path_reaches_git_cmd(
    doctor_windows_branch: str,
) -> None:
    """git.exe lives in Git\cmd, NOT usr\bin — a persisted PATH that only
    carries usr\bin (the cygpath fix) leaves fresh non-Git-Bash sessions
    with no git at all (fetch/clone: command not found). Seen live on this
    class of host; the doctor must detect it and point at the fix."""
    win = doctor_windows_branch
    assert "win-git-cmd" in win, (
        "doctor must emit a 'win-git-cmd' check: usr\bin on PATH does not "
        "imply git is reachable (git.exe is in Git\cmd)"
    )
    assert "cygpath -w /cmd" in win, (
        "must derive Git\cmd dynamically via `cygpath -w /cmd` "
        "(install-location independent), not hardcode C:\Program Files\Git"
    )
    assert "harden-env" in win, (
        "on a miss the doctor must point at `just harden-env`, which now "
        "appends the missing Git dirs to the persisted User PATH"
    )


def test_doctor_checks_machine_path_sanity(doctor_windows_branch: str) -> None:
    """Seen live: the HKLM Machine PATH was completely EMPTY, so every fresh
    shell was born without System32 (no powershell.exe/where.exe/reg.exe),
    masked for a long time because interactive shells inherited an enriched
    PATH from their parent. The doctor must detect it; repair stays manual
    (elevation + review of machine-specific entries)."""
    win = doctor_windows_branch
    assert "win-machine-path" in win, (
        "doctor must emit a 'win-machine-path' check for an empty or "
        "System32-less Machine PATH"
    )
    assert "ExpandString" in win, (
        "the printed fix must write REG_EXPAND_SZ via Registry.SetValue — "
        "SetEnvironmentVariable writes REG_SZ and leaves %SystemRoot% "
        "unexpanded at logon"
    )
    assert "ELEVATED" in win, (
        "must say the fix needs an elevated shell; doctor itself never "
        "writes the Machine scope"
    )


def test_doctor_powershell_fallback_when_system32_off_path(
    doctor_windows_branch: str,
) -> None:
    """A session spawned from a broken persisted PATH has no System32, so a
    bare `powershell.exe` dies with command-not-found — exactly when the
    doctor's Windows checks are needed most (seen live)."""
    assert "WindowsPowerShell/v1.0/powershell.exe" in doctor_windows_branch, (
        "doctor must fall back to powershell.exe by absolute path (via "
        "SYSTEMROOT) when it is not on PATH"
    )
