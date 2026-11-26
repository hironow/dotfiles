"""`just disk-gc` must not delete a cache a runner job is building from.

Why this exists
---------------
On 2026-11-16 `disk_gc.sh clean` removed `~/.cargo/registry/{src,cache}` inside
WSL while the self-hosted runner compiled a Rust project for CI. cargo
runs rustc for a registry crate with that crate's unpacked source as its cwd,
so rustc panicked with "expecting a current working directory to exist" and
the job failed. "Regenerated on demand" never meant "safe to delete while in
use".

Each leg (the WSL distro and the Windows profile) guards its own runner before
every deletion step, and treats "cannot tell" as busy: a detection that fails
open is the same accident waiting for a quieter day.

The script runs against fakes only. A preflight proves the fakes are in force
and that no candidate path leaves the test's tmp dir before `clean` runs.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash, run_bash

ROOT = Path(__file__).resolve().parents[2]
DISK = ROOT / "scripts" / "disk_gc.sh"

UNAMES = {"linux": "Linux", "windows": "MINGW64_NT-10.0-26300"}

# Detection fakes answer only the exact argv the script must use; anything
# else (`pgrep -f`, a tasklist whose /FI got rewritten) exits 2, which a
# fail-closed script reads as "cannot tell" and so deletes nothing.
FAKES = {
    "uname": 'printf "%s\\n" "$FAKE_UNAME"\n',
    "pgrep": """[ "$*" = "-x Runner.Worker" ] || exit 2
case "$(fake_state)" in
  busy) echo 4242 ;;
  idle) exit 1 ;;
  *) exit 3 ;;
esac
""",
    "tasklist": """[ "$*" = "/FI IMAGENAME eq Runner.Worker.exe /FO CSV /NH" ] || exit 2
case "$(fake_state)" in
  busy) echo '"Runner.Worker.exe","4242","Console","1","1,024 K"' ;;
  idle) echo 'INFO: No tasks are running which match the specified criteria.' ;;
  *) exit 1 ;;
