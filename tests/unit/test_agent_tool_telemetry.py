"""rtk and headroom are base tools (ADR 0047), installed through mise, with
their anonymous telemetry off everywhere they run.

rtk only reports after an explicit opt-in, but headroom's beacon is on by
default, so both are pinned off by environment: mise's global [env] for shells
that activate mise, the shared Claude settings env for Claude Code and every
hook it runs (rtk's rewrite hook included) wherever it was launched from, and
the persisted Windows User environment for anything started outside a shell.

Two variables, not one, for headroom: `HEADROOM_BEACON=off` is its own switch
and `DO_NOT_TRACK=1` is the cross-vendor opt-out it also honours. Both are
spelled out, because the beacon fails OPEN -- any value but `off` uploads --
and because a tool that reads only the general opt-out must see it too.

Every one of these sources covers processes a shell or Claude Code starts. A
headroom process started by something else carries them EXPLICITLY instead
(`scripts/jev_headroom.py`'s proxy), because the proxy reads neither Claude's
settings nor an interactive shell's mise env. `just doctor` then reads all
three sources back off this machine (`scripts/ai_tools_check.py`), and asks
headroom itself whether its beacon is on.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TELEMETRY_OFF = {
    "RTK_TELEMETRY_DISABLED": "1",
    "HEADROOM_BEACON": "off",
    "DO_NOT_TRACK": "1",
}

# What a headroom process must carry, wherever it was started from.
HEADROOM_OFF = {k: v for k, v in TELEMETRY_OFF.items() if k != "RTK_TELEMETRY_DISABLED"}

sys.path.insert(0, str(ROOT / "scripts"))

import ai_tools_check  # noqa: E402
import jev_headroom as hr  # noqa: E402


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


def test_the_proxy_process_carries_them_whatever_it_inherited() -> None:
    """The proxy is not started by a shell or by Claude Code, so none of the
    sources above reaches it: j-cc sets them on the process itself, and an
    inherited `on` must not win."""
    env = hr.proxy_env({"HEADROOM_BEACON": "on", "DO_NOT_TRACK": "0", "PATH": "p"})
    assert {name: env.get(name) for name in HEADROOM_OFF} == HEADROOM_OFF
    assert env["PATH"] == "p", "the rest of the environment passes through"


def test_the_doctor_checks_the_same_switches_this_test_declares() -> None:
    """Declaring the values is not the same as a machine having them, so
    `just doctor` reads all three sources back (scripts/ai_tools_check.py's
    _telemetry). It must look for exactly these switches: a value it does not
    know about is one nobody would notice missing."""
    assert ai_tools_check.TELEMETRY_OFF == TELEMETRY_OFF
