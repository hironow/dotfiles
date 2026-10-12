"""The justfile runs Node tooling through bun only (AGENTS.md: "Use only bun for Node").

The command guard stops agents from typing npm / npx / pnpm / yarn, but a recipe
that does it itself, or tells the operator to, slips through. This guard bans
invocations only: a command in command position, or a hint that names one.
Plain mentions (a comment, "npm ETARGET" in a diagnostic, a recipe name such as
`prune-rogue-npm-globals`) stay allowed.

Host-side (tests/unit/, `just ci`).
"""

from __future__ import annotations

import re
from pathlib import Path

JUSTFILE = Path(__file__).resolve().parents[2] / "justfile"

_TOOL = r"(?:npm|npx|pnpm|yarn)"
# The tool as a command: at line start, after a separator or a backtick, or
# after a command-introducing word (`command -v`, `xargs -0 -r`, `then`,
# `mise x --`, `sudo`, `env A=1`, `time`).
_IN_COMMAND_POSITION = re.compile(
    rf"(?:^|[;&|({{`]\s*"
    rf"|\b(?:then|do|exec|command -v|x|sudo|env|time|nice)\s+(?:--\s+)?(?:\w+=\S+\s+)*"
    rf"|\bxargs\s+(?:-\S+\s+)*){_TOOL}(?![\w-])"
)
# A hint that tells the operator to run one, e.g. "npm i -g x" / "pnpm dlx x".
_RUN_HINT = re.compile(
    r"\b(?:npm|pnpm|yarn)\s+(?:i|install|add|dlx|run|ls|exec)\b|\bnpx\s"
)


def _invocations() -> list[str]:
    found = []
    for number, raw in enumerate(JUSTFILE.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        command = line.lstrip("@-").strip()
        if _IN_COMMAND_POSITION.search(command) or _RUN_HINT.search(command):
            found.append(f"justfile:{number}: {line[:110]}")
    return found


def test_justfile_runs_node_tooling_through_bun_only() -> None:
    assert _invocations() == []


def test_guard_sees_an_invocation_and_ignores_a_mention() -> None:
    assert _IN_COMMAND_POSITION.search("npm ls --global")
    assert _IN_COMMAND_POSITION.search("command -v npx >/dev/null 2>&1 || exit 127")
    assert _RUN_HINT.search("echo 'Hint: npm i -g @devcontainers/cli'")
    for missed in (
        "mise x -- npm root -g",
        "git ls-files | xargs -0 -r npm view x",
        "sudo npm install x",
        "env A=1 npm root",
        "time npm root",
        "dir=`npm root -g`",
    ):
        assert _IN_COMMAND_POSITION.search(missed), missed
    assert not _IN_COMMAND_POSITION.search("check-npm-g:")
    assert not _RUN_HINT.search("echo 'on npm ETARGET run just harden-env'")
