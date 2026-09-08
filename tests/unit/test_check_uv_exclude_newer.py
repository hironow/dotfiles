"""Unit tests for scripts/check_uv_exclude_newer.py.

`[tool.uv] exclude-newer-package` lets one security fix through the 7-day
supply-chain quarantine (`exclude-newer = "7 days"`) by giving that package an
absolute upload-time cutoff. The cutoff never expires on its own: once the
release is older than the quarantine window the entry is dead weight that
silently freezes the package at that version, so later bumps become no-ops.
This gate fails when any entry's cutoff is older than the window, forcing the
entry to be deleted (and the lock re-resolved) instead of forgotten.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_uv_exclude_newer.py"


def _load():  # noqa: ANN202 - module object
    spec = importlib.util.spec_from_file_location("check_uv_exclude_newer", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)
WINDOW = timedelta(days=7)


def _pyproject(*entries: str, window: str = '"7 days"') -> str:
    body = ", ".join(entries)
    return (
        '[project]\nname = "x"\nversion = "0"\n\n[tool.uv]\n'
        f"exclude-newer = {window}\n"
        f"exclude-newer-package = {{ {body} }}\n"
    )


def test_fresh_override_is_not_reported() -> None:
    mod = _load()
    text = _pyproject('mlflow = "2026-09-04T06:00:00Z"')  # 4 days before NOW
    assert mod.expired_overrides(text, now=NOW, window=WINDOW) == []


def test_override_older_than_window_is_reported_with_its_age() -> None:
    mod = _load()
    text = _pyproject('mlflow = "2026-08-30T00:00:00Z"')  # 9.5 days before NOW
    found = mod.expired_overrides(text, now=NOW, window=WINDOW)
    assert [(pkg, cutoff.date().isoformat()) for pkg, cutoff, _age in found] == [
        ("mlflow", "2026-08-30")
    ]
    assert found[0][2] > WINDOW


def test_boundary_exactly_at_window_is_still_fresh() -> None:
    mod = _load()
    text = _pyproject('pkg = "2026-09-01T12:00:00Z"')  # exactly 7 days
    assert mod.expired_overrides(text, now=NOW, window=WINDOW) == []


def test_date_only_cutoff_is_accepted_as_midnight_utc() -> None:
    mod = _load()
    text = _pyproject('old = "2026-08-01"', 'new = "2026-09-06"')
    found = mod.expired_overrides(text, now=NOW, window=WINDOW)
    assert [pkg for pkg, _c, _a in found] == ["old"]


def test_window_is_read_from_the_global_exclude_newer_span() -> None:
    mod = _load()
    assert mod.quarantine_window(_pyproject('a = "2026-09-01"')) == timedelta(days=7)
    assert mod.quarantine_window(
        _pyproject('a = "2026-09-01"', window='"3 days"')
    ) == timedelta(days=3)


def test_window_falls_back_to_default_when_global_is_absent_or_absolute() -> None:
    mod = _load()
    assert mod.quarantine_window("[tool.uv]\n") == timedelta(days=7)
    assert mod.quarantine_window(
        '[tool.uv]\nexclude-newer = "2026-01-01T00:00:00Z"\n'
    ) == timedelta(days=7)


def test_no_tool_uv_table_means_nothing_to_check() -> None:
    mod = _load()
    assert (
        mod.expired_overrides('[project]\nname = "x"\n', now=NOW, window=WINDOW) == []
    )


def test_unparsable_cutoff_raises_value_error_naming_the_package() -> None:
    mod = _load()
    with pytest.raises(ValueError, match="broken"):
        mod.expired_overrides(_pyproject('broken = "soon"'), now=NOW, window=WINDOW)


def test_main_fails_and_names_expired_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load()
    py = tmp_path / "pyproject.toml"
    py.write_text(
        _pyproject('mlflow = "2026-08-20T00:00:00Z"', 'fresh = "2026-09-05T00:00:00Z"')
    )
    rc = mod.main([str(py), "--now", NOW.isoformat()])
    out = capsys.readouterr()
    assert rc == 1
    assert "mlflow" in out.err and "fresh" not in out.err
    assert "uv lock" in out.err  # tells the reader how to clean up


def test_main_passes_when_every_override_is_inside_the_window(tmp_path: Path) -> None:
    mod = _load()
    py = tmp_path / "pyproject.toml"
    py.write_text(_pyproject('mlflow = "2026-09-04T06:00:00Z"'))
    assert mod.main([str(py), "--now", NOW.isoformat()]) == 0


def test_main_treats_a_project_without_overrides_as_clean(tmp_path: Path) -> None:
    mod = _load()
    py = tmp_path / "pyproject.toml"
    py.write_text('[project]\nname = "x"\nversion = "0"\n')
    assert mod.main([str(py), "--now", NOW.isoformat()]) == 0


def test_main_fails_on_a_missing_pyproject(tmp_path: Path) -> None:
    mod = _load()
    assert mod.main([str(tmp_path / "nope" / "pyproject.toml")]) == 1
