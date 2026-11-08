"""Codex gets the dotfiles guard hooks and rtk's Codex hook, managed like Claude's.

Codex reads `<codex home>/hooks.json` (Claude-shaped blocks; its shell tool is
`Bash`, apply_patch answers to `Write|Edit`). Copies of the guards sat there
outside the sync and never ran. Sync now distributes the hook files (minus the
Claude-only rtk wrapper, plus a Codex-only rtk shim) and merges a fragment
rendered from `.claude/settings.hooks.json` with the same ownership rules as Claude's:
blocks pointing into `<codex home>/hooks/` are sync's, others are left alone,
and the block `rtk init --codex` writes is retired.
"""

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path, PureWindowsPath
from typing import cast

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import sync_agents
from _bash_hook import bash_path, resolve_bash
from sync_agents import (
    AgentTarget,
    _detect_managed_dir_orphans,
    _merge_hook_settings,
    _render_hook_command,
    _SyncItem,
    _wants_hook,
    codex_fragment_from_claude,
)

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
        (False, True, "hooks/rtk-hook-codex.py"),
        (False, True, "hooks/guard-codex.sh"),
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
    # Codex runs hooks through the session shell (pwsh on Windows), which
    # resolves bare bash to System32's WSL launcher: Git's sh instead
    assert _render_hook_command(command, windows, system="Windows") == (
        'sh "C:/Users/x/.codex/hooks/rtk-hook-codex.sh"'
    )
    posix = AgentTarget(directory=Path("/home/u/.codex"), name="Codex")
    assert _render_hook_command(command, posix, system="Linux") == (
        'bash "/home/u/.codex/hooks/rtk-hook-codex.sh"'
    )


def _claude_source() -> dict:
    return json.loads(
        (ROOT / ".claude/settings.hooks.json").read_text(encoding="utf-8")
    )


def _hook(command: str) -> dict:
    return {"type": "command", "command": command}


# The Codex fragment the repo kept by hand as `.codex/hooks.json` until it was
# rendered from the one source; rendering must reproduce it exactly.
CODEX_FRAGMENT = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Write|Edit|NotebookEdit",
                "hooks": [
                    _hook(
                        'bash "$CODEX_HOME/hooks/guard-codex.sh" block-prohibited-files.sh'
                    ),
                    _hook('bash "$CODEX_HOME/hooks/guard-codex.sh" block-secrets.sh'),
                ],
            },
            {
                "matcher": "Bash",
                "hooks": [
                    _hook(
                        'bash "$CODEX_HOME/hooks/guard-codex.sh" block-prohibited-commands.sh'
                    )
                ],
            },
            {
                "matcher": "Bash",
                "hooks": [_hook('bash "$CODEX_HOME/hooks/rtk-hook-codex.sh"')],
            },
        ],
        "PostToolUse": [
            {
                "matcher": "Write|Edit",
                "hooks": [_hook('bash "$CODEX_HOME/hooks/format-after-edit.sh"')],
            }
        ],
    }
}


def test_the_codex_fragment_is_rendered_from_the_claude_source() -> None:
    # One source: Codex's hooks are derived from .claude/settings.hooks.json,
    # so the repo ships no .codex/hooks.json that Codex would also load as
    # project hooks (they ran twice inside this repo).
    assert codex_fragment_from_claude(_claude_source()) == CODEX_FRAGMENT
    assert not (ROOT / ".codex" / "hooks.json").exists()


def test_a_hook_removed_from_the_source_leaves_codex_too() -> None:
    source = _claude_source()
    del source["hooks"]["PostToolUse"]
    assert "PostToolUse" not in codex_fragment_from_claude(source)["hooks"]


def test_an_unknown_hook_command_stops_the_render() -> None:
    source = {
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [_hook("rtk hook claude")]}]
        }
    }
    with pytest.raises(ValueError, match="rtk hook claude"):
        codex_fragment_from_claude(source)


