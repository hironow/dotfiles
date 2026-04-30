"""Unit tests for _resolve_targets in sync_agents.

Tests the CLI argument resolution that turns user-supplied identifiers
(e.g. "p", "a", "claude", "work-a", "all") into canonical AgentTarget keys.
"""

from pathlib import Path

# Import from scripts (add parent to path)
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (  # noqa: E402
    AGENTS,
    _resolve_targets,
)


def test_empty_args_defaults_to_claude_only() -> None:
    """Empty args means default = only the personal claude (.claude)."""
    # given
    args: list[str] = []

    # when
    keys = _resolve_targets(args)

    # then
    assert keys == ["claude"]


def test_single_short_alias_resolves() -> None:
    """Short aliases match the existing convention used by `just skills`."""
    # given / when / then
    assert _resolve_targets(["p"]) == ["claude"]
    assert _resolve_targets(["a"]) == ["work-a"]
    assert _resolve_targets(["b"]) == ["work-b"]
    assert _resolve_targets(["c"]) == ["work-c"]
    assert _resolve_targets(["d"]) == ["work-d"]
    assert _resolve_targets(["g"]) == ["gemini"]
    assert _resolve_targets(["x"]) == ["codex"]


def test_full_name_aliases_resolve() -> None:
    """Full names also work for clarity in scripts."""
    # given / when / then
    assert _resolve_targets(["claude"]) == ["claude"]
    assert _resolve_targets(["work-a"]) == ["work-a"]
    assert _resolve_targets(["gemini"]) == ["gemini"]
    assert _resolve_targets(["codex"]) == ["codex"]


def test_multiple_args_preserves_order_and_dedupes() -> None:
    """Multiple identifiers are accepted; duplicates removed."""
    # given
    args = ["p", "a", "claude", "b"]

    # when
    keys = _resolve_targets(args)

    # then
    assert keys == ["claude", "work-a", "work-b"]


def test_all_token_expands_to_every_agent() -> None:
    """Special token `all` expands to every defined agent."""
    # given
    args = ["all"]

    # when
    keys = _resolve_targets(args)

    # then
    expected = [a.key for a in AGENTS]
    assert keys == expected


def test_unknown_alias_raises() -> None:
    """Unknown identifier is a hard error (no silent fallback)."""
    # given / when / then
    with pytest.raises(ValueError, match="unknown target"):
        _resolve_targets(["nope"])


def test_comma_separated_string_is_split() -> None:
    """Convenience: a single comma-separated argument splits into items."""
    # given
    args = ["p,a,b"]

    # when
    keys = _resolve_targets(args)

    # then
    assert keys == ["claude", "work-a", "work-b"]
