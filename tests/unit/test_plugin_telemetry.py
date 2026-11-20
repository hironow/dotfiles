"""A declared Claude plugin whose own telemetry is on by default is switched off.

The switch goes in the shared Claude settings env, which reaches Claude Code and
every hook a plugin runs, wherever the session was launched from.

vercel@claude-plugins-official: its SessionStart and PostToolUse hooks POST to
telemetry.vercel.com unless VERCEL_PLUGIN_TELEMETRY=off
(vercel/vercel-plugin hooks/src/telemetry.mts, getTelemetryOverride). It does
not read DO_NOT_TRACK.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_OFF = {
    "vercel@claude-plugins-official": {"VERCEL_PLUGIN_TELEMETRY": "off"},
}


def _json(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def test_each_plugin_with_default_on_telemetry_is_declared() -> None:
    plugins = _json("dump/harness/claude-plugins.json")["plugins"]
    assert set(TELEMETRY_OFF) <= set(plugins)


def test_its_telemetry_is_off_in_the_shared_claude_env() -> None:
    env = _json(".claude/settings.shared.json")["env"]
    for plugin, switches in TELEMETRY_OFF.items():
        for name, value in switches.items():
            assert env.get(name) == value, (plugin, name)
