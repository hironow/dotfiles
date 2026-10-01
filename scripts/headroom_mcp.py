#!/usr/bin/env python3
"""Register headroom's MCP server in every Claude home, with its egress pinned.

headroom reaches Claude Code two ways. The proxy (scripts/jev_headroom.py, j-cc
only) compresses everything a session sends; this is the other one, and it is
the one every home gets: an MCP server offering headroom_compress,
headroom_retrieve and headroom_stats as tools the agent calls on demand. If the
server is down the tools simply vanish, so the blast radius of a broken headroom
is a missing tool rather than a dead session.

Through Claude Code's own `claude mcp add --scope user`, with CLAUDE_CONFIG_DIR
per home -- never by editing <home>/.claude.json here. That file holds all of a
home's live state (projects, history, the MCP registry), several homes run
sessions at once, and a hand-written rewrite would race their own writes. The
CLI is that file's write path.

The registration carries HEADROOM_BEACON=off and DO_NOT_TRACK=1 in its own `env`
block: Claude Code starts this server itself, so neither mise's `[env]` (no
shell is involved) nor a settings fragment reliably reaches it. The literals and
why there are two of them live in tests/unit/test_agent_tool_telemetry.py.

The command is `mise x -- headroom mcp serve`, not an absolute path: a pinned
path breaks on the next version bump, and a bare `headroom` depends on the PATH
of whatever started Claude Code -- a snapshot that may predate the install.

Reading and writing are split on purpose. The registry is READ out of
<home>/.claude.json, because `claude mcp list` has no machine-readable form
(there is no --json on 2.1.285) and parsing its prose would break on the next
release; every WRITE goes through the CLI. Reading a file cannot race anything.

Functional core / imperative shell: plan() turns a registry into the steps
needed, and reconcile() runs them through an injected CLI and reads the registry
again before judging. A registry that cannot be read stops that home and is
never taken for "missing".

Usage: headroom_mcp.py [--check] [--home DIR ...]
  --check  report without changing anything
  --home   use these directories as the homes (tests; repeatable)
Prints doctor-style OK/WARN lines; exit 1 on a WARN.
"""

from collections.abc import Callable, Mapping, Sequence
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SERVER = "headroom"
CLAUDE_HOMES = (
    ".claude",
    ".claude-work-a",
    ".claude-work-b",
    ".claude-work-c",
    ".claude-work-d",
)
COMMAND = "mise"
ARGS = ("x", "--", "headroom", "mcp", "serve")
# Both switches, because the beacon fails open and DO_NOT_TRACK overrides it
EGRESS = {"HEADROOM_BEACON": "off", "DO_NOT_TRACK": "1"}

CALL_TIMEOUT = 180.0  # one claude call
# --check as a whole: below doctor's wait for a checker, so a hanging home costs
# its own lines and never the report of the others
CHECK_BUDGET = 240.0

Cli = Callable[[list[str]], bool]  # claude argv -> did it succeed
Read = Callable[[], Mapping[str, object] | None]  # the registry, None if unreadable


def _registration() -> dict[str, object]:
    return {
        "type": "stdio",
        "command": COMMAND,
        "args": list(ARGS),
        "env": dict(EGRESS),
    }


# ---- Functional core ----


def declared(inventory: Mapping[str, object]) -> dict[str, object] | None:
    """The server's entry in a `.claude.json`-shaped mapping, if it has one."""
    servers = inventory.get("mcpServers")
    if not isinstance(servers, dict):
        return None
    entry = servers.get(SERVER)
    return entry if isinstance(entry, dict) else None


def wrong(entry: Mapping[str, object] | None) -> str | None:
    """What is wrong with `entry`, or None when it is exactly what we want."""
    if entry is None:
        return f"no {SERVER} MCP server"
    raw_args = entry.get("args")
    args = [str(arg) for arg in raw_args] if isinstance(raw_args, list) else []
    if entry.get("command") != COMMAND or args != list(ARGS):
        return f"{SERVER} runs {entry.get('command')} {' '.join(args)}"
    raw_env = entry.get("env")
    env = raw_env if isinstance(raw_env, dict) else {}
    missing = {k: v for k, v in EGRESS.items() if env.get(k) != v}
    if missing:
        spelled = ", ".join(f"{k}={v}" for k, v in sorted(missing.items()))
        return f"{SERVER}'s env lacks {spelled}"
    return None


