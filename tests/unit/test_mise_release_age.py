"""The newest-tool policy must also be valid for mise self-update."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_mise_quarantine_is_disabled_with_a_valid_zero_duration() -> None:
    settings = tomllib.loads(
        (ROOT / "config/mise/config.toml").read_text(encoding="utf-8")
    )["settings"]
    # Bare "0" fails mise's date-or-duration parser. Removing the setting
    # restores a 24-hour delay; neither implements our no-quarantine policy.
    assert settings["minimum_release_age"] == "0d"
