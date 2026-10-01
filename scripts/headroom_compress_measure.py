#!/usr/bin/env python3
"""Measure what headroom's compressor actually does, reproducibly.

The spoke (`ROOT_AGENTS_docs_agents_headroom.md`) publishes a ratio per payload
kind. That table used to be a one-off measurement whose payloads were never
written down, so after a version bump there was no way to tell a real change
from a different input -- which is exactly the trap this script removes. The
four payloads below are deterministic to the byte
(`tests/unit/test_headroom_compress_measure.py` pins them), so two runs on two
versions are comparable and a moved ratio means the compressor moved.

Run it through `just headroom-compress-measure`. It is NOT part of `just ci`:
it starts a real `headroom mcp serve` and calls `headroom_compress`, the same
way `just jev-headroom-verify` exercises the real proxy.

Egress: both switches (`HEADROOM_BEACON=off`, `DO_NOT_TRACK=1`) are forced into
the server's environment here rather than inherited, so a measurement can never
be the thing that turns the beacon on.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

EXIT_OK = 0
EXIT_FAIL = 1

# Rows in the generated payloads. 700 is what the published table used; it is
# large enough that a compressor has something to find and small enough that a
# run takes seconds.
ROWS = 700

# Forced, never inherited: see the module docstring.
EGRESS_OFF = {"HEADROOM_BEACON": "off", "DO_NOT_TRACK": "1"}

# How long to wait for one tools/call answer. Generous because the first call
# also pays for the server's start-up.
ANSWER_TIMEOUT_S = 240.0
INIT_TIMEOUT_S = 60.0


def log_lines() -> str:
    """Structured application logs: a fixed set of fields, varying values."""
    return "\n".join(
        f"2026-10-02T04:{i % 60:02d}:{i % 60:02d}Z INFO  worker[{i % 8}] "
        f"request_id=req-{i:05d} status=200 latency_ms={12 + i % 40} "
        f"path=/v1/items/{i}"
        for i in range(ROWS)
    )


def json_array() -> str:
    """A JSON array of uniform objects, indented as an API would return it."""
    return json.dumps(
        [
            {
                "id": i,
                "name": f"item-{i}",
                "active": i % 3 == 0,
                "score": round(i * 0.37, 2),
                "tags": ["alpha", "beta"][: i % 2 + 1],
            }
            for i in range(ROWS)
        ],
        indent=2,
    )


def ls_listing() -> str:
    """A long directory listing: columnar, highly regular, not structured data."""
    return "\n".join(
        f"-rw-r--r--  1 nino  staff  {1000 + i * 7:8d} Oct  2 "
        f"04:{i % 60:02d} file_{i:04d}.txt"
        for i in range(ROWS)
    )


def repetitive_prose() -> str:
    """Natural-language prose, repeated. The case the ML route would own."""
    return "\n".join(
        "The quick brown fox jumps over the lazy dog, and then it considers "
        "whether jumping was in fact the correct decision at all."
        for _ in range(ROWS // 7)
    )


# Order is the published table's order.
PAYLOADS: Mapping[str, Callable[[], str]] = {
    f"{ROWS} log lines": log_lines,
    f"{ROWS}-object JSON array": json_array,
    f"{ROWS}-line `ls -la` listing": ls_listing,
    "repetitive prose": repetitive_prose,
}


@dataclass(frozen=True)
class Measurement:
    """One payload's result. `after` is None when the call produced no answer."""

    label: str
    before: int
    after: int | None
    detail: str = ""

    @property
    def ratio(self) -> float | None:
        if self.after is None or self.before == 0:
            return None
        return self.after / self.before


def format_table(measurements: Sequence[Measurement], *, version: str) -> str:
    """Render the measurements as the markdown table the spoke publishes."""
    lines = [f"# {version}", "", "| payload | ratio |", "|---|---|"]
    for m in measurements:
        if m.ratio is None:
            cell = f"NOT MEASURED -- {m.detail or 'no answer'}"
        elif m.ratio >= 1.0:
            cell = "1.000 -- unchanged"
        else:
            cell = f"**{m.ratio:.3f}**"
        lines.append(f"| {m.label} | {cell} |")
    lines.append("")
    for m in measurements:
        after = "-" if m.after is None else str(m.after)
        lines.append(f"{m.label}: {m.before} -> {after} chars")
    return "\n".join(lines)


