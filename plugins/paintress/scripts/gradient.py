#!/usr/bin/env python3
"""Read and update the Gradient Gauge state for paintress expeditions."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LEVEL_NAMES = {
    0: "Depleted",
    1: "Warming",
    2: "Steady",
    3: "Rising",
    4: "Surging",
    5: "Gradient Attack",
}

PRIORITY_HINTS = {
    0: "Only pick low-priority, small-scope issues",
    1: "Low to normal priority",
    2: "Normal priority",
    3: "Normal to high priority",
    4: "High priority OK",
    5: "Attempt the most complex/highest-priority issue available",
}

DEFAULT_STATE: dict[str, int | str] = {
    "level": 0,
    "consecutive_failures": 0,
    "consecutive_skips": 0,
    "last_status": "",
    "last_updated": "",
}


def read_state(path: Path) -> dict:
    if not path.exists():
        return dict(DEFAULT_STATE)
    with path.open() as f:
        return json.load(f)


def write_state(path: Path, state: dict) -> None:
    with path.open("w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
        f.write("\n")


def update_state(state: dict, status: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()

    if status == "success":
        state["level"] = min(state.get("level", 0) + 1, 5)
        state["consecutive_failures"] = 0
        state["consecutive_skips"] = 0
    elif status.startswith("skip"):
        state["level"] = max(state.get("level", 0) - 1, 0)
        state["consecutive_failures"] = 0
        state["consecutive_skips"] = state.get("consecutive_skips", 0) + 1
    elif status.startswith("fail") or status.startswith("partial"):
        state["level"] = 0
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        state["consecutive_skips"] = 0

    state["last_status"] = status
    state["last_updated"] = now
    return state


def format_output(state: dict) -> dict:
    level = state.get("level", 0)
    return {
        **state,
        "level_name": LEVEL_NAMES.get(level, "Unknown"),
        "priority_hint": PRIORITY_HINTS.get(level, ""),
        "gommage": (
            state.get("consecutive_failures", 0) >= 3
            or state.get("consecutive_skips", 0) >= 3
        ),
    }


def main() -> None:
    if len(sys.argv) < 3:
        print(
            "Usage: gradient.py <read|update> <gradient.json> [status]",
            file=sys.stderr,
        )
        sys.exit(1)

    command = sys.argv[1]
    path = Path(sys.argv[2])

    if command == "read":
        state = read_state(path)
        print(json.dumps(format_output(state), indent=2, ensure_ascii=False))

    elif command == "update":
        if len(sys.argv) < 4:
            print("Usage: gradient.py update <gradient.json> <status>", file=sys.stderr)
            sys.exit(1)
        status = sys.argv[3]
        state = read_state(path)
        state = update_state(state, status)
        write_state(path, state)
        print(json.dumps(format_output(state), indent=2, ensure_ascii=False))

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
