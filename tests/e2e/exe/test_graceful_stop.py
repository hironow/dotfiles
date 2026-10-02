"""6.7, 6.9 and 6.2 on one scenario: two sleeps, two wakes (Phase 6 plan D13, D2).

Each part could be a test with its own wake and sleep, at about 25 node-minutes
apiece. Run as one scenario they share the node: two tasks are awake when the
lease runs out (the pool has two workers), and each resume boundary gets one of
them.

- Task A wrote a marker. Its resume is thrown in right after `drained`, when no
  controller pod is left to carry it out, so it runs at the next wake (6.9),
  and A comes back with its marker (6.7).
- Task B wrote a marker too. Its resume is thrown in while the drain is
  `draining`; whatever the controller manages, L1 suspends again before it
  writes `drained` (6.9). (The Control API probe from inside a task, plan F5,
  is test_control_api_barrier.py.)
- Both boundaries still end in a graceful stop and 0 nodes, and the first L1
  tick of the next wake, which observes before it reopens anything, sees no
  actor awake.
- The second wake shows L1 putting the router and the controller back on the
  new lease after `drained` (a Cancel of that record). A last sleep, cancelled
  by an extend while it drains, shows them restored mid-drain: 6.2's router
  restore.

The scenario runs once, in a module fixture that records what it saw and where
it stopped, and each test asserts its own part. The `exe` fixture's teardown
leaves 0 nodes whatever happened.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest
from exe_live import Exe, log, stamp, utcnow


@dataclass
class Scenario:
    seen: dict[str, Any] = field(default_factory=dict)
    stopped: str = ""

    def need(self, *keys: str) -> None:
        missing = [k for k in keys if k not in self.seen]
        if missing:
            pytest.fail(
                f"the scenario stopped before {missing}: {self.stopped or 'no error recorded'}"
            )


# The branches in which L1 puts the router and the controller back (DecideL1):
# Cancel when a drain record is left from another lease, Reopen when there is
# none but a gate is still shut. A wake after `drained` is a Cancel (seen at
# W2's first wake, 09:56:03Z).
RESTORES = ("Cancel", "Reopen")


def first_decision(
    exe: Exe, since: datetime, branches: tuple[str, ...] = ()
) -> dict[str, Any]:
    """The first L1 decision since a moment, optionally of the given branches."""

    def probe() -> dict[str, Any] | None:
        for entry in exe.l1_decisions(since):
            decision = entry["jsonPayload"]["exe_l1"]
            if not branches or decision.get("branch") in branches:
                return {"timestamp": entry["timestamp"], **decision}
        return None

    what = "/".join(branches) or "decision"
    return exe.wait_until(
        f"an L1 {what} since {stamp(since)}", probe, timeout=600, interval=20
    )


def marker_task(exe: Exe, prefix: str) -> tuple[str, str]:
    name = exe.unique(prefix)
    exe.apply_task(name)
    marker = secrets.token_hex(8)
    return name, marker


def run_scenario(exe: Exe, s: Scenario) -> None:
    step: Callable[[str, Any], None] = s.seen.__setitem__

    # the first wake (the node may already be up: then there is nothing to
    # reopen, and the second wake below is the proof)
    woke = exe.wake("1h")
    step("first_tick_1", first_decision(exe, woke))

    # two awake tasks with markers
    a, marker_a = marker_task(exe, "e2e-a")
    b, marker_b = marker_task(exe, "e2e-b")
    step("tasks", {"a": a, "b": b})
    for name, marker in ((a, marker_a), (b, marker_b)):
        exe.wait_phase(name, "Running")
        exe.ssh(name, f"echo {marker} > /workspace/e2e-marker && sync")

    # the lease runs out; B's resume lands while draining, A's right after drained
    started = utcnow()
    generation = exe.sleep()
    step("draining", exe.wait_drain(generation, "draining", timeout=300, interval=5))
    exe.ax("resume", "task", b)
    step("drained", exe.wait_drain(generation, "drained"))
    exe.ax("resume", "task", a)
    exe.measure("drain", generation=generation, record=s.seen["drained"])

    # L2 stops the pool gracefully
    stopping = utcnow()
    step("enforce", exe.l2_run())
    step("generation", generation)
    step(
        "l2_forced",
        [
            e["jsonPayload"]["exe_l2"]
            for e in exe.l2_decisions(started)
            if e["jsonPayload"]["exe_l2"].get("action") == "stop-forced"
            or e.get("severity") == "ERROR"
        ],
    )
    step("stop", exe.wait_stopped(stopping))

    # the next wake: first what Substrate holds, then the tasks
    woke = exe.wake("30m")
    step("first_tick_2", first_decision(exe, woke))
    step("restore_2", first_decision(exe, woke, RESTORES))
    exe.wait_phase(a, "Running", timeout=600)
    step("a_came_back", True)
    step("marker_a", (exe.ssh(a, "cat /workspace/e2e-marker").strip(), marker_a))
    exe.wait_until(
        "B settled after the wake",
        lambda: exe.phase(b) in ("Suspended", "Running"),
        timeout=300,
    )
    step("b_after_wake", exe.phase(b))
    if s.seen["b_after_wake"] == "Suspended":
        exe.ax("resume", "task", b)
    exe.wait_phase(b, "Running")
    step("marker_b", (exe.ssh(b, "cat /workspace/e2e-marker").strip(), marker_b))

    # a drain cancelled by an extend restores both gates mid-drain
    cancelling = utcnow()
    generation = exe.sleep()
    exe.wait_drain(generation, "draining", timeout=300, interval=5)
    exe.just("exe-extend", "15m")
    step("cancel", first_decision(exe, cancelling, ("Cancel",)))
    exe.wait_until(
        "the router and the controller back after the cancel",
        lambda: (
            exe.ready_replicas("ate-system", "atenet-router") >= 1
            and exe.ready_replicas("ax-system", "ax-controller") >= 1
        ),
        timeout=300,
    )
    step("gates_after_cancel", True)


@pytest.fixture(scope="module")
def scenario(exe: Exe) -> Scenario:
    s = Scenario()
    try:
        run_scenario(exe, s)
    except Exception as exc:  # noqa: BLE001 - recorded; each test fails on the part it needed
        s.stopped = f"{type(exc).__name__}: {exc}"
        log(f"the scenario stopped: {s.stopped}")
    exe.measure("scenario", seen=s.seen, stopped=s.stopped)
    return s


def test_graceful_sleep_keeps_files(scenario: Scenario) -> None:
    """6.7: drained, a graceful stop with no page, 0 nodes, and A's file intact."""
    scenario.need("drained", "enforce", "l2_forced", "stop", "marker_a")
    s = scenario.seen
    assert not s["drained"].get("failure"), s["drained"]
    assert s["enforce"].get("action") == "stop-graceful", s["enforce"]
    assert s["enforce"].get("leaseGeneration") == s["generation"], s["enforce"]
    assert s["l2_forced"] == [], s["l2_forced"]
    got, want = s["marker_a"]
    assert got == want


