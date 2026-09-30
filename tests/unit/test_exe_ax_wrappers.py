"""ax-job and ax-exec, the operator's way to run work in AX tasks (Phase 6 plan D12).

The wrappers run under bash with stub `exe-reaper`, `gcloud` and `ax` on PATH,
each logging every call it gets, one line per call with its argv quoted.

The `ax` stub is a small fake AX. Tasks and their phases live in files, a
Pending task turns Running after a set number of `ax get tasks` calls, and
`ax ssh` runs the command it carries on this machine, with /tmp/ax-job/ moved
under the test's own directory. So the guest half, exe/scripts/ax-job-guest.sh,
really runs: under dash, Debian's /bin/sh and so the task image's, where this
machine has it. That covers the detached launch, the polls and the
process-group kill, not a description of them. Transport failures are
injected per call: a poll that resets, or a launch that ran but whose reply
was lost.

The Claude token is synthetic and built by concatenation, so no credential
pattern ever appears in this file.
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

# POSIX process groups and bash/dash stubs: on Windows the guest launch hangs
# and os.killpg does not exist. The platform check also lets ty skip the rest.
if sys.platform == "win32":
    pytest.skip("POSIX-only: process groups and shell stubs", allow_module_level=True)

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "exe" / "scripts"
AX_JOB = SCRIPTS / "ax-job"
AX_EXEC = SCRIPTS / "ax-exec"
GUEST = SCRIPTS / "ax-job-guest.sh"
BASH = shutil.which("bash") or "/bin/bash"
GUEST_SH = "/bin/dash" if Path("/bin/dash").exists() else "sh"

TASK_REPO = "asia-northeast1-docker.pkg.dev/zz-p/exe-task"
DIGEST = "4f2b9d0c485ef63591557233792ce033c71efc6716a3b9508dc637ff10649e83"
IMAGE = f"{TASK_REPO}/task:42ec88ce7815005a@sha256:{DIGEST}"
TOKEN = "sk-ant-" + "oat01-" + "zZ9_" * 20

TASKS_HEADER = "NAME   ATESPACE   PHASE   ACTOR   WORKER-IP   AGE\n"

EXE_REAPER_STUB = r"""#!/usr/bin/env bash
{ printf 'exe-reaper'; printf ' %q' "$@"; printf '\n'; } >> "$FAKE_LOG"
[ "$1" = may-start ] || { echo "stub exe-reaper: unexpected call: $*" >&2; exit 97; }
n=$(( $(cat "$FAKE_STATE/may-start" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$FAKE_STATE/may-start"
IFS=, read -r -a answers <<< "$FAKE_MAY_START"
rc="${answers[$((n - 1))]:-${answers[-1]}}"
if [ "$rc" = 0 ]; then echo "may start"; exit 0; fi
echo "exe-reaper: refused: the lease has 4m0s left, and this needs 35m0s (just exe-extend)" >&2
exit "$rc"
"""

GCLOUD_STUB = r"""#!/usr/bin/env bash
{ printf 'gcloud'; printf ' %q' "$@"; printf '\n'; } >> "$FAKE_LOG"
case " $* " in
  *" artifacts docker images describe "*)
    if [ -n "${FAKE_IMAGE_MISSING:-}" ]; then echo "ERROR: image not found" >&2; exit 1; fi ;;
  *" artifacts docker tags add "*)
    if [ -n "${FAKE_TAG_FAIL:-}" ]; then echo "ERROR: permission denied" >&2; exit 1; fi ;;
  *" secrets versions access "*) printf '%s' "$FAKE_TOKEN" ;;
  *) echo "stub gcloud: unexpected call: $*" >&2; exit 97 ;;
