"""Unit tests for the rtk PreToolUse wrapper ROOT_AGENTS_hooks_rtk-hook-claude.sh.

The wrapper stands in front of `rtk hook claude` so that rtk's rewriting keeps
working everywhere EXCEPT the one case Claude Code's worktree-isolation guard
cannot verify: a bare `git …` rewritten to `rtk git …`. The guard reads the
post-rewrite command, sees a launcher it cannot look through, and refuses the
whole call — so a worktree-isolated agent loses git entirely.

Verified live (2026-09-29) from an isolated worktree, for `git status --short`:

    This agent is isolated in the worktree <path>, but this command runs rtk
    with a git command among its operands: ... so what it runs cannot be shown
    not to be git. Refusing to run it ...

Note it says "runs rtk" for a command typed as bare `git`: the hook rewrite
lands before the guard evaluates. Suppressing just that one rewrite inside an
isolation worktree restores plain git and costs nothing elsewhere.

Unlike block-prohibited-commands.py this wrapper is an OPTIMISER, not a guard:
every failure path must FAIL OPEN (exit 0, no stdout => the command runs
unchanged). The tests below pin that, because "fix" it to fail closed and every
Bash call dies whenever rtk hiccups.

rtk is stubbed rather than invoked for real: the wrapper only ever reads
`updatedInput.command` out of rtk's answer, so a canned stub pins the contract
exactly and keeps the suite hermetic on machines/CI without rtk installed.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

from _bash_hook import run_bash

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "ROOT_AGENTS_hooks_rtk-hook-claude.sh"
COMPANION = ROOT / "ROOT_AGENTS_hooks_rtk-hook-claude.py"

EXIT_ALLOW = 0

pytestmark = pytest.mark.skipif(
    sys.platform == "win32"
    or shutil.which("bash") is None
    or shutil.which("python3") is None,
    reason=(
        "Linux/WSL/CI only: the wrapper `exec python3`s its companion, but on "
        "native Windows `python3` resolves to the non-functional MS-Store stub "
        "(exit 49) and MSYS bash's pwd-derived paths aren't consumable by the "
        "Windows interpreter — not a harness-fixable issue"
    ),
)

# An rtk answer for a bare `git status`, captured verbatim from rtk 0.45.0.
RTK_GIT_REWRITE = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecisionReason": "RTK auto-rewrite",
        "updatedInput": {"command": "rtk git status"},
        "permissionDecision": "allow",
    }
}


def _rtk_stub(stdout: str, exit_code: int = 0) -> str:
    """A fake `rtk` that drains stdin and replays a canned answer."""
    return (
        "#!/bin/sh\n"
        "cat >/dev/null\n"
        f"printf '%s' {json.dumps(stdout)}\n"
        f"exit {exit_code}\n"
    )


def _path_without_rtk() -> str:
    """The real PATH with every entry that provides an `rtk` removed.

    Lets the fail-open test assert on a genuinely rtk-less environment without
    hand-building a PATH (which would also have to carry python3 and bash).
    """
    keep = [
        entry
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry and not (Path(entry) / "rtk").exists()
    ]
    return os.pathsep.join(keep)


def _run(
    payload: dict,
    *,
    tmp_path: Path,
    rtk_stub: str | None,
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Feed a PreToolUse payload to the wrapper; return (exit code, stdout)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    path = _path_without_rtk()
    if rtk_stub is not None:
        stub = bin_dir / "rtk"
        stub.write_text(rtk_stub)
        stub.chmod(0o755)
        path = f"{bin_dir}{os.pathsep}{path}"
    env = {**os.environ, "PATH": path}
    env.pop("RTK_HOOK_PERMISSION_DECISION", None)
    env.update(env_overrides or {})
    result = run_bash(
        HOOK,
        cwd=tmp_path,
        companions=(COMPANION,),
        input=json.dumps(payload),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode, result.stdout.strip()


def _payload(command: str, cwd: Path | str) -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
        "cwd": str(cwd),
    }


@pytest.fixture()
def isolation_worktree(tmp_path: Path) -> Path:
    """A path shaped like a Claude Code isolation worktree."""
    wt = tmp_path / "dotfiles" / ".claude" / "worktrees" / "agent-abc123"
    wt.mkdir(parents=True)
    return wt


@pytest.fixture()
def plain_repo(tmp_path: Path) -> Path:
    """An ordinary checkout — no isolation worktree in the path."""
    repo = tmp_path / "dotfiles"
    repo.mkdir(exist_ok=True)
    return repo


# --- The carve-out: git inside an isolation worktree ----------------------


def test_git_rewrite_is_suppressed_inside_isolation_worktree(
    tmp_path: Path, isolation_worktree: Path
) -> None:
    """The whole point: no rewrite emitted, so plain `git` reaches the guard."""
    code, out = _run(
        _payload("git status", isolation_worktree),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(RTK_GIT_REWRITE)),
    )
    assert code == EXIT_ALLOW
    assert out == ""


def test_flagged_rtk_git_rewrite_is_suppressed(
    tmp_path: Path, isolation_worktree: Path
) -> None:
    """rtk's own options may sit between the launcher and `git`."""
    answer = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"command": "rtk --ultra-compact git diff"},
            "permissionDecision": "allow",
        }
    }
    code, out = _run(
        _payload("git diff", isolation_worktree),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(answer)),
    )
    assert code == EXIT_ALLOW
    assert out == ""