def test_the_codex_fragment_runs_the_guards_and_rtk() -> None:
    fragment = codex_fragment_from_claude(_claude_source())
    commands = {
        (event, block["matcher"], hook["command"])
        for event, blocks in fragment["hooks"].items()
        for block in blocks
        for hook in block["hooks"]
    }
    # the exit-2 guards go through the deny adapter (test_codex_guard_adapter)
    guarded = 'bash "$CODEX_HOME/hooks/guard-codex.sh" '
    for script in ("block-prohibited-files.sh", "block-secrets.sh"):
        assert (
            "PreToolUse",
            "Write|Edit|NotebookEdit",
            guarded + script,
        ) in commands
    assert (
        "PreToolUse",
        "Bash",
        guarded + "block-prohibited-commands.sh",
    ) in commands
    # rtk answers with JSON on stdout already
    assert (
        "PreToolUse",
        "Bash",
        'bash "$CODEX_HOME/hooks/rtk-hook-codex.sh"',
    ) in commands


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
    sys.platform == "win32",
    reason="the fake rtk is a shell script, which native Python cannot run; "
    "test_rtk_hook_codex covers the logic on every OS",
)
@pytest.mark.parametrize(("rtk_dir", "named"), [("bin", True), ("shims", False)])
def test_the_rtk_shim_names_the_real_binary_and_fails_open(
    tmp_path: Path, rtk_dir: str, named: bool
) -> None:
    """The shell entry runs the Python companion (test_rtk_hook_codex) with the
    first real Python, as the command guard's does. A shim-only rtk forwards
    nothing: it needs mise's config, which Codex's sandbox cannot read."""
    bash = resolve_bash()
    shim = ROOT / "ROOT_AGENTS_hooks_rtk-hook-codex.sh"
    companion = ROOT / "ROOT_AGENTS_hooks_rtk-hook-codex.py"
    staged = tmp_path / "hooks"
    staged.mkdir()
    shutil.copy(shim, staged / "rtk-hook-codex.sh")
    shutil.copy(companion, staged / "rtk-hook-codex.py")
    bin_dir = tmp_path / rtk_dir
    bin_dir.mkdir()
    answer = (
        '{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
        '"permissionDecision":"allow","updatedInput":{"command":"rtk git status"}}}'
    )
    fake = bin_dir / "rtk"
    fake.write_text(
        f"#!/bin/sh\ncat >/dev/null\nprintf '%s' '{answer}'\n",
        encoding="utf-8",
        newline="\n",
    )
    fake.chmod(0o755)
    python_dir = bash_path(Path(sys.executable).parent)

    def run(path: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                bash,
                "-c",
                f'PATH="{path}"; . "{(staged / "rtk-hook-codex.sh").as_posix()}"',
            ],
            input='{"tool_name":"Bash","tool_input":{"command":"git status"}}',
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    with_rtk = run(f"$(cd '{bin_dir.as_posix()}' && pwd):{python_dir}:/usr/bin:/bin")
    assert with_rtk.returncode == 0, with_rtk.stderr
    if named:
        out = json.loads(with_rtk.stdout)["hookSpecificOutput"]
        assert out["permissionDecision"] == "allow"
        command = out["updatedInput"]["command"]
        assert command.endswith("/rtk git status")
        assert command != "rtk git status"
    else:
        assert with_rtk.stdout == ""
    without = run(f"{python_dir}:/usr/bin:/bin")
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


# agent-hook registrations name a release binary, or a home's stable link to
# one. Sync must own them like the script blocks it owns today, so that
# reverting the agent-hook wiring and syncing again replaces them instead of
# leaving both (plan: agent-hooks-go). It owns a handler whose program is the
# binary, quoted and placed as the renderer writes it for that harness
# (Claude's exec form; Codex's sh, PowerShell, and cmd forms), with no member
# the renderer never writes. What follows the program is not compared, so a
# changed template's older handlers are still owned. So a path with an
# apostrophe, `$`, or a space still counts, and a handler whose program the
# shell would read differently, or that holds another member, stays its
# author's.

HEX = "0123456789abcdef"
DATA = "/home/u/.local/share/dotfiles/agent-hooks"
RELEASE = f"{DATA}/releases/{HEX}/agent-hook"
WINDOWS_DATA = "AppData\\Local\\dotfiles\\agent-hooks"
WINDOWS_RELEASE = f"{WINDOWS_DATA}\\releases\\{HEX}\\agent-hook.exe"
ARGS = ["pre", "--hook", "files-guard"]
CLOSED_SH = " codex pre --hook files-guard || { printf '%s\\n' 'agent-hook failed' >&2; exit 2; }"


def _stable(home: str) -> str:
    return f"{DATA}/current/{home}/agent-hook"


def _windows_stable(home: str) -> str:
    return f"{WINDOWS_DATA}\\current\\{home}\\agent-hook.exe"


def _hook(command: str, **fields: object) -> dict:
    return {"type": "command", "command": command, **fields}


def _claude(home: Path) -> AgentTarget:
    return AgentTarget(directory=home, name="Claude", key="claude", receives_hooks=True)


