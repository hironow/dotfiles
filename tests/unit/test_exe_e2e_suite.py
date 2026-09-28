"""The live e2e suite's own contract (Phase 6 plan D13, item 6.10).

tests/e2e/exe wakes the real node, so it must never run by accident: without
EXE_E2E=1 every test in it is skipped, and `just exe-e2e` is the one way in.
These tests run pytest on the suite without the variable, and read the recipe.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SUITE = REPO / "tests" / "e2e" / "exe"
JUSTFILE = REPO / "justfile"


def recipe(name: str) -> tuple[list[str], str]:
    """A recipe's attribute lines and its body, from the root justfile."""
    lines = JUSTFILE.read_text().splitlines()
    start = next(
        i for i, line in enumerate(lines) if re.match(rf"^{re.escape(name)}\b.*:", line)
    )
    attributes = []
    i = start - 1
    while i >= 0 and lines[i].startswith("["):
        attributes.append(lines[i])
        i -= 1
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return attributes, "\n".join(body)


def test_without_exe_e2e_every_live_test_is_skipped() -> None:
    env = {k: v for k, v in os.environ.items() if k != "EXE_E2E"}
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(SUITE),
            "-q",
            "-p",
            "no:cacheprovider",
            "-rs",
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    summary = r.stdout.strip().splitlines()[-1]
    assert re.search(r"\b\d+ skipped\b", summary), summary
    assert "passed" not in summary and "failed" not in summary, summary


def test_the_suite_has_the_graceful_and_the_forced_path() -> None:
    names = {p.name for p in SUITE.glob("test_*.py")}
    assert names >= {"test_graceful_stop.py", "test_forced_stop.py"}


def test_the_recipe_is_the_way_in() -> None:
    attributes, body = recipe("exe-e2e")
    assert "[positional-arguments]" in attributes
    assert "EXE_E2E=1" in body
    assert "tests/e2e/exe" in body
    assert '"$@"' in body
    # a live run needs the image it runs, pinned by digest
    assert re.search(r"\$\{EXE_E2E_IMAGE:\?", body)


def test_the_readme_says_what_each_run_costs_and_leaves() -> None:
    readme = (SUITE / "README.md").read_text()
    for needed in (
        "EXE_E2E",
        "just exe-e2e",
        "EXE_E2E_IMAGE",
        "measurements.jsonl",
        "0 nodes",
    ):
        assert needed in readme, needed
