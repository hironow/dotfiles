"""The runner GC's Linux leg never collects under a job it does not own.

ADR-0093 D4: a concurrency guard is held by a test that runs the code. These
run scripts/runner_gc.sh against a synthetic runner (RUNNER_GC_ROOT) with bash
function fakes for `uname`, `id`, `pgrep` and `podman`, and check what the
sweep removed:

- a running job is found by the executable name (`pgrep -x Runner.Worker`);
  any other pgrep form also matches processes that are not jobs (`-f` matches
  command lines), which the fake answers with a pid outside the GC's ancestry,
  so the GC would read a job that is not there and collect nothing;
- RUNNER_GC_FORCE bypasses the job guard for Podman only: the toolcache leg
  re-checks, since deleting a version a live job resolved breaks it;
- the workspace sweep backs off for a concurrent job unless the run names the
  install (RUNNER_GC_ROOT) and says it is safe (RUNNER_GC_ALLOW_BUSY=1).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from _bash_fakes import require_bash_fakes
from _bash_hook import bash_path, resolve_bash, run_bash

ROOT = Path(__file__).resolve().parents[2]
GC = ROOT / "scripts" / "runner_gc.sh"
FAKES = ("uname", "id", "pgrep", "podman", "wsl.exe", "powershell.exe")
LAUNCHERS = ("wsl.exe", "powershell.exe")
FOREIGN = "999999"
MONTH = 30 * 24 * 3600

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the Linux leg; bare bash on native Windows is WSL's",
)


def _gnu_find() -> bool:
    try:
        done = subprocess.run(
            ["find", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return False
    return done.returncode == 0 and "GNU" in done.stdout


def _age(path: Path) -> None:
    then = time.time() - MONTH
    os.utime(path, (then, then))


def _runner(tmp_path: Path) -> Path:
    """A runner install: .runner, a cold checkout, and two go patches."""
    root = tmp_path / "runner"
    (root / "_work" / "cold-repo" / "src").mkdir(parents=True)
    (root / ".runner").write_text("{}\n", encoding="utf-8")
    for version in ("1.25.0", "1.25.11"):
        arch = root / "_work" / "_tool" / "go" / version / "x64"
        arch.mkdir(parents=True)
        (arch.parent / "x64.complete").write_text("", encoding="utf-8")
    cold = root / "_work" / "cold-repo"
    _age(cold / "src")
    _age(cold)
    return root


def _run(
    tmp_path: Path, *, job_x: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the GC; `pgrep -x Runner.Worker` prints job_x, any other pgrep a
    pid outside the GC's ancestry."""
    if shutil.which("ps") is None:
        pytest.skip("needs ps")
    io = tmp_path / "io.sh"
    io.write_text(
        "uname() { echo Linux; }\n"
        "id() { echo 1000; }\n"
        f'pgrep() {{ if [ "$*" = "-x Runner.Worker" ]; then {job_x}; else echo {FOREIGN}; fi; }}\n'
        "podman() { return 127; }\n"
        "wsl.exe() { exit 91; }\n"
        "powershell.exe() { exit 91; }\n",
        encoding="utf-8",
    )
    bash_dir = Path(resolve_bash()).parent
    environ = {
        "PATH": ":".join(
            bash_path(p) for p in (bash_dir, Path("/usr/bin"), Path("/bin"))
        ),
        "HOME": str(tmp_path),
        "BASH_ENV": bash_path(io),
        "RUNNER_GC_ROOT": str(tmp_path / "runner"),
        **(env or {}),
    }
    require_bash_fakes(tmp_path, environ, FAKES, LAUNCHERS)
    return run_bash(
        GC,
        cwd=tmp_path,
        env=environ,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_a_worker_is_found_by_its_executable_name(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    done = _run(tmp_path, job_x="return 1")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "another runner job is executing" not in done.stdout
    assert not (runner / "_work" / "cold-repo").exists(), done.stdout


@pytest.mark.skipif(
    not _gnu_find(), reason="the toolcache leg lists versions with GNU find -printf"
)
def test_force_does_not_reach_the_toolcache(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    done = _run(tmp_path, job_x=f"echo {FOREIGN}", env={"RUNNER_GC_FORCE": "1"})
    assert done.returncode == 0, done.stdout + done.stderr
    assert "toolcache: SKIP" in done.stdout
    assert (runner / "_work" / "_tool" / "go" / "1.25.0").is_dir()


@pytest.mark.skipif(
    not _gnu_find(), reason="the toolcache leg lists versions with GNU find -printf"
)
def test_an_idle_runner_reaps_superseded_patches(tmp_path: Path) -> None:
    # The other half of the guard: with no job, the leg does run.
    runner = _runner(tmp_path)
    done = _run(tmp_path, job_x="return 1")
    assert done.returncode == 0, done.stdout + done.stderr
    assert not (runner / "_work" / "_tool" / "go" / "1.25.0").exists(), done.stdout
    assert (runner / "_work" / "_tool" / "go" / "1.25.11").is_dir()


def test_a_busy_runner_keeps_its_workspaces(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    done = _run(tmp_path, job_x=f"echo {FOREIGN}", env={"RUNNER_GC_FORCE": "1"})
    assert done.returncode == 0, done.stdout + done.stderr
    assert "workspaces: SKIP" in done.stdout
    assert (runner / "_work" / "cold-repo").is_dir()


def test_a_named_install_may_be_swept_when_busy_on_request(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    done = _run(
        tmp_path,
        job_x=f"echo {FOREIGN}",
        env={"RUNNER_GC_FORCE": "1", "RUNNER_GC_ALLOW_BUSY": "1"},
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert not (runner / "_work" / "cold-repo").exists(), done.stdout


def test_a_job_stops_the_whole_run(tmp_path: Path) -> None:
    runner = _runner(tmp_path)
    done = _run(tmp_path, job_x=f"echo {FOREIGN}")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "another runner job is executing" in done.stdout
    assert (runner / "_work" / "cold-repo").is_dir()