esac
"""

# The fake AX. `ax ssh NAME -a ATESPACE -- CMD...` runs CMD here, as the real
# one runs it in the task, and exits with its status. Faults, keyed by the
# guest operation and its count ("poll:2" is the second poll):
#   FAKE_SSH_RESET       the call fails at the transport and nothing runs
#   FAKE_SSH_RESET_ALL   every call of that operation fails so
#   FAKE_SSH_LOST_REPLY  the command runs, but its reply is lost
#   FAKE_SUSPEND_AT      at that poll, a drain has suspended the task
AX_STUB = r"""#!/usr/bin/env bash
{ printf 'ax'; printf ' %q' "$@"; printf '\n'; } >> "$FAKE_LOG"
tasks="$FAKE_STATE/tasks"
reset() {
  echo "rpc error: code = Internal desc = stream terminated by RST_STREAM with error code: INTERNAL_ERROR" >&2
  exit 1
}
case "$1" in
  apply)
    n=$(( $(ls "$FAKE_STATE/applied" | wc -l) + 1 ))
    cp "$3" "$FAKE_STATE/applied/$n.yaml"
    name="$(awk '$1 == "name:" { print $2; exit }' "$3")"
    echo Pending > "$tasks/$name"
    echo "${FAKE_RUNNING_AFTER:-1}" > "$FAKE_STATE/countdown-$name"
    echo "task.ax.io/$name created" ;;
  get)
    printf 'NAME   ATESPACE   PHASE   ACTOR   WORKER-IP   AGE\n'
    for f in "$tasks"/*; do
      [ -e "$f" ] || continue
      name="${f##*/}"
      phase="$(cat "$f")"
      if [ "$phase" = Pending ] && [ -f "$FAKE_STATE/countdown-$name" ]; then
        left="$(cat "$FAKE_STATE/countdown-$name")"
        if [ "$left" -le 0 ]; then
          refused=$(cat "$FAKE_STATE/refusals" 2>/dev/null || echo 0)
          if [ "$refused" -lt "${FAKE_NO_WORKER:-0}" ]; then
            echo $((refused + 1)) > "$FAKE_STATE/refusals"
            phase=Failed
            echo "no free workers" > "$FAKE_STATE/reason-$name"
          else
            phase="${FAKE_START_PHASE:-Running}"
            rm -f "$FAKE_STATE/reason-$name"
          fi
          echo "$phase" > "$f"
        else
          echo $((left - 1)) > "$FAKE_STATE/countdown-$name"
        fi
      fi
      printf '%s   exe   %s   %s   10.0.0.9   1m\n' "$name" "$phase" "$name"
    done ;;
  ssh)
    name="$2"
    while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do shift; done
    shift
    phase="$(cat "$tasks/$name" 2>/dev/null || true)"
    if [ "$phase" != Running ]; then
      echo "fetching task \"$name\": task is in phase \"$phase\" (must be Running to ssh)" >&2
      exit 1
    fi
    op="${5:-}"
    n=$(( $(cat "$FAKE_STATE/ssh-$op" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$FAKE_STATE/ssh-$op"
    if [ "$op" = poll ] && [ -n "${FAKE_SUSPEND_AT:-}" ] && [ "$n" -ge "$FAKE_SUSPEND_AT" ]; then
      echo Suspended > "$tasks/$name"
      echo "fetching task \"$name\": task is in phase \"Suspended\" (must be Running to ssh)" >&2
      exit 1
    fi
    if [[ " ${FAKE_SSH_RESET:-} " == *" $op:$n "* ]] || [ "${FAKE_SSH_RESET_ALL:-}" = "$op" ]; then reset; fi
    args=("${FAKE_GUEST_SH:-sh}")
    shift
    for a in "$@"; do args+=("${a/#\/tmp\/ax-job\//$FAKE_GUEST/ax-job/}"); done
    if [[ " ${FAKE_SSH_LOST_REPLY:-} " == *" $op:$n "* ]]; then
      "${args[@]}" > /dev/null 2>&1
      reset
    fi
    exec "${args[@]}" ;;
  delete) rm -f "$tasks/$3" "$FAKE_STATE/reason-$3"; echo "task \"$3\" deleted" ;;
  describe)
    printf 'Name:         %s\nPhase:        %s\n\nConditions:\n' "$3" "$(cat "$tasks/$3" 2>/dev/null)"
    if [ -f "$FAKE_STATE/reason-$3" ]; then
      printf '  Ready  False   ActorResumeFailed  resuming actor exe/%s: rpc error: code = ResourceExhausted desc = no free workers available\n' "$3"
    fi ;;
  suspend) echo Suspended > "$tasks/$3"; echo "task \"$3\" suspended" ;;
  resume)
    echo Pending > "$tasks/$3"
    echo "${FAKE_RUNNING_AFTER:-1}" > "$FAKE_STATE/countdown-$3"
    echo "task \"$3\" resumed" ;;
  *) echo "stub ax: unexpected call: $*" >&2; exit 97 ;;