class _Server:
    """A `headroom mcp serve` subprocess spoken to over stdio JSON-RPC.

    stdin is deliberately held open for the whole session: the server cancels a
    pending tool call when stdin reaches EOF, so writing every request and then
    closing returns no answers at all.
    """

    def __init__(self, executable: str) -> None:
        self._proc = subprocess.Popen(
            [executable, "mcp", "serve"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, **EGRESS_OFF},
            bufsize=1,
        )
        self._lines: queue.Queue[str] = queue.Queue()
        self._answers: dict[int, dict[str, object]] = {}
        stdout = self._proc.stdout
        if stdout is None:  # pragma: no cover - Popen with PIPE always sets it
            raise RuntimeError("no stdout from headroom mcp serve")
        self._reader = threading.Thread(
            target=lambda: [self._lines.put(line) for line in stdout], daemon=True
        )
        self._reader.start()

    def send(self, message: Mapping[str, object]) -> None:
        stdin = self._proc.stdin
        if stdin is None:  # pragma: no cover
            raise RuntimeError("no stdin to headroom mcp serve")
        stdin.write(json.dumps(message) + "\n")
        stdin.flush()

    def answer(self, want: int, budget: float) -> dict[str, object] | None:
        """Wait for the answer to `want`, KEEPING every other answer seen.

        Discarding other ids while scanning loses any answer the server returns
        out of order -- it then looks exactly like the server never replied.
        """
        end = time.monotonic() + budget
        while want not in self._answers and (left := end - time.monotonic()) > 0:
            try:
                line = self._lines.get(timeout=left)
            except queue.Empty:
                break
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            identifier = message.get("id")
            if isinstance(identifier, int):
                self._answers[identifier] = message
        return self._answers.get(want)

    def close(self) -> None:
        self._proc.kill()
        self._proc.wait(timeout=10)


def _compressed_length(message: Mapping[str, object]) -> tuple[int | None, str]:
    """Pull `compressed`'s length out of one tools/call answer."""
    if "error" in message:
        return None, f"server error: {str(message['error'])[:120]}"
    result = message.get("result")
    if not isinstance(result, Mapping):
        return None, "answer carried no result"
    content = result.get("content")
    if not isinstance(content, list):
        return None, "result carried no content"
    text = "".join(
        part["text"]
        for part in content
        if isinstance(part, Mapping) and isinstance(part.get("text"), str)
    )
    try:
        body = json.loads(text)
    except json.JSONDecodeError:
        return None, f"content was not JSON: {text[:80]!r}"
    compressed = body.get("compressed")
    if not isinstance(compressed, str):
        return None, f"no `compressed` string in {sorted(body)}"
    return len(compressed), ""


def measure(executable: str) -> list[Measurement]:
    """Run every payload through one server. Never raises on a bad answer."""
    server = _Server(executable)
    try:
        server.send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "headroom-compress-measure", "version": "1"},
                },
            }
        )
        if server.answer(1, INIT_TIMEOUT_S) is None:
            return [
                Measurement(label, len(build()), None, "server never initialized")
                for label, build in PAYLOADS.items()
            ]
        server.send({"jsonrpc": "2.0", "method": "notifications/initialized"})

        pending: dict[int, tuple[str, int]] = {}
        for offset, (label, build) in enumerate(PAYLOADS.items()):
            identifier = 10 + offset
            payload = build()
            pending[identifier] = (label, len(payload))
            server.send(
                {
                    "jsonrpc": "2.0",
                    "id": identifier,
                    "method": "tools/call",
                    "params": {
                        "name": "headroom_compress",
                        "arguments": {"content": payload},
                    },
                }
            )

        measurements: list[Measurement] = []
        for identifier, (label, before) in pending.items():
            message = server.answer(identifier, ANSWER_TIMEOUT_S)
            if message is None:
                measurements.append(
                    Measurement(label, before, None, "no answer within the timeout")
                )
                continue
            after, detail = _compressed_length(message)
            measurements.append(Measurement(label, before, after, detail))
        return measurements
    finally:
        server.close()


def _version(executable: str) -> str:
    result = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.stdout.strip() or "headroom, version unknown"


def main(argv: Sequence[str]) -> int:
    executable = argv[1] if len(argv) > 1 else "headroom"
    measurements = measure(executable)
    print(format_table(measurements, version=_version(executable)))
    unmeasured = [m for m in measurements if m.ratio is None]
    if unmeasured:
        print(
            "\nheadroom-compress-measure: FAILED -- "
            f"{len(unmeasured)} of {len(measurements)} payload(s) produced no "
            "ratio. A missing row is reported, never silently dropped:",
            file=sys.stderr,
        )
        for m in unmeasured:
            print(f"  - {m.label}: {m.detail}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv))
