"""The hook-rejection scan must not match the phrase inside job payloads.

Why this exists
---------------
The runner refuses a hook whose path lacks a script extension with:

    ArgumentException: /usr/local/bin/runner-gc is not a valid path to a
    script. Make sure it ends in '.sh', '.ps1' or '.js'.

`just status` finds that by grepping the job's own log, which is the only
place it is recorded. But a Worker log also contains the **job payload** —
inputs, environment, and the body of the PR that triggered it. Grepping for
the bare phrase therefore matches any job whose PR description happens to
quote it.

That is not hypothetical: this repo's own work on the disk GC produced PRs
discussing the rejection message, and running one of them turned `just status`
red with `hook REJECTED in 1 of the 11 job(s)` while the hook was working
perfectly. A monitor that cries wolf about its own documentation is worse than
none — the next real rejection gets waved off.

Anchoring on the configured hook path fixes it: the runner names the path it
refused, and a payload quoting the phrase does not carry this runner's hook
value in front of it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
STATUS_SH = ROOT / "scripts" / "gc_status.sh"

PHRASE = "is not a valid path to a script"


@pytest.fixture(scope="module")
def status_text() -> str:
    return STATUS_SH.read_text(encoding="utf-8")


def test_rejection_scan_is_anchored_to_the_hook_path(status_text: str) -> None:
    """Both legs must search for "<hook> <phrase>", never the phrase alone."""
    bare = [
        (n, line.strip())
        for n, line in enumerate(status_text.splitlines(), 1)
        if PHRASE in line
        # The comment explaining the trap may name the phrase; only reject it
        # where it is actually used as a search pattern.
        and not line.lstrip().startswith("#")
        and not re.search(r"\$\{?_?h", line, re.IGNORECASE)
    ]
    assert not bare, (
        "these searches match the phrase anywhere in the job log, including a "
        f"PR body that merely quotes it: {bare}"
    )


def test_rejection_scan_matches_literally(status_text: str) -> None:
    """A hook path is a filesystem path, not a regex.

    Windows paths carry backslashes and both legs may see `.`; interpolating
    one into a regex would either mis-match or, worse, quietly match something
    else. Both greps have to be literal.
    """
    used = [line for line in status_text.splitlines() if PHRASE in line]
    assert used, "status must still detect the runner's rejection message"
    literal = [
        line
        for line in used
        if line.lstrip().startswith("#") or "grep -lF" in line or "-SimpleMatch" in line
    ]
    assert len(literal) == len(used), (
        "the hook path must be matched literally (`grep -lF` / PowerShell "
        f"`-SimpleMatch`), not as a pattern: {set(used) - set(literal)}"
    )
