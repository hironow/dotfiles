"""Codex gets the dotfiles guard hooks and rtk's Codex hook, managed like Claude's.

Codex reads `<codex home>/hooks.json` (Claude-shaped blocks; its shell tool is
`Bash`, apply_patch answers to `Write|Edit`). Copies of the guards sat there
outside the sync and never ran. Sync now distributes the hook files (minus the
Claude-only rtk wrapper, plus a Codex-only rtk shim) and merges the
`.codex/hooks.json` fragment with the same ownership rules as Claude's:
blocks pointing into `<codex home>/hooks/` are sync's, others are left alone,
and the block `rtk init --codex` writes is retired.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import sync_agents  # noqa: E402
from sync_agents import (  # noqa: E402
    AgentTarget,
    _detect_managed_dir_orphans,
    _merge_hook_settings,
    _render_hook_command,
    _SyncItem,
    _wants_hook,
)
from _bash_hook import resolve_bash  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _codex(home: Path) -> AgentTarget:
    return AgentTarget(
        directory=home, name="Codex", key="codex", receives_codex_hooks=True
    )


def test_the_codex_target_receives_codex_hooks() -> None:
    [codex] = [agent for agent in sync_agents.AGENTS if agent.key == "codex"]
    assert codex.receives_codex_hooks and not codex.receives_hooks


@pytest.mark.parametrize(
    ("claude", "codex", "path"),
    [
        (True, True, "hooks/block-secrets.sh"),
        (True, False, "hooks/rtk-hook-claude.py"),
        (False, True, "hooks/rtk-hook-codex.sh"),
        (True, True, "docs/agents/rtk.md"),
    ],
)
def test_hook_files_are_split_by_agent(
    tmp_path: Path, claude: bool, codex: bool, path: str
) -> None:
    claude_agent = AgentTarget(
        directory=tmp_path / "c", name="Claude", receives_hooks=True
    )
    assert _wants_hook(claude_agent, path) is claude
    assert _wants_hook(_codex(tmp_path / "x"), path) is codex
    plain = AgentTarget(directory=tmp_path / "g", name="Gemini")
    assert _wants_hook(plain, path) is (not path.startswith("hooks/"))


def test_codex_commands_render_into_the_codex_home() -> None:
    windows = AgentTarget(
        directory=cast(Path, PureWindowsPath(r"C:\Users\x\.codex")), name="Codex"
    )
    command = 'bash "$CODEX_HOME/hooks/rtk-hook-codex.sh"'
    # Codex runs hooks through cmd.exe on Windows: Git's sh, never System32 bash
    assert _render_hook_command(command, windows, system="Windows") == (
        'sh "C:/Users/x/.codex/hooks/rtk-hook-codex.sh"'
    )
    posix = AgentTarget(directory=Path("/home/u/.codex"), name="Codex")
    assert _render_hook_command(command, posix, system="Linux") == (
        'bash "/home/u/.codex/hooks/rtk-hook-codex.sh"'
    )


def test_the_codex_fragment_runs_the_guards_and_rtk() -> None:
    fragment = json.loads((ROOT / ".codex/hooks.json").read_text(encoding="utf-8"))
    commands = {
        (event, block["matcher"], hook["command"])
        for event, blocks in fragment["hooks"].items()
        for block in blocks
        for hook in block["hooks"]
    }
    for script in ("block-prohibited-files.sh", "block-secrets.sh"):
        assert (
            "PreToolUse",
            "Write|Edit|NotebookEdit",
            f'bash "$CODEX_HOME/hooks/{script}"',
        ) in commands
    for script in ("block-prohibited-commands.sh", "rtk-hook-codex.sh"):
        assert ("PreToolUse", "Bash", f'bash "$CODEX_HOME/hooks/{script}"') in commands


def test_merging_keeps_foreign_blocks_and_retires_rtks_own(tmp_path: Path) -> None:
    agent = _codex(tmp_path / "codex")
    hooks_dir = agent.directory / "hooks"
    hooks_dir.mkdir(parents=True)
    stale = {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": f"sh '{hooks_dir}/block-prohibited-commands.sh'",
            }
        ],
    }
    rtk_own = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "rtk hook codex"}],
    }
    herdr = {
        "hooks": [
            {
                "type": "command",
                "command": f'powershell -File "{agent.directory}/herdr-agent-state.ps1" session',
                "timeout": 10,
            }
        ]
    }
    (agent.directory / "hooks.json").write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [stale, rtk_own], "SessionStart": [herdr]}}
        ),
        encoding="utf-8",
    )

    assert _merge_hook_settings(ROOT, agent, system="Linux")
    merged = json.loads((agent.directory / "hooks.json").read_text(encoding="utf-8"))
    commands = [h["command"] for b in merged["hooks"]["PreToolUse"] for h in b["hooks"]]
    assert "rtk hook codex" not in commands
    assert f"sh '{hooks_dir}/block-prohibited-commands.sh'" not in commands
    assert f'bash "{agent.directory.as_posix()}/hooks/rtk-hook-codex.sh"' in commands
    assert merged["hooks"]["SessionStart"] == [herdr]
    # the Claude settings file is not Codex's
    assert not (agent.directory / "settings.json").exists()
    assert not _merge_hook_settings(ROOT, agent, system="Linux")


def test_a_stale_codex_hook_file_is_an_orphan_but_the_claude_wrapper_is_not_expected(
    tmp_path: Path,
) -> None:
    agent = _codex(tmp_path / "codex")
    hooks_dir = agent.directory / "hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "old-guard.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    sources = [
        _SyncItem(
            source=ROOT / f"ROOT_AGENTS_hooks_{n}",
            relative_path=f"hooks/{n}",
            is_directory=False,
        )
        for n in ("rtk-hook-claude.py", "rtk-hook-codex.sh")
    ]
    orphans = [d.relative_path for d in _detect_managed_dir_orphans(agent, sources)]
    assert "hooks/old-guard.sh" in orphans


@pytest.mark.skipif(
    shutil.which("sh") is None and sys.platform == "win32", reason="no sh"
)
def test_the_rtk_shim_passes_rtks_answer_through_and_fails_open(tmp_path: Path) -> None:
    # Codex reads permissionDecision:"allow" only as the carrier of
    # updatedInput (it grants no approval), so nothing is stripped
    bash = resolve_bash()
    shim = (ROOT / "ROOT_AGENTS_hooks_rtk-hook-codex.sh").as_posix()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    answer = '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"rtk git status"}}}'
    fake = bin_dir / "rtk"
    fake.write_text(
        f"#!/bin/sh\ncat >/dev/null\nprintf '%s' '{answer}'\n",
        encoding="utf-8",
        newline="\n",
    )
    fake.chmod(0o755)

    def run(path: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [bash, "-c", f'PATH="{path}"; . "{shim}"'],
            input='{"tool_name":"Bash","tool_input":{"command":"git status"}}',
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    with_rtk = run(f"$(cd '{bin_dir.as_posix()}' && pwd):/usr/bin:/bin")
    assert with_rtk.returncode == 0
    assert json.loads(with_rtk.stdout) == json.loads(answer)
    without = run("/usr/bin:/bin")
    assert (without.returncode, without.stdout) == (0, "")


@pytest.mark.parametrize(
    ("command", "retired"),
    [
        ("rtk hook claude", True),
        ("rtk hook codex", True),
        # what a later rtk installer may write: still rtk's own block
        ("rtk hook codex --format json", True),
        ("rtk.exe hook claude", True),
        (
            '"C:/Users/u/AppData/Local/mise/installs/rtk/0.51.0/rtk.exe" hook codex',
            True,
        ),
        # a user's own wrapper around it is theirs
        ("my-wrapper rtk hook codex", False),
        ("rtk git status", False),
    ],
)
def test_rtk_installer_blocks_are_recognised_across_rtk_versions(
    command: str, retired: bool
) -> None:
    block = {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]}
    assert sync_agents._is_retired_hook_block(block) is retired
