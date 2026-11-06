"""Bounded calls, and Go and hookrelease, for doctor and sync.

run() starts a program with a deadline and keeps a bounded share of what it
prints. go_environment() finds the Go that tools/agent-hooks builds with, and
build_hookrelease() and check_release() build and run cmd/hookrelease there.
"""

import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Thread
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/agent-hooks"
PROGRAM_TIMEOUT = 30
CHECK_TIMEOUT = 300
OUTPUT_LIMIT = 65536
PIPE_GRACE = 1


@dataclass(frozen=True)
class Outcome:
    exit_code: int | None = 0
    stdout: str = ""
    stderr: str = ""
    reason: str | None = None
    timed_out: bool = False
    stdout_bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.reason is None and not self.timed_out


def run(
    args: tuple[str, ...] | list[str],
    *,
    timeout: float,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    input: bytes | None = None,
) -> Outcome:
    """Run a call with a deadline, and keep what doctor reads of it.

    It keeps the exit code, the first OUTPUT_LIMIT bytes of stdout and of
    stderr, and stdout's whole size. On POSIX the call leads a session of its
    own. Past the deadline (the call, or a pipe it left open, still running)
    its whole process group is killed. On Windows only the call is killed
    (job objects are the Windows host's item B3). A process outside the group
    that still holds a pipe is not waited for past PIPE_GRACE.
    """
    try:
        child = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL if input is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
    except FileNotFoundError:
        return Outcome(None, reason=f"missing: {args[0]}")
    except (OSError, ValueError) as exc:
        return Outcome(None, reason=f"cannot start: {exc}")
    stdout = bytearray()
    stderr_output = bytearray()
    stdout_bytes = 0

    def drain(stream: BinaryIO, kept: bytearray, count_stdout: bool) -> None:
        nonlocal stdout_bytes
        with stream:
            # One read of the pipe at a time: a buffered read waits for 8 KiB
            # or EOF, and a pipe held from outside the group gives neither.
            while chunk := os.read(stream.fileno(), 8192):
                if count_stdout:
                    stdout_bytes += len(chunk)
                kept.extend(chunk[: max(0, OUTPUT_LIMIT - len(kept))])

    def feed(stream: BinaryIO, payload: bytes) -> None:
        try:
            with stream:
                stream.write(payload)
        except OSError:
            pass  # The call can exit, or close stdin, before it reads.

    assert child.stdout is not None and child.stderr is not None
    # Daemon threads: a pipe held from outside the group must not keep
    # doctor from exiting.
    pipes = [
        Thread(target=drain, args=(child.stdout, stdout, True), daemon=True),
        Thread(target=drain, args=(child.stderr, stderr_output, False), daemon=True),
    ]
    if input is not None:
        assert child.stdin is not None
        pipes.append(Thread(target=feed, args=(child.stdin, input), daemon=True))
    deadline = time.monotonic() + timeout
    for pipe in pipes:
        pipe.start()
    # The pipes first, then the call: the call is reaped only once it is
    # done, so a group kill never comes after the reap. The group's ID is the
    # call's pid, and a reap frees that pid for another process to take.
    for pipe in pipes:
        pipe.join(timeout=max(0, deadline - time.monotonic()))
    timed_out = any(pipe.is_alive() for pipe in pipes)
    if not timed_out:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
    if timed_out:
        if os.name == "nt":
            child.kill()
        else:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Every process of the group had already exited.
    child.wait()
    grace = time.monotonic() + PIPE_GRACE  # one grace for all the pipes
    for pipe in pipes:
        pipe.join(timeout=max(0, grace - time.monotonic()))
    stderr = bytes(stderr_output).decode("utf-8", errors="replace")
    reason = (
        f"timed out after {timeout:g} s"
        if timed_out
        else None
        if child.returncode == 0
        else f"exits {child.returncode}"
        + (f": {stderr.strip()}" if stderr.strip() else "")
    )
    return Outcome(
        None if timed_out else child.returncode,
        bytes(stdout).decode("utf-8", errors="replace"),
        stderr,
        reason,
        timed_out=timed_out,
        stdout_bytes=stdout_bytes,
    )


def go_environment(env: Mapping[str, str]) -> tuple[dict[str, str], Outcome]:
    """env with the Go that tools/agent-hooks builds with first on PATH.

    That Go is mise's, found in the module's directory; with no mise, PATH's
    `go`. The outcome says why there is none.
    """
    selected = dict(env)
    mise = shutil.which("mise", path=env.get("PATH", ""))
    if mise:
        outcome = run(
            [mise, "which", "go"], cwd=MODULE, env=env, timeout=PROGRAM_TIMEOUT
        )
        if not outcome.ok:
            return selected, replace(outcome, reason=f"mise which go: {outcome.reason}")
        go = outcome.stdout.strip()
        if not go or not Path(go).is_file() or not os.access(go, os.X_OK):
            return selected, Outcome(None, reason="mise which go: missing executable")
        selected["PATH"] = str(Path(go).parent) + os.pathsep + env.get("PATH", "")
    elif not shutil.which("go", path=env.get("PATH", "")):
        return selected, Outcome(None, reason="missing Go on PATH")
    return selected, Outcome()


def build_hookrelease(directory: Path, env: Mapping[str, str]) -> tuple[str, Outcome]:
    """Build cmd/hookrelease into directory, with env's Go (go_environment).

    It runs the program directly, not through the recipe: `go run` turns a
    child's exit 2 into 1.
    """
    checker = str(directory / "hookrelease")
    built = run(
        ["go", "build", "-o", checker, "./cmd/hookrelease"],
        cwd=MODULE,
        env=env,
        timeout=CHECK_TIMEOUT,
    )
    return checker, built


def check_release(checker: str, path: str, env: Mapping[str, str]) -> Outcome:
    """`hookrelease check PATH`: 0 the same bytes, 1 another release ID than
    this checkout's, 3 the same ID with other bytes, 2 cannot check."""
    return run([checker, "check", path], cwd=MODULE, env=env, timeout=CHECK_TIMEOUT)
