"""sync-agents must not uninstall a third-party integration living in hooks/.

`<agent>/hooks/` is sync-owned (stale dotfiles hooks are deleted) and a
settings.json hook block whose commands all point there is treated as managed
(replaced by the fragment). herdr installs its Claude integration into that
same directory and registers it in settings.json:

    # installed by herdr
    # managed by herdr; reinstalling or updating the integration overwrites this file.

Without an ownership check, every sync deleted the file and dropped its block,
silently removing herdr's integration. A file carrying an installer header is
the installer's, so both the file and the blocks calling it are left alone.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from sync_agents import (  # noqa: E402
    AgentTarget,
    _detect_managed_dir_orphans,
    _merge_hook_settings,
    _SyncItem,
)

HERDR_HEADER = (
    "# installed by herdr\n"
    "# managed by herdr; reinstalling or updating the integration overwrites"
    " this file.\n"
    "# HERDR_INTEGRATION_ID=claude\n"
    'param([string]$Action = "")\n'
)


@pytest.fixture()
def agent(tmp_path: Path) -> AgentTarget:
    home = tmp_path / "claude-home"
    (home / "hooks").mkdir(parents=True)
    return AgentTarget(directory=home, name="Test", receives_hooks=True)


def _managed_source(dotfiles: Path, name: str) -> _SyncItem:
    return _SyncItem(
        source=dotfiles / f"ROOT_AGENTS_hooks_{name}",
        relative_path=f"hooks/{name}",
        is_directory=False,
    )


def _orphan_paths(agent: AgentTarget, sources: list[_SyncItem]) -> list[str]:
    return [d.relative_path for d in _detect_managed_dir_orphans(agent, sources)]


def _herdr_block(agent: AgentTarget) -> dict:
    # Windows form, as herdr writes it: backslash path inside -File "...".
    script = str(agent.directory / "hooks" / "herdr-agent-state.ps1").replace("/", "\\")
    command = f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script}" session'
    return {"matcher": "", "hooks": [{"type": "command", "command": command}]}


def test_installer_owned_hook_file_is_not_an_orphan(
    agent: AgentTarget, tmp_path: Path
) -> None:
    # given a herdr-installed hook beside a dotfiles-managed one
    hooks = agent.directory / "hooks"
    (hooks / "herdr-agent-state.ps1").write_text(HERDR_HEADER, encoding="utf-8")
    (hooks / "block-secrets.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    sources = [_managed_source(tmp_path, "block-secrets.sh")]

    # when orphans are detected
    orphans = _orphan_paths(agent, sources)

    # then herdr's file is kept
    assert "hooks/herdr-agent-state.ps1" not in orphans


def test_stale_dotfiles_hook_is_still_an_orphan(
    agent: AgentTarget, tmp_path: Path
) -> None:
    # given a hook whose ROOT_AGENTS_ source was removed (no installer header)
    (agent.directory / "hooks" / "old-hook.sh").write_text(
        "#!/usr/bin/env bash\necho old\n", encoding="utf-8"
    )

    # when orphans are detected
    orphans = _orphan_paths(agent, [])

    # then it is still swept
    assert orphans == ["hooks/old-hook.sh"]


def test_block_calling_installer_owned_hook_survives_merge(
    agent: AgentTarget, tmp_path: Path
) -> None:
    # given herdr's file and its settings block, plus a dotfiles hook fragment
    (agent.directory / "hooks" / "herdr-agent-state.ps1").write_text(
        HERDR_HEADER, encoding="utf-8"
    )
    herdr = _herdr_block(agent)
    (agent.directory / "settings.json").write_text(
        json.dumps({"hooks": {"SessionStart": [herdr]}}), encoding="utf-8"
    )
    fragment = tmp_path / "dotfiles" / ".claude" / "settings.hooks.json"
    fragment.parent.mkdir(parents=True)
    fragment.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/block-secrets.sh"',
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    # when the hook fragment is merged
    _merge_hook_settings(tmp_path / "dotfiles", agent)

    # then herdr's block is still registered
    merged = json.loads((agent.directory / "settings.json").read_text(encoding="utf-8"))
    assert merged["hooks"]["SessionStart"] == [herdr]


def test_block_calling_a_missing_hook_file_is_still_managed(
    agent: AgentTarget, tmp_path: Path
) -> None:
    # given a block pointing into hooks/ at a file that no longer exists
    stale = _herdr_block(agent)
    (agent.directory / "settings.json").write_text(
        json.dumps({"hooks": {"SessionStart": [stale]}}), encoding="utf-8"
    )
    fragment = tmp_path / "dotfiles" / ".claude" / "settings.hooks.json"
    fragment.parent.mkdir(parents=True)
    fragment.write_text(json.dumps({"hooks": {}}), encoding="utf-8")

    # when the hook fragment is merged
    _merge_hook_settings(tmp_path / "dotfiles", agent)

    # then the dangling block is dropped as before
    merged = json.loads((agent.directory / "settings.json").read_text(encoding="utf-8"))
    assert "SessionStart" not in merged.get("hooks", {})


def test_bom_hook_keeps_its_file_and_settings_block(
    agent: AgentTarget, tmp_path: Path
) -> None:
    script = agent.directory / "hooks" / "herdr-agent-state.ps1"
    script.write_text(HERDR_HEADER, encoding="utf-8-sig")
    herdr = _herdr_block(agent)
    settings = agent.directory / "settings.json"
    settings.write_text(
        json.dumps({"hooks": {"SessionStart": [herdr]}}), encoding="utf-8"
    )
    fragment = tmp_path / "dotfiles" / ".claude" / "settings.hooks.json"
    fragment.parent.mkdir(parents=True)
    fragment.write_text(json.dumps({"hooks": {}}), encoding="utf-8")

    assert "hooks/herdr-agent-state.ps1" not in _orphan_paths(agent, [])
    _merge_hook_settings(tmp_path / "dotfiles", agent)
    assert json.loads(settings.read_text(encoding="utf-8"))["hooks"][
        "SessionStart"
    ] == [herdr]


@pytest.mark.parametrize("quote", ['"', "'"])
def test_quoted_hook_with_spaces_keeps_its_settings_block(
    agent: AgentTarget, tmp_path: Path, quote: str
) -> None:
    script = agent.directory / "hooks" / "herdr custom.ps1"
    script.write_text(HERDR_HEADER, encoding="utf-8")
    path = str(script).replace("/", "\\")
    block = {
        "hooks": [
            {
                "type": "command",
                "command": f"powershell -File {quote}{path}{quote} session",
            }
        ]
    }
    settings = agent.directory / "settings.json"
    settings.write_text(
        json.dumps({"hooks": {"SessionStart": [block]}}), encoding="utf-8"
    )
    fragment = tmp_path / "dotfiles" / ".claude" / "settings.hooks.json"
    fragment.parent.mkdir(parents=True)
    fragment.write_text(json.dumps({"hooks": {}}), encoding="utf-8")

    assert "hooks/herdr custom.ps1" not in _orphan_paths(agent, [])
    _merge_hook_settings(tmp_path / "dotfiles", agent)
    assert json.loads(settings.read_text(encoding="utf-8"))["hooks"][
        "SessionStart"
    ] == [block]