esac
""",
    "mise": 'echo "mise $*" >> "$FAKE_TRACE"\n',
    "go": 'echo "go $*" >> "$FAKE_TRACE"\n',
}

# FAKE_JOB=busy-after-gone reports idle until FAKE_WATCH has been deleted,
# then busy: a job that starts while the sweep is half way through.
STATE_FN = """fake_state() {
  case "$FAKE_JOB" in
    busy-after-gone) if [ -e "$FAKE_WATCH" ]; then echo idle; else echo busy; fi ;;
    *) echo "$FAKE_JOB" ;;
  esac
}
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text("#!/bin/sh\n" + STATE_FN + body, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _caches(home: Path, lad: Path, leg: str) -> list[Path]:
    """The candidates in the order disk_gc.sh sweeps them, per leg."""
    first = [
        home / ".bun/install/cache",
        home / ".cargo/registry/cache",
        home / ".cargo/registry/src",
    ]
    if leg == "windows":
        return [*first, lad / "uv/cache", lad / "npm-cache"]
    return [*first, home / ".cache/uv", home / ".cache/node-gyp"]


class Sandbox:
    def __init__(self, tmp_path: Path, leg: str) -> None:
        self.tmp = tmp_path
        self.home = tmp_path / "home"
        self.lad = tmp_path / "localappdata"
        self.bin = tmp_path / "fakebin"
        self.trace = tmp_path / "trace"
        for d in (self.home, self.lad, self.bin):
            d.mkdir()
        self.trace.touch()
        for name, body in FAKES.items():
            _write_exec(self.bin / name, body)
        self.caches = _caches(self.home, self.lad, leg)
        for c in self.caches:
            c.mkdir(parents=True)
            (c / "blob").write_text("x", encoding="utf-8")
        bash_dir = Path(resolve_bash()).parent
        dirs = [self.bin, bash_dir, bash_dir.parent / "usr/bin"]
        if os.name != "nt":
            dirs += [Path("/usr/bin"), Path("/bin")]
        self.env = {
            "PATH": ":".join(bash_path(p) for p in dirs),
            "HOME": bash_path(self.home),
            "LOCALAPPDATA": str(self.lad),
            "DISK_GC_NO_WSL": "1",
            "FAKE_UNAME": UNAMES[leg],
            "FAKE_JOB": "idle",
            "FAKE_WATCH": bash_path(self.caches[0]),
            "FAKE_TRACE": bash_path(self.trace),
            "SystemRoot": os.environ.get("SystemRoot", ""),
        }

    def run(self, mode: str, **extra: str):
        return run_bash(
            DISK,
            mode,
            cwd=self.tmp,
            env={**self.env, **extra},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    def preflight(self, **extra: str) -> None:
        """Refuse to run `clean` unless the fakes are in force and every
        candidate the script would touch sits under this test's tmp dir."""
        probe = self.tmp / "preflight.sh"
        probe.write_text(
            'for c in uname pgrep tasklist mise go; do type -P "$c"; done\n'
            "echo ---\n"
            'for c in wsl.exe powershell.exe tasklist.exe; do type -P "$c"; done\n'
            "exit 0\n",
            encoding="utf-8",
            newline="\n",
        )
        proc = run_bash(
            probe,
            cwd=self.tmp,
            env=self.env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        fakes, _, launchers = proc.stdout.partition("---")
        resolved = fakes.split()
        if len(resolved) != len(FAKES) or not all(
            p.startswith(bash_path(self.bin)) for p in resolved
        ):
            raise RuntimeError(f"fake layer not in force: {proc.stdout!r}")
        if launchers.split():
            raise RuntimeError(f"PATH reaches a host launcher: {launchers!r}")
        report = self.run("report", **extra)
        # Git Bash may print the same dir under another mount (%TEMP% shows
        # up as /tmp via cygpath), so match the tmp dir's unique tail.
        root = f"{self.tmp.parent.name}/{self.tmp.name}/"
        listed = re.findall(
            r"^\s+\S+\s+(\S*(?:cache|src)\S*)\s*$", report.stdout, re.MULTILINE
        )
        if not listed or any(root not in p for p in listed):
            raise RuntimeError(f"report lists paths outside the sandbox: {listed!r}")

    def traced(self) -> str:
        return self.trace.read_text(encoding="utf-8")


@pytest.fixture(params=sorted(UNAMES))
def box(request: pytest.FixtureRequest, tmp_path: Path) -> Sandbox:
    sandbox = Sandbox(tmp_path, request.param)
    sandbox.preflight()
    return sandbox


def test_idle_runner_lets_clean_reclaim_everything(box: Sandbox) -> None:
    """The control: a guard that always skips would silently stop the GC."""
    proc = box.run("clean")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SKIP" not in proc.stdout
    assert [c for c in box.caches if c.exists()] == []
    assert "mise prune" in box.traced() and "go clean" in box.traced()


def test_busy_runner_keeps_every_cache(box: Sandbox) -> None:
    box.env["FAKE_JOB"] = "busy"
    proc = box.run("clean")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SKIP: a runner job is executing" in proc.stdout
    assert [c for c in box.caches if not c.exists()] == []
    assert box.traced() == "", "mise prune / go clean ran during a job"


def test_detection_failure_fails_closed(box: Sandbox) -> None:
    box.env["FAKE_JOB"] = "broken"
    proc = box.run("clean")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "SKIP: cannot tell" in proc.stdout
    assert [c for c in box.caches if not c.exists()] == []
    assert box.traced() == ""


def test_a_job_starting_mid_sweep_stops_the_rest(box: Sandbox) -> None:
    """One check up front would leave minutes of `rm -rf` unguarded."""
    box.env["FAKE_JOB"] = "busy-after-gone"
    proc = box.run("clean")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "SKIP: a runner job is executing" in proc.stdout
    assert not box.caches[0].exists()
    assert all(c.exists() for c in box.caches[1:]), proc.stdout


def test_allow_busy_overrides_the_guard(box: Sandbox) -> None:
    box.env["FAKE_JOB"] = "busy"
    proc = box.run("clean", DISK_GC_ALLOW_BUSY="1")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert [c for c in box.caches if c.exists()] == []


@pytest.mark.parametrize(
    ("job", "word"), [("busy", "busy"), ("idle", "idle"), ("broken", "unknown")]
)
def test_report_shows_the_runner_job_state(tmp_path: Path, job: str, word: str) -> None:
    """report is the only path that runs the real detection on a live box."""
    box = Sandbox(tmp_path, "linux")
    box.env["FAKE_JOB"] = job
    proc = box.run("report")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert f"runner job: {word}" in proc.stdout
    assert all(c.exists() for c in box.caches)