# What the renderer writes for Claude: the exec form, with no shell, so the
# command is the program path itself, and the path is the home's stable link.
RENDERED_CLAUDE = {
    "exec, stable link": _hook(
        _stable("claude"), args=["claude", *ARGS], timeout=30, onFailure="block"
    ),
    "exec, stable link, apostrophe and $": _hook(
        "/home/o'brien $x/.local/share/dotfiles/agent-hooks/current/claude/agent-hook",
        args=["claude", *ARGS],
    ),
    "exec, windows stable link": _hook(
        f"C:\\Users\\O'Brien $x\\{_windows_stable('claude')}", args=["claude", *ARGS]
    ),
}

# A Claude handler that names a release directly. Sync writes the home's
# stable link and has never written a release path, so such a handler is a
# user's, kept as it is (PR 3d.1; the owner, 2026-11-06). Codex's are too
# (PR 3d.2, CODEX_RELEASE_PATHS).
CLAUDE_RELEASE_PATHS = {
    "exec, release": _hook(
        RELEASE, args=["claude", *ARGS], timeout=30, onFailure="block"
    ),
    "exec, windows release": _hook(
        f"C:\\Users\\O'Brien $x\\{WINDOWS_RELEASE}", args=["claude", *ARGS]
    ),
}

STABLE = _stable("codex")
WINDOWS_STABLE_LINK = _windows_stable("codex")

# What it writes for Codex: sh on POSIX, PowerShell or cmd on Windows.
RENDERED_CODEX = {
    # sh: single quotes, with ' written as '\''.
    "sh, closed": _hook(f"'{_stable('codex')}'{CLOSED_SH}", timeout=30),
    "sh, stable link": _hook(f"'{_stable('codex')}' codex pre --hook rtk", timeout=30),
    # On POSIX, `\` is a filename character, not a separator.
    "sh, backslash in a name": _hook(
        "'/home/a\\b/.local/share/dotfiles/agent-hooks/current/codex/agent-hook' codex"
    ),
    "sh, apostrophe": _hook(
        "'/home/o'\\''brien/.local/share/dotfiles/agent-hooks/current/codex/"
        "agent-hook' codex pre"
    ),
    # PowerShell: & and single quotes, with ' written as ''. Nothing inside
    # single quotes expands.
    "powershell": _hook(
        f"& 'C:\\Users\\O''Brien $x %y% !z!\\{WINDOWS_STABLE_LINK}' codex pre --hook files-guard;"
        " if ($LASTEXITCODE -ne 0) { '{}' }"
    ),
    "powershell, stable link": _hook(
        f"& 'C:\\Users\\u\\{_windows_stable('codex')}' codex pre --hook rtk", timeout=30
    ),
    # cmd: double quotes, content literal ($ and spaces included).
    "cmd": _hook(
        f'"C:\\Users\\build$\\A B\\{WINDOWS_STABLE_LINK}" codex pre --hook files-guard'
        ' || echo {"decision":"block"}'
    ),
    "cmd, stable link": _hook(
        f'"C:\\Users\\u\\{_windows_stable("codex")}" codex post --hook formatter'
    ),
}


@pytest.mark.parametrize("hook", RENDERED_CLAUDE.values(), ids=RENDERED_CLAUDE.keys())
def test_a_claude_agent_hook_block_is_managed_for_claude_only(
    tmp_path: Path, hook: dict
) -> None:
    block = {"matcher": "Bash", "hooks": [hook]}
    assert sync_agents._is_managed_hook_block(block, _claude(tmp_path / "claude"))
    assert not sync_agents._is_managed_hook_block(block, _codex(tmp_path / "codex"))


@pytest.mark.parametrize("hook", RENDERED_CODEX.values(), ids=RENDERED_CODEX.keys())
def test_a_codex_agent_hook_block_is_managed_for_codex_only(
    tmp_path: Path, hook: dict
) -> None:
    block = {"matcher": "Bash", "hooks": [hook]}
    assert sync_agents._is_managed_hook_block(block, _codex(tmp_path / "codex"))
    assert not sync_agents._is_managed_hook_block(block, _claude(tmp_path / "claude"))


