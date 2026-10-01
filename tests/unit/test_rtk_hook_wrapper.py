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
import shlex
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


def _path_without(*names: str) -> str:
    """The real PATH with every entry that provides one of `names` removed.

    Lets a test assert on a genuinely rtk-less environment without hand-building
    a PATH (which would also have to carry python3 and bash). `mise` is taken
    out too wherever the test means "there is no way to reach rtk at all": the
    wrapper asks mise when rtk is not on PATH, so leaving a real mise in place
    would let it find the real rtk and pass the test for the wrong reason.
    """
    keep = [
        entry
        for entry in os.environ.get("PATH", "").split(os.pathsep)
        if entry and not any((Path(entry) / name).exists() for name in names)
    ]
    return os.pathsep.join(keep)


def _executable(path: Path, script: str) -> Path:
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def _run(
    payload: dict,
    *,
    tmp_path: Path,
    rtk_stub: str | None,
    extra_bin: dict[str, str] | None = None,
    hide: tuple[str, ...] = ("rtk", "mise"),
    env_overrides: dict[str, str] | None = None,
) -> tuple[int, str]:
    """Feed a PreToolUse payload to the wrapper; return (exit code, stdout).

    `extra_bin` writes further stubs next to the rtk one (a fake `mise`, say);
    `hide` names the real executables PATH must not provide.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    path = _path_without(*hide)
    for name, script in (extra_bin or {}).items():
        _executable(bin_dir / name, script)
    if rtk_stub is not None:
        _executable(bin_dir / "rtk", rtk_stub)
    if rtk_stub is not None or extra_bin:
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


@pytest.mark.parametrize(
    ("typed", "rewrite"),
    [
        # git need not be the first command (found in review)
        ("FOO=1 git log", "FOO=1 rtk git log"),
        ("cd sub && git status", "cd sub && rtk git status"),
        ("ls && git status", "rtk ls && rtk git status"),
        # operators need no spaces around them
        ("cd sub&&git status", "cd sub&&rtk git status"),
        ("(git log)", "(rtk git log)"),
        # `#` inside a word is no comment in bash
        ("echo issue#1 && git status", "echo issue#1 && rtk git status"),
    ],
)
def test_a_git_rewrite_anywhere_in_the_command_is_suppressed(
    tmp_path: Path, isolation_worktree: Path, typed: str, rewrite: str
) -> None:
    answer = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"command": rewrite},
        }
    }
    code, out = _run(
        _payload(typed, isolation_worktree),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(answer)),
    )
    assert (code, out) == (EXIT_ALLOW, "")


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
    """Neither rtk nor a mise that could find one must break every Bash call."""
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=None,
    )
    assert code == EXIT_ALLOW
    assert out == ""


# --- Resolving rtk when PATH has none --------------------------------------
#
# A Claude Code session's environment is a snapshot taken when it started, so a
# tool mise installed afterwards is invisible to it, and after the hand-placed
# ~/.local/bin/rtk 0.45.0 is pruned a stale session has no rtk at all. mise
# answers from its own configuration rather than from PATH, so asking it is the
# difference between "rtk works in this session" and "no rewrites until the
# session is restarted".


def _mise_stub(rtk_path: Path | str, *, exit_code: int = 0, witness: Path) -> str:
    """A fake `mise` that answers `which rtk`, and records that it was asked."""
    return (
        "#!/bin/sh\n"
        f"printf 'asked %s\\n' \"$*\" >> {json.dumps(str(witness))}\n"
        f'[ "$1" = which ] || exit 1\n'
        f"printf '%s\\n' {json.dumps(str(rtk_path))}\n"
        f"exit {exit_code}\n"
    )


def test_rtk_absent_from_path_is_resolved_through_mise(
    tmp_path: Path, plain_repo: Path
) -> None:
    rtk = _executable(tmp_path / "mise-rtk", _rtk_stub(json.dumps(RTK_GIT_REWRITE)))
    witness = tmp_path / "mise-was-asked"
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=None,
        extra_bin={"mise": _mise_stub(rtk, witness=witness)},
    )
    assert code == EXIT_ALLOW
    assert witness.exists(), "the wrapper never asked mise"
    # The rewrite landed, which it could not have done from PATH alone. Outside
    # an isolation worktree the git rewrite is kept, minus the auto-approval.
    answer = json.loads(out)["hookSpecificOutput"]
    # The shell that runs the rewrite has the same PATH, without rtk: a bare
    # `rtk git status` would fail with "rtk: command not found" (seen live on
    # Windows, where it broke every rewritable Bash call), so the rewrite
    # names the copy mise found.
    assert (
        answer["updatedInput"]["command"] == f"{shlex.quote(rtk.as_posix())} git status"
    )
    assert "permissionDecision" not in answer


@pytest.mark.parametrize(
    ("typed", "rewrite", "expected"),
    [
        ("rtk gain", "rtk gain", "{L} gain"),
        ("cat README.md", "rtk read README.md", "{L} read README.md"),
        # Anything but the plain `rtk <command>` shape is left unrewritten: the
        # typed command runs as it is. Finding the launchers in compound shell
        # needs a shell parser (quotes, $( ), comments, heredocs, line
        # continuations, arithmetic, redirections: all found in review), and a
        # missed one fails with "command not found" while no rewrite never does.
        ("cat rtk read", "rtk read rtk read", None),
        ("git status && ls", "rtk git status && rtk ls", None),
        ("FOO=1 git log", "FOO=1 rtk git log", None),
        ('git commit -m "a; rtk b"', 'rtk git commit -m "a; rtk b"', None),
        ("echo x | grep x", "echo x | rtk grep x", None),
    ],
)
def test_a_mise_rtk_rewrite_is_kept_only_in_the_plain_shape(
    tmp_path: Path, plain_repo: Path, typed: str, rewrite: str, expected: str | None
) -> None:
    answer = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"command": rewrite},
        }
    }
    rtk = _executable(tmp_path / "mise-rtk", _rtk_stub(json.dumps(answer)))
    code, out = _run(
        _payload(typed, plain_repo),
        tmp_path=tmp_path,
        rtk_stub=None,
        extra_bin={"mise": _mise_stub(rtk, witness=tmp_path / "asked")},
    )
    assert code == EXIT_ALLOW
    if expected is None:
        assert out == ""
        return
    command = json.loads(out)["hookSpecificOutput"]["updatedInput"]["command"]
    assert command == expected.replace("{L}", shlex.quote(rtk.as_posix()))


def test_an_rtk_on_path_keeps_the_bare_launcher(
    tmp_path: Path, plain_repo: Path
) -> None:
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(RTK_GIT_REWRITE)),
    )
    assert code == EXIT_ALLOW
    assert json.loads(out)["hookSpecificOutput"]["updatedInput"]["command"] == (
        "rtk git status"
    )


def test_an_rtk_on_path_wins_and_mise_is_never_asked(
    tmp_path: Path, plain_repo: Path
) -> None:
    """PATH first, always. Preferring mise's copy would override whatever the
    operator deliberately put in front of it, and when mise's own config is
    stale its answer is the WORSE one -- measured: a stale config made
    `mise x -- rtk` resolve to the 0.45.0 shadow."""
    witness = tmp_path / "mise-was-asked"
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(RTK_GIT_REWRITE)),
        extra_bin={"mise": _mise_stub("/nowhere/rtk", witness=witness)},
    )
    assert code == EXIT_ALLOW
    assert not witness.exists(), "mise was asked although rtk was on PATH"
    assert json.loads(out)["hookSpecificOutput"]["updatedInput"]["command"] == (
        "rtk git status"
    )


def test_a_mise_that_cannot_find_rtk_still_fails_open(
    tmp_path: Path, plain_repo: Path
) -> None:
    """`mise which rtk` exits non-zero when the tool is not active in this
    directory -- which is exactly what a stale live config produces."""
    witness = tmp_path / "mise-was-asked"
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=None,
        extra_bin={"mise": _mise_stub("", exit_code=1, witness=witness)},
    )
    assert code == EXIT_ALLOW
    assert out == ""
    assert witness.exists()


def test_a_mise_answer_that_is_not_executable_fails_open(
    tmp_path: Path, plain_repo: Path
) -> None:
    witness = tmp_path / "mise-was-asked"
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=None,
        extra_bin={"mise": _mise_stub(tmp_path / "does-not-exist", witness=witness)},
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
    stub.write_text(_rtk_stub(json.dumps(RTK_GIT_REWRITE)), encoding="utf-8")
    stub.chmod(0o755)
    result = run_bash(
        HOOK,
        cwd=tmp_path,
        companions=(COMPANION,),
        input="}{ not json",
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{_path_without('rtk', 'mise')}",
        },
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
    stub.write_text(_rtk_stub(json.dumps(RTK_GIT_REWRITE)), encoding="utf-8")
    stub.chmod(0o755)
    result = run_bash(
        HOOK,
        cwd=isolation_worktree,
        companions=(COMPANION,),
        input=json.dumps(payload),
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{_path_without('rtk', 'mise')}",
        },
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


def test_only_the_rewrite_is_forwarded_whatever_rtk_adds(
    tmp_path: Path, plain_repo: Path
) -> None:
    """A later rtk may approve some other way (the legacy top-level
    `decision: approve`, say). The wrapper forwards the rewrite and nothing
    else, so no field rtk adds can turn an optimiser into an approver."""
    answer = {
        "decision": "approve",
        "hookSpecificOutput": {
            **RTK_GIT_REWRITE["hookSpecificOutput"],
            "additionalContext": "rtk says hi",
        },
    }
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(answer)),
    )
    assert code == EXIT_ALLOW
    assert json.loads(out) == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"command": "rtk git status"},
        }
    }


def test_an_answer_without_a_rewrite_is_dropped(
    tmp_path: Path, plain_repo: Path
) -> None:
    answer = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }
    code, out = _run(
        _payload("git status", plain_repo),
        tmp_path=tmp_path,
        rtk_stub=_rtk_stub(json.dumps(answer)),
    )
    assert (code, out) == (EXIT_ALLOW, "")


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
