#!/usr/bin/env python3
"""Enforce the bun-only Node policy (ADR 0027) for MCP client configs.

MCP servers are launched by the agent host process directly, NOT through the
Bash tool -- so neither the PreToolUse block-prohibited-commands guard nor the
`Bash(npx:*)` permission deny ever sees them. A `command: "npx"` (or npm/pnpm/
yarn) therefore slips into a committed MCP config unchecked. This static gate is
the wall for that path: it parses the repo's active MCP client configs and fails
if any server launches Node tooling via a banned runner.

Scope is the explicit list of MCP client configs this repo deploys (mirrors the
hardcoded-targets style of check_uv_flatt_index.sh). It deliberately does NOT
auto-discover every tracked json/toml: example MCP snippets under vendored
submodules or docs are not launched and must not fail the gate, and an unrelated
malformed config must not break this policy check. Add a new client config here
when a new family appears.

Resolution covers the cheap real wrappers (env/sudo prefixes, corepack <pm>,
`mise exec -- <runner>`, `bash -c "<script>"`); arbitrary shell interpretation
beyond `-c` is out of scope. `bun`/`bunx`/`node`/`uv`/`uvx`/`deno` and direct
binaries are allowed.

Exit code: 0 = clean, 1 = violations found (listed on stderr). Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path

EXIT_OK = 0
EXIT_FAIL = 1

# Banned Node runners (package managers / their dlx runners). `node` itself is
# allowed: running a local server script directly does not violate bun-only.
BANNED_RUNNERS = {"npm", "npx", "pnpm", "pnpx", "yarn", "yarnpkg"}
COREPACK_PMS = {"npm", "pnpm", "yarn"}
WRAPPERS = {"env", "sudo", "time", "nohup", "command"}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}

# Server-map keys across MCP client schemas: Claude/Gemini/mcporter (mcpServers),
# Zed (context_servers), VS Code (servers), Codex TOML table (mcp_servers).
SERVER_MAP_KEYS = ("mcpServers", "context_servers", "servers", "mcp_servers")

# Active MCP client configs this repo deploys. Tracked files only; vendored
# submodule internals and gitignored locals (e.g. .vscode/mcp.json) are out of
# the distributed source and intentionally excluded.
CONFIG_FILES = (
    ".mcp.json",
    ".gemini/settings.json",
    ".zed/settings.json",
    "config/mcporter.json",
    ".codex/config.toml",
)

_ASSIGNMENT_RE = re.compile(r"^[A-Za-z_]\w*=")
_RUNNER_TOKEN_RE = re.compile(
    r"(?:^|[\s;&|()])(" + "|".join(sorted(BANNED_RUNNERS)) + r")(?:[\s;&|()]|$)"
)


def _basename(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def banned_runner(command: object, args: object) -> str | None:
    """Return the offending Node runner basename for a server spec, else None.

    Recurses one level through wrapper prefixes; resolves corepack/mise/shell
    forms. Anything it cannot positively classify as a banned runner is allowed.
    """
    if not isinstance(command, str) or not command:
        return None
    argv = [a for a in args if isinstance(a, str)] if isinstance(args, list) else []
    base = _basename(command)

    if base in BANNED_RUNNERS:
        return base

    if base == "corepack":
        for arg in argv:
            if arg.startswith("-"):
                continue
            pm = arg.split("@", 1)[0]  # `pnpm@9` -> `pnpm`
            return pm if pm in COREPACK_PMS else None
        return None

    if base in WRAPPERS:
        rest = list(argv)
        while rest and (rest[0].startswith("-") or _ASSIGNMENT_RE.match(rest[0])):
            rest.pop(0)
        return banned_runner(rest[0], rest[1:]) if rest else None

    if base == "mise":
        if ("exec" in argv or "x" in argv) and "--" in argv:
            tail = argv[argv.index("--") + 1 :]
            return banned_runner(tail[0], tail[1:]) if tail else None
        return None

    if base in SHELLS and "-c" in argv:
        idx = argv.index("-c")
        if idx + 1 < len(argv):
            match = _RUNNER_TOKEN_RE.search(argv[idx + 1])
            if match:
                return match.group(1)
        return None

    return None


def find_violations(config: object, source: str) -> list[str]:
    """Collect bun-only violations for one parsed config object."""
    violations: list[str] = []
    if not isinstance(config, dict):
        return violations
    for key in SERVER_MAP_KEYS:
        block = config.get(key)
        if not isinstance(block, dict):
            continue
        for name, spec in block.items():
            if not isinstance(spec, dict):
                continue
            runner = banned_runner(spec.get("command"), spec.get("args"))
            if runner is not None:
                violations.append(
                    f"{source}: MCP server '{name}' launches Node via "
                    f"'{runner}'. Node tooling is bun-only (ADR 0027) -- use "
                    f"'bunx' (npx->bunx) or run the server binary directly."
                )
    return violations


def _load(path: Path) -> object:
    text = path.read_text()
    if path.suffix == ".toml":
        return tomllib.loads(text)
    return json.loads(text)


def check_files(root: Path, files: tuple[str, ...]) -> list[str]:
    """Lint each existing config; skip missing or unparsable files."""
    violations: list[str] = []
    for rel in files:
        path = root / rel
        if not path.exists():
            continue
        try:
            config = _load(path)
        except (
            json.JSONDecodeError,
            tomllib.TOMLDecodeError,
            UnicodeDecodeError,
            OSError,
        ):
            # Syntax validity is another tool's job; never break this policy gate.
            continue
        violations.extend(find_violations(config, rel))
    return violations


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    violations = check_files(root, CONFIG_FILES)
    if violations:
        print(
            "check-mcp-node-runner: FAILED -- MCP configs must not launch Node "
            "tooling via npm/npx/pnpm/yarn (bun-only, ADR 0027):",
            file=sys.stderr,
        )
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return EXIT_FAIL
    print(
        f"check-mcp-node-runner: OK -- {len(CONFIG_FILES)} MCP client configs "
        "launch no banned Node runner."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
