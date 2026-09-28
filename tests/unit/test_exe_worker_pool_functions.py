"""The shell functions tofu/exe-cluster embeds in its guards and install step.

worker_pool.sh is embedded into the pool guard and the Substrate install step,
drain_guard.sh into the pool guard and the install's drain guard, so these
tests run the real functions under bash. kubectl and ax are stubs on
PATH: they answer from FAKE_* variables and log every call they get.

The first case under test: a worker reports its capacity once, at startup, to
the store the API server has then. After the store is replaced, the install
restarts exactly the workers that started before the new store's claim
existed. It deletes their pods rather than rolling the Deployment, because a
4Gi surge pod cannot fit on the one node. It does this only while no task is
Running, and any doubt fails the apply instead of taking a worker away.

The second: while L1 drains (Phase 6 plan D2), the install must not run, since
it reopens the router L1 closed, and the pool guard must not let the workers
be replaced under actors still checkpointing. gcloud is a stub too, answering
the ops bucket's listing and drain.json from FAKE_* variables.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FUNCTIONS = REPO / "tofu" / "exe-cluster" / "worker_pool.sh"
DRAIN_GUARD = REPO / "tofu" / "exe-cluster" / "drain_guard.sh"
BASH = shutil.which("bash") or "/bin/bash"

STORE_BORN = "2026-09-27T19:15:02Z"
BEFORE_THE_STORE = "2026-09-27T17:40:11Z"
AFTER_THE_STORE = "2026-09-27T19:21:40Z"
TASKS_HEADER = "NAME   ATESPACE   PHASE       ACTOR    WORKER-IP   AGE\n"

KUBECTL_STUB = r"""#!/usr/bin/env bash
echo "kubectl $*" >> "$FAKE_LOG"
case " $* " in
  *" get pvc "*) printf '%s' "$FAKE_STORE_BORN" ;;
  *" get pods "*) printf '%s' "$FAKE_WORKERS" ;;
  *" delete pod "*) exit 0 ;;
  *" wait "*) exit 0 ;;
  *) echo "stub kubectl: unexpected call: $*" >&2; exit 97 ;;
esac
"""

GCLOUD_STUB = r"""#!/usr/bin/env bash
echo "gcloud $*" >> "$FAKE_LOG"
if [ -n "${FAKE_GCLOUD_FAIL:-}" ] && [[ " $* " == *" $FAKE_GCLOUD_FAIL "* ]]; then
  echo "gcloud: 503 from the bucket" >&2
  exit 1
fi
case " $* " in
  *" storage ls gs://$OPS_BUCKET/ "*) printf '%s' "$FAKE_LISTING" ;;
  *" storage cat gs://$OPS_BUCKET/drain.json "*) printf '%s' "$FAKE_DRAIN" ;;
  *) echo "stub gcloud: unexpected call: $*" >&2; exit 97 ;;
esac
"""

AX_STUB = r"""#!/usr/bin/env bash
echo "ax $*" >> "$FAKE_LOG"
if [ -n "${FAKE_AX_FAIL:-}" ]; then
  echo "ax: cannot reach the server" >&2
  exit 1
