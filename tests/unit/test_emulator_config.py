"""Static checks that keep the emulator's side files in step with compose.yaml.

The env example, the local `ci-emu` gate, and the published ports each restate
something compose.yaml or the emulator workflow already decides. These tests
read both sides, so a port or a step that changes in one place cannot leave the
other describing a stack that no longer exists.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EMULATOR = ROOT / "emulator"
WORKFLOW = ROOT / ".github" / "workflows" / "test-emulators.yaml"

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


_SCRIPT = re.compile(r"\bscripts/([\w.-]+\.sh)\b")
_JUST_CALL = re.compile(r"^\s*just ([\w-]+)")


def _recipe_lines(recipes: dict, name: str, seen: set[str]) -> list[str]:
    """The body of `name` with every nested `just <recipe>` line expanded.

    `just --dump` returns each body line as a list of fragments: plain strings
    and nested lists for `{{ ... }}` interpolations. Only the strings matter
    here, so the interpolations are dropped.
    """
    if name in seen:
        return []
    seen.add(name)
    lines: list[str] = []
    for fragments in recipes[name]["body"]:
        line = "".join(part for part in fragments if isinstance(part, str))
        called = _JUST_CALL.match(line)
        if called and called.group(1) in recipes:
            lines += _recipe_lines(recipes, called.group(1), seen)
        else:
            lines.append(line)
    return lines


@pytest.mark.skipif(shutil.which("just") is None, reason="needs just to dump recipes")
def test_ci_emu_runs_only_scripts_the_emulator_workflow_runs() -> None:
    # `ci-emu` is the local equivalent of the emulator workflow. A script the
    # workflow left out on purpose (it needs a service the lite stack does not
    # start) must not come back through the local gate.
    dump = subprocess.run(
        [
            "just",
            "--justfile",
            str(ROOT / "justfile"),
            "--dump",
            "--dump-format",
            "json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    recipes = json.loads(dump)["recipes"]
    local = {
        script
        for line in _recipe_lines(recipes, "ci-emu", set())
        for script in _SCRIPT.findall(line)
    }
    workflow = {
        script
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
        for script in _SCRIPT.findall(line)
    }
    assert local, "ci-emu runs no emulator script; the expansion found nothing"
    extra = sorted(local - workflow)
    assert not extra, (
        f"ci-emu runs {extra}, which the emulator workflow does not run. "
        "Keep the local gate to the workflow's steps."
    )


def _service_block(name: str) -> str:
    text = (EMULATOR / "compose.yaml").read_text(encoding="utf-8")
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:\n|^\S)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert match, f"compose.yaml has no {name} service"
    return match.group(1)


def test_mcp_inspector_publishes_its_proxy_for_the_browser() -> None:
    # The Inspector UI runs in the browser and calls its proxy directly on
    # <page host>:6277 (upstream client/src/utils/configUtils.ts). The proxy
    # accepts only origins in ALLOWED_ORIGINS and needs its session token.
    block = _service_block("mcp-inspector")
    ports = re.findall(r'^\s+- "([^"]+)"', block, re.MULTILINE)
    assert ports, "mcp-inspector publishes no port"
    assert all(port.startswith("127.0.0.1:") for port in ports), (
        f"bind every Inspector port to loopback: {ports}"
    )
    assert "127.0.0.1:${MCP_INSPECTOR_PORT:-6274}:6274" in ports
    assert any(port.endswith(":6277") for port in ports), (
        "publish the proxy port 6277; the browser UI cannot reach it otherwise"
    )
    origins = re.search(r"^\s+- ALLOWED_ORIGINS=(\S+)$", block, re.MULTILINE)
    assert origins, "set ALLOWED_ORIGINS so the proxy accepts the published UI"
    assert "http://localhost:${MCP_INSPECTOR_PORT:-6274}" in origins.group(1).split(",")
    assert re.search(r"^\s+- MCP_AUTO_OPEN_ENABLED=false$", block, re.MULTILINE), (
        "turn off the auto-open; there is no browser inside the container"
    )
    assert "DANGEROUSLY_OMIT_AUTH" not in block, "keep the proxy's auth token"