@pytest.mark.parametrize(
    "hook", CLAUDE_RELEASE_PATHS.values(), ids=CLAUDE_RELEASE_PATHS.keys()
)
def test_a_claude_block_that_names_a_release_is_the_users(
    tmp_path: Path, hook: dict
) -> None:
    claude = _claude(tmp_path / "claude")
    block = {"matcher": "Bash", "hooks": [hook]}
    # given a Claude block that runs a release directly, sync does not own it
    assert not sync_agents._is_managed_hook_block(block, claude)
    # and a sync keeps it as it is
    merged = _merged_after_revert(claude, "settings.json", hook)
    assert block in merged["hooks"]["PreToolUse"]


# The same rule for Codex (PR 3d.2): sync writes only the stable link.
CODEX_RELEASE_PATHS = {
    "sh, release": _hook(f"'{RELEASE}'{CLOSED_SH}", timeout=30),
    "sh, backslash in a name": _hook(
        f"'/home/a\\b/.local/share/dotfiles/agent-hooks/releases/{HEX}/agent-hook' codex"
    ),
    "powershell, release": _hook(
        f"& 'C:\\Users\\O''Brien $x\\{WINDOWS_RELEASE}' codex pre --hook files-guard;"
        " if ($LASTEXITCODE -ne 0) { '{}' }"
    ),
    "cmd, release": _hook(
        f'"C:\\Users\\build$\\A B\\{WINDOWS_RELEASE}" codex pre --hook files-guard'
    ),
}


@pytest.mark.parametrize(
    "hook", CODEX_RELEASE_PATHS.values(), ids=CODEX_RELEASE_PATHS.keys()
)
def test_a_codex_block_that_names_a_release_is_the_users(
    tmp_path: Path, hook: dict
) -> None:
    codex = _codex(tmp_path / "codex")
    block = {"matcher": "Bash", "hooks": [hook]}
    # given a Codex block that runs a release directly, sync does not own it
    assert not sync_agents._is_managed_hook_block(block, codex)
    # and a sync keeps it as it is
    merged = _merged_after_revert(codex, "hooks.json", hook)
    assert block in merged["hooks"]["PreToolUse"]


def test_a_block_that_also_runs_a_user_command_is_not_managed(tmp_path: Path) -> None:
    agent = _codex(tmp_path / "codex")
    block = {
        "matcher": "Bash",
        "hooks": [RENDERED_CODEX["sh, closed"], _hook("./scripts/mine.sh")],
    }
    assert not sync_agents._is_managed_hook_block(block, agent)


