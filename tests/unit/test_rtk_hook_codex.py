"""Codex's rtk hook names rtk's real binary in every rewrite it forwards.

Inside Codex's Windows sandbox the rewritten `rtk ls -la` found mise's shim on
PATH, and the shim died with "No version is set for shim: rtk": the sandbox
cannot read ~/.config/mise/config.toml (Codex skips ~/.config). The hook runs
as the user, outside the sandbox, so it asks `mise which rtk` for the real
binary (whose directory the sandbox can read, codex_sandbox_tools) and puts its
path in the rewrite. As in the Claude wrapper, only the plain `rtk <command>`
shape is kept; and Codex runs commands through pwsh on Windows, so only a path
that needs no quoting is used. Anything else forwards nothing: the typed command
runs, which costs the compression and never the command.
"""

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, file: str):  # noqa: ANN202 - a module loaded by path
    spec = importlib.util.spec_from_file_location(name, ROOT / file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


codex = _load("rtk_hook_codex", "ROOT_AGENTS_hooks_rtk-hook-codex.py")
claude = _load("rtk_hook_claude", "ROOT_AGENTS_hooks_rtk-hook-claude.py")

REAL = "C:/Users/u/AppData/Local/mise/installs/rtk/0.50.0/rtk.exe"


@pytest.mark.parametrize(
    ("mise_answer", "on_path", "launcher"),
    [
        (REAL, "C:/Users/u/AppData/Local/mise/shims/rtk.exe", REAL),
        (None, "/home/u/.local/bin/rtk", "/home/u/.local/bin/rtk"),
        # a shim needs mise's config, which the sandbox cannot read
        (None, "C:/Users/u/AppData/Local/mise/shims/rtk.exe", None),
        (None, None, None),
    ],
)
def test_the_real_binary_is_preferred_and_a_shim_never_used(
    mise_answer: str | None, on_path: str | None, launcher: str | None
) -> None:
    assert codex.choose_launcher(mise_answer, on_path) == launcher


@pytest.mark.parametrize(
    ("command", "launcher", "named"),
    [
        ("rtk ls -la", REAL, f"{REAL} ls -la"),
        ("rtk git status", "C:\\Users\\u\\rtk.exe", "C:/Users/u/rtk.exe git status"),
        ("rtk ls && rtk git status", REAL, None),
        ("FOO=1 rtk git log", REAL, None),
        # a path that needs quoting would need pwsh's & on Windows
        ("rtk ls", "C:/Users/John Doe/rtk.exe", None),
    ],
)
def test_only_a_plain_rewrite_with_an_unquoted_path_is_named(
    command: str, launcher: str, named: str | None
) -> None:
    assert codex.named(command, launcher) == named


@pytest.mark.parametrize(
    "command",
    ["rtk ls -la", "rtk read a.txt", "rtk ls && rtk git status", "cat rtk", "rtk"],
)
def test_codex_and_claude_keep_the_same_rewrites(command: str) -> None:
    # Two standalone hooks (each is copied alone into an agent home), one rule
    kept_by_codex = codex.named(command, REAL) is not None
    kept_by_claude = claude._with_launcher(command, REAL) is not None
    assert kept_by_codex == kept_by_claude


def _answer(command: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecisionReason": "RTK auto-rewrite",
            "updatedInput": {"command": command},
            "permissionDecision": "allow",
        }
    }


def test_the_answer_keeps_codexs_allow_and_names_the_binary() -> None:
    # Codex reads permissionDecision:"allow" only as the carrier of
    # updatedInput (it grants no approval), so nothing is stripped
    answer = _answer("rtk ls -la")
    before = copy.deepcopy(answer)
    out = codex.respond(answer, REAL)
    expected = copy.deepcopy(before)
    expected["hookSpecificOutput"]["updatedInput"]["command"] = f"{REAL} ls -la"
    assert out == expected
    assert answer == before


@pytest.mark.parametrize(
    "answer",
    [{}, {"hookSpecificOutput": "x"}, _answer("rtk ls && rtk git status")],
)
def test_anything_else_forwards_nothing(answer: dict) -> None:
    assert codex.respond(answer, REAL) is None
