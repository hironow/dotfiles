"""Static checks that keep the emulator's side files in step with compose.yaml.

The env example, the local `ci-emu` gate, and the published ports each restate
something compose.yaml or the emulator workflow already decides. These tests
read both sides, so a port or a step that changes in one place cannot leave the
other describing a stack that no longer exists.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EMULATOR = ROOT / "emulator"

# A published port is `"127.0.0.1:<host>:<container>"`, where <host> is a
# number or `${VAR:-<default>}`.
_PUBLISHED = re.compile(r'"127\.0\.0\.1:(?:\$\{\w+:-(\d+)\}|(\d+)):(\d+)"')
_ENV_LOCALHOST = re.compile(r"^export (\w+)=localhost:(\d+)\s*$", re.MULTILINE)


def _published_host_ports() -> set[str]:
    text = (EMULATOR / "compose.yaml").read_text(encoding="utf-8")
    return {default or fixed for default, fixed, _ in _PUBLISHED.findall(text)}


def test_env_example_localhost_ports_are_published_host_ports() -> None:
    published = _published_host_ports()
    env = (EMULATOR / ".env.local.example").read_text(encoding="utf-8")
    pairs = _ENV_LOCALHOST.findall(env)
    assert pairs, "the env example names no localhost:<port> address"
    stale = {name: port for name, port in pairs if port not in published}
    assert not stale, (
        f"{stale} point at ports compose.yaml does not publish on the host. "
        "Use the default host port from emulator/compose.yaml."
    )
