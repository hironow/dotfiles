#!/usr/bin/env python3
"""Fail when a `[tool.uv] exclude-newer-package` override has outlived the quarantine.

The uv projects in this repo hold back every release for 7 days
(`[tool.uv] exclude-newer = "7 days"`, ADR 0028 / dependabot.yaml). A security
fix that needs a younger release is let through per package with
`exclude-newer-package = { <pkg> = "<upload time>" }` — an ABSOLUTE cutoff.
That cutoff never expires by itself: once the admitted release is older than
the window the entry only freezes the package at that version, so later
Dependabot bumps become silent no-ops. This gate turns the "removable after
<date>" comment into a mechanical failure: delete the entry, run `uv lock`.

Usage: check_uv_exclude_newer.py PYPROJECT [PYPROJECT ...] [--now ISO8601]
Exit 0 = every override is younger than the window (or none exist); 1 = at
least one expired / unparsable entry, or a pyproject could not be read.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Fixed-length units uv accepts for a relative `exclude-newer` span. Calendar
# units (month, year) have no fixed length and are refused rather than guessed.
_SPAN_UNITS: dict[str, timedelta] = {
    "minute": timedelta(minutes=1),
    "min": timedelta(minutes=1),
    "m": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "hr": timedelta(hours=1),
    "h": timedelta(hours=1),
    "day": timedelta(days=1),
    "d": timedelta(days=1),
    "week": timedelta(weeks=1),
    "wk": timedelta(weeks=1),
    "w": timedelta(weeks=1),
}
_RELATIVE_SPAN = re.compile(r"^\s*(\d+)\s*([a-zA-Z]+)\s*$")


def _parse_cutoff(pkg: str, raw: object) -> datetime:
    """RFC 3339 timestamp or bare YYYY-MM-DD (= midnight UTC), as uv accepts."""
    if not isinstance(raw, str):
        raise ValueError(
            f"{pkg}: exclude-newer-package value must be a string, got {raw!r}"
        )
    text = raw.strip()
    if len(text) == 10:
        text += "T00:00:00Z"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{pkg}: cannot parse exclude-newer-package cutoff {raw!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def quarantine_window(pyproject_text: str) -> timedelta | None:
    """The global `exclude-newer` span as a duration, or None when the project
    has no relative quarantine (absent, or an absolute timestamp): then the
    per-package entries are plain pins and nothing can "expire".

    Raises ValueError for a relative span this gate cannot measure (calendar
    units, unknown words) — guessing 7 days here once told a reviewer to delete
    a load-bearing override.
    """
    tool_uv = tomllib.loads(pyproject_text).get("tool", {}).get("uv", {})
    raw = tool_uv.get("exclude-newer")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if _looks_absolute(text):
        return None
    m = _RELATIVE_SPAN.match(text)
    if m is None:
        raise ValueError(f"cannot measure global exclude-newer span {raw!r}")
    count, unit = int(m.group(1)), m.group(2).lower().rstrip("s")
    if unit not in _SPAN_UNITS:
        raise ValueError(
            f"cannot measure global exclude-newer span {raw!r}: unit {m.group(2)!r} "
            "has no fixed length or is unknown (minutes/hours/days/weeks are supported)"
        )
    return count * _SPAN_UNITS[unit]


def _looks_absolute(text: str) -> bool:
    """RFC 3339 timestamp or YYYY-MM-DD, as uv also accepts for exclude-newer."""
    try:
        _parse_cutoff("exclude-newer", text)
    except ValueError:
        return False
    return True


def expired_overrides(
    pyproject_text: str, *, now: datetime, window: timedelta
) -> list[tuple[str, datetime, timedelta]]:
    """(package, cutoff, age) for every override whose cutoff is older than `window`."""
    tool_uv = tomllib.loads(pyproject_text).get("tool", {}).get("uv", {})
    overrides = tool_uv.get("exclude-newer-package") or {}
    expired: list[tuple[str, datetime, timedelta]] = []
    for pkg, raw in overrides.items():
        cutoff = _parse_cutoff(pkg, raw)
        age = now - cutoff
        if age > window:
            expired.append((pkg, cutoff, age))
    return expired


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("pyprojects", nargs="+", help="pyproject.toml files to check")
    parser.add_argument("--now", help="override the current time (ISO 8601; tests)")
    args = parser.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    failed = False
    for path_str in args.pyprojects:
        path = Path(path_str)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"check-uv-exclude-newer: cannot read {path}: {exc}", file=sys.stderr)
            failed = True
            continue
        try:
            window = quarantine_window(text)
            if window is None:
                continue  # no relative quarantine here -> nothing can expire
            expired = expired_overrides(text, now=now, window=window)
        except (ValueError, tomllib.TOMLDecodeError) as exc:
            print(f"check-uv-exclude-newer: {path}: {exc}", file=sys.stderr)
            failed = True
            continue
        for pkg, cutoff, age in expired:
            print(
                f"check-uv-exclude-newer: {path}: exclude-newer-package `{pkg}` cutoff "
                f"{cutoff.date().isoformat()} is {age.days} days old (window {window.days}d) — "
                f"the release it admits is out of quarantine; delete the entry and run `uv lock`",
                file=sys.stderr,
            )
            failed = True
    if not failed:
        print(
            "check-uv-exclude-newer: OK -- no exclude-newer-package override has outlived the quarantine window"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