# Hooks whose program is not a home's stable link in a form the renderer
# writes: mentioning the path, a form it does not write, another program, or a
# handler with a member it never writes. Each names the stable link, which
# sync owns, so only its form keeps it the user's.
NOT_RUNNING_A_RELEASE = {
    "not a release id": _hook(
        "'/opt/dotfiles/agent-hooks/releases/latest/agent-hook' codex"
    ),
    "longer name": _hook(f"'{STABLE}-extra' codex"),
    "echo": _hook(f'echo "{STABLE}"'),
    "argument": _hook(f"sha256sum {STABLE}"),
    "unbalanced quotes": _hook(f"'{STABLE}\" codex pre"),
    "assignment": _hook(f"AGENT_HOOK={STABLE} printf ok"),
    "redirection": _hook(f"sha256sum<{STABLE}"),
    "redirection after a path": _hook(f"/bin/cat<{STABLE}"),
    "relative": _hook("'dotfiles/agent-hooks/current/codex/agent-hook' codex"),
    "unquoted shell form": _hook(f"{STABLE} codex pre"),
    "double-quoted posix path": _hook(f'"{STABLE}" codex pre'),
    "single-quoted windows path": _hook(f"'C:\\Users\\u\\{WINDOWS_STABLE_LINK}' codex"),
    "powershell with a posix path": _hook(f"& '{STABLE}' codex"),
    "text after the quote": _hook(f"'{STABLE}'x codex"),
    "exec form, relative": _hook("agent-hook", args=ARGS),
    # On POSIX these name one file whose name holds backslashes.
    "posix backslashes, sh": _hook(
        "'/tmp/user\\dotfiles\\agent-hooks\\current\\codex\\agent-hook' codex"
    ),
    "posix backslashes, exec form": _hook(
        "/tmp/user\\dotfiles\\agent-hooks\\current\\codex\\agent-hook", args=ARGS
    ),
    # The harness still expands these, so the path does not name itself: cmd's
    # %VAR% and !VAR! inside double quotes, Claude's ${...} placeholders.
    "cmd, %": _hook(
        '"C:\\data\\%TEMP%\\dotfiles\\agent-hooks\\current\\codex\\agent-hook.exe" codex'
    ),
    "cmd, !": _hook(
        '"C:\\data\\!X!\\dotfiles\\agent-hooks\\current\\codex\\agent-hook.exe" codex'
    ),
    "exec form, placeholder": _hook(
        "/home/${CLAUDE_PROJECT_DIR}/dotfiles/agent-hooks/current/codex/agent-hook",
        args=ARGS,
    ),
    "exec form, another program": _hook("/usr/bin/env", args=[STABLE]),
    # PowerShell reads ‘ ’ ‚ ‛ as single quotes, and `&` resolves * ? [ ] as
    # wildcards when the literal path is missing (pwsh 7.6.9: '[ab]' ran 'a').
    "powershell, smart quote": _hook(
        f"& 'C:\\Users\\O\u2019Brien\\{WINDOWS_STABLE_LINK}' codex"
    ),
    "powershell, bracket": _hook(f"& 'C:\\Users\\[ab]\\{WINDOWS_STABLE_LINK}' codex"),
    "powershell, star": _hook(f"& 'C:\\Users\\a*\\{WINDOWS_STABLE_LINK}' codex"),
    "powershell, question mark": _hook(
        f"& 'C:\\Users\\a?\\{WINDOWS_STABLE_LINK}' codex"
    ),
    # The stable link's home is lowercase letters, digits, and `-`, one name.
    "stable link, upper case home": _hook(f"'{DATA}/current/Upper/agent-hook' codex"),
    "stable link, empty home": _hook(f"'{DATA}/current//agent-hook' codex"),
    "stable link, nested home": _hook(f"'{DATA}/current/a/b/agent-hook' codex"),
    "stable link, longer name": _hook(f"'{_stable('claude')}-x' codex"),
    # The suffix follows the OS: none on POSIX, `.exe` on Windows.
    "posix .exe, sh": _hook(f"'{STABLE}.exe' codex"),
    "posix .exe, exec form": _hook(f"{STABLE}.exe", args=ARGS),
    "windows without .exe, cmd": _hook(
        f'"C:\\Users\\u\\{WINDOWS_STABLE_LINK.removesuffix(".exe")}" codex'
    ),
    "windows without .exe, exec form": _hook(
        f"C:\\Users\\u\\{WINDOWS_STABLE_LINK.removesuffix('.exe')}", args=ARGS
    ),
    # A control character is never part of a path the renderer writes.
    "a tab, sh": _hook(
        "'/home/a\tb/.local/share/dotfiles/agent-hooks/current/codex/agent-hook' codex"
    ),
    "a tab, exec form": _hook(
        "/home/a\tb/.local/share/dotfiles/agent-hooks/current/codex/agent-hook",
        args=ARGS,
    ),
    # Members the renderer never writes. Codex ignores args, and commandWindows
    # changes what runs on Windows.
    "codex form with commandWindows": _hook(
        f"'{STABLE}'{CLOSED_SH}", commandWindows="mine.cmd"
    ),
    "codex form with async": _hook(f"'{STABLE}'{CLOSED_SH}", **{"async": True}),
    "codex form with args": _hook(f"'{STABLE}'{CLOSED_SH}", args=[]),
    "exec form with statusMessage": _hook(STABLE, args=ARGS, statusMessage="checking"),
    "another type": {"type": "prompt", "command": STABLE, "args": ARGS},
    # The renderer writes one ASCII space after the program and nothing
    # before it. sh, bash, and zsh split words on space, tab, and newline
    # only, so another separator joins the next word to the program's name.
    "nbsp after the path": _hook(f"'{STABLE}'\u00a0codex pre"),
    "ideographic space after the path": _hook(f"'{STABLE}'\u3000codex pre"),
    "unit separator after the path": _hook(f"'{STABLE}'\x1fcodex pre"),
    "tab after the path": _hook(f"'{STABLE}'\tcodex pre"),
    "a line after the path": _hook(f"'{STABLE}'\nmine"),
    "leading space": _hook(f" '{STABLE}' codex pre"),
    "leading nbsp": _hook(f"\u00a0'{STABLE}' codex pre"),
    "powershell, two spaces after &": _hook(
        f"&  'C:\\Users\\u\\{WINDOWS_STABLE_LINK}' codex"
    ),
    "cmd, nbsp after the path": _hook(
        f'"C:\\Users\\u\\{WINDOWS_STABLE_LINK}"\u00a0codex'
    ),
}


