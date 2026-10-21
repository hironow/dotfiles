"""The initial setup must put the browser CLI the playwright-cli skill runs on PATH.

Why this exists
---------------
hironow/skills ships a `playwright-cli` skill (deployed to `~/.agents/skills`
and symlinked into the Claude/Codex homes) whose first line reads: if
`playwright-cli` is not on PATH, run
`bunx --package @playwright/mcp playwright-cli <args>`.

That fallback cannot work. `@playwright/mcp`'s only bin is `playwright-mcp` --
true for the last 14 published versions (npm registry, checked 2026-10-21) --
and the package that does ship a `playwright-cli` bin is `@playwright/cli`. So
unless a machine's initial setup puts `playwright-cli` on PATH, the skill has
nothing to run at all.

`config/mise/config.toml` is that setup's single source of truth: `install.sh`
and `just install` materialise its `[tools]` on a Mac, Linux or WSL host (a
repo-local `config/mise/config.toml` is not read as a project config, so this
file is the only declaration that reaches PATH). These tests keep the
declaration from being dropped, or replaced by `playwright` -- the test runner,
a different package that ships no `playwright-cli` bin.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "mise" / "config.toml"

TOOL = "npm:@playwright/cli"
# `latest` (the policy this file's agent-facing CLIs follow) or an exact pin.
# An empty value, a range, and the `next` alpha channel are all rejected: the
# setup has to be the same on every machine (ADR 0006).
_VERSION = re.compile(r"latest|\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?")


def _tools() -> dict[str, object]:
    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))["tools"]


def _declared_version(spec: object) -> object:
    """The version spec of a mise tool entry (a string or a `version` table)."""
    if isinstance(spec, dict):
        return spec.get("version")
    return spec


def test_the_initial_setup_declares_playwright_cli() -> None:
    """Only this file puts `playwright-cli` on PATH for the skill to find."""
    assert TOOL in _tools(), (
        f"config/mise/config.toml must declare {TOOL!r}. The hironow/skills "
        "`playwright-cli` skill runs `playwright-cli`, and its documented "
        "`bunx --package @playwright/mcp playwright-cli` fallback has no such "
        "bin (that package ships only `playwright-mcp`)."
    )


def test_the_declared_tool_is_not_the_playwright_test_runner() -> None:
    """`playwright` is the test runner: another package, another bin."""
    declared = {key.split(":", 1)[-1] for key in _tools()}
    assert "playwright" not in declared, (
        "config/mise/config.toml declares `playwright` (the test runner). It "
        "ships no `playwright-cli` bin, so the skill would still not run."
    )


def test_the_declared_version_spec_is_usable() -> None:
    """`latest` or an exact pin; empty, ranged and `next` specs are not."""
    version = _declared_version(_tools()[TOOL])
    assert isinstance(version, str) and _VERSION.fullmatch(version), (
        f"{TOOL} must be `latest` or an exact version; found {version!r}. "
        "Ranges and the `next` alpha channel would make what the initial "
        "setup installs drift between machines."
    )