# --- Everything else keeps rtk ---------------------------------------------


def test_git_rewrite_is_kept_outside_isolation_worktree(
    tmp_path: Path, plain_repo: Path
) -> None:
    """Ordinary sessions must lose nothing — git output is rtk's biggest win."""
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(RTK_GIT_REWRITE)),
    )
    assert code == EXIT_ALLOW
    emitted = json.loads(out)
    command = emitted["hookSpecificOutput"]["updatedInput"]["command"]
    assert command == "rtk git status"


def test_non_git_rewrite_survives_inside_isolation_worktree(
    tmp_path: Path, isolation_worktree: Path
) -> None:
    """The veto is git-only: ls/grep/rg/... stay compressed even when isolated."""
    answer = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"command": "rtk ls -la"},
            "permissionDecision": "allow",
        }
    }
    code, out = _run(
        _payload("ls -la", isolation_worktree),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(answer)),
    )
    assert code == EXIT_ALLOW
    emitted = json.loads(out)
    assert emitted["hookSpecificOutput"]["updatedInput"]["command"] == "rtk ls -la"


# --- Fail open (this is an optimiser, never a guard) -----------------------


def test_wrapper_is_transparent_when_rtk_declines(
    tmp_path: Path, plain_repo: Path
) -> None:
    """rtk prints nothing for commands it does not rewrite (eval, mise, ...)."""
    code, out = _run(
        _payload("eval echo hi", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(""),
    )
    assert code == EXIT_ALLOW
    assert out == ""


def test_wrapper_fails_open_when_rtk_missing(tmp_path: Path, plain_repo: Path) -> None:
    """No rtk on PATH must not break every Bash call in the session."""
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=None,
    )
    assert code == EXIT_ALLOW
    assert out == ""


def test_wrapper_fails_open_when_rtk_errors(tmp_path: Path, plain_repo: Path) -> None:
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub("boom", exit_code=1),
    )
    assert code == EXIT_ALLOW
    assert out == ""


def test_wrapper_fails_open_on_unparseable_rtk_output(
    tmp_path: Path, plain_repo: Path
) -> None:
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub("not json at all"),
    )
    assert code == EXIT_ALLOW
    assert out == ""


def test_wrapper_fails_open_on_unparseable_payload(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "rtk"
    stub.write_text(_rtk_stub(json.dumps(RTK_GIT_REWRITE)))
    stub.chmod(0o755)
    result = run_bash(
        HOOK,
        cwd=tmp_path,
        companions=(COMPANION,),
        input="}{ not json",
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{_path_without_rtk()}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == EXIT_ALLOW
    assert result.stdout.strip() == ""


def test_missing_cwd_falls_back_to_process_cwd(
    tmp_path: Path, isolation_worktree: Path
) -> None:
    """A payload without `cwd` still gets the carve-out when the process is in one."""
    payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "rtk"
    stub.write_text(_rtk_stub(json.dumps(RTK_GIT_REWRITE)))
    stub.chmod(0o755)
    result = run_bash(
        HOOK,
        cwd=isolation_worktree,
        companions=(COMPANION,),
        input=json.dumps(payload),
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{_path_without_rtk()}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == EXIT_ALLOW
    assert result.stdout.strip() == ""


# --- rtk's auto-approval (operator policy, one named constant) -------------


def test_permission_decision_is_stripped_by_default(
    tmp_path: Path, plain_repo: Path
) -> None:
    """Default STRIP: the rewrite is forwarded, the auto-approval is not.

    rtk answers `permissionDecision: "allow"` for everything it rewrites, which
    suppresses the normal permission prompt for most Bash traffic. Stripping it
    keeps the rewrite (the token saving) while leaving the permission decision
    to Claude Code.
    """
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(RTK_GIT_REWRITE)),
    )
    assert code == EXIT_ALLOW
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["updatedInput"]["command"] == "rtk git status"
    assert "permissionDecision" not in hso
    assert "permissionDecisionReason" not in hso


def test_permission_decision_is_kept_when_policy_is_keep(
    tmp_path: Path, plain_repo: Path
) -> None:
    """KEEP: rtk's answer is forwarded verbatim, auto-approval included."""
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(RTK_GIT_REWRITE)),
        env_overrides={"RTK_HOOK_PERMISSION_DECISION": "keep"},
    )
    assert code == EXIT_ALLOW
    hso = json.loads(out)["hookSpecificOutput"]
    assert hso["permissionDecision"] == "allow"
    assert hso["permissionDecisionReason"] == "RTK auto-rewrite"
