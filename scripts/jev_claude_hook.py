#!/usr/bin/env python3
"""Claude Code PreToolUse hook: run default Agent launches at Jev's chosen effort.

Injected only into `jev-claude` sessions (--settings); see docs/runbook/jev-launchers.md.
It fails open: any problem leaves the launch exactly as Claude sent it.
"""

from collections.abc import Callable
import json
import os
from pathlib import Path
import sys
from typing import TextIO

from jev_core import hook_output, plan_agent_rewrite
from jev_launch import choose_effort, jev_key


def decide(payload: object, effort_of: Callable[[str], str]) -> dict | None:
    """Functional core: the hook's JSON output for this call, or None to do nothing."""
    if not isinstance(payload, dict) or payload.get("tool_name") not in {
        "Agent",
        "Task",
    }:
        return None
    tool_input = payload.get("tool_input")
    # A cheap shape check first, so calls that will not move never reach Jev.
    if (
        not isinstance(tool_input, dict)
        or plan_agent_rewrite(tool_input, "medium") is None
    ):
        return None
    updated = plan_agent_rewrite(tool_input, effort_of(tool_input["prompt"]))
    return hook_output(updated) if updated else None


def _record(before: dict, after: dict, effort: str) -> None:
    """Optional evidence for the verification run; never contains the prompt or key."""
    path = os.environ.get("JEV_HOOK_LOG")
    if path:
        record = {
            "effort": effort,
            "from": before.get("subagent_type") or "general-purpose",
            "to": after["subagent_type"],
        }
        with Path(path).open("a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")


def main(stdin: TextIO, stdout: TextIO) -> None:
    try:
        payload = json.load(stdin)
        key = jev_key()
        if not key:
            return
        chosen: list[str] = []

        def effort_of(task: str) -> str:
            chosen.append(choose_effort(task, key))
            return chosen[0]

        output = decide(payload, effort_of)
        if output:
            _record(
                payload["tool_input"],
                output["hookSpecificOutput"]["updatedInput"],
                chosen[0],
            )
            json.dump(output, stdout)
    except Exception:  # noqa: BLE001 - a routing helper must never break a session
        return


if __name__ == "__main__":
    main(sys.stdin, sys.stdout)
