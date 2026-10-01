"""6.8: with L1 gone, L2 still stops the node within its bound, and pages (plan D13).

L1 is taken out (its CronJob suspended, restored afterwards whatever happens),
a task is awake, and the lease runs out at once (`just exe-sleep`; plan D13's
5-minute lease was a test detail, and the path is the same, inbox M48.1). No
drain record exists for that lease, so L2 treats the heartbeat as stopped at
the deadline: it waits out the heartbeat window, then forces the stop. The
forced stop is logged at ERROR with notify set, which is exactly what the
"exe: L2 forced a stop" alert policy matches, and the operator confirms that
its email arrived. The stop latency is recorded with an actor awake (plan F4,
D8).

The forced decision is read from Cloud Logging, not from enforce.json: a
scheduled L2 tick may force first, and every tick after it records the pool
already stopped.

The forced stop takes the awake actor down with the node, so its task is left
behind; delete it at the next wake (the test says which).
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from datetime import timedelta

import pytest

from exe_live import REPO, Exe, log, parse_time, utcnow

# W3 only: the operator on email, after the manager's go. EXE_E2E alone runs
# the rest of the suite and never this; running the whole directory once
# started it by accident (W2, 19:18 JST).
pytestmark = pytest.mark.skipif(
    os.environ.get("EXE_E2E_FORCED") != "1",
    reason="the forced stop pages the operator: EXE_E2E_FORCED=1 runs it (W3, with the manager's go)",
)

# With no drain record for the lease, L2 treats the heartbeat as stopped at the
# deadline and forces once HeartbeatStaleAfter is over: heartbeat_stale_ticks
# L2 ticks (lease.HeartbeatStaleAfter), from exe/lease-constants.json. A
# scheduled L2 tick comes at most one L2 tick after that.
CONSTANTS = json.loads(
    (REPO / "exe" / "lease-constants.json").read_text(encoding="utf-8")
)
L2_TICK = timedelta(minutes=CONSTANTS["l2_tick_minutes"])
HEARTBEAT_WINDOW = CONSTANTS["heartbeat_stale_ticks"] * L2_TICK


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

    # when the lease runs out now
    exe.just("exe-sleep")
    deadline = exe.lease_deadline()
    assert deadline is not None
    generation = exe.lease_generation()

    # then L2 forces the stop once the heartbeat window is over, and not later
    # than one scheduled L2 tick after it
    forced: list[dict] = []
    while not forced:
        assert utcnow() <= deadline + HEARTBEAT_WINDOW + L2_TICK, (
            f"no forced stop by the bound; last enforce.json: {exe.enforce()}"
        )
        time.sleep(60)
        exe.l2_run()
        forced = [
            e
            for e in exe.l2_decisions(deadline)
            if e["jsonPayload"]["exe_l2"].get("action") == "stop-forced"
        ]
    decision = forced[0]
    fields = decision["jsonPayload"]["exe_l2"]
    forced_at = parse_time(decision["timestamp"])
    exe.measure(
        "forced_stop",
        task=name,
        deadline=deadline,
        forced_at=forced_at,
        decision=fields,
    )
    assert forced_at > deadline + HEARTBEAT_WINDOW, fields
    assert fields.get("leaseGeneration") == generation, fields

    # and the decision is the one the page is made from
    assert fields.get("notify") is True, fields
    assert decision["severity"] == "ERROR", decision

    # and the node goes, with an actor awake on it
    exe.wait_stopped(deadline)
    exe.measure(
        "operator_check",
        note="confirm the 'exe: L2 forced a stop' email arrived",
        leftover_task=name,
    )
    log(
        f"OPERATOR: confirm the email 'exe: L2 forced a stop'. At the next wake: ax delete task {name} -a exe"
    )
