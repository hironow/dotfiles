"""After a reboot nothing starts the WSL distro, so the runner service and
runner-gc.timer stay silent until a human opens a terminal (ADR 0035 family).

`wsl_autostart.ps1` + a logon-trigger Scheduled Task close that gap. Every
failure mode below is *silent* — the scripts exit 0, the runner just never
comes back:

- **Env-var distro default.** A Scheduled Task does not inherit the
  installer's shell environment, so a distro name left to an env-var default
  falls back to 'Ubuntu' at logon and starts the wrong (or no) distro, while
  every interactive run of the installer works. The name must be baked into
  the task's command line.
- **`wsl --list --running` failure semantics.** With no distro running —
  the exact case autostart exists for — wsl.exe exits non-zero. Under
  `$ErrorActionPreference = 'Stop'` pwsh 7 turns that into a terminating
  error (powershell.exe 5.1 does not), so the valve must treat a non-zero
  exit as "nothing is running" and proceed (fail-open), never throw.
- **Substring distro match.** 'Ubuntu' is a substring of 'Ubuntu-24.04'; a
  contains-match reports "already running" while the target distro is down,
  and the valve disables the very mechanism it guards.
- **UTF-16 output.** wsl.exe emits UTF-16LE by default; unstripped NULs make
  every name comparison fail, which reads as "not running" and double-starts
  (harmless) or garbles the status pipe (not harmless).
- **systemd contract.** Without `[boot] systemd=true` the distro starts,
  `true` runs, and no service ever comes up — all green logs, no runner. The
  payload must fail hard on `systemctl is-system-running` not reaching
  running/degraded.
- **Zero-match globs.** `systemctl is-active 'actions.runner.*'` exits 0
  when NO unit matches, so unit presence must be counted, not glob-checked.
- **Exit-code purity.** A duplicate Runner.Listener (someone ran run.sh by
  hand) is a different fact than "the distro failed to start"; folding it
  into the exit code turns the autostart task permanently red while it works
  perfectly. Duplicates are WARN here, FAIL in `just status`.
- **No keepalive = a 1-minute runner.** WSL terminates a distro shortly
  after its last CLIENT exits; systemd services inside do not count. This
  box's runner only ever survived because a terminal happened to stay open
  (measured live: graceful poweroff ~60-90s after the last wsl.exe client).
  A boot-and-exit autostart therefore protects nothing — the payload must
  END by blocking as a persistent keepalive client, and its Scheduled Task
  must carry no execution time limit (a limit kills the process tree and
  takes the keepalive with it).
- **pgrep self-match.** The keepalive-presence probe greps the marker out of
  process command lines; an unbracketed pattern matches the probe's own
  command line and reports "already attached" forever (same trap as
  `pgrep -f Runner.Worker` in runner_gc.sh).

Static checks plus behavioral runs against a stub wsl.exe (`-WslExe` exists
so the stub can be injected) whenever pwsh is available.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
AUTOSTART = SCRIPTS / "wsl_autostart.ps1"
INSTALL_WIN = SCRIPTS / "install_runner_gc_win.ps1"
INSTALL = SCRIPTS / "install_runner_gc.sh"
STATUS = SCRIPTS / "gc_status.sh"
PWSH = shutil.which("pwsh")

pwshonly = pytest.mark.skipif(PWSH is None, reason="needs pwsh to run the payload")


# --- static: installer wires the task correctly ------------------------------


def test_installer_registers_logon_autostart_task() -> None:
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert "dotfiles-wsl-autostart" in text, (
        "install_runner_gc_win.ps1 must register the WSL autostart task."
    )
    assert "-AtLogOn" in text, (
        "the autostart trigger must be logon: boot triggers need elevation "
        "and the WSL VM wants a user session."
    )
    assert "IgnoreNew" in text, (
        "overlapping firings must collapse to one (-MultipleInstances "
        "IgnoreNew) — duplicate-start valve."
    )
    assert "wsl_autostart.ps1" in text


def test_installer_bakes_distro_into_the_task_command_line() -> None:
    """A task does not inherit the installer's env, so an env-var default
    silently starts the wrong distro at logon."""
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert "-Distro {1}" in text, (
        "the distro name must be baked into the task's -Argument string, "
        "not left to a runtime default."
    )


def test_installer_does_not_claim_the_smoke_fire_proves_recovery() -> None:
    """At install time the distro is already running (the WSL leg installs
    first), so valve A short-circuits and LastTaskResult=0 proves nothing."""
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert "after the next reboot" in text, (
        "the installer must point at `just status` after a reboot as the "
        "real proof, not the immediate smoke fire."
    )


def test_installer_survives_an_unreplaceable_s4u_task() -> None:
    """The GC task registers S4U when elevated; a later UNELEVATED re-run
    cannot unregister it (access denied). The installer claims it needs no
    Administrator, so it must keep the existing task and continue to the
    autostart + hook steps instead of dying mid-install."""
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert "keeping it as-is" in text, (
        "install_runner_gc_win.ps1 must degrade gracefully when the "
        "existing S4U task cannot be unregistered unelevated."
    )


def test_bash_dispatcher_passes_the_resolved_distro() -> None:
    """install_runner_gc.sh resolves RUNNER_GC_WSL_DISTRO; the ps1 must get
    that same value instead of re-defaulting to 'Ubuntu'."""
    text = INSTALL.read_text(encoding="utf-8")
    assert '-Distro "$_distro"' in text, (
        "install_runner_gc.sh must forward the resolved distro to "
        "install_runner_gc_win.ps1."
    )


# --- static: payload survives its known failure modes ------------------------


def test_payload_is_fail_open_on_wsl_list_errors() -> None:
    text = AUTOSTART.read_text(encoding="utf-8")
    assert "$ErrorActionPreference = 'Continue'" in text, (
        "'Stop' + pwsh 7 turns wsl.exe's non-zero 'nothing running' exit "
        "into a terminating error; exit codes are data here."
    )
    assert "WSL_UTF8" in text, (
        "wsl.exe emits UTF-16LE by default; WSL_UTF8=1 is the primary fix, "
        "NUL stripping the fallback."
    )


def test_payload_matches_the_distro_exactly() -> None:
    text = AUTOSTART.read_text(encoding="utf-8")
    assert "-contains $Distro" in text, (
        "the running check must be an exact match — 'Ubuntu' is a substring "
        "of 'Ubuntu-24.04' and a contains-match silences the autostart."
    )
    assert "--quiet" in text, (
        "--quiet drops the locale-dependent header and ' (Default)' suffix."
    )


def test_payload_ends_as_a_blocking_keepalive_client() -> None:
    """systemd services do not keep a WSL distro alive — only a connected
    client does. Boot-and-exit would leave the runner dead ~1 min later."""
    text = AUTOSTART.read_text(encoding="utf-8")
    assert "dotfiles-wsl-keepalive" in text, (
        "the payload must attach a marked, persistent keepalive client."
    )
    assert "keepaliv[e]" in text, (
        "the presence probe must bracket-escape its pattern or it matches "
        "its own command line and reports 'already attached' forever."
    )


def test_installer_gives_the_keepalive_task_no_time_limit() -> None:
    """An ExecutionTimeLimit kills the task's process tree when it expires —
    including the keepalive, resurrecting the 1-minute-runner failure."""
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert "-ExecutionTimeLimit (New-TimeSpan -Seconds 0)" in text, (
        "the autostart task must run without a time limit; it IS the keepalive."
    )


def test_payload_enforces_the_systemd_contract() -> None:
    text = AUTOSTART.read_text(encoding="utf-8")
    assert "is-system-running" in text, (
        "without systemd the distro starts, nothing comes up, and every "
        "log line stays green — this must be a hard failure."
    )
    assert "list-units" in text, (
        "`is-active 'actions.runner.*'` exits 0 on zero matches; unit "
        "presence must be counted."
    )


# --- static: status surfaces the new facts -----------------------------------


def test_status_checks_the_autostart_task_by_trigger_shape() -> None:
    text = STATUS.read_text(encoding="utf-8")
    assert "MSFT_TaskLogonTrigger" in text, (
        "a logon task is Interactive by design, and LastTaskResult stays 0 "
        "when valve A short-circuits — the trigger class is the only "
        "structural check that means anything."
    )


def test_status_does_not_flag_a_running_keepalive_as_failure() -> None:
    """A forever-running task reports LastTaskResult 0x41301
    (SCHED_S_TASK_RUNNING = 267009). Treating non-zero as FAIL turns the
    healthy keepalive permanently red."""
    text = STATUS.read_text(encoding="utf-8")
    assert "267009" in text, (
        "gc_status.sh must exempt SCHED_S_TASK_RUNNING before judging the "
        "autostart task's LastTaskResult."
    )


def test_status_does_not_flag_a_running_gc_task_as_failure() -> None:
    """Same 267009 trap, other task: catch `just status` while the hourly GC
    task is mid-run and its LastTaskResult reads SCHED_S_TASK_RUNNING — seen
    live 2026-08-22 as a red `FAIL last run: result 267009` directly under a
    green `scheduled task: Running`. A red line that means 'healthy' trains
    the reader to ignore the line."""
    text = STATUS.read_text(encoding="utf-8")
    assert "running now (result 267009" in text, (
        "the GC task's last-run judgment must exempt SCHED_S_TASK_RUNNING "
        "(267009) and report it as running, exactly like the autostart "
        "task's judgment already does."
    )


def test_status_captures_distro_running_state_once_up_front() -> None:
    """The WSL probe itself boots the distro, so a check made after it always
    reads 'running' (order-dependent silent pass)."""
    text = STATUS.read_text(encoding="utf-8")
    capture = text.index("--quiet --running")
    first_leg = text.index("_windows_status() {")
    assert capture < first_leg, (
        "gc_status.sh must capture the running state before either leg "
        "executes, not inside one of them."
    )


def test_status_counts_runner_listeners_without_killing_set_e() -> None:
    text = STATUS.read_text(encoding="utf-8")
    assert "pgrep -cx Runner.Listener || true" in text, (
        "pgrep exits 1 on zero matches; under `set -e` a bare command "
        "substitution assignment aborts the whole status script."
    )


# --- behavioral: run the payload against a stub wsl.exe ----------------------

# No param() block: a [Parameter()] attribute would make the stub an advanced
# script, and PowerShell would then try to bind wsl.exe's flags to common
# parameters (-d is ambiguous with -Debug, -e with -ErrorAction/-ErrorVariable)
# instead of passing them through in $args.
STUB = r"""
$line = ($args | ForEach-Object { "$_" }) -join ' '
Add-Content -LiteralPath $env:STUB_LOG -Value $line
if ($line -like '*--list*--running*') {
    if ($env:STUB_RUNNING_NAMES) {
        foreach ($n in $env:STUB_RUNNING_NAMES -split ';') {
            if ($env:STUB_NULS -eq '1') {
                # emulate UTF-16LE mis-decoding: NUL after every char
                ($n.ToCharArray() -join "`0") + "`0"
            } else { $n }
        }
    }
    exit [int]"0$($env:STUB_RUNNING_EXIT)"
}
if ($line -like '*is-system-running*') { 'running'; exit 0 }
if ($line -like '*list-units*') { 'actions.runner.test.service loaded active running x'; exit 0 }
if ($line -like '*keepaliv*' -and $line -like '*pgrep*') {
    if ($env:STUB_KEEPALIVE -eq '1') { exit 0 } else { exit 1 }
}
if ($line -like '*pgrep*') { "$env:STUB_LISTENERS"; exit 0 }
exit 0
"""


def _run_payload(
    tmp_path: Path, env: dict[str, str]
) -> tuple[subprocess.CompletedProcess[str], str]:
    stub = tmp_path / "wsl_stub.ps1"
    stub.write_text(STUB, encoding="ascii")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="ascii")
    overrides = dict(os.environ)
    overrides.update(env)
    overrides["STUB_LOG"] = str(log)
    proc = subprocess.run(
        [
            str(PWSH),
            "-NoProfile",
            "-File",
            str(AUTOSTART),
            "-Distro",
            "Ubuntu",
            "-WslExe",
            str(stub),
        ],
        capture_output=True,
        text=True,
        env=overrides,
    )
    return proc, log.read_text(encoding="ascii")


@pwshonly
def test_sibling_distro_does_not_satisfy_the_running_check(tmp_path: Path) -> None:
    """'Ubuntu-24.04' running must not read as 'Ubuntu' running."""
    proc, calls = _run_payload(
        tmp_path, {"STUB_RUNNING_NAMES": "Ubuntu-24.04", "STUB_LISTENERS": "1"}
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "-d Ubuntu" in calls, (
        "the payload must still start 'Ubuntu' when only a sibling distro is running."
    )
    assert "while" in calls, "the keepalive must be attached for the target distro."


@pwshonly
def test_nothing_running_nonzero_exit_still_starts(tmp_path: Path) -> None:
    """wsl.exe exits non-zero when no distro runs — the case autostart is
    FOR. The payload must proceed, not throw or stay silent."""
    proc, calls = _run_payload(
        tmp_path,
        {"STUB_RUNNING_NAMES": "", "STUB_RUNNING_EXIT": "1", "STUB_LISTENERS": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "-d Ubuntu" in calls
    assert "while" in calls, "the keepalive must be attached."


@pwshonly
def test_existing_keepalive_short_circuits_even_with_nul_padding(
    tmp_path: Path,
) -> None:
    """A present keepalive means a prior instance already owns the distro's
    lifetime — attaching a second one would stack clients forever. The NUL
    padding on the running list must not defeat the exact-name match."""
    proc, calls = _run_payload(
        tmp_path,
        {"STUB_RUNNING_NAMES": "Ubuntu", "STUB_NULS": "1", "STUB_KEEPALIVE": "1"},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "already running" in proc.stdout, (
        "the NUL-stripped exact match must recognize the running distro."
    )
    assert "while" not in calls, (
        "the keepalive valve must short-circuit without attaching a second "
        "keepalive client."
    )


@pwshonly
def test_duplicate_listeners_warn_but_do_not_fail(tmp_path: Path) -> None:
    """Duplicates are someone else's launch, not this script's failure —
    folding them into the exit code turns the task permanently red."""
    proc, _ = _run_payload(tmp_path, {"STUB_LISTENERS": "3"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WARN" in proc.stdout
