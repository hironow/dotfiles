#!/usr/bin/env python3
"""Register the MCP servers dotfiles declares with every agent (ADR 0087).

dump/harness/mcp-servers.json names remote MCP servers that need no secret.
`just deploy` registers each one with Claude Code (in every home), Codex, Pi and
Antigravity. A server a user added by hand is never touched, and nothing is
removed for being undeclared.

A server that needs a secret (google-dev-knowledge needs an API key) is never
registered: the declaration lists it under "guided", and a run prints its setup
steps for each agent that lacks it. The key never passes through dotfiles.

Every write goes through the agent's own `mcp add` / `mcp remove`, never a
hand edit: the CLI owns its file and a running session writes it too. Reading
is from the file itself, because only some of the CLIs can list as JSON:

  claude       <home>/.claude.json            mcpServers.<name>.url
               (a plain `claude`, no CLAUDE_CONFIG_DIR: ~/.claude.json)
  codex        $CODEX_HOME/config.toml        [mcp_servers.<name>] url
  pi           $PI_CODING_AGENT_DIR/mcp.json  mcpServers.<name>.url
  antigravity  ~/.gemini/config/mcp_config.json  mcpServers.<name>.serverUrl

Functional core / imperative shell, as in headroom_mcp.py: plan() turns a
registry into CLI calls, and reconcile() runs them through an injected CLI and
reads the registry again before judging. A registry that cannot be read stops
that agent; it is never taken for empty. An agent whose CLI is not on PATH is
skipped with an INFO line.

Usage: agent_mcp.py [--check]
  --check  report without changing anything
Prints doctor-style lines; exit 1 on a WARN.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
import tomllib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import claude_homes
from codex_agy_plugins import ANTIGRAVITY_NAMES
from doctor_lines import Line, failed, fmt

NAME = "agent-mcp"
RECIPE = "just agent-mcp-install"
DECLARATION = Path(__file__).resolve().parents[1] / "dump/harness/mcp-servers.json"
EXECUTABLES: dict[str, tuple[str, ...]] = {
    "claude": ("claude",),
    "codex": ("codex",),
    "pi": ("pi",),
    "antigravity": ANTIGRAVITY_NAMES,
}
AGENTS = tuple(EXECUTABLES)

Registry = dict[str, str | None]  # server name -> its URL; None for a stdio server
Read = Callable[[], Registry | None]  # None when the registry cannot be read
Cli = Callable[[list[str]], bool]  # argv after the executable -> did it succeed
Which = Callable[[str], str | None]


@dataclass(frozen=True)
class Guided:
    """A server that needs a secret: set up by hand, never by a run."""

    url: str
    header: str
    env: str
    setup: str
    steps: tuple[str, ...] = ()  # run once, before any agent's `mcp add`

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))  # JSON gives a list


@dataclass(frozen=True)
class Server:
    """A server a run registers.

    claude_plugin: the Claude Code plugin that already registers it under the
    same name, so Claude is left to the plugin.
    sign_in: it needs a browser sign-in. `codex mcp add` starts that sign-in at
    once and waits for it, so Codex is shown the command instead.
    """

    url: str
    claude_plugin: str | None = None
    sign_in: bool = False


@dataclass(frozen=True)
class Declared:
    servers: dict[str, Server]
    guided: dict[str, Guided]  # name -> how to set it up by hand


def load(path: Path) -> Declared:
    raw = json.loads(path.read_text(encoding="utf-8"))
    servers = {name: Server(**entry) for name, entry in raw["servers"].items()}
    guided = {name: Guided(**entry) for name, entry in raw.get("guided", {}).items()}
    return Declared(servers, guided)


def wanted(declared: Declared, agent: str) -> dict[str, str]:
    """{name: url} of the servers a run registers with `agent`."""
    return {
        name: server.url
        for name, server in declared.servers.items()
        if not (agent == "claude" and server.claude_plugin)
        and not (agent == "codex" and server.sign_in)
    }


def sign_in_note(agent: str, name: str) -> str | None:
    """What to do after a run adds a server that needs a sign-in."""
    if agent == "pi":
        return f"sign in once: pi mcp login {name}"
    if agent == "antigravity":
        return f"sign in to {name} once, when Antigravity asks"
    return None


# ---- Reading each agent's registry ----


def _servers(table: object, key: str) -> Registry | None:
    """{name: url} out of a mapping of server tables; None when it is not one."""
    if not isinstance(table, dict):
        return None
    registry: Registry = {}
    for name, entry in table.items():
        url = entry.get(key) if isinstance(entry, dict) else None
        registry[name] = url if isinstance(url, str) else None
    return registry


def _json_servers(path: Path, key: str) -> Registry | None:
    """A JSON registry. A missing file is empty: the agent never stored one."""
    if not path.is_file():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return _servers(parsed.get("mcpServers", {}), key)


def read_claude(home: Path) -> Registry | None:
    return _json_servers(home / ".claude.json", "url")


def read_codex(codex_home: Path) -> Registry | None:
    path = codex_home / "config.toml"
    if not path.is_file():
        return {}
    try:
        parsed = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return _servers(parsed.get("mcp_servers", {}), "url")


def read_pi(agent_dir: Path) -> Registry | None:
    return _json_servers(agent_dir / "mcp.json", "url")


def read_antigravity(config_dir: Path) -> Registry | None:
    return _json_servers(config_dir / "mcp_config.json", "serverUrl")


# ---- Functional core ----


def add_args(agent: str, name: str, url: str) -> list[str]:
    if agent == "claude":
        return ["mcp", "add", "--scope", "user", "--transport", "http", name, url]
    if agent == "antigravity":
        return ["mcp", "add", name, url]  # it detects an http URL itself
    return ["mcp", "add", name, "--url", url]


def remove_args(agent: str, name: str) -> list[str]:
    if agent == "claude":
        return ["mcp", "remove", name, "--scope", "user"]
    return ["mcp", "remove", name]


def drift(declared: Mapping[str, str], registry: Registry) -> tuple[list, list]:
    """(declared names the registry lacks, names it holds at another URL)."""
    missing = sorted(name for name in declared if name not in registry)
    moved = sorted(
        name
        for name, url in declared.items()
        if name in registry and registry[name] != url
    )
    return missing, moved


def describe(missing: Sequence[str], moved: Sequence[str]) -> str:
    parts = []
    if missing:
        parts.append(f"missing {', '.join(missing)}")
    if moved:
        parts.append(f"{', '.join(moved)} at another URL")
    return "; ".join(parts)


def plan(agent: str, declared: Mapping[str, str], registry: Registry) -> list[list]:
    """The CLI calls that register every declared server. A server at another
    URL is removed first: Claude Code's `mcp add` fails on a name it holds."""
    missing, moved = drift(declared, registry)
    steps: list[list] = []
    for name in sorted({*missing, *moved}):
        if name in moved:
            steps.append(remove_args(agent, name))
        steps.append(add_args(agent, name, declared[name]))
    return steps


