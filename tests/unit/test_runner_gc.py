"""The disk-GC mechanism for both self-hosted runners must not silently
stop collecting (ADR 0035).

Why this exists
---------------
Every failure mode below is *silent* — the scripts still exit 0, they just stop
reclaiming, and the disk resumes its one-way growth until WSL can no longer
start:

- **Job detection.** `pgrep -f Runner.Worker` matches the GC script's own
  command line, so it reports "a job is running" 100% of the time and the GC
  skips forever. Only `pgrep -x` (exact executable name) is correct.
- **MSYS path mangling.** Git Bash rewrites unix-looking arguments
  (`/usr/local/bin/runner-gc`, `/mnt/c/...`, a bare `/`) into Windows paths
  before `wsl.exe` sees them, so every Windows->WSL dispatch must disable the
  conversion.
- **Half a sweep.** The Windows entrypoints must drive the native runner *and*
  the WSL one; an `exec` into WSL would drop the Windows leg silently.
- **Mojibake logs.** `powershell.exe` (5.1) reads a BOM-less UTF-8 script as
  ANSI, so the Windows scripts must stay ASCII-only to remain readable in the
  Scheduled Task's log — the only trace an unattended run leaves.

Static checks only (part of `tests/unit/`): the scripts drive a live runner,
systemd and the Windows task scheduler, none of which is reproducible
host-side.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
GC = SCRIPTS / "runner_gc.sh"
INSTALL = SCRIPTS / "install_runner_gc.sh"
COMPACT = SCRIPTS / "wsl_compact.sh"
GC_WIN = SCRIPTS / "runner_gc_win.ps1"
INSTALL_WIN = SCRIPTS / "install_runner_gc_win.ps1"
BASH = shutil.which("bash") or "/bin/bash"

# Every script that shells out to wsl.exe from a possible Git Bash host.
DISPATCHERS = (GC, INSTALL, COMPACT)


def test_job_detection_uses_exact_name_match() -> None:
    """`pgrep -f Runner.Worker` self-matches; only `pgrep -x` is correct."""
    text = GC.read_text(encoding="utf-8")
    assert re.search(r"pgrep\s+-x\s+Runner\.Worker", text), (
        "runner_gc.sh must detect a running job with `pgrep -x Runner.Worker`."
    )
    # -f may legitimately appear in a comment explaining the trap, so only
    # reject it as an actual invocation.
    bad = [
        line
        for line in text.splitlines()
        if re.search(r"^\s*[^#]*pgrep\s+(-\w*f\w*\s+)", line)
    ]
    assert not bad, (
        "runner_gc.sh invokes `pgrep -f`, which matches its own command line "
        f"and disables the GC permanently: {bad}"
    )


def test_dispatchers_disable_msys_path_conversion() -> None:
    """Git Bash mangles unix-looking argv before wsl.exe receives it."""
    for script in DISPATCHERS:
        text = script.read_text(encoding="utf-8")
        if "wsl.exe" not in text:
            continue
        assert "MSYS_NO_PATHCONV=1" in text and "MSYS2_ARG_CONV_EXCL" in text, (
            f"{script.name} calls wsl.exe without disabling MSYS path "
            "conversion; unix paths arrive rewritten to Windows paths."
        )


def test_retention_is_time_based_and_overridable() -> None:
    """The 2h budget is the decision in ADR 0035; keep it configurable."""
    text = GC.read_text(encoding="utf-8")
    assert 'RETENTION="${RUNNER_GC_RETENTION:-2h}"' in text, (
        "runner_gc.sh must default to a 2h retention overridable by "
        "RUNNER_GC_RETENTION."
    )
    # All three docker prunes must be age-filtered, never unconditional.
    for cmd in ("container prune", "image prune", "builder prune"):
        pattern = rf"docker {cmd}[^\n]*--filter \"until=\$\{{RETENTION\}}\""
        assert re.search(pattern, text), (
            f"`docker {cmd}` must carry the --filter until=$RETENTION guard."
        )


def test_gc_prunes_docker_container_buildx_builders() -> None:
    """`docker builder prune` does not reach docker-container builders."""
    text = GC.read_text(encoding="utf-8")
    assert "docker buildx prune" in text and "--builder" in text, (
        "runner_gc.sh must also prune non-default buildx builders, whose "
        "cache lives inside their own container."
    )


def test_installer_upserts_hook_without_duplicating() -> None:
    """Re-running the installer must not append the hook key twice."""
    text = INSTALL.read_text(encoding="utf-8")
    assert re.search(r'grep -v "\^\$\{_hook_key\}="', text), (
        "install_runner_gc.sh must strip the prior hook line before appending "
        "so repeated runs stay idempotent."
    )
    # `sed -i` is BSD/GNU-incompatible; reject real invocations but allow the
    # comment that explains why the upsert avoids it.
    bad = [
        line for line in text.splitlines() if re.search(r"^\s*[^#]*\bsed\s+-i\b", line)
    ]
    assert not bad, f"install_runner_gc.sh must stay portable (no `sed -i`): {bad}"


def test_compaction_stays_advisory() -> None:
    """Compaction stops the distro and kills CI; never self-apply it."""
    text = COMPACT.read_text(encoding="utf-8")
    assert "--shutdown" in text, "wsl_compact.sh should document the shutdown."
    assert not re.search(r"^\s*[^#]*wsl\.exe --shutdown", text, re.M), (
        "wsl_compact.sh must not execute `wsl --shutdown` itself — it would "
        "take the self-hosted runner offline without asking."
    )
    assert not re.search(r"^\s*[^#]*--allow-unsafe", text, re.M), (
        "sparse VHD is disabled by Microsoft over data corruption (ADR 0035); "
        "never force it on a CI host."
    )


def test_windows_scripts_are_ascii_only() -> None:
    """powershell.exe (5.1) reads a BOM-less UTF-8 script as ANSI.

    Any non-ASCII byte then arrives mojibake in the Scheduled Task log, which
    is the only record an unattended run leaves behind.
    """
    for script in (GC_WIN, INSTALL_WIN):
        raw = script.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), (
            f"{script.name} must not carry a UTF-8 BOM."
        )
        bad = [
            (n, line)
            for n, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1)
            if any(ord(ch) > 127 for ch in line)
        ]
        assert not bad, f"{script.name} must stay ASCII-only: {bad}"


def test_windows_gc_skips_while_a_job_runs() -> None:
    """Same job-safety contract as the Linux leg."""
    text = GC_WIN.read_text(encoding="utf-8")
    assert "Get-Process -Name 'Runner.Worker'" in text, (
        "runner_gc_win.ps1 must check for an in-flight job before pruning."
    )
    assert "--filter=until=$Retention" in text, (
        "Windows docker prunes must carry the same age filter as the WSL leg."
    )


def test_windows_installer_upserts_hook_without_bom() -> None:
    """The runner's .env parser chokes on a BOM, and re-runs must not stack."""
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert "UTF8Encoding($false)" in text, (
        "install_runner_gc_win.ps1 must write .env as UTF-8 without a BOM."
    )
    assert '-notmatch "^$hookKey="' in text, (
        "install_runner_gc_win.ps1 must drop the prior hook line so repeated "
        "runs stay idempotent."
    )
    assert "Unregister-ScheduledTask" in text, (
        "the installer must clear the old task so triggers do not stack."
    )


def test_windows_entrypoint_drives_both_runners() -> None:
    """`just runner-gc` must sweep the WSL *and* the native Windows runner."""
    for script, ps1 in (
        (GC, "runner_gc_win.ps1"),
        (INSTALL, "install_runner_gc_win.ps1"),
    ):
        text = script.read_text(encoding="utf-8")
        assert "wsl.exe" in text and ps1 in text, (
            f"{script.name}'s Windows branch must drive both legs, not just WSL."
        )
        assert "exec wsl.exe" not in text, (
            f"{script.name} must not `exec` into WSL — that would skip the "
            "Windows leg entirely."
        )


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "native Windows: bare `bash` resolves to System32 (WSL) bash, which "
        "cannot read the drive-lettered script path; runs on Linux/WSL/CI"
    ),
)
def test_scripts_parse() -> None:
    """`bash -n` every script so a syntax error cannot ship."""
    for script in (GC, INSTALL, COMPACT, SCRIPTS / "disk_gc.sh"):
        proc = subprocess.run([BASH, "-n", str(script)], capture_output=True, text=True)
        assert proc.returncode == 0, f"{script.name}: {proc.stderr}"
