"""The rtk wrapper's decisions, as a pure function tested on every OS.

ROOT_AGENTS_hooks_rtk-hook-claude.py runs rtk, then decides what to forward:
the worktree git veto, mise's launcher, the permission strip. respond() takes
rtk's answer and the facts the shell gathered and returns the answer to print
(None: print nothing). The end-to-end tests in test_rtk_hook_wrapper.py need
bash and a real python3 and skip on Windows; these do not.
"""

import copy
import importlib.util
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "rtk_hook_claude", ROOT / "ROOT_AGENTS_hooks_rtk-hook-claude.py"
)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

PLAIN = "/home/u/repo"
WORKTREE = "/home/u/repo/.claude/worktrees/agent-1"
MISE_RTK = "C:/Users/u/AppData/Local/mise/installs/rtk/0.50.0/rtk.exe"


def _answer(command: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "RTK auto-rewrite",
            "updatedInput": {"command": command},
        }
    }


def _respond(
    command: str, *, cwd: str = PLAIN, off_path: str | None = None, strip: bool = True
) -> dict | None:
    return hook.respond(_answer(command), cwd=cwd, off_path=off_path, strip=strip)


def test_a_rewrite_is_forwarded_without_the_approval() -> None:
    assert _respond("rtk git status") == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"command": "rtk git status"},
        }
    }


def test_keep_forwards_rtks_answer_as_it_is() -> None:
    assert _respond("rtk ls", strip=False) == _answer("rtk ls")


@pytest.mark.parametrize("command", ["rtk git status", "cd x && rtk git log"])
def test_git_is_vetoed_in_an_isolation_worktree(command: str) -> None:
    assert _respond(command, cwd=WORKTREE) is None


def test_other_commands_keep_rtk_in_a_worktree() -> None:
    assert _respond("rtk ls", cwd=WORKTREE) is not None


def test_mises_rtk_is_named_in_a_plain_rewrite() -> None:
    out = _respond("rtk read a.txt", off_path=MISE_RTK)
    assert out is not None
    assert out["hookSpecificOutput"]["updatedInput"]["command"] == (
        f"{shlex.quote(MISE_RTK)} read a.txt"
    )


def test_mises_rtk_drops_any_other_rewrite() -> None:
    assert _respond("rtk ls && rtk git status", off_path=MISE_RTK) is None


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"hookSpecificOutput": "x"},
        {"hookSpecificOutput": {"hookEventName": "PreToolUse"}},
    ],
)
def test_an_answer_without_a_rewrite_prints_nothing(answer: dict) -> None:
    assert hook.respond(answer, cwd=PLAIN, off_path=None, strip=True) is None


def test_rtks_answer_is_not_mutated() -> None:
    answer = _answer("rtk read a.txt")
    before = copy.deepcopy(answer)
    hook.respond(answer, cwd=PLAIN, off_path=MISE_RTK, strip=False)
    assert answer == before