def reconcile(
    read: Read, cli: Cli, agent: str, declared: Mapping[str, str], *, check: bool
) -> tuple[list[str], str | None]:
    """(what was fixed, what is still wrong) for one agent's registry."""
    registry = read()
    if registry is None:
        return ([], "could not read the MCP registry")
    missing, moved = drift(declared, registry)
    if not missing and not moved:
        return ([], None)
    if check:
        return ([], describe(missing, moved))
    failures = [
        f"{agent} {' '.join(step)}"
        for step in plan(agent, declared, registry)
        if not cli(step)
    ]
    after = read()
    if after is None:
        return ([], f"{describe(missing, moved)} (could not read it back)")
    still_missing, still_moved = drift(declared, after)
    fixed = [f"added {name}" for name in missing if name not in still_missing] + [
        f"replaced {name}" for name in moved if name not in still_moved
    ]
    if not still_missing and not still_moved:
        return (fixed, None)
    problem = describe(still_missing, still_moved)
    if failures:
        problem += f" ({'; '.join(failures)} failed)"
    return (fixed, problem)


def _how(kind: str, label: str, name: str, server: Guided) -> str:
    key = f"{server.header}: <key>"
    if kind == "claude":
        home = label.partition(" ")[2]
        prefix = "" if home in ("", "~") else f"CLAUDE_CONFIG_DIR={home} "
        return (
            f'{prefix}claude mcp add --scope user --transport http --header "{key}" '
            f"{name} {server.url}"
        )
    if kind == "codex":
        return (
            f"codex mcp add {name} --url {server.url}, then under "
            f"[mcp_servers.{name}] in config.toml set "
            f'env_http_headers = {{ "{server.header}" = "{server.env}" }} '
            f"and export {server.env}"
        )
    if kind == "pi":
        return f"pi mcp add {name} --url {server.url} --header {server.header}=<key>"
    return f'antigravity mcp add --header "{key}" {name} {server.url}'