esac
"""

# macOS has no setsid(1); Debian's does exactly this: a new session, then exec.
SETSID_SHIM = """#!/usr/bin/env python3
import os
import sys

os.setsid()
os.execvp(sys.argv[1], sys.argv[1:])
"""


@dataclass
class Run:
    result: subprocess.CompletedProcess[str]
    calls: list[str]
    state: Path
    guest: Path

    @property
    def code(self) -> int:
        return self.result.returncode

    def called(self, prefix: str) -> list[str]:
        return [c for c in self.calls if c.startswith(prefix)]

    def index(self, prefix: str) -> int:
        return next(i for i, c in enumerate(self.calls) if c.startswith(prefix))

    def ssh(self, op: str) -> list[str]:
        """The `ax ssh` calls that carried guest operation `op`."""
        return [c for c in self.called("ax ssh") if f" ax-job-guest {op} " in c]

    def task(self, name: str) -> str | None:
        f = self.state / "tasks" / name
        return f.read_text(encoding="utf-8").strip() if f.exists() else None

    def applied(self) -> list[str]:
        return [
            p.read_text(encoding="utf-8")
            for p in sorted((self.state / "applied").glob("*.yaml"))
        ]


def setup(tmp_path: Path, tasks: dict[str, str] | None = None) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    for name, body in (
        ("exe-reaper", EXE_REAPER_STUB),
        ("gcloud", GCLOUD_STUB),
        ("ax", AX_STUB),
        ("setsid", SETSID_SHIM),
    ):
        stub = bin_dir / name
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    (tmp_path / "state" / "tasks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "state" / "applied").mkdir(exist_ok=True)
    (tmp_path / "guest").mkdir(exist_ok=True)
    for name, phase in (tasks or {}).items():
        (tmp_path / "state" / "tasks" / name).write_text(phase + "\n", encoding="utf-8")


def run(tmp_path: Path, script: Path, *args: str, **fake: str) -> Run:
    setup(tmp_path)
    log = tmp_path / "calls.log"
    log.touch()
    env = {
        "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "FAKE_LOG": str(log),
        "FAKE_STATE": str(tmp_path / "state"),
        "FAKE_GUEST": str(tmp_path / "guest"),
        "FAKE_GUEST_SH": GUEST_SH,
        "FAKE_MAY_START": "0",
        "FAKE_TOKEN": TOKEN,
        "EXE_AR_TASK_REPO": TASK_REPO,
        "EXE_CLAUDE_SECRET": "exe-claude-oauth-token",
        "EXE_PROJECT_ID": "zz-p",
        "AX_ATESPACE": "exe",
        "AX_JOB_POLL_SECONDS": "0.1",
        "AX_JOB_START_SECONDS": "5",
        "AX_JOB_SSH_SECONDS": "20",
        "AX_JOB_MAX_POLL_FAILURES": "3",
        **fake,
    }
    result = subprocess.run(
        [BASH, str(script), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        encoding="utf-8",
        errors="replace",
    )
    return Run(
        result,
        log.read_text(encoding="utf-8").splitlines(),
        tmp_path / "state",
        tmp_path / "guest",
    )


def job(tmp_path: Path, *cmd: str, flags: tuple[str, ...] = (), **fake: str) -> Run:
    return run(
        tmp_path, AX_JOB, "--image", IMAGE, "--name", "j1", *flags, "--", *cmd, **fake
    )


# --- ax-job: the exit code and the task's end ---------------------------------


@pytest.mark.parametrize("code", [0, 7])
def test_the_commands_exit_code_is_ax_jobs_own(tmp_path: Path, code: int) -> None:
    r = job(tmp_path, "sh", "-c", f"echo hello from the task; exit {code}")

    assert r.code == code, r.result.stderr
    assert "hello from the task" in r.result.stdout
    # and the task is gone, whatever the command's code was
    assert r.called("ax delete task j1")
    assert r.task("j1") is None


def test_keep_on_failure_keeps_only_a_failed_tasks_task(tmp_path: Path) -> None:
    failed = job(tmp_path / "a", "sh", "-c", "exit 7", KEEP_ON_FAILURE="1")
    assert failed.code == 7
    assert not failed.called("ax delete")
    assert failed.task("j1") == "Running"

    passed = job(tmp_path / "b", "true", KEEP_ON_FAILURE="1")
    assert passed.code == 0
    assert passed.called("ax delete task j1")


def test_the_output_arrives_whole_and_in_order(tmp_path: Path) -> None:
    # given a command that writes across several polls, without a final newline
    r = job(
        tmp_path,
        "sh",
        "-c",
        "for i in 1 2 3; do echo line $i; sleep 0.3; done; printf tail",
    )
    assert r.code == 0, r.result.stderr
    assert r.result.stdout.splitlines() == ["line 1", "line 2", "line 3", "tail"]


# --- ax-job: the image ------------------------------------------------------------


def test_an_image_is_required(tmp_path: Path) -> None:
    r = run(tmp_path, AX_JOB, "--name", "j1", "--", "true")
    assert r.code == 2
    assert "--image" in r.result.stderr
    assert r.calls == []


@pytest.mark.parametrize(
    "image",
    [
        f"{TASK_REPO}/task:latest",
        f"ghcr.io/x/task@sha256:{DIGEST}",
        f"{TASK_REPO}-other/task@sha256:{DIGEST}",
        f"{TASK_REPO}/task@sha256:{DIGEST[:-1]}",
    ],
    ids=["not-pinned", "not-artifact-registry", "another-repository", "short-digest"],
)
def test_an_image_it_cannot_protect_is_refused(tmp_path: Path, image: str) -> None:
    # Only an image pinned by digest in exe-task can carry the inuse- tag
    # that keeps Artifact Registry's cleanup off it (plan D10).
    r = run(tmp_path, AX_JOB, "--image", image, "--", "true")
    assert r.code == 2
    assert r.calls == []


def test_an_image_the_registry_lacks_is_refused_before_anything_exists(
    tmp_path: Path,
) -> None:
    r = job(tmp_path, "true", FAKE_IMAGE_MISSING="1")
    assert r.code == 1
    assert not r.called("gcloud artifacts docker tags add")
    assert not r.called("ax apply")


def test_the_image_is_tagged_before_the_task_exists(tmp_path: Path) -> None:
    before = int(time.time())
    r = job(tmp_path, "true")
    assert r.code == 0, r.result.stderr

    (tag,) = r.called("gcloud artifacts docker tags add")
    m = re.search(r":inuse-" + DIGEST[:12] + r"-(\d+)", tag)
    assert m, tag
    assert before <= int(m.group(1)) <= int(time.time())
    assert f"{TASK_REPO}/task@sha256:{DIGEST}" in tag
    assert r.index("gcloud artifacts docker tags add") < r.index("ax apply")


def test_a_failed_tag_creates_no_task(tmp_path: Path) -> None:
    r = job(tmp_path, "true", FAKE_TAG_FAIL="1")
    assert r.code == 1
    assert not r.called("ax apply")


def test_the_task_is_the_image_with_debug_and_nothing_else(tmp_path: Path) -> None:
    r = job(tmp_path, "true")
    (manifest,) = r.applied()
    assert "kind: Task" in manifest
    assert re.search(r"^\s+name: j1$", manifest, re.M)
    assert re.search(r"^\s+atespace: exe$", manifest, re.M)
    assert f'image: "{IMAGE}"' in manifest
    assert re.search(r"^\s+debug: true$", manifest, re.M)
    # no command (the runner is the image's), no env, no workspace
    for field in ("command:", "env:", "workspaces:"):
        assert field not in manifest


def test_a_name_already_taken_is_refused(tmp_path: Path) -> None:
    setup(tmp_path)
    (tmp_path / "state" / "tasks" / "j1").write_text("Suspended\n", encoding="utf-8")
    r = job(tmp_path, "true")
    assert r.code == 1
    assert not r.called("ax apply")
    # and the task that had the name is untouched
    assert not r.called("ax delete")
    assert r.task("j1") == "Suspended"


# --- ax-job: the lease -------------------------------------------------------------


def test_the_lease_is_checked_before_anything_exists(tmp_path: Path) -> None:
    r = job(tmp_path, "true", FAKE_MAY_START="3")
    assert r.code == 3
    assert "just exe-extend" in r.result.stderr
    assert not r.called("gcloud")
    assert not r.called("ax apply")


def test_a_start_that_ate_the_margin_is_refused_and_its_task_deleted(
    tmp_path: Path,
) -> None:
    # given provisioning slow enough that the lease no longer covers the job
    r = job(
        tmp_path,
        "true",
        flags=("--timeout", "30m"),
        FAKE_MAY_START="0,3",
        FAKE_RUNNING_AFTER="3",
    )
    assert r.code == 3
    # both checks asked for the timeout plus five minutes
    checks = r.called("exe-reaper may-start")
    assert len(checks) == 2
    assert all(c.endswith("-need 2100s") for c in checks), checks
    # the second came after the task was applied, and nothing was launched
    second = [i for i, c in enumerate(r.calls) if c.startswith("exe-reaper may-start")][
        1
    ]
    assert r.index("ax apply") < second
    assert not r.ssh("launch")
    assert r.called("ax delete task j1")


def test_a_task_that_fails_to_start_is_deleted(tmp_path: Path) -> None:
    r = job(tmp_path, "true", FAKE_START_PHASE="Failed")
    assert r.code == 1
    assert not r.ssh("launch")
    assert r.called("ax delete task j1")


def test_a_task_that_never_runs_is_deleted(tmp_path: Path) -> None:
    r = job(tmp_path, "true", FAKE_RUNNING_AFTER="100000", AX_JOB_START_SECONDS="1")
    assert r.code == 1
    assert not r.ssh("launch")
    assert r.called("ax delete task j1")


# --- ax-job: the timeout and the transport ---------------------------------------


def gone(pid: int) -> bool:
    """Whether pid has exited, allowing a moment for it to be reaped."""
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_the_timeout_kills_the_commands_whole_process_group(tmp_path: Path) -> None:
    # given a command whose shell and backgrounded child both record their pids
    pids = tmp_path / "pids"
    started = time.monotonic()
    r = job(
        tmp_path,
        "sh",
        "-c",
        f"echo $$ > {pids}; sleep 60 & echo $! >> {pids}; sleep 60",
        flags=("--timeout", "2s"),
    )
    assert r.code == 124, r.result.stderr
    assert time.monotonic() - started < 40
    # then both are gone, the backgrounded one too
    recorded = [int(p) for p in pids.read_text(encoding="utf-8").split()]
    assert len(recorded) == 2
    assert all(gone(p) for p in recorded), recorded
    assert r.called("ax delete task j1")


def test_a_reset_poll_is_retried_and_never_read_as_the_exit(tmp_path: Path) -> None:
    r = job(tmp_path, "sh", "-c", "sleep 0.5; exit 5", FAKE_SSH_RESET="poll:1 poll:2")
    assert r.code == 5, r.result.stderr
    assert len(r.ssh("launch")) == 1


def test_a_lost_launch_reply_does_not_run_the_command_twice(tmp_path: Path) -> None:
    ran = tmp_path / "ran"
    r = job(tmp_path, "sh", "-c", f"echo once >> {ran}", FAKE_SSH_LOST_REPLY="launch:1")
    assert r.code == 0, r.result.stderr
    assert len(r.ssh("launch")) == 2
    assert ran.read_text(encoding="utf-8").splitlines() == ["once"]


def test_a_drain_that_suspends_the_task_mid_command_keeps_it(tmp_path: Path) -> None:
    r = job(tmp_path, "sleep", "30", FAKE_SUSPEND_AT="2")
    assert r.code == 75
    assert "suspended" in r.result.stderr.lower()
    assert not r.called("ax delete")
    assert r.task("j1") == "Suspended"


def test_a_task_that_stops_answering_is_kept_not_deleted(tmp_path: Path) -> None:
    # The command may still be running: only a definitive end deletes.
    r = job(tmp_path, "sleep", "30", FAKE_SSH_RESET_ALL="poll")
    assert r.code == 69
    assert not r.called("ax delete")
    assert "ax delete task j1" in r.result.stderr


# --- ax-job: the Claude credential (Q20) ---------------------------------------------


def test_the_claude_token_travels_only_in_the_launch(tmp_path: Path) -> None:
    r = job(
        tmp_path,
        "sh",
        "-c",
        'echo "token=$CLAUDE_CODE_OAUTH_TOKEN"',
        flags=("--claude",),
    )
    assert r.code == 0, r.result.stderr
    # read from Secret Manager on the operator's own credentials
    (access,) = r.called("gcloud secrets versions access")
    assert "exe-claude-oauth-token" in access
    # the command saw it, and the terminal did not
    assert "token=" in r.result.stdout
    assert TOKEN not in r.result.stdout
    assert TOKEN not in r.result.stderr
    # it is in no manifest, and in no call but the detached launch
    assert all(TOKEN not in m for m in r.applied())
    carrying = [c for c in r.calls if TOKEN in c]
    assert carrying
    assert carrying == r.ssh("launch")


def test_a_token_split_across_polls_is_still_redacted(tmp_path: Path) -> None:
    half = len(TOKEN) // 2
    r = job(
        tmp_path,
        "sh",
        "-c",
        f"printf 'a {TOKEN[:half]}'; sleep 0.5; printf '{TOKEN[half:]} b\\n'",
    )
    assert r.code == 0, r.result.stderr
    assert TOKEN[half:] not in r.result.stdout
    assert TOKEN[:half] not in r.result.stdout
    assert "a sk-ant-" in r.result.stdout


def test_without_claude_no_token_is_read(tmp_path: Path) -> None:
    r = job(tmp_path, "true")
    assert not r.called("gcloud secrets")


# --- ax-exec -----------------------------------------------------------------------------


def exec_(tmp_path: Path, tasks: dict[str, str], *args: str, **fake: str) -> Run:
    setup(tmp_path, tasks)
    return run(tmp_path, AX_EXEC, *args, **fake)


def test_ax_exec_resumes_runs_and_suspends_again(tmp_path: Path) -> None:
    r = exec_(tmp_path, {"w1": "Suspended"}, "w1", "--", "sh", "-c", "echo hi; exit 4")
    assert r.code == 4, r.result.stderr
    assert "hi" in r.result.stdout
    assert r.index("ax resume task w1") < r.calls.index(r.ssh("launch")[0])
    assert r.called("ax suspend task w1")
    assert r.task("w1") == "Suspended"
    assert not r.called("ax delete")


def test_ax_exec_leaves_a_running_task_running(tmp_path: Path) -> None:
    r = exec_(tmp_path, {"w1": "Running"}, "w1", "--", "true")
    assert r.code == 0, r.result.stderr
    assert not r.called("ax resume")
    assert not r.called("ax suspend")
    assert r.task("w1") == "Running"


def test_ax_exec_refuses_a_task_that_does_not_exist(tmp_path: Path) -> None:
    r = exec_(tmp_path, {}, "w9", "--", "true")
    assert r.code == 1
    assert not r.called("ax ssh")


def test_ax_exec_checks_the_lease_again_after_the_resume(tmp_path: Path) -> None:
    r = exec_(tmp_path, {"w1": "Suspended"}, "w1", "--", "true", FAKE_MAY_START="0,3")
    assert r.code == 3
    assert len(r.called("exe-reaper may-start")) == 2
    assert not r.ssh("launch")
    # and it puts the task back the way it found it
    assert r.task("w1") == "Suspended"


def test_ax_exec_refuses_before_resuming_on_a_refused_lease(tmp_path: Path) -> None:
    r = exec_(tmp_path, {"w1": "Suspended"}, "w1", "--", "true", FAKE_MAY_START="3")
    assert r.code == 3
    assert not r.called("ax resume")


def test_ax_exec_never_deletes_even_on_a_timeout(tmp_path: Path) -> None:
    r = exec_(tmp_path, {"w1": "Running"}, "w1", "--timeout", "1s", "--", "sleep", "30")
    assert r.code == 124
    assert not r.called("ax delete")


def test_ax_exec_passes_the_claude_token_only_in_the_launch(tmp_path: Path) -> None:
    r = exec_(
        tmp_path,
        {"w1": "Running"},
        "w1",
        "--claude",
        "--",
        "sh",
        "-c",
        'echo "$CLAUDE_CODE_OAUTH_TOKEN"',
    )
    assert r.code == 0, r.result.stderr
    assert TOKEN not in r.result.stdout
    assert [c for c in r.calls if TOKEN in c] == r.ssh("launch")


# --- the guest half, on its own ---------------------------------------------------------


def guest(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    setup(tmp_path)
    env = {**os.environ, "PATH": f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        [GUEST_SH, "-c", GUEST.read_text(encoding="utf-8"), "ax-job-guest", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
        encoding="utf-8",
        errors="replace",
    )


def test_guest_poll_reads_from_the_offset_then_the_status(tmp_path: Path) -> None:
    d = tmp_path / "j"
    d.mkdir()
    (d / "log").write_text("abcdef", encoding="utf-8")
    assert guest(tmp_path, "poll", str(d), "2", "T0").stdout == "cdef\nT0 6 running\n"
    (d / "exit").write_text("3\n", encoding="utf-8")
    assert guest(tmp_path, "poll", str(d), "6", "T0").stdout == "\nT0 6 3\n"


def test_guest_poll_of_a_job_that_vanished_says_lost(tmp_path: Path) -> None:
    # /tmp does not survive a suspend: a resumed task has no job directory.
    assert guest(tmp_path, "poll", str(tmp_path / "gone"), "0", "T0").stdout == (
        "\nT0 0 lost\n"
    )


def test_guest_launch_starts_the_command_once(tmp_path: Path) -> None:
    d = tmp_path / "ax-job" / "j"
    count = tmp_path / "count"
    cmd = ("sh", "-c", f"echo x >> {count}; exit 9")
    assert "started" in guest(tmp_path, "launch", str(d), *cmd).stdout
    assert "started" in guest(tmp_path, "launch", str(d), *cmd).stdout
    deadline = time.monotonic() + 10
    while not (d / "exit").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert (d / "exit").read_text(encoding="utf-8").strip() == "9"
    assert count.read_text(encoding="utf-8").splitlines() == ["x"]


def test_guest_kill_takes_the_whole_group(tmp_path: Path) -> None:
    # given a launched command, which launch answers for only once it leads
    # its own process group
    d = tmp_path / "ax-job" / "j"
    guest(tmp_path, "launch", str(d), "sh", "-c", "sleep 60 & sleep 60")
    pgid = int((d / "pid").read_text(encoding="utf-8"))
    assert os.getpgid(pgid) == pgid
    # when it is killed, then the whole group is gone
    assert "killed" in guest(tmp_path, "kill", str(d)).stdout
    with pytest.raises(ProcessLookupError):
        os.killpg(pgid, 0)


@pytest.fixture(autouse=True)
def _no_stray_jobs(tmp_path: Path):
    """Kill anything a failing test left running under this test's guest."""
    yield
    for pid_file in tmp_path.rglob("ax-job/*/pid"):
        try:
            os.killpg(int(pid_file.read_text(encoding="utf-8")), signal.SIGKILL)
        except (ProcessLookupError, ValueError, PermissionError):
            pass


