"""Session guard: a unit-test run must not leave files in the checkout."""

from __future__ import annotations

from pathlib import Path

import pytest
from _checkout_guard import checkout_changes

ROOT = Path(__file__).resolve().parents[2]
_BEFORE = pytest.StashKey[frozenset[str] | None]()


def pytest_sessionstart(session: pytest.Session) -> None:
    session.config.stash[_BEFORE] = checkout_changes(ROOT)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
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
