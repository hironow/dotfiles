#!/usr/bin/env python3
"""Live check of the Claude worker hook. Run it once the Claude usage limit has reset.

Exit 0 = pass, 1 = fail (a real defect), 2 = blocked (usage limit; nothing was learned).
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import tempfile

from jev_core import SONNET, claude_session_args
from jev_launch import hook_command

AGENT_KEYS = {"agent_type", "subagent_type", "agentType"}
PROMPT = (
    "Use the Agent tool exactly once with subagent_type general-purpose and this "
    "prompt: 'Redesign the distributed lock protocol across three services, prove "
    "safety under partial failure, then plan the migration of all callers. Analysis "
    "only: do not use any tool and do not edit files; answer in one sentence.' "
    "Then reply with the single word DONE."
)


@dataclass
class Report:
    status: str
    reason: str
    evidence: list[str] = field(default_factory=list)


def _walk(value: object):
    """Yield (key, value) for every mapping entry in a JSON document."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key, inner
            yield from _walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner)


def analyze(stream_lines: list[str], hook_records: list[dict]) -> Report:
    """Functional core: decide pass/fail/blocked from what the run left behind."""
    events = []
    for line in stream_lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    if any("hit your weekly limit" in json.dumps(event) for event in events):
        return Report("blocked", "Claude usage limit; try again after it resets")
    if not hook_records:
        return Report(
            "fail",
            "the hook never recorded a rewrite: it did not run, or Jev gave no answer",
        )
    target = hook_records[-1]["to"]
    types = [
        value for event in events for key, value in _walk(event) if key in AGENT_KEYS
    ]
    evidence = [
        json.dumps({key: value})
        for event in events
        for key, value in _walk(event)
        if key == "effort" or (key in AGENT_KEYS and value == target)
    ]
    if target not in types:
        return Report(
            "fail",
            f"the hook chose {target} but no subagent started as it: updatedInput was ignored for Agent",
            evidence,
        )
    return Report("pass", f"a subagent started as {target}", evidence)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "hook.log"
        env = {**os.environ, "JEV_HOOK_LOG": str(log)}
        command = [
            "claude",
            "-p",
            PROMPT,
            "--model",
            SONNET,
            "--effort",
            "medium",
            *claude_session_args(hook_command()),
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-hook-events",
        ]
        run = subprocess.run(
            command, env=env, capture_output=True, text=True, timeout=300, check=False
        )
        records = (
            [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
            if log.exists()
            else []
        )
    report = analyze(run.stdout.splitlines(), records)
    print(f"{report.status.upper()}: {report.reason}")
    for line in dict.fromkeys(report.evidence):
        print(f"  {line}")
    if report.status == "pass":
        print(
            "Also confirm the effort visually: run /tasks in a jev-claude session and read the worker row."
        )
    return {"pass": 0, "fail": 1, "blocked": 2}[report.status]


if __name__ == "__main__":
    raise SystemExit(main())
