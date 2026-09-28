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
  writes `drained` (6.9). From inside B, the Control API must not answer (the
  barrier's named assumption, plan F5).
- Both boundaries still end in a graceful stop and 0 nodes, and the first L1
  tick of the next wake, which observes before it reopens anything, sees no
  actor awake.
- The second wake shows L1 reopening the router and the controller on the new
  lease after `drained` (Reopen). A last sleep, cancelled by an extend while it
  drains, shows them restored mid-drain (Cancel): 6.2's router restore.

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

# A TLS handshake with the Control API, by name and by its ClusterIP, with
# verification on: the task does not trust the cluster's CA, so a server that
# answers fails verification, and that failure is the proof it answered. No
# answer is a timeout, a reset or a refusal. A bare TCP connect proves nothing
# inside an actor (Phase 5, finding 5).
PROBE = """
import socket, ssl, sys
ctx = ssl.create_default_context()
answered = []
for host in sys.argv[1:]:
    try:
        with socket.create_connection((host, 443), timeout=5) as s:
            with ctx.wrap_socket(s, server_hostname="api.ate-system.svc"):
                answered.append(host)
    except ssl.SSLCertVerificationError:
        answered.append(host)
    except OSError as exc:
        print(host, "no answer:", type(exc).__name__)
print("ANSWERED", " ".join(answered))
"""


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


def first_decision(
    exe: Exe, since: datetime, branch: str | None = None
) -> dict[str, Any]:
    """The first L1 decision since a moment, optionally of one branch."""

    def probe() -> dict[str, Any] | None:
        for entry in exe.l1_decisions(since):
            decision = entry["jsonPayload"]["exe_l1"]
            if branch is None or decision.get("branch") == branch:
                return {"timestamp": entry["timestamp"], **decision}
        return None

    return exe.wait_until(
        f"an L1 {branch or 'decision'} since {stamp(since)}",
        probe,
        timeout=600,
        interval=20,
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

    cluster_ip = exe.kubectl(
        "-n", "ate-system", "get", "service", "api", "-o", "jsonpath={.spec.clusterIP}"
    )
    step(
        "probe",
        exe.ax(
            "ssh",
            b,
            "--",
            "python3",
            "-c",
            PROBE,
            "api.ate-system.svc",
            cluster_ip.strip(),
        ).strip(),
    )

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
    step("reopen_2", first_decision(exe, woke, "Reopen"))
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
    step("cancel", first_decision(exe, cancelling, "Cancel"))
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


def test_a_task_cannot_reach_the_control_api(scenario: Scenario) -> None:
    """Plan F5, the barrier's named assumption: no answer from inside a task."""
    scenario.need("probe")
    assert scenario.seen["probe"].splitlines()[-1] == "ANSWERED", scenario.seen["probe"]


def test_the_gates_reopen_on_a_valid_lease(scenario: Scenario) -> None:
    """6.2: Reopen at the wake after drained, and Cancel restoring both gates mid-drain."""
    scenario.need("reopen_2", "cancel", "gates_after_cancel")
    s = scenario.seen
    for key in ("reopen_2", "cancel"):
        assert s[key]["router"] == 1 and s[key]["controller"] == 1, s[key]