def plan(entry: Mapping[str, object] | None) -> list[list[str]]:
    """The claude calls that make `entry` right. Empty when it already is.

    A wrong entry is removed first: `mcp add` on a name that exists is an error,
    and silently leaving the old one would keep an unpinned egress.
    """
    if wrong(entry) is None:
        return []
    add = ["mcp", "add", SERVER, "--scope", "user"]
    for name, value in sorted(EGRESS.items()):
        add += ["--env", f"{name}={value}"]
    add += ["--", COMMAND, *ARGS]
    remove = ["mcp", "remove", SERVER, "--scope", "user"]
    return [remove, add] if entry is not None else [add]


def reconcile(read: Read, cli: Cli, *, check: bool) -> tuple[str | None, str | None]:
    """(what was fixed, what is still wrong) for one home."""
    registry = read()
    if registry is None:
        return (None, "could not read the MCP registry")
    problem = wrong(declared(registry))
    if problem is None:
        return (None, None)
    if check:
        return (None, problem)
    for step in plan(declared(registry)):
        if not cli(step) and step[1] == "add":
            return (None, f"{problem} (claude {' '.join(step)} failed)")
    after = read()
    if after is None:
        return (None, f"{problem} (the registry could not be read back)")
    still = wrong(declared(after))
    if still is not None:
        return (None, f"{problem} (still {still} after the fix)")
    return (problem, None)


# ---- Imperative shell ----


def _cli(claude: str, home: Path, deadline: float | None) -> Cli:
    def run(args: list[str]) -> bool:
        timeout = CALL_TIMEOUT
        if deadline is not None:
            timeout = min(timeout, max(0.0, deadline - time.monotonic()))
            if timeout <= 0:
                return False
        try:
            done = subprocess.run(  # noqa: S603 - resolved argv, no shell
                [claude, *args],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
                env={**os.environ, "CLAUDE_CONFIG_DIR": str(home)},
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0

    return run


def _read(home: Path) -> Read:
    """The home's registry, read straight from the file Claude Code owns.

    A missing file is an EMPTY registry, not an unreadable one: a home Claude
    Code has never started in simply has no server yet. Only a file that exists
    and will not parse counts as unreadable, and that must never be taken for
    "missing" -- doing so would delete and re-add the server on every run.
    """

    def read() -> Mapping[str, object] | None:
        path = home / ".claude.json"
        if not path.is_file():
            return {}
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    return read


def _homes(argv: Sequence[str]) -> list[Path]:
    given = [Path(value) for flag, value in zip(argv, argv[1:]) if flag == "--home"]
    if given:
        return given
    return [
        Path.home() / name for name in CLAUDE_HOMES if (Path.home() / name).is_dir()
    ]


def main(argv: Sequence[str]) -> int:
    check = "--check" in argv
    claude = shutil.which("claude")
    if not claude:
        print("WARN headroom-mcp - claude not on PATH: mise install")
        return 1
    homes = _homes(argv)
    failed = False
    deadline = time.monotonic() + CHECK_BUDGET if check else None
    for home in homes:
        fixed, problem = reconcile(
            _read(home), _cli(claude, home, deadline), check=check
        )
        if fixed:
            print(f"OK   headroom-mcp - ~/{home.name}: fixed: {fixed}")
        if problem:
            failed = True
            fix = "just headroom-mcp-register" if check else "see the line above"
            print(f"WARN headroom-mcp - ~/{home.name}: {problem}: {fix}")
    if not failed:
        print(
            f"OK   headroom-mcp - {SERVER} registered, egress pinned, "
            f"in {len(homes)} Claude home(s)"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
