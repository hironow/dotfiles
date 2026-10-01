"""The harness for the exe stack's end-to-end tests (Phase 6 plan D13).

These tests wake the real node, run real tasks and stop the real pool, so they
cost node time and change live state. Every one of them is skipped unless
EXE_E2E=1, and `just exe-e2e` is the way to run them. No mocks: a stand-in for
the cluster would assert nothing about it.

The harness drives the stack only through the operator's own paths: the `just`
recipes (wake, extend, sleep, the L2 run), the ops bucket's records read with
gcloud, `ax` and `kubectl` with the kubeconfig `just exe-ctx` writes, GKE's
operations and Cloud Logging. Every test leaves the pool at 0, and the `exe`
fixture makes sure of it even when the test fails: it deletes the test's tasks,
sleeps, runs L2 until the node is gone, and fails loudly if it cannot.

Measurements the phase report needs (stop latency above all, plan D8) are
appended as JSON lines to $EXE_E2E_OUT/measurements.jsonl.
"""

from __future__ import annotations

import json
import os
import secrets
import shlex
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
ATESPACE = "exe"


def utcnow() -> datetime:
    return datetime.now(UTC)


def stamp(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def log(message: str) -> None:
    # The operator watches a live run as it goes (pytest -s).
    print(f"[e2e {stamp(utcnow())}] {message}", flush=True)


class CommandFailed(AssertionError):
    pass


@dataclass
class Exe:
    """The live stack, as the operator reaches it."""

    image: str
    out: Path
    kubeconfig: str
    outputs: dict[str, str] = field(default_factory=dict)
    tasks: list[str] = field(default_factory=list)

    # --- commands -----------------------------------------------------------

    def run(
        self, *cmd: str, timeout: float = 300, check: bool = True, quiet: bool = False
    ) -> str:
        if not quiet:
            log("$ " + shlex.join(cmd))
        try:
            r = subprocess.run(
                list(cmd),
                cwd=REPO,
                env={**os.environ, "KUBECONFIG": self.kubeconfig},
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandFailed(
                f"timed out after {timeout:.0f}s: {shlex.join(cmd)}"
            ) from exc
        if check and r.returncode != 0:
            raise CommandFailed(
                f"exit {r.returncode}: {shlex.join(cmd)}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}"
            )
        return r.stdout

    def just(self, *args: str, timeout: float = 900) -> str:
        return self.run("just", *args, timeout=timeout)

    def output(self, name: str) -> str:
        if name not in self.outputs:
            self.outputs[name] = self.run(
                "just", "_tofu-out", "exe-platform", name, quiet=True
            ).strip()
        return self.outputs[name]

    def gcloud(self, *args: str, timeout: float = 180, check: bool = True) -> str:
        return self.run(
            "mise",
            "x",
            "--",
            "gcloud",
            *args,
            "--project",
            self.output("project_id"),
            timeout=timeout,
            check=check,
            quiet=True,
        )

    def kubectl(self, *args: str, timeout: float = 120, check: bool = True) -> str:
        return self.run("kubectl", *args, timeout=timeout, check=check, quiet=True)

    def ax(
        self, *args: str, timeout: float = 120, check: bool = True, quiet: bool = False
    ) -> str:
        """ax, with -a placed before any `--`, where it is still a flag."""
        cut = args.index("--") if "--" in args else len(args)
        return self.run(
            "mise",
            "x",
            "--",
            "ax",
            *args[:cut],
            "-a",
            ATESPACE,
            *args[cut:],
            timeout=timeout,
            check=check,
            quiet=quiet,
        )

    def measure(self, what: str, **values: Any) -> None:
        log(f"measured {what}: {values}")
        with (self.out / "measurements.jsonl").open("a", encoding="utf-8") as f:
            f.write(
                json.dumps({"what": what, "at": stamp(utcnow()), **values}, default=str)
                + "\n"
            )

    # --- waiting ----------------------------------------------------------------

    def wait_until[T](
        self,
        what: str,
        probe: Callable[[], T | None],
        timeout: float,
        interval: float = 10,
    ) -> T:
        """Poll probe until it returns something truthy; a failed command is a miss."""
        deadline = time.monotonic() + timeout
        last: object = None
        while True:
            try:
                value = probe()
                if value:
                    return value
                last = value
            except CommandFailed as exc:
                last = exc
            if time.monotonic() >= deadline:
                raise AssertionError(
                    f"{what}: not within {timeout:.0f}s (last: {last!r})"
                )
            time.sleep(interval)

    # --- the ops bucket -------------------------------------------------------------

    def ops_object(self, name: str) -> dict[str, Any] | None:
        uri = f"gs://{self.output('bucket_ops')}/{name}"
        if not self.gcloud("storage", "ls", uri, check=False).strip():
            return None
        return json.loads(self.gcloud("storage", "cat", uri))

    def lease_generation(self) -> int:
        uri = f"gs://{self.output('bucket_ops')}/lease.json"
        return int(
            self.gcloud(
                "storage", "objects", "describe", uri, "--format=value(generation)"
            ).strip()
        )

    def lease_deadline(self) -> datetime | None:
        lease = self.ops_object("lease.json")
        return parse_time(lease["deadline"]) if lease else None

    def drain(self) -> dict[str, Any]:
        return self.ops_object("drain.json") or {}

    def enforce(self) -> dict[str, Any]:
        return self.ops_object("enforce.json") or {}

    # --- the node ---------------------------------------------------------------------

    def nodes(self) -> int:
        return len(self.kubectl("get", "nodes", "-o", "name").split())

    def ready_replicas(self, namespace: str, name: str) -> int:
        ready = self.kubectl(
            "-n",
            namespace,
            "get",
            "deployment",
            name,
            "-o",
            "jsonpath={.status.readyReplicas}",
            check=False,
        )
        return int(ready.strip() or 0)

    def wake(self, duration: str = "1h") -> datetime:
        woke = utcnow()
        self.just("exe-wake", duration)
        self.wait_ready()
        self.measure(
            "wake_to_ready", woke=stamp(woke), seconds=(utcnow() - woke).total_seconds()
        )
        return woke

    def wait_ready(self) -> None:
        """A node, the Control API, ax-server, and both gates L1 reopens on a live lease."""
        self.wait_until("a node", lambda: self.nodes() >= 1, timeout=900, interval=15)
        for namespace, name in (
            ("ate-system", "ate-api-server"),
            ("ax-system", "ax-server"),
            ("ate-system", "atenet-router"),
            ("ax-system", "ax-controller"),
        ):
            self.wait_until(
                f"{namespace}/{name} ready",
                lambda ns=namespace, n=name: self.ready_replicas(ns, n) >= 1,
                timeout=900,
                interval=15,
            )
        self.wait_until(
            "ax answers",
            lambda: "NAME" in self.ax("get", "tasks", check=False, quiet=True),
            timeout=300,
        )

    def sleep(self) -> int:
        """`just exe-sleep`; returns the lease generation the drain is about."""
        self.just("exe-sleep")
        return self.lease_generation()

    def wait_drain(
        self, generation: int, phase: str, timeout: float = 1800, interval: float = 10
    ) -> dict[str, Any]:
        def probe() -> dict[str, Any] | None:
            d = self.drain()
            if d.get("leaseGeneration") != generation:
                return None
            if d.get("phase") == "drain-failed" and phase != "drain-failed":
                raise AssertionError(f"the drain failed: {d}")
            return d if d.get("phase") == phase else None

        return self.wait_until(
            f"drain.json {phase} for lease generation {generation}",
            probe,
            timeout,
            interval,
        )

    def l2_run(self) -> dict[str, Any]:
        self.just("exe-l2-run", timeout=600)
        return self.enforce()

    def wait_stopped(self, since: datetime) -> dict[str, Any]:
        """0 nodes, and the stop latency: setSize(0) to the node gone (plan D8)."""
        self.wait_until("0 nodes", lambda: self.nodes() == 0, timeout=1500, interval=15)
        gone = utcnow()
        ops = json.loads(
            self.gcloud(
                "container",
                "operations",
                "list",
                "--location",
                self.output("zone"),
                f'--filter=operationType=SET_NODE_POOL_SIZE AND startTime>="{stamp(since)}"',
                "--format=json",
            )
            or "[]"
        )
        record: dict[str, Any] = {"node_gone_seen": stamp(gone)}
        if ops:
            op = min(ops, key=lambda o: o["startTime"])
            record |= {
                "set_size_start": op["startTime"],
                "set_size_end": op.get("endTime"),
                "status": op.get("status"),
                "seconds_to_gone_seen": (
                    gone - parse_time(op["startTime"])
                ).total_seconds(),
            }
            if op.get("endTime"):
                record["seconds_set_size_op"] = (
                    parse_time(op["endTime"]) - parse_time(op["startTime"])
                ).total_seconds()
        self.measure("stop_latency", **record)
        return record

    # --- tasks ----------------------------------------------------------------------------

    def unique(self, prefix: str) -> str:
        return f"{prefix}-{secrets.token_hex(3)}"

    def phase(self, name: str) -> str:
        for line in self.ax("get", "tasks", quiet=True).splitlines()[1:]:
            cols = line.split()
            if cols and cols[0] == name:
                return cols[2]
        return ""

    def apply_task(self, name: str) -> None:
        manifest = self.out / f"{name}.yaml"
        manifest.write_text(
            "apiVersion: ax.io/v1alpha1\n"
            "kind: Task\n"
            "metadata:\n"
            f"  name: {name}\n"
            f"  atespace: {ATESPACE}\n"
            "spec:\n"
            f'  image: "{self.image}"\n'
            "  debug: true\n",
            encoding="utf-8",
        )
        self.tasks.append(name)
        self.run("mise", "x", "--", "ax", "apply", "-f", str(manifest))

    def wait_phase(self, name: str, phase: str, timeout: float = 900) -> None:
        self.wait_until(
            f"task {name} {phase}",
            lambda: self.phase(name) == phase,
            timeout,
            interval=10,
        )

    def ssh(self, name: str, script: str, timeout: float = 120) -> str:
        return self.ax("ssh", name, "--", "sh", "-c", script, timeout=timeout)

    # --- logs -------------------------------------------------------------------------------

    def logs(
        self, filter_: str, since: datetime, limit: int = 500
    ) -> list[dict[str, Any]]:
        text = self.gcloud(
            "logging",
            "read",
            f'{filter_} AND timestamp>="{stamp(since)}"',
            "--order=asc",
            f"--limit={limit}",
            "--format=json",
        )
        return json.loads(text or "[]")

    def l1_decisions(self, since: datetime) -> list[dict[str, Any]]:
        return self.logs(
            'resource.type="k8s_container" AND resource.labels.namespace_name="exe-ops" '
            'AND jsonPayload.exe_l1.event="decision"',
            since,
        )

    def l2_decisions(self, since: datetime) -> list[dict[str, Any]]:
        return self.logs(
            f'resource.type="cloud_run_job" AND resource.labels.job_name="{self.output("l2_enforcer_job")}" '
            'AND jsonPayload.exe_l2.event="decision"',
            since,
        )


def leave_asleep(e: Exe) -> None:
    """Delete this test's tasks while a node is up, then get the pool to 0.

    EXE_E2E_KEEP_AWAKE=1 leaves the node up after the tasks are gone, so that
    one wake serves several modules in a row (W3). The last run of the window
    goes without it, and the lease and L2 remain the backstop.
    """
    if e.nodes() == 0:
        return
    for name in e.tasks:
        e.ax("delete", "task", name, check=False)
    if os.environ.get("EXE_E2E_KEEP_AWAKE") == "1":
        log(
            f"EXE_E2E_KEEP_AWAKE=1: the node stays up; the lease runs to {e.lease_deadline()}"
        )
        return
    deadline = e.lease_deadline()
    if deadline is None or deadline > utcnow():
        e.just("exe-sleep")
    started = utcnow()
    give_up = time.monotonic() + 1800
    while e.nodes() > 0:
        if time.monotonic() > give_up:
            raise AssertionError(
                "TEARDOWN: the node is still up 30 min after exe-sleep: page the operator"
            )
        e.l2_run()
        time.sleep(120)
    log(
        f"teardown: 0 nodes, {(utcnow() - started).total_seconds():.0f}s after the sleep"
    )
