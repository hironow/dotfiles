"""`just update-all` also updates the Pi extensions.

`just deploy` (scripts/install_pi_extensions.py) installs a declared Pi
package only when it is missing and deliberately leaves healthy ones alone.
Without an explicit update path, each machine kept whatever version it first
installed: a Windows host stayed on a pi-background-tasks release that aborts
every Sonnet 5.5 session once the anthropic provider is logged in, while WSL
had moved on. `pi update --extensions` goes through npm, so ~/.npmrc's
seven-day quarantine (`just harden-env`) still gates the packages it does not
exempt.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

JUSTFILE = Path(__file__).resolve().parents[2] / "justfile"


def _recipe_body(name: str) -> str:
    text = JUSTFILE.read_text(encoding="utf-8")
    match = re.search(
        rf"^{re.escape(name)}:\n((?:[ \t]+.*\n|\n)+?)(?=^\S|\Z)", text, re.M
    )
    assert match, f"recipe {name} not found"
    return match.group(1)


@pytest.mark.parametrize("recipe", ["update-all", "update-all-safe"])
def test_update_all_updates_the_pi_extensions(recipe: str) -> None:
    body = _recipe_body(recipe)
    assert "pi update --extensions" in body
    # a machine without Pi skips the step instead of failing the whole update
    assert "command -v pi" in body
    # npm's quarantine can refuse a fresh transitive dependency of an exempt
    # extension (ETARGET); that is the quarantine working, so warn and go on
    # with the remaining updates instead of aborting them
    step = next(line for line in body.splitlines() if "pi update --extensions" in line)
    assert "pi update --extensions ||" in step
