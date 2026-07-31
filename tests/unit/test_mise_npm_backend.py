"""mise's npm backend must install with bun, not the embedded aube.

Why this exists
---------------
`npm.package_manager` defaults to `auto`, which uses mise's embedded `aube`.
For claude-code that silently produces a broken install:

- claude-code ships a 263 MB native binary that its `postinstall` (install.cjs)
  puts in place. Under aube's virtual-store layout the installed
  `bin/claude.exe` stays a **500-byte stub**, and the `.bin/claude` shim then
  runs `node claude.exe`, which dies with `ERR_UNKNOWN_FILE_EXTENSION`.
- Nothing reports this. The tool "installs" fine and only fails when invoked,
  so the box keeps working purely because a stray npm-global copy shadows the
  mise one on PATH — and `just prune-rogue-npm-globals`, which exists to
  remove exactly that copy, is then the thing that breaks `claude`.

Measured on this host, same version (2.1.218) both ways:

| backend | bin/claude.exe | invocation                        |
| ------- | -------------- | --------------------------------- |
| aube    | 500 B          | ERR_UNKNOWN_FILE_EXTENSION        |
| bun     | 263,931,552 B  | `2.1.218 (Claude Code)`           |

bun is also the package manager this repo standardises on (ADR 0027), so this
costs no new exception.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "mise" / "config.toml"


def _settings() -> dict:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8")).get("settings", {})


def test_npm_backend_installs_with_bun() -> None:
    """`auto` (embedded aube) cannot unpack claude-code's native binary."""
    chosen = _settings().get("npm", {}).get("package_manager")
    assert chosen == "bun", (
        "config/mise/config.toml must set [settings.npm] package_manager = "
        f'"bun"; found {chosen!r}. Under the default "auto" (aube), '
        "claude-code installs as a 500-byte stub that cannot run."
    )


def test_npm_backend_is_not_a_banned_package_manager() -> None:
    """The setting accepts npm/pnpm too; both are barred here (ADR 0027)."""
    chosen = _settings().get("npm", {}).get("package_manager")
    assert chosen not in {"npm", "pnpm", "yarn"}, (
        f"{chosen!r} would have mise shell out to a package manager this repo "
        "forbids; bun is the only sanctioned Node package manager."
    )
