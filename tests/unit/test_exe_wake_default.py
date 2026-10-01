"""The `exe-wake` / `exe-extend` recipe defaults ARE the default lease.

exe/lease-constants.json's default_lease_minutes is the lease an operator gets
by typing `just exe-wake` with no argument. The Go reaper and the Quint model
mirror it under their own lockstep tests; the two recipes carry it as a
duration literal in the justfile, which nothing else reads, so this test holds
them to it. A default that drifts from the constant silently changes what a
bare wake costs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_CONSTANTS = _REPO_ROOT / "exe" / "lease-constants.json"

_UNIT_MINUTES = {"h": 60, "m": 1}


def _minutes(duration: str) -> int:
    """Minutes in a Go-style duration made of h/m parts, e.g. "1h30m"."""
    parts = re.findall(r"(\d+)([hm])", duration)
    assert parts and "".join(n + u for n, u in parts) == duration, duration
    return sum(int(n) * _UNIT_MINUTES[u] for n, u in parts)


def _recipe_default(recipe: str) -> str:
    match = re.search(
        rf'^{re.escape(recipe)} duration="([^"]+)":',
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert match, f"{recipe} with a duration default not found in the justfile"
    return match.group(1)


def _default_lease_minutes() -> int:
    return int(
        json.loads(_CONSTANTS.read_text(encoding="utf-8"))["default_lease_minutes"]
    )


def test_exe_wake_default_is_the_default_lease() -> None:
    assert _minutes(_recipe_default("exe-wake")) == _default_lease_minutes()


def test_exe_extend_default_is_the_default_lease() -> None:
    assert _minutes(_recipe_default("exe-extend")) == _default_lease_minutes()


def test_the_default_lease_is_one_hour() -> None:
    # Cost first (manager-loop inbox M20, T4): a bare wake authorises one hour.
    assert _default_lease_minutes() == 60
