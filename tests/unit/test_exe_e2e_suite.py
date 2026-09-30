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
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
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
        encoding="utf-8",
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
    readme = (SUITE / "README.md").read_text(encoding="utf-8")
    for needed in (
        "EXE_E2E",
        "just exe-e2e",
        "EXE_E2E_IMAGE",
        "measurements.jsonl",
        "0 nodes",
    ):
        assert needed in readme, needed


def test_the_forced_stop_needs_its_own_opt_in() -> None:
    # W3 needs the operator on email and the manager's go. Running the
    # directory once started it in W2 (pytest collected it beside the file
    # asked for): EXE_E2E alone must never start it.
    text = (SUITE / "test_forced_stop.py").read_text(encoding="utf-8")
    assert re.search(
        r"pytestmark = pytest\.mark\.skipif\(\s*os\.environ\.get\(\"EXE_E2E_FORCED\"\) != \"1\"",
        text,
    )


def test_a_path_argument_runs_only_that_path() -> None:
    # The directory is the default only when no argument names what to run.
    _, body = recipe("exe-e2e")
    assert re.search(r'if \[ "\$#" -eq 0 \]; then\s+set -- tests/e2e/exe', body)
    assert not re.search(r"pytest tests/e2e/exe", body)


def test_keeping_the_node_up_still_deletes_the_tasks() -> None:
    # W3 chains modules in one wake (EXE_E2E_KEEP_AWAKE=1). The node may stay
    # up; a test's tasks may not, and the lease stays the backstop.
    text = (SUITE / "exe_live.py").read_text(encoding="utf-8")
    body = text[text.index("def leave_asleep") :]
    delete = body.index('"delete", "task"')
    keep = body.index('os.environ.get("EXE_E2E_KEEP_AWAKE")')
    sleep = body.index('"exe-sleep"')
    assert delete < keep < sleep


def test_the_forced_stop_waits_the_window_l2_really_waits() -> None:
    # L2 treats a lease with no drain record as a heartbeat that stopped at
    # the deadline, and forces after HeartbeatStaleAfter, which is
    # heartbeat_stale_ticks L2 ticks (lease.HeartbeatStaleAfter), 20 minutes.
    # A hardcoded 2 minutes read it as L1 ticks and would fail every W3.
    text = (SUITE / "test_forced_stop.py").read_text(encoding="utf-8")
    assert "lease-constants.json" in text
    assert re.search(r'\["heartbeat_stale_ticks"\]\s*\*\s*L2_TICK', text)
    assert "timedelta(minutes=2)" not in text