fi
printf '%s' "$FAKE_TASKS"
"""


def run_function(
    tmp_path: Path, call: str, **fake: str
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    """Source worker_pool.sh under `set -euo pipefail` and run `call`."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (
        ("kubectl", KUBECTL_STUB),
        ("ax", AX_STUB),
        ("gcloud", GCLOUD_STUB),
    ):
        stub = bin_dir / name
        stub.write_text(body)
        stub.chmod(0o755)
    log = tmp_path / "calls.log"
    log.touch()
    env = {
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(tmp_path),
        "ATESPACE": "exe",
        "POOL": "exe-gvisor",
        "STORE_NAMESPACE": "exe-store",
        "STORE_CLAIM": "store-postgres-0",
        "FAKE_LOG": str(log),
        "FAKE_STORE_BORN": STORE_BORN,
        "FAKE_WORKERS": "",
        "FAKE_TASKS": TASKS_HEADER,
        "OPS_BUCKET": "zz-ops",
        "FAKE_LISTING": "gs://zz-ops/lease.json\ngs://zz-ops/enforce.json\n",
        "FAKE_DRAIN": "",
        **fake,
    }
    script = (
        f'set -euo pipefail\nsource "{FUNCTIONS}"\nsource "{DRAIN_GUARD}"\n{call}\n'
    )
    result = subprocess.run(
        [BASH, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return result, log.read_text().splitlines()


RESTART = 'restart_workers_from_a_replaced_store "ate-setup"'


def workers(*pods: tuple[str, str]) -> str:
    """What `kubectl get pods -o jsonpath=...` prints: name, start time."""
    return "".join(f"{name} {started}\n" for name, started in pods)


def tasks(*rows: tuple[str, str]) -> str:
    """What `ax get tasks -a exe` prints: a header, then one row per task."""
    return TASKS_HEADER + "".join(
        f"{name}   exe   {phase}   <none>   <none>   5m\n" for name, phase in rows
    )


def calls_to(log: list[str], verb: str) -> list[str]:
    return [line for line in log if f" {verb} " in f" {line} "]


@pytest.mark.parametrize(
    "fake_workers",
    [
        pytest.param(
            workers(
                ("exe-gvisor-5c57-a", AFTER_THE_STORE),
                ("exe-gvisor-5c57-b", AFTER_THE_STORE),
            ),
            id="started-on-the-current-store",
        ),
        pytest.param(
            workers(("exe-gvisor-5c57-a", ""), ("exe-gvisor-5c57-b", "")),
            id="not-started-yet",
        ),
        pytest.param("", id="no-worker-pods"),
    ],
)
def test_workers_that_did_not_report_to_an_old_store_are_left_alone(
    tmp_path: Path, fake_workers: str
) -> None:
    result, log = run_function(tmp_path, RESTART, FAKE_WORKERS=fake_workers)

    assert result.returncode == 0, result.stderr
    assert not calls_to(log, "delete"), log
    assert not [line for line in log if line.startswith("ax ")], (
        "nothing to restart, so there is nothing to check tasks for"
    )
    assert "every exe-gvisor worker started on the current store" in result.stdout


def test_workers_that_reported_to_a_replaced_store_are_restarted(
    tmp_path: Path,
) -> None:
    result, log = run_function(
        tmp_path,
        RESTART,
        FAKE_WORKERS=workers(
            ("exe-gvisor-5c57-old", BEFORE_THE_STORE),
            ("exe-gvisor-5c57-new", AFTER_THE_STORE),
        ),
        FAKE_TASKS=tasks(("p6", "Suspended")),
    )

    assert result.returncode == 0, result.stderr
    deletes = calls_to(log, "delete")
    assert len(deletes) == 1, log
    assert " exe-gvisor-5c57-old" in deletes[0]
    assert "exe-gvisor-5c57-new" not in deletes[0], (
        "a worker that started on the current store reported to it"
    )
    assert "-n exe " in deletes[0]
    assert not calls_to(log, "rollout"), (
        "never roll the worker Deployment: its 4Gi surge pod cannot fit on the "
        "one node, so the rollout would deadlock"
    )
    checked = log.index("ax get tasks -a exe")
    deleted = log.index(deletes[0])
    waited = log.index(calls_to(log, "wait")[0])
    assert checked < deleted < waited, (
        "check tasks, then delete the pods, then wait for their replacements"
    )
    assert "-l ate.dev/worker-pool=exe-gvisor" in log[waited]


def test_a_running_task_fails_loudly_and_no_worker_is_touched(
    tmp_path: Path,
) -> None:
    result, log = run_function(
        tmp_path,
        RESTART,
        FAKE_WORKERS=workers(("exe-gvisor-5c57-old", BEFORE_THE_STORE)),
        FAKE_TASKS=tasks(("p5", "Running"), ("p6", "Suspended")),
    )

    assert result.returncode == 1
    assert "ate-setup: 1 task(s) Running in atespace exe." in result.stderr
    assert "CRASH" in result.stderr
    assert "Suspend every task" in result.stderr
    assert not calls_to(log, "delete"), log


def test_a_task_list_that_cannot_be_read_fails_closed(tmp_path: Path) -> None:
    result, log = run_function(
        tmp_path,
        RESTART,
        FAKE_WORKERS=workers(("exe-gvisor-5c57-old", BEFORE_THE_STORE)),
        FAKE_AX_FAIL="1",
    )

    assert result.returncode != 0
    assert "cannot reach the server" in result.stderr
    assert not calls_to(log, "delete"), log


def test_a_store_claim_without_a_creation_time_fails_closed(
    tmp_path: Path,
) -> None:
    result, log = run_function(
        tmp_path,
        RESTART,
        FAKE_STORE_BORN="",
        FAKE_WORKERS=workers(("exe-gvisor-5c57-old", BEFORE_THE_STORE)),
    )

    assert result.returncode != 0
    assert "store-postgres-0" in result.stderr
    assert not calls_to(log, "delete"), log


def test_the_shared_check_counts_only_running_rows(tmp_path: Path) -> None:
    result, _ = run_function(
        tmp_path,
        'refuse_while_tasks_run "worker pool guard" "Changing $POOL now would CRASH them."',
        FAKE_TASKS=tasks(("p5", "Running"), ("p6", "Suspended"), ("Running", "Failed")),
    )

    assert result.returncode == 1
    assert "worker pool guard: 1 task(s) Running in atespace exe." in result.stderr
    assert "Changing exe-gvisor now would CRASH them." in result.stderr


# --- refuse_while_draining ----------------------------------------------------

WITH_DRAIN = (
    "gs://zz-ops/lease.json\ngs://zz-ops/drain.json\ngs://zz-ops/enforce.json\n"
)
INSTALL_CHECK = 'refuse_while_draining "ate-setup" "draining drained"'
POOL_CHECK = 'refuse_while_draining "worker pool guard" "draining"'


def drain_record(phase: str) -> str:
    """drain.json as L1 writes it; the empty phase is "no drain"."""
    return (
        f'{{"phase":"{phase}","heartbeat":"2026-09-28T04:00:00Z","leaseGeneration":7}}'
    )


def test_no_drain_record_yet_lets_the_step_through(tmp_path: Path) -> None:
    # Before L1's first tick there is no record at all; nothing can be draining.
    result, log = run_function(tmp_path, INSTALL_CHECK)

    assert result.returncode == 0, result.stderr
    assert "ate-setup: no drain record yet" in result.stdout
    assert not [line for line in log if " storage cat " in line], log


@pytest.mark.parametrize(
    ("check", "phase", "refused"),
    [
        pytest.param(INSTALL_CHECK, "", False, id="install-no-drain"),
        pytest.param(INSTALL_CHECK, "draining", True, id="install-draining"),
        pytest.param(INSTALL_CHECK, "drained", True, id="install-drained"),
        pytest.param(INSTALL_CHECK, "drain-failed", False, id="install-drain-failed"),
        pytest.param(POOL_CHECK, "draining", True, id="pool-draining"),
        pytest.param(POOL_CHECK, "drained", False, id="pool-drained"),
    ],
)
def test_the_step_refuses_exactly_the_phases_it_names(
    tmp_path: Path, check: str, phase: str, refused: bool
) -> None:
    result, _ = run_function(
        tmp_path, check, FAKE_LISTING=WITH_DRAIN, FAKE_DRAIN=drain_record(phase)
    )

    if refused:
        assert result.returncode == 1
        assert f"drain.json says {phase}" in result.stderr
        assert "L1" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert f"drain.json says {phase or 'none'}" in result.stdout


@pytest.mark.parametrize(
    ("fake", "says"),
    [
        pytest.param({"FAKE_GCLOUD_FAIL": "ls"}, "cannot list", id="listing-fails"),
        pytest.param(
            {"FAKE_LISTING": WITH_DRAIN, "FAKE_GCLOUD_FAIL": "cat"},
            "cannot be read",
            id="record-unreadable",
        ),
        pytest.param(
            {"FAKE_LISTING": WITH_DRAIN, "FAKE_DRAIN": '{"phase":'},
            "cannot be read",
            id="record-garbled",
        ),
    ],
)
def test_a_drain_record_that_cannot_be_read_fails_closed(
    tmp_path: Path, fake: dict[str, str], says: str
) -> None:
    # A step that cannot tell whether L1 is draining must not guess "no".
    result, _ = run_function(tmp_path, INSTALL_CHECK, **fake)

    assert result.returncode != 0
    assert says in result.stderr