# --- the just recipes ------------------------------------------------------------------

JUSTFILE = REPO / "justfile"


def recipe(name: str) -> tuple[list[str], str]:
    """A recipe's attribute lines and its body, from the root justfile."""
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines) if re.match(rf"^{re.escape(name)}\b.*:", line)
    )
    attributes = []
    i = start - 1
    while i >= 0 and lines[i].startswith("["):
        attributes.append(lines[i])
        i -= 1
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return attributes, "\n".join(body)


@pytest.mark.parametrize(
    ("name", "tool"), [("exe-ax-job", "ax-job"), ("exe-ax-exec", "ax-exec")]
)
def test_the_recipes_pass_every_word_through_as_its_own_argument(
    name: str, tool: str
) -> None:
    # `-- sh -c 'echo a b'` must reach the wrapper as four words, not five:
    # just joins {{ args }} with spaces, so only "$@" keeps them apart.
    attributes, body = recipe(name)
    assert "[positional-arguments]" in attributes
    assert f'_exe-ax {tool} "$@"' in body
    assert "{{" not in body


def wrapper_env() -> set[str]:
    """Every EXE_ variable ax-job, ax-exec and ax-lib.sh require (${VAR:?...})."""
    names: set[str] = set()
    for script in (AX_JOB, AX_EXEC, SCRIPTS / "ax-lib.sh"):
        names |= set(
            re.findall(r"\$\{(EXE_[A-Z_]+):\?", script.read_text(encoding="utf-8"))
        )
    return names


