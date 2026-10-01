"""Codex sees a guard's block only as a deny decision on stdout.

Codex runs a hook through the session's shell (codex-rs core/src/session/
mod.rs build_hooks_config); on Windows that is `pwsh -Command`, which reports
every non-zero exit as 1. The guards' exit 2 reached Codex as "hook exited with
code 1", a failed hook, and a failed hook fails open: pnpm ran and a .yml file
was created. guard-codex.sh runs a guard and turns its exit 2 + stderr into
permissionDecision:"deny", which survives any shell; other exits pass through.
"""

import json
import shutil
from pathlib import Path

import pytest
from _bash_hook import run_bash

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "ROOT_AGENTS_hooks_guard-codex.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _guard(tmp_path: Path, body: str) -> Path:
    guard = tmp_path / "guard.sh"
    guard.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8", newline="\n")
    return guard


def _adapt(tmp_path: Path, guard: Path, payload: str) -> tuple[int, str, str]:
    done = run_bash(
        ADAPTER,
        guard.name,
        cwd=tmp_path,
        companions=(guard,),
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode, done.stdout, done.stderr


def test_a_block_becomes_a_deny_decision_on_stdout(tmp_path: Path) -> None:
    guard = _guard(
        tmp_path,
        'input="$(cat)"\nprintf \'BLOCKED: %s\\nsecond\\tline\\n\' "$input" >&2\nexit 2',
    )
    payload = '{"command":"C:\\\\x \\"q\\""}'
    code, out, _ = _adapt(tmp_path, guard, payload)
    assert code == 0
    assert json.loads(out) == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"BLOCKED: {payload} second line",
        }
    }


def test_a_silent_block_still_denies(tmp_path: Path) -> None:
    code, out, _ = _adapt(tmp_path, _guard(tmp_path, "exit 2"), "{}")
    assert code == 0
    reason = json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    assert reason == "blocked by guard.sh"


def test_an_allow_passes_stdout_through(tmp_path: Path) -> None:
    guard = _guard(tmp_path, "cat >/dev/null\nprintf '%s' '{\"ok\":1}'\nexit 0")
    assert _adapt(tmp_path, guard, "{}") == (0, '{"ok":1}', "")


def test_a_broken_guard_keeps_its_exit_and_stderr(tmp_path: Path) -> None:
    code, out, err = _adapt(tmp_path, _guard(tmp_path, "echo oops >&2\nexit 1"), "{}")
    assert (code, out) == (1, "")
    assert "oops" in err


@pytest.mark.skipif(
    shutil.which("python3") is None and shutil.which("python") is None,
    reason="the command guard runs a Python companion",
)
def test_the_command_guard_denies_pnpm_through_the_adapter(tmp_path: Path) -> None:
    guard = ROOT / "ROOT_AGENTS_hooks_block-prohibited-commands.sh"
    done = run_bash(
        ADAPTER,
        guard.name,
        cwd=tmp_path,
        companions=(guard, guard.with_suffix(".py")),
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "pnpm i"}}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0
    decision = json.loads(done.stdout)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "bun" in decision["permissionDecisionReason"]
