"""Unit tests for _merge_settings_fragment in sync_agents.

The shared settings fragment (`.claude/settings.shared.json`) carries the
cross-machine `env` block plus a curated set of top-level settings keys, and is
merged into each claude-family agent's `settings.json` the same update-in-place
way as the hook fragment. Ownership model (stronger than the hook merge):

- `env`: sync OWNS the whole block — target env is replaced wholesale, so keys
  the fragment drops are removed. Machine-local env must live in
  `settings.local.json` (which sync never touches).
- `settings`: curated top-level keys are upserted (add/update only); all other
  target keys (theme, language, enabledPlugins, hooks, statusLine, ...) are
  preserved untouched. Top-level key removal is NOT auto-propagated (v1).

The function is idempotent and dry-run aware, mirroring `_merge_hook_settings`.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (  # noqa: E402
    AgentTarget,
    _merge_hook_settings,
    _merge_settings_fragment,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> dict[str, Path]:
    """Create dotfiles and target (agent home) directory structure."""
    dotfiles_dir = tmp_path / "dotfiles"
    target_dir = tmp_path / "target"
    dotfiles_dir.mkdir()
    target_dir.mkdir()
    return {"dotfiles": dotfiles_dir, "target": target_dir}


def _make_agent(target_dir: Path) -> AgentTarget:
    """Create an AgentTarget pointing to target_dir."""
    return AgentTarget(directory=target_dir, name="Test")


def _write_shared_fragment(dotfiles_dir: Path, data: dict) -> Path:
    """Write the shared settings fragment under <dotfiles>/.claude/."""
    path = dotfiles_dir / ".claude" / "settings.shared.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def _write_hook_fragment(dotfiles_dir: Path, data: dict) -> Path:
    """Write the hook settings fragment under <dotfiles>/.claude/."""
    path = dotfiles_dir / ".claude" / "settings.hooks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return path


def _write_target(target_dir: Path, data: dict) -> Path:
    """Write the agent's settings.json target."""
    path = target_dir / "settings.json"
    path.write_text(json.dumps(data, indent=2))
    return path


def _read_target(target_dir: Path) -> dict:
    return json.loads((target_dir / "settings.json").read_text())


def test_env_replaced_wholesale(workspace: dict[str, Path]) -> None:
    """env is owned by sync: dropped keys are removed, fragment keys present."""
    # given
    _write_shared_fragment(workspace["dotfiles"], {"env": {"KEEP": "1", "ADDED": "2"}})
    _write_target(workspace["target"], {"env": {"KEEP": "old", "STALE": "x"}})
    agent = _make_agent(workspace["target"])

    # when
    changed = _merge_settings_fragment(workspace["dotfiles"], agent)

    # then
    assert changed is True
    result = _read_target(workspace["target"])
    assert result["env"] == {"KEEP": "1", "ADDED": "2"}
    assert "STALE" not in result["env"]


def test_toplevel_keys_upserted_and_unrelated_preserved(
    workspace: dict[str, Path],
) -> None:
    """Curated top-level keys are upserted; unrelated keys are untouched."""
    # given
    _write_shared_fragment(
        workspace["dotfiles"],
        {
            "env": {"A": "1"},
            "settings": {
                "includeGitInstructions": False,
                "promptSuggestionEnabled": False,
            },
        },
    )
    _write_target(
        workspace["target"],
        {
            "env": {"A": "1"},
            "theme": "dark-daltonized",
            "language": "japanese",
            "enabledPlugins": {"x@y": True},
            "statusLine": {"type": "command", "command": "x"},
        },
    )
    agent = _make_agent(workspace["target"])

    # when
    changed = _merge_settings_fragment(workspace["dotfiles"], agent)

    # then
    assert changed is True
    result = _read_target(workspace["target"])
    assert result["includeGitInstructions"] is False
    assert result["promptSuggestionEnabled"] is False
    # unrelated keys preserved verbatim
    assert result["theme"] == "dark-daltonized"
    assert result["language"] == "japanese"
    assert result["enabledPlugins"] == {"x@y": True}
    assert result["statusLine"] == {"type": "command", "command": "x"}