def test_the_recipe_sets_everything_the_wrappers_and_may_start_read() -> None:
    attributes, body = recipe("_exe-ax")
    assert "[positional-arguments]" in attributes
    exported = set(re.findall(r"\bexport ([A-Z_ ]+)", body))
    exported_names = {n for group in exported for n in group.split()}
    required = wrapper_env() | {
        "EXE_OPS_BUCKET",
        "GOOGLE_OAUTH_ACCESS_TOKEN",
        "KUBECONFIG",
    }
    assert wrapper_env() >= {"EXE_AR_TASK_REPO", "EXE_CLAUDE_SECRET", "EXE_PROJECT_ID"}
    assert required <= exported_names, required - exported_names


def test_the_recipe_builds_exe_reaper_outside_the_tree() -> None:
    # M32: a binary built in the module is one broad `git add` from the repo.
    _, body = recipe("_exe-ax")
    assert re.search(r'bin="\$\(mktemp -d\)"', body)
    assert 'go build -o "$bin/exe-reaper"' in body
    assert "rm -rf" not in body


# --- no free worker (W2 finding, inbox M43) --------------------------------------
#
# AX fails a task on the first ResumeActor refusal, "no free workers
# available", and never retries it. A worker frees within a few minutes of the
# task it held being deleted.


