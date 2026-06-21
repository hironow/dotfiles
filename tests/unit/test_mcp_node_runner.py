"""Unit tests for scripts/check_mcp_node_runner.py.

MCP servers are launched by the agent host directly (not through the Bash
tool), so the PreToolUse Bash guard and the `Bash(npx:*)` permission deny do
NOT cover them -- a `command: "npx"` can sneak into a committed MCP config
unchecked (one already did). This static gate is the only wall enforcing the
bun-only Node policy (ADR 0027) for MCP client configs.

The checker is parser-based (json + tomllib), mirroring the
"parser, not regex" stance of the block-prohibited-commands guard.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_mcp_node_runner.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_mcp_node_runner", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


# --- direct commands ---------------------------------------------------------


def test_npx_in_mcp_servers_is_flagged() -> None:
    cfg = {"mcpServers": {"docs": {"command": "npx", "args": ["-y", "some-pkg"]}}}
    assert mod.find_violations(cfg, ".mcp.json")


@pytest.mark.parametrize("runner", ["npm", "npx", "pnpm", "pnpx", "yarn", "yarnpkg"])
def test_every_banned_runner_is_flagged(runner: str) -> None:
    cfg = {"mcpServers": {"s": {"command": runner, "args": []}}}
    assert mod.find_violations(cfg, "f.json")


@pytest.mark.parametrize("ok", ["bunx", "bun", "node", "uvx", "uv", "deno", "docker"])
def test_allowed_runners_are_clean(ok: str) -> None:
    cfg = {"mcpServers": {"s": {"command": ok, "args": ["start"]}}}
    assert mod.find_violations(cfg, "f.json") == []


def test_absolute_path_npx_is_flagged() -> None:
    cfg = {"mcpServers": {"s": {"command": "/opt/homebrew/bin/npx", "args": []}}}
    assert mod.find_violations(cfg, "f.json")


# --- wrapper / corepack / shell forms ---------------------------------------


def test_env_wrapper_does_not_hide_npx() -> None:
    cfg = {"mcpServers": {"s": {"command": "env", "args": ["FOO=1", "npx", "pkg"]}}}
    assert mod.find_violations(cfg, "f.json")


def test_corepack_versioned_pm_is_flagged() -> None:
    cfg = {"mcpServers": {"s": {"command": "corepack", "args": ["pnpm@9", "dlx", "x"]}}}
    assert mod.find_violations(cfg, "f.json")


def test_mise_exec_runner_is_flagged() -> None:
    cfg = {"mcpServers": {"s": {"command": "mise", "args": ["exec", "--", "npx", "p"]}}}
    assert mod.find_violations(cfg, "f.json")


def test_bash_dash_c_with_npx_is_flagged() -> None:
    cfg = {"mcpServers": {"s": {"command": "bash", "args": ["-c", "npx -y pkg"]}}}
    assert mod.find_violations(cfg, "f.json")


def test_bun_x_subcommand_is_clean() -> None:
    """`bun x pkg` is the bun-native runner, not a banned one."""
    cfg = {"mcpServers": {"s": {"command": "bun", "args": ["x", "pkg"]}}}
    assert mod.find_violations(cfg, "f.json") == []


# --- schema shapes -----------------------------------------------------------


def test_zed_context_servers_shape_is_scanned() -> None:
    cfg = {"context_servers": {"s": {"command": "npx", "args": ["-y", "p"]}}}
    assert mod.find_violations(cfg, ".zed/settings.json")


def test_vscode_servers_shape_is_scanned() -> None:
    cfg = {"servers": {"s": {"command": "npx", "args": ["-y", "p"]}}}
    assert mod.find_violations(cfg, ".vscode/mcp.json")


def test_codex_toml_table_shape_is_scanned() -> None:
    """Shape as tomllib would parse `[mcp_servers.s] command="npx"`."""
    cfg = {"mcp_servers": {"s": {"command": "npx", "args": ["-y", "p"]}}}
    assert mod.find_violations(cfg, ".codex/config.toml")


# --- the live repo configs must stay clean (regression) ----------------------


def test_repo_configs_pass_the_gate() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
