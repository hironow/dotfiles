"""The bounded call doctor and sync share (agent_hook_release.run)."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import agent_hook_release as release

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.name == "nt", reason="Windows host B3 covers job objects")
def test_timeout_kills_grandchildren_before_they_can_write(tmp_path: Path) -> None:
    written = tmp_path / "grandchild-wrote"
    grandchild = (
        "import time; from pathlib import Path; "
        "print('ready', flush=True); time.sleep(1); "
        f"Path({str(written)!r}).write_text('late', encoding='utf-8')"
    )
    child = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}]); time.sleep(10)"
    )
    outcome = release.run([sys.executable, "-c", child], timeout=0.5)
    assert outcome.timed_out and "ready" in outcome.stdout
    time.sleep(1.2)
    assert not written.exists()


def test_the_group_is_killed_before_its_leader_is_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A skip in the body, not skipif: the type checker narrows on it.
    if sys.platform == "win32":
        pytest.skip("process groups are POSIX")
    # given a call that exits at once, leaving a grandchild in its group that
    # keeps stdout open and would write a file later
    written = tmp_path / "grandchild-wrote"
    grandchild = (
        "import time; from pathlib import Path; time.sleep(2); "
        f"Path({str(written)!r}).write_text('late', encoding='utf-8')"
    )
    child = (
        "import subprocess, sys; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}])"
    )
    # The leader's pid is the group's ID, and reaping the leader frees it for
    # another process: record the order of the group kill and the reap.
    events: list[str] = []
    real_killpg, real_waitpid = os.killpg, os.waitpid

    def killpg(group: int, number: int) -> None:
        events.append("kill")
        real_killpg(group, number)

    def waitpid(pid: int, options: int) -> tuple[int, int]:
        reaped = real_waitpid(pid, options)
        if reaped[0] != 0:
            events.append("reap")
        return reaped

    monkeypatch.setattr(release.os, "killpg", killpg)
    monkeypatch.setattr(release.os, "waitpid", waitpid)
    # when the grandchild holds the pipe past the deadline
    outcome = release.run([sys.executable, "-c", child], timeout=0.5)
    # then the group is killed before its leader is reaped, grandchild included
    assert outcome.timed_out
    assert events == ["kill", "reap"]
    time.sleep(2.2)
    assert not written.exists()


def test_a_pipe_held_from_outside_the_group_does_not_hold_doctor(
    tmp_path: Path,
) -> None:
    if sys.platform == "win32":
        pytest.skip("setsid is POSIX")
    # given a call that prints a line, and whose grandchild leaves the group
    # (setsid) and keeps both pipes open for 30 s, where no group kill
    # reaches it
    pid_file = tmp_path / "escaped.pid"
    child = (
        "import subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
        "start_new_session=True); "
        f"open({str(pid_file)!r}, 'w', encoding='utf-8').write(str(p.pid)); "
        "print('ready', flush=True); time.sleep(30)"
    )
    # A grace of 2 s keeps one grace shared by both pipes (2.5 s in all) far
    # from one grace per pipe (4.5 s), even on a loaded machine.
    parent = (
        f"import json, sys, time; sys.path.insert(0, {str(ROOT / 'scripts')!r}); "
        "import agent_hook_release as release; release.PIPE_GRACE = 2; "
        "started = time.monotonic(); "
        f"result = release.run([sys.executable, '-c', {child!r}], timeout=0.5); "
        "print(json.dumps([result.timed_out, time.monotonic() - started, "
        "result.stdout]), end='')"
    )
    started = time.monotonic()
    try:
        # when doctor's call times out
        done = subprocess.run(
            [sys.executable, "-c", parent], capture_output=True, timeout=15, check=False
        )
    except subprocess.TimeoutExpired:
        pytest.fail("doctor waited for the escaped process to let go of the pipe")
    finally:
        if pid_file.exists():
            os.kill(int(pid_file.read_text(encoding="utf-8")), signal.SIGKILL)
    # then the call returns after its limit plus one grace, with the line it
    # printed, and doctor exits long before the escaped process lets go
    assert done.returncode == 0, done
    timed_out, took, stdout = json.loads(done.stdout)
    assert timed_out and stdout == "ready\n", (timed_out, stdout)
    assert took < 0.5 + 2 + 1.0, took
    assert time.monotonic() - started < 10


def test_run_drains_both_streams_but_keeps_only_the_first_65536_bytes() -> None:
    command = """import sys, threading
writers = [threading.Thread(target=stream.write, args=(byte * 1048576,))
           for stream, byte in ((sys.stdout.buffer, b'a'), (sys.stderr.buffer, b'b'))]
for writer in writers: writer.start()
for writer in writers: writer.join()
"""
    outcome = release.run([sys.executable, "-c", command], timeout=5)
    assert outcome.ok
    assert outcome.stdout == "a" * 65536
    assert outcome.stderr == "b" * 65536
    assert outcome.stdout_bytes == 1048576


def test_endless_output_still_times_out_with_bounded_capture() -> None:
    command = """import sys, time
while True:
    sys.stdout.buffer.write(b'x' * 8192)
    sys.stdout.buffer.flush()
    time.sleep(0.001)
"""
    outcome = release.run([sys.executable, "-c", command], timeout=0.3)
    assert outcome.timed_out
    assert len(outcome.stdout.encode("utf-8")) <= 65536
    assert outcome.stdout_bytes > 65536


def test_run_accepts_input_bytes() -> None:
    outcome = release.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.stdout.buffer.write(sys.stdin.buffer.read())",
        ],
        input=b"hook-input\n",
        timeout=5,
    )
    assert outcome.ok and outcome.stdout == "hook-input\n"


def test_run_without_input_gives_eof_instead_of_inheriting_stdin() -> None:
    child = (
        "import sys; print('inherited' if sys.stdin.buffer.read() else 'eof', end='')"
    )
    parent = (
        f"import sys; sys.path.insert(0, {str(ROOT / 'scripts')!r}); "
        "import agent_hook_release as release; "
        f"result = release.run([sys.executable, '-c', {child!r}], timeout=1); "
        "assert result.ok, result; print(result.stdout, end='')"
    )
    done = subprocess.run(
        [sys.executable, "-c", parent],
        input=b"must not reach the child\n",
        capture_output=True,
        timeout=5,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == b"eof"