def guidance(
    declared: Declared, registries: Mapping[str, Mapping[str, str | None]]
) -> list[Line]:
    """INFO lines on what a run leaves to a person, for each registry (keyed
    `<agent>` or `claude ~/<home>`) that lacks it: a guided server anywhere,
    and in Codex a server that needs a sign-in. Empty once all have them."""
    lines: list[Line] = [
        (
            "INFO",
            NAME,
            (
                f"{name} for codex: codex mcp add {name} --url {server.url} "
                "(it signs in through the browser)"
            ),
        )
        for name, server in sorted(declared.servers.items())
        if server.sign_in and "codex" in registries and name not in registries["codex"]
    ]
    for name, server in sorted(declared.guided.items()):
        lacking = [label for label, reg in registries.items() if name not in reg]
        if not lacking:
            continue
        lines.append(
            (
                "INFO",
                NAME,
                (
                    f"{name} needs an API key, so it is set up by hand ({server.setup}), "
                    "in a personal project, never one tofu manages, once:"
                ),
            )
        )
        lines += [("INFO", NAME, f"{name} setup: {step}") for step in server.steps]
        lines += [
            (
                "INFO",
                NAME,
                f"{name} for {label}: {_how(label.split()[0], label, name, server)}",
            )
            for label in lacking
        ]
    return lines


# ---- Imperative shell ----


@dataclass(frozen=True)
class Target:
    label: str  # how lines name it: "codex", or "claude ~/.claude-work-a"
    kind: str  # one of AGENTS
    read: Read
    cli: Cli


def _succeeds(run: claude_homes.Run) -> Cli:
    # success is the exit status: an empty stdout still counts
    return lambda args: run(args) is not None


def without_config_dir(env: Mapping[str, str]) -> dict[str, str]:
    """The environment a plain `claude` runs in: no CLAUDE_CONFIG_DIR, so it
    reads and writes ~/.claude.json, whatever home started this run."""
    return {k: v for k, v in env.items() if k != "CLAUDE_CONFIG_DIR"}


def _executable(kind: str, which: Which) -> str | None:
    return next((path for name in EXECUTABLES[kind] if (path := which(name))), None)


def _targets(
    home: Path,
    env: Mapping[str, str],
    which: Which,
    deadline: float | None,
    skipped: list[Line],
) -> Iterator[Target]:
    claude = _executable("claude", which)
    if claude is None:
        skipped.append(("INFO", NAME, "claude not on PATH; skipped"))
    else:
        # A plain `claude` keeps its registry in ~/.claude.json, apart from
        # every home's; visited only once that file exists
        if (home / ".claude.json").is_file():
            run = claude_homes.cli_runner(
                claude, home, without_config_dir(env), deadline
            )
            yield Target(
                "claude ~", "claude", lambda: read_claude(home), _succeeds(run)
            )
        for claude_home in claude_homes.existing(home):
            run = claude_homes.runner(claude, claude_home, deadline)
            yield Target(
                f"claude ~/{claude_home.name}",
                "claude",
                lambda h=claude_home: read_claude(h),
                _succeeds(run),
            )
    dirs = {
        "codex": (Path(env.get("CODEX_HOME", home / ".codex")), read_codex),
        "pi": (
            Path(env.get("PI_CODING_AGENT_DIR", home / ".pi/agent")),
            read_pi,
        ),
        "antigravity": (home / ".gemini/config", read_antigravity),
    }
    for kind, (directory, reader) in dirs.items():
        path = _executable(kind, which)
        if path is None:
            names = " / ".join(EXECUTABLES[kind])
            skipped.append(("INFO", NAME, f"{names} not on PATH; skipped"))
            continue
        yield Target(
            kind,
            kind,
            lambda d=directory, r=reader: r(d),
            _succeeds(claude_homes.cli_runner(path, home, env, deadline)),
        )


def main(argv: Sequence[str]) -> int:
    check = "--check" in argv
    declared = load(DECLARATION)
    deadline = time.monotonic() + claude_homes.CHECK_BUDGET if check else None
    fix = RECIPE if check else "see the line above"
    skipped: list[Line] = []
    lines: list[Line] = []
    registries: dict[str, Registry] = {}
    visited = 0
    for target in _targets(Path.home(), os.environ, shutil.which, deadline, skipped):
        visited += 1
        fixed, problem = reconcile(
            target.read,
            target.cli,
            target.kind,
            wanted(declared, target.kind),
            check=check,
        )
        found: list[Line] = []
        for item in fixed:
            found.append(("OK", NAME, f"{target.label}: fixed: {item}"))
            name = item.rpartition(" ")[2]
            note = sign_in_note(target.kind, name)
            if declared.servers[name].sign_in and note:
                found.append(("INFO", NAME, f"{target.label}: {name}: {note}"))
        if problem:
            found.append(("WARN", NAME, f"{target.label}: {problem}: {fix}"))
        for line in found:
            print(fmt(line))
        lines += found
        registry = target.read()
        if registry is not None:
            registries[target.label] = registry
    for line in [*skipped, *guidance(declared, registries)]:
        print(fmt(line))
    if failed(lines):
        return 1
    count = len(declared.servers)
    print(fmt(("OK", NAME, f"{count} MCP server(s) registered in {visited} place(s)")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