def test_a_resume_while_draining_still_ends_suspended(scenario: Scenario) -> None:
    """6.9, first boundary: drained anyway, nothing awake at the next wake, B intact."""
    scenario.need("draining", "drained", "first_tick_2", "marker_b")
    s = scenario.seen
    assert s["first_tick_2"]["awake"] == 0, s["first_tick_2"]
    assert s["first_tick_2"]["actors"] >= 2, s["first_tick_2"]
    got, want = s["marker_b"]
    assert got == want


def test_a_resume_after_drained_runs_at_the_next_wake(scenario: Scenario) -> None:
    """6.9, second boundary: the stop was graceful, and A came back by itself."""
    scenario.need("enforce", "first_tick_2", "a_came_back")
    s = scenario.seen
    assert s["enforce"].get("action") == "stop-graceful", s["enforce"]
    assert s["first_tick_2"]["awake"] == 0, s["first_tick_2"]
    assert s["a_came_back"] is True


def test_the_gates_reopen_on_a_valid_lease(scenario: Scenario) -> None:
    """6.2: both gates back at the wake after drained, and after a cancel mid-drain."""
    scenario.need("restore_2", "cancel", "gates_after_cancel")
    s = scenario.seen
    for key in ("restore_2", "cancel"):
        assert s[key]["router"] == 1 and s[key]["controller"] == 1, s[key]
