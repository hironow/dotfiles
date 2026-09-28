"""The e2e harness never shortens a lease it finds standing (W3 finding 14).

W3 woke the node for an hour. test_control_api_barrier's fixture then ran
`just exe-wake 30m`, which set the lease to 30 minutes from then and cut the
window's hour short, so the manual steps after it had to extend first. A wake
that would end sooner than the lease already standing is now skipped: that
lease keeps the node up, and waking would only shorten it.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType

_HARNESS = Path(__file__).resolve().parents[2] / "tests" / "e2e" / "exe" / "exe_live.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("exe_live", _HARNESS)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # dataclasses resolve the module's annotations through sys.modules
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


live = _load()
NOW = datetime(2026, 9, 29, 1, 15, tzinfo=UTC)


def test_durations_read_as_the_wake_recipe_reads_them() -> None:
    # `just exe-wake` hands its argument to Go's time.ParseDuration.
    assert live.parse_duration("30m") == timedelta(minutes=30)
    assert live.parse_duration("1h") == timedelta(hours=1)
    assert live.parse_duration("1h30m") == timedelta(hours=1, minutes=30)
    assert live.parse_duration("90s") == timedelta(seconds=90)


def test_a_wake_that_would_shorten_the_standing_lease_is_skipped() -> None:
    assert live.wake_would_shorten(NOW + timedelta(minutes=50), NOW, "30m")


def test_every_other_wake_goes_ahead() -> None:
    # a shorter lease, none at all, or one already run out: waking is the point
    assert not live.wake_would_shorten(NOW + timedelta(minutes=20), NOW, "30m")
    assert not live.wake_would_shorten(None, NOW, "30m")
    assert not live.wake_would_shorten(NOW - timedelta(minutes=5), NOW, "1h")