def test_a_task_refused_a_worker_is_applied_again_once(tmp_path: Path) -> None:
    r = job(tmp_path, "true", FAKE_NO_WORKER="1", AX_JOB_WORKER_WAIT_SECONDS="0.1")
    assert r.code == 0, r.result.stderr
    assert len(r.applied()) == 2
    # the refused task was deleted before the second apply
    applies = [i for i, c in enumerate(r.calls) if c.startswith("ax apply")]
    assert any(
        c.startswith("ax delete task j1") for c in r.calls[applies[0] : applies[1]]
    )
    assert "no free worker" in r.result.stderr


def test_a_second_refusal_says_to_wait_for_a_worker(tmp_path: Path) -> None:
    r = job(tmp_path, "true", FAKE_NO_WORKER="2", AX_JOB_WORKER_WAIT_SECONDS="0.1")
    assert r.code == 1
    assert len(r.applied()) == 2
    assert not r.ssh("launch")
    assert "wait" in r.result.stderr and "no free worker" in r.result.stderr
    assert r.task("j1") is None


def test_another_start_failure_is_not_retried(tmp_path: Path) -> None:
    r = job(
        tmp_path, "true", FAKE_START_PHASE="Failed", AX_JOB_WORKER_WAIT_SECONDS="0.1"
    )
    assert r.code == 1
    assert len(r.applied()) == 1


def test_ax_exec_says_to_wait_for_a_worker_and_keeps_the_task(tmp_path: Path) -> None:
    r = exec_(tmp_path, {"w1": "Suspended"}, "w1", "--", "true", FAKE_NO_WORKER="1")
    assert r.code == 1
    assert "no free worker" in r.result.stderr
    assert not r.called("ax delete")
    assert not r.ssh("launch")
