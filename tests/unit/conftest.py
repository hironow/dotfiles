"""Session guard: a unit-test run must not leave files in the checkout."""

from __future__ import annotations

from pathlib import Path

import pytest
from _checkout_guard import checkout_changes

ROOT = Path(__file__).resolve().parents[2]
_BEFORE = pytest.StashKey[frozenset[str] | None]()


def _xdist_worker(session: pytest.Session) -> bool:
    """Under pytest-xdist the controller's session starts before every worker
    and finishes after them all, so it alone guards the checkout; a worker's
    verdict would not reach the run's exit status anyway."""
    return hasattr(session.config, "workerinput")


def pytest_sessionstart(session: pytest.Session) -> None:
    if _xdist_worker(session):
        return
    session.config.stash[_BEFORE] = checkout_changes(ROOT)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if _xdist_worker(session):
        return
    before = session.config.stash.get(_BEFORE, None)
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if before is None:
        if reporter is not None:
            reporter.write_line("checkout guard: no git baseline; skipped")
        return
    after = checkout_changes(ROOT) or frozenset()
    left = sorted(after - before)
    if not left:
        return
    if reporter is not None:
        reporter.write_line(
            f"checkout guard: the run left files in the checkout: {left}"
        )
    session.exitstatus = pytest.ExitCode.TESTS_FAILED