@pytest.mark.parametrize("agent", [_claude, _codex], ids=["claude", "codex"])
@pytest.mark.parametrize(
    "hook", NOT_RUNNING_A_RELEASE.values(), ids=NOT_RUNNING_A_RELEASE.keys()
)
def test_a_hook_that_does_not_run_a_release_is_not_managed(
    tmp_path: Path, hook: dict, agent: Callable[[Path], AgentTarget]
) -> None:
    block = {"matcher": "Bash", "hooks": [hook]}
    assert not sync_agents._is_managed_hook_block(block, agent(tmp_path / "home"))


def test_a_script_handler_with_a_member_sync_never_writes_is_not_managed(
    tmp_path: Path,
) -> None:
    # A command that points into the agent's hooks dir is sync's only if the
    # handler holds nothing sync never writes: Codex's commandWindows runs a
    # command of the user's on Windows, so the user's handler must survive.
    codex = _codex(tmp_path / "codex")
    (codex.directory / "hooks").mkdir(parents=True)
    script = f'bash "{codex.directory.as_posix()}/hooks/block-secrets.sh"'
    user_block = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": script, "commandWindows": "mine.cmd"}],
    }
    assert not sync_agents._is_managed_hook_block(user_block, codex)
    claude = _claude(tmp_path / "claude")
    claude_script = f'bash "{claude.directory.as_posix()}/hooks/block-secrets.sh"'
    claude_block = {
        "matcher": "Bash",
        "hooks": [
            {"type": "command", "command": claude_script, "statusMessage": "checking"}
        ],
    }
    assert not sync_agents._is_managed_hook_block(claude_block, claude)
    # and a sync keeps it
    (codex.directory / "hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [user_block]}}), encoding="utf-8"
    )
    _merge_hook_settings(ROOT, codex, system="Linux")
    merged = json.loads((codex.directory / "hooks.json").read_text(encoding="utf-8"))
    assert user_block in merged["hooks"]["PreToolUse"]


@pytest.mark.parametrize(
    "hook", NOT_RUNNING_A_RELEASE.values(), ids=NOT_RUNNING_A_RELEASE.keys()
)
def test_a_user_block_that_mentions_a_release_survives_a_sync(
    tmp_path: Path, hook: dict
) -> None:
    agent = _codex(tmp_path / "codex")
    (agent.directory / "hooks").mkdir(parents=True)
    user_block = {"matcher": "Bash", "hooks": [hook]}
    (agent.directory / "hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [user_block]}}), encoding="utf-8"
    )
    _merge_hook_settings(ROOT, agent, system="Linux")
    merged = json.loads((agent.directory / "hooks.json").read_text(encoding="utf-8"))
    assert user_block in merged["hooks"]["PreToolUse"]


def _merged_after_revert(agent: AgentTarget, file: str, hook: dict) -> dict:
    """Sync a home whose only block is an agent-hook one, as after a revert."""
    (agent.directory / "hooks").mkdir(parents=True)
    release_block = {"matcher": "Bash", "hooks": [hook]}
    (agent.directory / file).write_text(
        json.dumps({"hooks": {"PreToolUse": [release_block]}}), encoding="utf-8"
    )
    _merge_hook_settings(ROOT, agent, system="Linux")
    return json.loads((agent.directory / file).read_text(encoding="utf-8"))


def _commands(merged: dict) -> list[str]:
    return [
        hook["command"]
        for block in merged["hooks"]["PreToolUse"]
        for hook in block["hooks"]
    ]


@pytest.mark.parametrize("hook", RENDERED_CODEX.values(), ids=RENDERED_CODEX.keys())
def test_syncing_codex_after_a_revert_replaces_agent_hook_blocks(
    tmp_path: Path, hook: dict
) -> None:
    merged = _merged_after_revert(_codex(tmp_path / "codex"), "hooks.json", hook)
    assert {"matcher": "Bash", "hooks": [hook]} not in merged["hooks"]["PreToolUse"]
    assert any("guard-codex.sh" in command for command in _commands(merged))


@pytest.mark.parametrize("hook", RENDERED_CLAUDE.values(), ids=RENDERED_CLAUDE.keys())
def test_syncing_claude_after_a_revert_replaces_agent_hook_blocks(
    tmp_path: Path, hook: dict
) -> None:
    merged = _merged_after_revert(_claude(tmp_path / "claude"), "settings.json", hook)
    assert {"matcher": "Bash", "hooks": [hook]} not in merged["hooks"]["PreToolUse"]
    assert any("block-prohibited-files.sh" in command for command in _commands(merged))
