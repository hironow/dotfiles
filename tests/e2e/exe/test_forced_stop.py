"""6.8: with L1 gone, L2 still stops the node within its bound, and pages (plan D13).

L1 is taken out (its CronJob suspended, restored afterwards whatever happens),
a task is awake, and the lease runs out 5 minutes later. No drain record
exists for that lease, so L2 treats the heartbeat as stopped at the deadline:
it waits out the heartbeat window, then forces the stop. The forced stop is
logged at ERROR with notify set, which is exactly what the "exe: L2 forced a
stop" alert policy matches, and the operator confirms that its email arrived.
The stop latency is recorded with an actor awake (plan F4, D8).

The forced stop takes the awake actor down with the node, so its task is left
behind; delete it at the next wake (the test says which).
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import timedelta

import pytest

from exe_live import Exe, log, parse_time, utcnow

# exe/lease-constants.json: L2 forces heartbeat_stale_ticks L1 ticks after the
# deadline when no drain record exists, and a scheduled L2 tick comes at most
# l2_tick_minutes later.
HEARTBEAT_WINDOW = timedelta(minutes=2)
L2_TICK = timedelta(minutes=10)


@pytest.fixture
def l1_suspended(exe: Exe) -> Iterator[None]:
    exe.kubectl(
        "-n",
        "exe-ops",
        "patch",
        "cronjob",
        "exe-reap",
        "--type=merge",
        "-p",
        '{"spec":{"suspend":true}}',
    )
    try:
        # a tick already running ends on its own 45 s deadline
        exe.wait_until(
            "no L1 Job running",
            lambda: (
                exe.kubectl(
                    "-n",
                    "exe-ops",
                    "get",
                    "jobs",
                    "-o",
                    "jsonpath={.items[*].status.active}",
                ).strip()
                in ("", "0")
            ),
            timeout=180,
        )
        yield
    finally:
        exe.kubectl(
            "-n",
            "exe-ops",
            "patch",
            "cronjob",
            "exe-reap",
            "--type=merge",
            "-p",
            '{"spec":{"suspend":false}}',
        )
        log("L1's CronJob is running again")


def test_forced_stop_pages(exe: Exe, l1_suspended: None) -> None:
    # given an awake task and no L1
    exe.wake("1h")
    name = exe.unique("e2e-forced")
    exe.apply_task(name)
    exe.wait_phase(name, "Running")

    # when the lease runs out 5 minutes from now
    exe.just("exe-extend", "5m")
    deadline = exe.lease_deadline()
    assert deadline is not None
    generation = exe.lease_generation()

    # then L2 forces the stop once the heartbeat window is over, and not later
    # than one scheduled L2 tick after it
    enforce: dict = {}
    while enforce.get("action") != "stop-forced":
        assert utcnow() <= deadline + HEARTBEAT_WINDOW + L2_TICK, (
            f"no forced stop by the bound: {enforce}"
        )
        time.sleep(60)
        stopping = utcnow()
        enforce = exe.l2_run()
    forced_at = parse_time(enforce["at"])
    assert forced_at > deadline + HEARTBEAT_WINDOW, enforce
    assert enforce.get("leaseGeneration") == generation, enforce
    exe.measure(
        "forced_stop",
        task=name,
        deadline=deadline,
        forced_at=forced_at,
        enforce=enforce,
    )

    # and the decision is the one the page is made from
    decisions = [
        e
        for e in exe.l2_decisions(deadline)
        if e["jsonPayload"]["exe_l2"].get("action") == "stop-forced"
        and e["jsonPayload"]["exe_l2"].get("notify")
    ]
    assert decisions, "no forced-stop decision with notify in Cloud Logging"
    assert decisions[0]["severity"] == "ERROR", decisions[0]

    # and the node goes, with an actor awake on it
    exe.wait_stopped(stopping)
    exe.measure(
        "operator_check",
        note="confirm the 'exe: L2 forced a stop' email arrived",
        leftover_task=name,
    )
    log(
        f"OPERATOR: confirm the email 'exe: L2 forced a stop'. At the next wake: ax delete task {name} -a exe"
    )
