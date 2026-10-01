"""rtk and headroom are base tools (ADR 0047), installed through mise, with
their anonymous telemetry off everywhere they run.

rtk only reports after an explicit opt-in, but headroom's beacon is on by
default, so both are pinned off by environment: mise's global [env] for shells
that activate mise, the shared Claude settings env for Claude Code and every
hook it runs (rtk's rewrite hook included) wherever it was launched from, and
the persisted Windows User environment for anything started outside a shell.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_OFF = {"RTK_TELEMETRY_DISABLED": "1", "HEADROOM_BEACON": "off"}


def _mise() -> dict:
    return tomllib.loads((ROOT / "config/mise/config.toml").read_text(encoding="utf-8"))


def test_mise_installs_rtk_and_headroom_everywhere() -> None:
    tools = _mise()["tools"]
    assert "rtk" in tools
    headroom = tools["pypi:headroom-ai"]
    # `headroom wrap` starts the proxy; the bare package ships no proxy server
    assert "proxy" in headroom["extras"]
    for name in ("rtk", "pypi:headroom-ai"):
        spec = tools[name]
        assert not (isinstance(spec, dict) and "os" in spec), f"{name} is OS-gated"


def test_mise_env_turns_the_telemetry_off() -> None:
    env = _mise()["env"]
    assert {name: env.get(name) for name in TELEMETRY_OFF} == TELEMETRY_OFF


def test_claude_sessions_and_hooks_get_the_telemetry_off() -> None:
    shared = json.loads(
        (ROOT / ".claude/settings.shared.json").read_text(encoding="utf-8")
    )
    assert {name: shared["env"].get(name) for name in TELEMETRY_OFF} == TELEMETRY_OFF


def test_harden_env_persists_the_telemetry_off_for_windows() -> None:
    text = (ROOT / "scripts/harden_env.sh").read_text(encoding="utf-8")
    for name, value in TELEMETRY_OFF.items():
        assert re.search(
            rf"SetEnvironmentVariable\('{name}', '{value}', 'User'\)", text
        ), f"harden-env does not persist {name}={value} for the Windows user"