def test_hooks_block_preserved(workspace: dict[str, Path]) -> None:
    """The settings merge never touches an existing hooks block."""
    # given
    _write_shared_fragment(workspace["dotfiles"], {"env": {"A": "1"}})
    hooks_block = {
        "PreToolUse": [
            {"matcher": "Bash", "hooks": [{"type": "command", "command": "x"}]}
        ]
    }
    _write_target(workspace["target"], {"env": {"A": "0"}, "hooks": hooks_block})
    agent = _make_agent(workspace["target"])

    # when
    _merge_settings_fragment(workspace["dotfiles"], agent)

    # then
    result = _read_target(workspace["target"])
    assert result["hooks"] == hooks_block


def test_idempotent(workspace: dict[str, Path]) -> None:
    """A second run with an unchanged fragment is a no-op."""
    # given
    _write_shared_fragment(
        workspace["dotfiles"],
        {"env": {"A": "1"}, "settings": {"includeGitInstructions": False}},
    )
    _write_target(workspace["target"], {"env": {"OLD": "x"}})
    agent = _make_agent(workspace["target"])

    # when
    first = _merge_settings_fragment(workspace["dotfiles"], agent)
    after_first = (workspace["target"] / "settings.json").read_text()
    second = _merge_settings_fragment(workspace["dotfiles"], agent)
    after_second = (workspace["target"] / "settings.json").read_text()

    # then
    assert first is True
    assert second is False
    assert after_first == after_second


def test_dry_run_detects_without_writing(workspace: dict[str, Path]) -> None:
    """dry_run reports a change but writes nothing to disk."""
    # given
    _write_shared_fragment(workspace["dotfiles"], {"env": {"A": "1"}})
    _write_target(workspace["target"], {"env": {"OLD": "x"}})
    before = (workspace["target"] / "settings.json").read_text()
    agent = _make_agent(workspace["target"])

    # when
    changed = _merge_settings_fragment(workspace["dotfiles"], agent, dry_run=True)

    # then
    assert changed is True
    assert (workspace["target"] / "settings.json").read_text() == before


def test_missing_fragment_is_noop(workspace: dict[str, Path]) -> None:
    """No fragment file => no change, target untouched."""
    # given
    _write_target(workspace["target"], {"env": {"A": "1"}})
    before = (workspace["target"] / "settings.json").read_text()
    agent = _make_agent(workspace["target"])

    # when
    changed = _merge_settings_fragment(workspace["dotfiles"], agent)

    # then
    assert changed is False
    assert (workspace["target"] / "settings.json").read_text() == before


def test_creates_target_when_absent(workspace: dict[str, Path]) -> None:
    """A missing target settings.json is created from the fragment."""
    # given
    _write_shared_fragment(
        workspace["dotfiles"],
        {"env": {"A": "1"}, "settings": {"promptSuggestionEnabled": False}},
    )
    agent = _make_agent(workspace["target"])
    assert not (workspace["target"] / "settings.json").exists()

    # when
    changed = _merge_settings_fragment(workspace["dotfiles"], agent)

    # then
    assert changed is True
    result = _read_target(workspace["target"])
    assert result["env"] == {"A": "1"}
    assert result["promptSuggestionEnabled"] is False


def test_integration_hooks_then_settings(workspace: dict[str, Path]) -> None:
    """Sequential hook merge + settings merge both land in the final file.

    Guards against lost updates: each function reads fresh from disk, so running
    them back-to-back on the same settings.json preserves both results.
    """
    # given
    agent = _make_agent(workspace["target"])
    _write_hook_fragment(
        workspace["dotfiles"],
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [
                            {
                                "type": "command",
                                "command": '"$CLAUDE_PROJECT_DIR/.claude/hooks/foo.sh"',
                            }
                        ],
                    }
                ]
            }
        },
    )
    _write_shared_fragment(workspace["dotfiles"], {"env": {"A": "1"}})
    _write_target(workspace["target"], {"env": {"STALE": "x"}})

    # when (sequential, same process — mirrors sync_mode)
    _merge_hook_settings(workspace["dotfiles"], agent)
    _merge_settings_fragment(workspace["dotfiles"], agent)

    # then
    result = _read_target(workspace["target"])
    expected_cmd = f'"{agent.directory}/hooks/foo.sh"'
    assert result["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == expected_cmd
    assert result["env"] == {"A": "1"}
