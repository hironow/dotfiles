#!/usr/bin/env python3
"""Claude Code PreToolUse hook: let Jev choose how Agent launches run.

- A default worker (general-purpose) moves onto the worker-<effort> definition Jev picks.
- `codex:codex-rescue` gets `--model gpt-6-*` and `--effort` in front of its prompt.

Injected only into `j-cc` sessions (--settings); see docs/runbook/jev-launchers.md.
It fails open: any problem leaves the launch exactly as Claude sent it.
"""

from collections.abc import Callable
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import TextIO

from jev_core import hook_output, plan_agent_rewrite, plan_codex_rewrite
from jev_launch import choose_codex, choose_effort, jev_key, use_utf8_stdio


@dataclass
class Decision:
    output: dict
    record: dict  # evidence for the live verification; never the prompt or the key


def decide(
    payload: object,
    effort_of: Callable[[str], str],
    codex_of: Callable[[str], tuple[str, str]],
) -> Decision | None:
    """Functional core: the hook's JSON output for this call, or None to do nothing."""
    if not isinstance(payload, dict) or payload.get("tool_name") not in {
        "Agent",
        "Task",
    }:
        return None
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    # A cheap shape check first, so calls that will not move never reach Jev.
    if plan_codex_rewrite(tool_input, "", "") is not None:
        model, effort = codex_of(tool_input["prompt"])
        updated = plan_codex_rewrite(tool_input, model, effort)
        record = {"kind": "codex-rescue", "model": model, "effort": effort}
    elif plan_agent_rewrite(tool_input, "medium") is not None:
        effort = effort_of(tool_input["prompt"])
        updated = plan_agent_rewrite(tool_input, effort)
        record = {
            "effort": effort,
            "from": tool_input.get("subagent_type") or "general-purpose",
            "to": f"worker-{effort}",
        }
    else:
        return None
    return Decision(hook_output(updated), record) if updated else None


def _log(record: dict) -> None:
    path = os.environ.get("JEV_HOOK_LOG")
    if path:
        with Path(path).open("a", encoding="utf-8") as log:
            log.write(json.dumps(record) + "\n")


def main(stdin: TextIO, stdout: TextIO) -> None:
    try:
        payload = json.load(stdin)
        key = jev_key()
        if not key:
            return
        decision = decide(
            payload,
            lambda task: choose_effort(task, key),
            lambda task: choose_codex(task, key),
        )
        if decision:
            _log(decision.record)
            json.dump(decision.output, stdout)
    except Exception:  # noqa: BLE001 - a routing helper must never break a session
        return


if __name__ == "__main__":
    use_utf8_stdio()
    main(sys.stdin, sys.stdout)
