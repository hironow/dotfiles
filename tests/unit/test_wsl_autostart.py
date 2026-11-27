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

The checks of what the scripts say (the task's trigger, IgnoreNew, no time
limit, run-hidden, the bracketed probe, the status lines) are the
`wsl-autostart-facts` rule of tools/repo-lint (ADR-0093). The tests here run
the payload with pwsh against a stub wsl.exe (`-WslExe` exists so the stub can
be injected). Valve A, one keepalive per distro, is a concurrency guard, so it
is held by a run too (ADR-0093 D4): the stub answers the presence probe as
`pgrep -f` would.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from _pwsh import resolve_pwsh

ROOT = Path(__file__).resolve().parents[2]
AUTOSTART = ROOT / "scripts" / "wsl_autostart.ps1"
PWSH = resolve_pwsh(os.environ)

pwshonly = pytest.mark.skipif(PWSH is None, reason="needs pwsh to run the payload")


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
    tmp_path: Path,
    env: dict[str, str],
    *,
    stub_text: str = STUB,
    script: Path = AUTOSTART,
) -> tuple[subprocess.CompletedProcess[str], str]:
    stub = tmp_path / "wsl_stub.ps1"
    stub.write_text(stub_text, encoding="utf-8")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    overrides = dict(os.environ)
    overrides.update(env)
    overrides["STUB_LOG"] = str(log)
    # The payload logs to %TEMP%; a test must never write the real one.
    overrides["TEMP"] = overrides["TMP"] = str(tmp_path)
    proc = subprocess.run(
        [
            str(PWSH),
            "-NoProfile",
            "-File",
            str(script),
            "-Distro",
            "Ubuntu",
            "-WslExe",
            str(stub),
        ],
        capture_output=True,
        text=True,
        env=overrides,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return proc, log.read_text(encoding="utf-8")


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
def test_payload_keeps_its_lines_in_a_log_file(tmp_path: Path) -> None:
    """The task starts through run-hidden, so it has no window to print to:
    every line Write-Log prints must also land in %TEMP%\\wsl-autostart.log,
    or the keepalive's last words ("keepalive exited ...") reach no one."""
    proc, _ = _run_payload(
        tmp_path, {"STUB_RUNNING_NAMES": "Ubuntu", "STUB_KEEPALIVE": "1"}
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    log = tmp_path / "wsl-autostart.log"
    assert log.is_file(), "Write-Log must append to %TEMP%\\wsl-autostart.log"
    text = log.read_text(encoding="utf-8")
    assert "already running" in text and "nothing to do" in text, text


@pwshonly
def test_duplicate_listeners_warn_but_do_not_fail(tmp_path: Path) -> None:
    """Duplicates are someone else's launch, not this script's failure —
    folding them into the exit code turns the task permanently red."""
    proc, _ = _run_payload(tmp_path, {"STUB_LISTENERS": "3"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "WARN" in proc.stdout


# --- behavioral: valve A, one keepalive per distro (ADR-0093 D4) -------------

# The presence probe answered as `pgrep -f` would: the pattern the payload
# sends, matched case-sensitively against a process table. pgrep skips only
# itself; the shell that runs it, and the WSL relay around that, keep the
# probe's text in their command lines. STUB_KEEPALIVE=1 adds a live keepalive.
# Everything else is answered as STUB does, and the keepalive itself returns.
PGREP_STUB = r"""
$line = ($args | ForEach-Object { "$_" }) -join ' '
Add-Content -LiteralPath $env:STUB_LOG -Value $line
if ($line -match "pgrep -f '([^']+)'") {
    $pattern = $Matches[1]
    $table = @('sh -c ' + $args[-1])
    if ($env:STUB_KEEPALIVE -eq '1') {
        $table += "sh -c : dotfiles-wsl-keepalive; while :; do sleep 3600; done"
    }
    if (@($table | Where-Object { $_ -cmatch $pattern }).Count -gt 0) { exit 0 }
    exit 1
}
if ($line -like '*--list*--running*') { 'Ubuntu'; exit 0 }
if ($line -like '*is-system-running*') { 'running'; exit 0 }
if ($line -like '*list-units*') { 'actions.runner.test.service loaded active running x'; exit 0 }
if ($line -like '*pgrep -cx*') { '1'; exit 0 }
exit 0
"""


def check_no_keepalive_attaches_one(tmp_path: Path, script: Path) -> None:
    proc, calls = _run_payload(tmp_path, {}, stub_text=PGREP_STUB, script=script)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "a keepalive client is already attached" not in proc.stdout, (
        "the presence probe matched its own command line"
    )
    assert "dotfiles-wsl-keepalive; while" in calls, calls


def check_a_live_keepalive_is_not_doubled(tmp_path: Path, script: Path) -> None:
    proc, calls = _run_payload(
        tmp_path, {"STUB_KEEPALIVE": "1"}, stub_text=PGREP_STUB, script=script
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "a keepalive client is already attached" in proc.stdout, proc.stdout
    assert "dotfiles-wsl-keepalive; while" not in calls, calls


@pwshonly
def test_the_probe_does_not_find_itself(tmp_path: Path) -> None:
    check_no_keepalive_attaches_one(tmp_path, AUTOSTART)


@pwshonly
def test_a_live_keepalive_is_not_doubled(tmp_path: Path) -> None:
    check_a_live_keepalive_is_not_doubled(tmp_path, AUTOSTART)
