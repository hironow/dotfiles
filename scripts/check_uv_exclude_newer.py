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

DEFAULT_WINDOW = timedelta(days=7)
_RELATIVE_DAYS = re.compile(r"^\s*(\d+)\s*(?:d|day|days)\s*$")


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


def quarantine_window(pyproject_text: str) -> timedelta:
    """The global `exclude-newer` span ("N days"); DEFAULT_WINDOW if absent/absolute."""
    tool_uv = tomllib.loads(pyproject_text).get("tool", {}).get("uv", {})
    raw = tool_uv.get("exclude-newer")
    if isinstance(raw, str) and (m := _RELATIVE_DAYS.match(raw)):
        return timedelta(days=int(m.group(1)))
    return DEFAULT_WINDOW


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
        window = quarantine_window(text)
        try:
            expired = expired_overrides(text, now=now, window=window)
        except ValueError as exc:
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
