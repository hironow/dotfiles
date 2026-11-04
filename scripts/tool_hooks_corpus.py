#!/usr/bin/env python3
"""Write the corpora the agent-hook binary's rtk and formatter hooks are
tested against: tools/agent-hooks/internal/toolhookcorpus/{rtk,formatter}.jsonl.

The references are the old hook scripts, until the agent-hook plan's last PR
removes them (docs/plan/agent-hooks-go.md): the rtk hooks
(ROOT_AGENTS_hooks_rtk-hook-{claude,codex}.{sh,py}) and the formatter
(ROOT_AGENTS_hooks_format-after-edit.sh). This runs each scenario through each
script, as Claude Code and Codex run it today, in a temporary root built from
scratch: fake rtk, mise, uv, and gofmt programs (written here, in Python), the
scenario's files and links, and an environment that inherits nothing. It
records what the script did, every program it ran (with argv, stdin, cwd, and
the environment the program saw), and what the binary must do instead
(expectedGo), which it works out itself, never from Go.

Each run gets a difference ID, or none (each derived from the legacy run and
the scenario, and checked again by tests/unit/test_tool_hooks_corpus.py):

- none: the binary does exactly what the script did.
- unreadable: the payload is not one JSON value. rtk and the formatter fail
  open: the binary passes silently and runs nothing.
- reference-limit: a base scenario's payload plus an unused 4,301-digit
  integer, which Claude's rtk script cannot read. The binary answers as for
  the base.
- path-relative: the script ran a program found through a relative or empty
  PATH entry. The binary never runs one: it passes silently.
- rtk-answer-unreadable: rtk's answer is not one JSON value. The script may
  still forward it; the binary passes.
- nul-warning: the formatter's stderr holds bash's warning that a command
  substitution dropped a NUL. The binary writes only the notices.
- pass-diagnostic: the formatter printed jq's errors (a payload jq cannot
  index) and nothing else. The binary is silent.

The fakes: only rtk reads its stdin (the payload). mise, uv, and gofmt never
read theirs: in the formatter's loop they inherit the pipe holding the paths
still to come, and the real tools do not read it.

The environment: PATH is the scenario's entries, then @ROOT@/sys-bin, which
links bash (5 or later: bash 3.2 prints no NUL warning), jq, sed, grep, cat,
dirname, and python3 and python (this interpreter: Python 3.14, as the command
guard corpus). HOME is @ROOT@/home; LC_ALL=C.UTF-8; Python's stdin is strict
UTF-8 with its default 4,300-digit integer limit; AGENT_HOOK_PROBE shows that
the programs inherit the environment. RTK_HOOK_PERMISSION_DECISION is never
set: the strip is the policy.

Run `just tool-hooks-corpus` after changing one of these scripts or their
tests. This is Python, not Go, because it drives the script references; it
goes with them.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

import command_guard_corpus
import hook_payload_corpus
import old_script_fixes

ROOT = Path(__file__).resolve().parents[1]
CORPUS_DIR = ROOT / "tools/agent-hooks/internal/toolhookcorpus"
CORPORA = {"rtk": CORPUS_DIR / "rtk.jsonl", "formatter": CORPUS_DIR / "formatter.jsonl"}
PLACEHOLDER = "@ROOT@"
HARNESSES = ("claude", "codex")
# Each hook's scripts, the one run first.
SCRIPTS = {
    ("rtk", "claude"): (
        "ROOT_AGENTS_hooks_rtk-hook-claude.sh",
        "ROOT_AGENTS_hooks_rtk-hook-claude.py",
    ),
    ("rtk", "codex"): (
        "ROOT_AGENTS_hooks_rtk-hook-codex.sh",
        "ROOT_AGENTS_hooks_rtk-hook-codex.py",
    ),
    ("formatter", "claude"): ("ROOT_AGENTS_hooks_format-after-edit.sh",),
    ("formatter", "codex"): ("ROOT_AGENTS_hooks_format-after-edit.sh",),
}
SYS_TOOLS = ("bash", "jq", "sed", "grep", "cat", "dirname")
PROBE = "agent-hook-probe"
RECORDED_ENV = ("PATH", "HOME", "AGENT_HOOK_PROBE")
# The rtk scripts' own timeouts; the formatter has none.
TIMEOUT_SECONDS = {"rtk": 10, "mise": 10}
DIFFERENCES = (
    "",
    "unreadable",
    "reference-limit",
    "path-relative",
    "rtk-answer-unreadable",
    "nul-warning",
    "pass-diagnostic",
)
NUL_WARNING = re.compile(
    r"(?:@ROOT@/hooks/)?ROOT_AGENTS_hooks_format-after-edit\.sh: line [0-9]+: "
    r"warning: command substitution: ignored null byte in input\n"
)
JQ_DIAGNOSTIC = re.compile(r"jq: [^\n]*\n")
# A run of them outside the notices is kept as one marker: how many lines
# jq writes, and their text, differ between jq versions (1.7.1 on Linux CI,
# 1.8.2 on macOS).
JQ_MARKER = "jq: <errors>\n"
NOTICE_HEAD = "ruff still reports issues in "
CLEAN_RUFF = "All checks passed"

# A synthetic payload's pieces. No token shapes: these corpora hold no key.
WORKTREE = "work/.claude/worktrees/agent-1"


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def unb64(text: str) -> bytes:
    return base64.b64decode(text)


def answer(
    stdout: str | bytes = b"", stderr: str | bytes = b"", exit_code: int = 0
) -> dict:
    """A fake program's answer: what it writes, in order, and its exit code."""
    out = stdout.encode() if isinstance(stdout, str) else stdout
    err = stderr.encode() if isinstance(stderr, str) else stderr
    return {"stdout": b64(out), "stderr": b64(err), "exit": exit_code}


@dataclass
class Scenario:
    """One environment and payload, run through the hook's script for each
    harness. Paths under the temporary root are written relative to it;
    @ROOT@ in a payload, a PATH entry, a link, or an answer is the root."""

    name: str
    hook: str
    payload: bytes
    path: list[str]
    fakes: dict[str, dict] = field(default_factory=dict)
    files: dict[str, str] = field(default_factory=dict)
    dirs: list[str] = field(default_factory=list)
    links: dict[str, str] = field(default_factory=dict)
    cwd: str = "work"
    harnesses: tuple[str, ...] = HARNESSES
    mirrors: tuple[str, ...] = ()
    base: str = ""


def doc(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


# ---- rtk scenarios ----

RTK = {"rtk": "path-a/rtk"}


def rtk_answer(command: str, *, allow: bool = True, **extra: object) -> str:
    """rtk's answer to `rtk hook claude|codex` for a rewrite, as rtk 1.1.0
    writes it: the tool input with the command replaced."""
    output: dict = {
        "hookEventName": "PreToolUse",
        "permissionDecisionReason": "RTK auto-rewrite",
        "updatedInput": {"command": command, "description": "d", "timeout": 5000},
    }
    if allow:
        output["permissionDecision"] = "allow"
    output.update(extra)
    return json.dumps({"hookSpecificOutput": output}, separators=(",", ":"))


def bash_payload(
    command: str, cwd: object = f"{PLACEHOLDER}/work", **more: object
) -> bytes:
    payload: dict = {
        "session_id": "s",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "d", "timeout": 5000},
    }
    if cwd is not None:
        payload["cwd"] = cwd
    payload.update(more)
    return doc(payload)


def rtk_on_path(rtk_stdout: str, *, exit_code: int = 0) -> dict:
    """The fakes of a scenario with rtk on PATH at path-a, answering this."""
    return {"path-a/rtk": answer(rtk_stdout, exit_code=exit_code)}


def rtk_scenarios() -> list[Scenario]:
    path = [f"{PLACEHOLDER}/path-a", f"{PLACEHOLDER}/mise-bin"]
    s: list[Scenario] = []

    def add(
        name: str,
        payload: bytes,
        fakes: dict,
        *,
        path_entries: list[str] | None = None,
        mirrors: tuple[str, ...] = (),
        dirs: list[str] | None = None,
        links: dict[str, str] | None = None,
        cwd: str = "work",
        base: str = "",
    ) -> None:
        s.append(
            Scenario(
                name=name,
                hook="rtk",
                payload=payload,
                path=path if path_entries is None else path_entries,
                fakes=fakes,
                dirs=dirs or [],
                links=links or {},
                cwd=cwd,
                mirrors=mirrors,
                base=base,
            )
        )

    add(
        "rewrite",
        bash_payload("git status"),
        rtk_on_path(rtk_answer("rtk git status")),
        mirrors=(
            "test_git_rewrite_is_kept_outside_isolation_worktree",
            "test_permission_decision_is_stripped_by_default",
            "test_an_rtk_on_path_keeps_the_bare_launcher",
        ),
    )
    add(
        "rewrite-without-allow",
        bash_payload("ls -la"),
        rtk_on_path(rtk_answer("rtk ls -la", allow=False)),
    )
    add(
        "no-rewrite",
        bash_payload("echo hi"),
        rtk_on_path(""),
        mirrors=("test_wrapper_is_transparent_when_rtk_declines",),
    )
    add(
        "rtk-exit-1",
        bash_payload("git status"),
        rtk_on_path(rtk_answer("rtk git status"), exit_code=1),
        mirrors=("test_wrapper_fails_open_when_rtk_errors",),
    )
    add(
        "rtk-not-json",
        bash_payload("git status"),
        rtk_on_path("not json"),
        mirrors=("test_wrapper_fails_open_on_unparseable_rtk_output",),
    )
    add("rtk-array", bash_payload("git status"), rtk_on_path("[1]"))
    add("rtk-empty-object", bash_payload("git status"), rtk_on_path("{}"))
    add(
        "rtk-hook-output-string",
        bash_payload("git status"),
        rtk_on_path('{"hookSpecificOutput":"x"}'),
    )
    add(
        "rtk-no-updated-input",
        bash_payload("git status"),
        rtk_on_path(
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
        ),
        mirrors=("test_an_answer_without_a_rewrite_is_dropped",),
    )
    add(
        "rtk-updated-input-without-command",
        bash_payload("git status"),
        rtk_on_path('{"hookSpecificOutput":{"updatedInput":{"description":"x"}}}'),
    )
    add(
        "rtk-command-not-a-string",
        bash_payload("git status"),
        rtk_on_path(
            '{"hookSpecificOutput":{"updatedInput":{"command":["rtk git status"]}}}'
        ),
    )
    add(
        "rtk-updated-input-not-an-object",
        bash_payload("git status"),
        rtk_on_path('{"hookSpecificOutput":{"updatedInput":"rtk git status"}}'),
    )
    add(
        "rtk-deny",
        bash_payload("ls"),
        rtk_on_path(
            rtk_answer(
                "rtk ls", permissionDecision="deny", permissionDecisionReason="denied"
            )
        ),
    )
    add(
        "rtk-ask",
        bash_payload("ls"),
        rtk_on_path(rtk_answer("rtk ls", permissionDecision="ask")),
    )
    add(
        "rtk-extra-members",
        bash_payload("git status"),
        rtk_on_path(
            json.dumps(
                {
                    "decision": "approve",
                    "continue": True,
                    "hookSpecificOutput": json.loads(
                        rtk_answer("rtk git status", additionalContext="rtk says hi")
                    )["hookSpecificOutput"],
                }
            )
        ),
        mirrors=("test_only_the_rewrite_is_forwarded_whatever_rtk_adds",),
    )
    add(
        "rtk-other-event-name",
        bash_payload("ls"),
        rtk_on_path(rtk_answer("rtk ls", hookEventName="PostToolUse")),
    )
    add(
        "rtk-null-event-name",
        bash_payload("ls"),
        rtk_on_path(rtk_answer("rtk ls", hookEventName=None)),
    )
    add(
        "rtk-numbers-kept",
        bash_payload("ls"),
        rtk_on_path(
            '{"hookSpecificOutput":{"hookEventName":"PreToolUse","updatedInput":'
            '{"command":"rtk ls","n":9007199254740993,"f":1.5e2}},"permissionDecision":"allow"}'
        ),
    )
    add(
        "rtk-answer-nan",
        bash_payload("ls"),
        rtk_on_path(
            '{"hookSpecificOutput":{"updatedInput":{"command":"rtk ls","x":NaN}}}'
        ),
    )
    add(
        "rtk-answer-duplicate-names",
        bash_payload("ls"),
        rtk_on_path(
            '{"hookSpecificOutput":{"updatedInput":{"command":"rtk ls","command":"rtk git status"}}}'
        ),
    )
    add(
        "rtk-answer-trailing-data",
        bash_payload("ls"),
        rtk_on_path(rtk_answer("rtk ls") + " x"),
    )
    add(
        "rtk-answer-non-ascii",
        bash_payload("ls é"),
        rtk_on_path(rtk_answer("rtk ls é ✓")),
    )
    s.append(
        Scenario(
            name="rtk-answer-invalid-utf8",
            hook="rtk",
            payload=bash_payload("ls"),
            path=path,
            fakes={
                "path-a/rtk": answer(
                    rtk_answer("rtk ls").encode().replace(b"rtk ls", b"rtk ls \xff")
                )
            },
        )
    )
    # The worktree veto (Claude only vetoes; Codex forwards).
    wt = f"{PLACEHOLDER}/{WORKTREE}"
    add(
        "veto",
        bash_payload("git status", cwd=wt),
        rtk_on_path(rtk_answer("rtk git status")),
        dirs=[WORKTREE],
        mirrors=("test_git_rewrite_is_suppressed_inside_isolation_worktree",),
    )
    add(
        "veto-flagged",
        bash_payload("git diff", cwd=wt),
        rtk_on_path(rtk_answer("rtk --ultra-compact git diff")),
        dirs=[WORKTREE],
        mirrors=("test_flagged_rtk_git_rewrite_is_suppressed",),
    )
    for i, (typed, rewrite) in enumerate(
        [
            ("FOO=1 git log", "FOO=1 rtk git log"),
            ("cd sub && git status", "cd sub && rtk git status"),
            ("ls && git status", "rtk ls && rtk git status"),
            ("cd sub&&git status", "cd sub&&rtk git status"),
            ("(git log)", "(rtk git log)"),
            ("echo issue#1 && git status", "echo issue#1 && rtk git status"),
            ("git status", 'rtk "unbalanced git'),
            ("ls", "rtk #c\ngit status"),
        ]
    ):
        add(
            f"veto-anywhere-{i}",
            bash_payload(typed, cwd=wt),
            rtk_on_path(rtk_answer(rewrite)),
            dirs=[WORKTREE],
            mirrors=("test_a_git_rewrite_anywhere_in_the_command_is_suppressed",),
        )
    add(
        "worktree-keeps-other-rewrites",
        bash_payload("ls -la", cwd=wt),
        rtk_on_path(rtk_answer("rtk ls -la")),
        dirs=[WORKTREE],
        mirrors=("test_non_git_rewrite_survives_inside_isolation_worktree",),
    )
    add(
        "veto-from-process-cwd",
        bash_payload("git status", cwd=None),
        rtk_on_path(rtk_answer("rtk git status")),
        dirs=[WORKTREE],
        cwd=WORKTREE,
        mirrors=("test_missing_cwd_falls_back_to_process_cwd",),
    )
    add(
        "payload-cwd-plain-process-cwd-worktree",
        bash_payload("git status"),
        rtk_on_path(rtk_answer("rtk git status")),
        dirs=[WORKTREE],
        cwd=WORKTREE,
    )
    add(
        "payload-cwd-worktree-process-cwd-plain",
        bash_payload("git status", cwd=wt),
        rtk_on_path(rtk_answer("rtk git status")),
        dirs=[WORKTREE],
    )
    for name, value in [
        ("zero", 0),
        ("empty-string", ""),
        ("empty-array", []),
        ("empty-object", {}),
        ("false", False),
        ("null", None),
        ("one", 1),
        ("array", [wt]),
        ("true", True),
    ]:
        payload = json.loads(bash_payload("git status", cwd=None))
        payload["cwd"] = value
        add(
            f"cwd-{name}",
            doc(payload),
            rtk_on_path(rtk_answer("rtk git status")),
            dirs=[WORKTREE],
            cwd=WORKTREE,
        )
    # Where rtk is found.
    mise_rtk = "mise/installs/rtk/rtk"
    mise_answers = {
        "mise-bin/mise": answer(f"{PLACEHOLDER}/{mise_rtk}\n"),
        mise_rtk: answer(rtk_answer("rtk read a.txt")),
    }
    add(
        "mise-only",
        bash_payload("cat a.txt"),
        mise_answers,
        mirrors=(
            "test_rtk_absent_from_path_is_resolved_through_mise",
            "test_mises_rtk_is_named_in_a_plain_rewrite",
        ),
    )
    add(
        "mise-only-not-plain",
        bash_payload("ls && git status"),
        {
            "mise-bin/mise": answer(f"{PLACEHOLDER}/{mise_rtk}\n"),
            mise_rtk: answer(rtk_answer("rtk ls && rtk git status")),
        },
        mirrors=(
            "test_a_mise_rtk_rewrite_is_kept_only_in_the_plain_shape",
            "test_mises_rtk_drops_any_other_rewrite",
        ),
    )
    spaced = "mise dir/rtk"
    add(
        "mise-only-spaced-path",
        bash_payload("ls"),
        {
            "mise-bin/mise": answer(f"{PLACEHOLDER}/{spaced}\n"),
            spaced: answer(rtk_answer("rtk ls")),
        },
    )
    add(
        "mise-fails",
        bash_payload("ls"),
        {"mise-bin/mise": answer("", "mise: rtk not found\n", 1)},
        mirrors=("test_a_mise_that_cannot_find_rtk_still_fails_open",),
    )
    add("mise-empty", bash_payload("ls"), {"mise-bin/mise": answer("\n")})
    s.append(
        Scenario(
            name="mise-not-executable",
            hook="rtk",
            payload=bash_payload("ls"),
            path=path,
            fakes={"mise-bin/mise": answer(f"{PLACEHOLDER}/plain/rtk\n")},
            files={"plain/rtk": "not a program\n"},
            mirrors=("test_a_mise_answer_that_is_not_executable_fails_open",),
        )
    )
    add(
        "no-rtk",
        bash_payload("ls"),
        {},
        mirrors=("test_wrapper_fails_open_when_rtk_missing",),
    )
    add(
        "rtk-on-path-and-through-mise",
        bash_payload("ls"),
        {
            "path-a/rtk": answer(rtk_answer("rtk ls")),
            "mise-bin/mise": answer(f"{PLACEHOLDER}/{mise_rtk}\n"),
            mise_rtk: answer(rtk_answer("rtk git status")),
        },
        mirrors=(
            "test_an_rtk_on_path_wins_and_mise_is_never_asked",
            "test_the_real_binary_is_preferred_and_a_shim_never_used",
        ),
    )
    add(
        "rtk-on-path-in-shims",
        bash_payload("ls"),
        {"shims/rtk": answer(rtk_answer("rtk ls"))},
        path_entries=[f"{PLACEHOLDER}/shims", f"{PLACEHOLDER}/mise-bin"],
    )
    # PATH entries the kernel resolves: link/.. goes through the link.
    add(
        "path-through-a-link",
        bash_payload("ls"),
        {
            "outside/bin/rtk": answer(rtk_answer("rtk ls")),
            "inside/bin/rtk": answer(rtk_answer("rtk git status")),
        },
        path_entries=[f"{PLACEHOLDER}/inside/link/../bin"],
        dirs=["outside/deep"],
        links={"inside/link": f"{PLACEHOLDER}/outside/deep"},
    )
    add(
        "path-relative-rtk",
        bash_payload("ls"),
        {"work/rtk": answer(rtk_answer("rtk ls"))},
        path_entries=["", f"{PLACEHOLDER}/mise-bin"],
    )
    add(
        "path-relative-mise",
        bash_payload("ls"),
        {
            "work/mise": answer(f"{PLACEHOLDER}/{mise_rtk}\n"),
            mise_rtk: answer(rtk_answer("rtk ls")),
        },
        path_entries=[""],
    )
    # Odd payloads.
    add("payload-root-array", b"[1]", rtk_on_path(rtk_answer("rtk ls")))
    add("payload-root-string", b'"git status"', rtk_on_path(rtk_answer("rtk ls")))
    add(
        "payload-other-tool",
        doc(
            {
                "tool_name": "Write",
                "tool_input": {"command": "git status"},
                "cwd": f"{PLACEHOLDER}/work",
            }
        ),
        rtk_on_path(rtk_answer("rtk git status")),
    )
    add(
        "payload-unreadable-nan",
        bash_payload("git status").replace(b'"timeout":5000', b'"timeout":NaN'),
        rtk_on_path(rtk_answer("rtk git status")),
        mirrors=("test_wrapper_fails_open_on_unparseable_payload",),
    )
    add(
        "payload-unreadable-garbage",
        b"not json",
        rtk_on_path(rtk_answer("rtk git status")),
    )
    add(
        "payload-crlf-whitespace",
        bash_payload("git status").replace(b",", b",\r\n"),
        rtk_on_path(rtk_answer("rtk git status")),
    )
    base = bash_payload("git status")
    add("base-limits", base, rtk_on_path(rtk_answer("rtk git status")))
    for digits in (4300, 4301):
        add(
            f"integer-{digits}-digits",
            hook_payload_corpus.with_member(base, b'"x":' + b"9" * digits),
            rtk_on_path(rtk_answer("rtk git status")),
            base="base-limits",
        )
    return s


# ---- formatter scenarios ----

UV = {"uv-bin/uv": None}  # marker: a uv fake with per-path checks


def uv_fake(checks: dict[str, dict] | None = None) -> dict:
    """A fake uv: `ruff format` and `ruff check --fix` answer nothing; `ruff
    check <p>` answers checks[p], else All checks passed."""
    return {
        "default": answer(),
        "checks": checks or {},
        "clean": answer("All checks passed!\n"),
    }


def edit_payload(file_path: object) -> bytes:
    return doc(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": file_path, "content": "x"},
            "tool_response": {},
        }
    )


def patch_payload(patch: str) -> bytes:
    return doc(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "apply_patch",
            "tool_input": {"command": patch},
            "tool_response": "ok",
        }
    )


def formatter_scenarios() -> list[Scenario]:
    path = [f"{PLACEHOLDER}/uv-bin", f"{PLACEHOLDER}/go-bin"]
    gofmt = {"go-bin/gofmt": answer()}
    s: list[Scenario] = []

    def add(
        name: str,
        payload: bytes,
        *,
        checks: dict | None = None,
        uv: bool = True,
        go: bool = True,
        fakes: dict | None = None,
        files: dict[str, str] | None = None,
        dirs: list[str] | None = None,
        links: dict[str, str] | None = None,
        path_entries: list[str] | None = None,
        mirrors: tuple[str, ...] = (),
    ) -> None:
        all_fakes = dict(fakes or {})
        if uv:
            all_fakes["uv-bin/uv"] = uv_fake(checks)
        if go:
            all_fakes.update(gofmt)
        s.append(
            Scenario(
                name=name,
                hook="formatter",
                payload=payload,
                path=path if path_entries is None else path_entries,
                fakes=all_fakes,
                files={"work/a.py": "x = 1\n", "work/b.go": "package b\n"}
                | (files or {}),
                dirs=dirs or [],
                links=links or {},
                mirrors=mirrors,
            )
        )

    issues = answer("a.py:1:1: F401 unused\nFound 1 error.\n", exit_code=1)
    # fixed-one-path (scripts/old_script_fixes.py): the old formatter read
    # each line of file_path, NULs and trailing newlines dropped, and so
    # formatted b.go, which none of these calls wrote.
    add(
        "fix-one-path-newline-inside",
        edit_payload(f"{PLACEHOLDER}/work/nowhere\n{PLACEHOLDER}/work/b.go"),
    )
    add("fix-one-path-trailing-newline", edit_payload("b.go\n"))
    add("fix-one-path-nul", edit_payload("b.\u0000go"))
    add(
        "fix-one-path-newline-in-a-go-name",
        edit_payload("a\nb.go"),
        files={"work/a\nb.go": "package a\n"},
    )
    add(
        "py-clean",
        edit_payload("a.py"),
        mirrors=("test_python_edit_formats_only_the_edited_file",),
    )
    add("py-absolute", edit_payload(f"{PLACEHOLDER}/work/a.py"))
    add("py-issues", edit_payload("a.py"), checks={"a.py": issues})
    add(
        "py-issues-on-both-streams",
        edit_payload("a.py"),
        checks={
            "a.py": answer(
                "a.py:1:1: F401 unused\n", "warning: deprecated setting\n", 1
            )
        },
    )
    add("py-empty-output", edit_payload("a.py"), checks={"a.py": answer()})
    add(
        "py-nul-clean",
        edit_payload("a.py"),
        checks={"a.py": answer(b"All checks passed!\x00\n")},
    )
    add(
        "py-nul-issues",
        edit_payload("a.py"),
        checks={"a.py": answer(b"bad\x00 line\n", exit_code=1)},
    )
    warning = "ROOT_AGENTS_hooks_format-after-edit.sh: line 38: warning: command substitution: ignored null byte in input"
    add(
        "py-nul-rebuilds-the-warning-text",
        edit_payload("a.py"),
        checks={
            "a.py": answer(
                b"\x00".join(c.encode() for c in warning) + b"\nreal issue\n",
                exit_code=1,
            )
        },
    )
    add(
        "py-notice-body-looks-like-jq",
        edit_payload("a.py"),
        checks={"a.py": answer("jq: ordinary notice body\n", exit_code=1)},
    )
    add(
        "py-trailing-newlines",
        edit_payload("a.py"),
        checks={"a.py": answer("issue\n\n\n", exit_code=1)},
    )
    add("py-no-uv", edit_payload("a.py"), uv=False)
    add(
        "go",
        edit_payload("b.go"),
        mirrors=("test_go_edit_formats_only_the_edited_file",),
    )
    add("go-no-gofmt", edit_payload("b.go"), go=False)
    for suffix in (".ts", ".tsx", ".js", ".jsx"):
        add(
            f"no-formatter-{suffix[1:]}",
            edit_payload(f"component{suffix}"),
            files={f"work/component{suffix}": "export {}\n"},
            mirrors=("test_ts_js_edit_never_runs_project_wide_format",),
        )
    add("missing-file", edit_payload("gone.py"))
    add("directory", edit_payload("pkg.py"), dirs=["work/pkg.py"])
    add("symlink-to-a-file", edit_payload("link.py"), links={"work/link.py": "a.py"})
    add(
        "symlink-to-nothing",
        edit_payload("dangling.py"),
        links={"work/dangling.py": "nowhere.py"},
    )
    add(
        "spaces-in-the-path",
        edit_payload("a b.py"),
        files={"work/a b.py": "x = 1\n"},
        checks={"a b.py": issues},
    )
    add("two-paths-in-one-field", edit_payload("a.py\nb.go"))
    add("nul-in-the-path", edit_payload("a.\u0000py"))
    add("file-path-zero", edit_payload(0), files={"work/0": "x\n"})
    add("file-path-array", edit_payload(["a.py"]))
    add(
        "file-path-empty-falls-back-to-the-patch",
        doc(
            {
                "tool_input": {
                    "file_path": "",
                    "command": "*** Begin Patch\n*** Add File: a.py\n+x\n*** End Patch\n",
                }
            }
        ),
    )
    patch = (
        "*** Begin Patch\n*** Update File: a.py\n@@\n-x=1\n+x = 1\n*** Add File: b.go\n+package b\n"
        "*** Delete File: gone.py\n*** Update File: c.py\n*** Move to: d.py\n*** End Patch\n"
    )
    add(
        "patch",
        patch_payload(patch),
        files={"work/d.py": "y = 2\n"},
        checks={"d.py": issues},
        mirrors=("test_a_codex_patch_formats_each_file_it_writes",),
    )
    add("patch-crlf", patch_payload(patch.replace("\n", "\r\n")))
    add(
        "every-file-of-a-patch",
        patch_payload(
            "*** Begin Patch\n*** Add File: a.py\n*** Add File: b.go\n*** Add File: c.py\n*** Add File: e.go\n*** End Patch\n"
        ),
        files={"work/c.py": "z = 3\n", "work/e.go": "package e\n"},
        checks={"c.py": issues},
    )
    add("root-array", b"[]")
    add("tool-input-string", doc({"tool_input": "a.py"}))
    add(
        "unreadable-nan",
        edit_payload("a.py").replace(b'"content":"x"', b'"content":NaN'),
    )
    add(
        "path-relative-uv",
        edit_payload("a.py"),
        uv=False,
        path_entries=["", f"{PLACEHOLDER}/go-bin"],
        fakes={"work/uv": uv_fake()},
    )
    return s


# ---- the environment ----


def require_the_pinned_python() -> None:
    have = unicodedata.unidata_version
    if have != command_guard_corpus.PYTHON_UNICODE:
        msg = (
            f"this Python has Unicode {have}; the corpus follows "
            f"{command_guard_corpus.PYTHON_UNICODE} (Python 3.14)"
        )
        raise SystemExit(msg)


def sys_tools() -> dict[str, str]:
    """The system programs the scripts need, by name; bash must be 5 or later."""
    found = {}
    for name in SYS_TOOLS:
        program = shutil.which(name)
        if program is None:
            raise SystemExit(f"the tool-hooks corpus needs {name} on PATH")
        found[name] = program
    major = subprocess.run(
        [found["bash"], "-c", "echo ${BASH_VERSINFO[0]}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    if int(major) < 5:
        raise SystemExit(
            f"the tool-hooks corpus needs bash 5 or later (bash 3.2 prints no NUL warning); found {major}"
        )
    return found


FAKE = """#!{python}
import json, os, sys
ROOT = {root!r}
LABEL = {label!r}
READS_STDIN = {reads_stdin!r}
RECORDED_ENV = {recorded_env!r}

def main():
    with open(os.path.join(ROOT, "fakes.json"), encoding="utf-8") as config:
        rules = json.load(config)[LABEL]
    stdin = sys.stdin.buffer.read() if READS_STDIN else None
    chosen = rules.get("default") if "default" in rules else rules
    if "checks" in rules and "check" in sys.argv[1:] and "--fix" not in sys.argv[1:]:
        chosen = rules["checks"].get(sys.argv[-1], rules["clean"])
    record = {{
        "tool": LABEL,
        "argv": sys.argv,
        "stdin": None if stdin is None else stdin.decode("utf-8", "surrogateescape"),
        "cwd": os.getcwd(),
        "env": {{name: os.environ.get(name) for name in RECORDED_ENV}},
        "answer": chosen,
    }}
    with open(os.path.join(ROOT, "invocations.jsonl"), "a", encoding="utf-8") as log:
        log.write(json.dumps(record) + "\\n")
    import base64
    sys.stdout.buffer.write(base64.b64decode(chosen["stdout"]))
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(base64.b64decode(chosen["stderr"]))
    sys.stderr.buffer.flush()
    sys.exit(chosen["exit"])

main()
"""


def substitute(value: object, root: str) -> object:
    """A scenario value with @ROOT@ as the root."""
    if isinstance(value, str):
        return value.replace(PLACEHOLDER, root)
    if isinstance(value, list):
        return [substitute(v, root) for v in value]
    if isinstance(value, dict):
        return {
            k.replace(PLACEHOLDER, root): substitute(v, root) for k, v in value.items()
        }
    return value


def placeholder(value: object, root: str) -> object:
    """A recorded value with the root written @ROOT@."""
    if isinstance(value, str):
        return value.replace(root, PLACEHOLDER)
    if isinstance(value, list):
        return [placeholder(v, root) for v in value]
    if isinstance(value, dict):
        return {
            k.replace(root, PLACEHOLDER): placeholder(v, root) for k, v in value.items()
        }
    return value


def fake_rules(rule: dict, root: str) -> dict:
    """A fake's rules with the root in its answers."""

    def sub_answer(a: dict) -> dict:
        return a | {
            "stdout": b64(
                unb64(a["stdout"]).replace(PLACEHOLDER.encode(), root.encode())
            )
        }

    if "checks" in rule:
        return {
            "default": sub_answer(rule["default"]),
            "clean": sub_answer(rule["clean"]),
            "checks": {k: sub_answer(v) for k, v in rule["checks"].items()},
        }
    return sub_answer(rule)


def build(
    scenario: Scenario, tools: dict[str, str], fixes: frozenset[str] = frozenset()
) -> str:
    """The scenario's temporary root, physical, built from scratch, its hooks
    the old scripts with the named fixes made (scripts/old_script_fixes.py)."""
    root = str(Path(tempfile.mkdtemp(prefix="tool-hooks-")).resolve())
    for d in ["work", "home", "sys-bin", "hooks", *scenario.dirs]:
        Path(root, d).mkdir(parents=True, exist_ok=True)
    for name, program in tools.items():
        Path(root, "sys-bin", name).symlink_to(program)
    for name in ("python3", "python"):
        Path(root, "sys-bin", name).symlink_to(sys.executable)
    for link, target in scenario.links.items():
        Path(root, link).parent.mkdir(parents=True, exist_ok=True)
        Path(root, link).symlink_to(str(substitute(target, root)))
    for rel, content in scenario.files.items():
        Path(root, rel).parent.mkdir(parents=True, exist_ok=True)
        Path(root, rel).write_text(content, encoding="utf-8")
    rules = {}
    for label, rule in scenario.fakes.items():
        target = Path(root, label)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            FAKE.format(
                python=sys.executable,
                root=root,
                label=label,
                reads_stdin=PurePosixPath(label).name == "rtk",
                recorded_env=RECORDED_ENV,
            ),
            encoding="utf-8",
        )
        target.chmod(0o755)
        rules[label] = fake_rules(rule, root)
    Path(root, "fakes.json").write_text(json.dumps(rules), encoding="utf-8")
    for harness_scripts in {SCRIPTS[(scenario.hook, h)] for h in scenario.harnesses}:
        for script in harness_scripts:
            mine = [
                old_script_fixes.FIXES[name]
                for name in sorted(fixes)
                if old_script_fixes.FIXES[name].script == script
            ]
            target = Path(root, "hooks", script)
            shutil.copy(ROOT / script, target)
            if mine:
                target.write_text(
                    old_script_fixes.apply_fixes(
                        target.read_text(encoding="utf-8"), mine
                    ),
                    encoding="utf-8",
                )
    return root


def environment(scenario: Scenario, root: str) -> dict[str, str]:
    return {
        "PATH": ":".join(
            str(substitute(e, root)) for e in [*scenario.path, f"{PLACEHOLDER}/sys-bin"]
        ),
        "HOME": f"{root}/home",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8:strict",
        "PYTHONINTMAXSTRDIGITS": "4300",
        "AGENT_HOOK_PROBE": PROBE,
    }


def recorded(invocation: dict, root: str) -> dict:
    """A logged invocation with the root written @ROOT@, in its answer too."""
    found = placeholder(invocation, root)
    assert isinstance(found, dict)
    answered = invocation["answer"]
    found["answer"] = answered | {
        stream: b64(
            unb64(answered[stream]).replace(root.encode(), PLACEHOLDER.encode())
        )
        for stream in ("stdout", "stderr")
    }
    return found


def run_legacy(scenario: Scenario, harness: str, root: str) -> dict:
    """One legacy run: the script as the harness runs it today."""
    log = Path(root, "invocations.jsonl")
    log.unlink(missing_ok=True)
    script = Path(root, "hooks", SCRIPTS[(scenario.hook, harness)][0])
    done = subprocess.run(
        [str(Path(root, "sys-bin", "bash")), str(script)],
        input=scenario.payload.replace(PLACEHOLDER.encode(), root.encode()),
        env=environment(scenario, root),
        cwd=Path(root, scenario.cwd),
        capture_output=True,
        check=False,
    )
    invocations = (
        [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        if log.exists()
        else []
    )
    return {
        "exit": done.returncode,
        "stdout": done.stdout.decode("utf-8", "replace").replace(root, PLACEHOLDER),
        "stderr": done.stderr.decode("utf-8", "replace").replace(root, PLACEHOLDER),
        "invocations": [recorded(i, root) for i in invocations],
    }


# ---- the world the in-process fake answers from ----


def join_as_python(entry: str, name: str) -> str:
    """os.path.join(entry, name) for a name without a slash, spelled out: no
    pathlib, which would drop "." segments the kernel resolves."""
    if not entry or entry.endswith("/"):
        return entry + name
    return f"{entry}/{name}"


def search(entries: list[str], name: str, cwd: str) -> dict | None:
    """process.Search: the first entry where name is an executable
    non-directory, joined as os.path.join joins, relative entries from cwd."""
    for entry in entries:
        candidate = join_as_python(entry, name)
        resolved = Path(cwd, candidate)
        if resolved.exists() and os.access(resolved, os.X_OK) and not resolved.is_dir():
            return {"path": candidate, "relative": not entry.startswith("/")}
    return None


def formatter_paths(payload: bytes) -> list[str]:
    """The paths the formatter tests, read as the script reads them."""
    try:
        value = json.loads(payload)
    except ValueError:
        return []
    tool_input = value.get("tool_input") if isinstance(value, dict) else None
    if not isinstance(tool_input, dict):
        return []

    def subst(text: str) -> str:
        return text.replace("\x00", "").rstrip("\n")

    file_path = tool_input.get("file_path")
    if isinstance(file_path, str) and subst(file_path):
        return subst(file_path).split("\n")
    command = tool_input.get("command")
    if isinstance(command, str):
        patch = subst(command)
        if "*** Begin Patch" in patch:
            return [
                m.group(2)
                for line in patch.split("\n")
                if (
                    m := re.match(r"\*\*\* (Add File|Update File|Move to): (.*)$", line)
                )
            ]
    return []


def fixed_formatter_paths(payload: bytes) -> list[str]:
    """The paths the formatter with its bug fixed tests (fixed-one-path): a
    string file_path names one file, exactly as given; else as before."""
    try:
        value = json.loads(payload)
    except ValueError:
        return []
    tool_input = value.get("tool_input") if isinstance(value, dict) else None
    file_path = tool_input.get("file_path") if isinstance(tool_input, dict) else None
    if isinstance(file_path, str) and file_path:
        return [file_path]
    return formatter_paths(payload)


def world(scenario: Scenario, root: str) -> dict:
    """What the in-process fake Machine answers: lookups, executability, and
    regular files, evaluated on the real scenario root."""
    cwd = str(Path(root, scenario.cwd))
    entries = str(environment(scenario, root)["PATH"]).split(":")
    names = {"rtk", "mise", "uv", "gofmt"}
    lookups = {name: search(entries, name, cwd) for name in sorted(names)}
    executable: dict[str, bool] = {}
    unstartable: list[str] = []
    files: dict[str, bool] = {}
    for label, rule in scenario.fakes.items():
        if PurePosixPath(label).name != "mise":
            continue
        answered = unb64(fake_rules(rule, root)["stdout"]).decode("utf-8", "replace")
        candidate = answered.strip()
        if candidate:
            resolved = Path(cwd, candidate)
            executable[candidate] = os.access(resolved, os.X_OK)
            # A path that is not an executable file cannot be started:
            # running it fails, and the fake never logs it.
            if not (resolved.is_file() and os.access(resolved, os.X_OK)):
                unstartable.append(candidate)
    payload = scenario.payload.replace(PLACEHOLDER.encode(), root.encode())
    # The paths the old formatter tests, and those the fixed one tests.
    for path in formatter_paths(payload) + fixed_formatter_paths(payload):
        files[path] = bool(path) and "\x00" not in path and Path(cwd, path).is_file()
    found = placeholder(
        {
            "cwd": cwd,
            "lookups": lookups,
            "executable": executable,
            "unstartable": unstartable,
            "regularFiles": files,
        },
        root,
    )
    assert isinstance(found, dict)
    return found


# ---- expectedGo ----


def expected_invocation(invocation: dict) -> dict:
    """An invocation as the binary must run it. A fake is a script with a
    shebang, so its argv[0] is the path the caller gave execve (the kernel's
    view: inside/link/../bin/rtk stays unresolved), which is the path the
    binary must run. The argv[0] the caller chose is not observable this way;
    the launch tests pin it."""
    tool = PurePosixPath(invocation["tool"]).name
    args = invocation["argv"][1:]
    stdin = invocation["stdin"]
    return {
        "tool": invocation["tool"],
        "path": invocation["argv"][0],
        "args": args,
        "stdin": None
        if stdin is None
        else b64(stdin.encode("utf-8", "surrogateescape")),
        "timeoutSeconds": TIMEOUT_SECONDS.get(tool, 0),
        "combined": tool == "uv" and "check" in args and "--fix" not in args,
        "cwd": invocation["cwd"],
        "env": invocation["env"],
        "answer": invocation["answer"],
    }


def notices(invocations: list[dict]) -> list[str]:
    """The formatter's notices, built from the recorded output of each
    reported `ruff check` (stdout then stderr, as one pipe holds them)."""
    found = []
    for invocation in invocations:
        argv = invocation["argv"]
        if (
            PurePosixPath(invocation["tool"]).name != "uv"
            or "check" not in argv[1:]
            or "--fix" in argv[1:]
        ):
            continue
        output = (
            unb64(invocation["answer"]["stdout"])
            + unb64(invocation["answer"]["stderr"])
        ).decode("utf-8", "replace")
        output = output.replace("\x00", "").rstrip("\n")
        if output and CLEAN_RUFF not in output:
            found.append(f"{NOTICE_HEAD}{argv[-1]}:\n{output}\n")
    return found


def formatter_stderr_segments(
    stderr: str, expected: list[str]
) -> list[tuple[str, str]]:
    """Read the formatter's legacy stderr against its notices, from the start:
    each notice is taken whole where it comes, its body protected, and only
    outside the notices may a NUL warning or a jq error stand. Returns the
    segments as (kind, text), kind "notice", "warning", or "jq"; fails on
    anything else."""
    pos, queue, segments = 0, list(expected), []
    while pos < len(stderr):
        if queue and stderr.startswith(queue[0], pos):
            segments.append(("notice", queue[0]))
            pos += len(queue.pop(0))
        elif match := NUL_WARNING.match(stderr, pos):
            segments.append(("warning", match.group()))
            pos = match.end()
        elif match := JQ_DIAGNOSTIC.match(stderr, pos):
            segments.append(("jq", match.group()))
            pos = match.end()
        else:
            msg = f"unexpected formatter stderr at {pos}: {stderr[pos : pos + 80]!r}"
            raise ValueError(msg)
    if queue:
        msg = f"notices never written: {queue!r}"
        raise ValueError(msg)
    return segments


def read_formatter_stderr(stderr: str, expected: list[str]) -> tuple[bool, bool]:
    """(warned, jq_diagnostic) of the formatter's legacy stderr."""
    kinds = {kind for kind, _ in formatter_stderr_segments(stderr, expected)}
    return "warning" in kinds, "jq" in kinds


def relative_programs(legacy: dict, scenario: Scenario) -> bool:
    """Whether the script ran a fake installed under a relative PATH entry."""
    relative_dirs = {
        str(PurePosixPath(scenario.cwd, e))
        for e in scenario.path
        if not e.startswith("/") and not e.startswith(PLACEHOLDER)
    }
    return any(
        str(PurePosixPath(i["tool"]).parent) in relative_dirs
        for i in legacy["invocations"]
    )


NOTHING = {
    "exit": 0,
    "stdout": "",
    "stdoutJSON": False,
    "stderr": "",
    "invocations": [],
}


def check_derived(scenario: Scenario, base: Scenario) -> None:
    """Fail unless a derived scenario is its base (itself not derived) with one
    unused integer member added to the payload, in the same environment: only
    then may it take the base's expected behavior."""
    same = (
        base.hook,
        base.path,
        base.fakes,
        base.files,
        base.dirs,
        base.links,
        base.cwd,
        base.harnesses,
    )
    mine = (
        scenario.hook,
        scenario.path,
        scenario.fakes,
        scenario.files,
        scenario.dirs,
        scenario.links,
        scenario.cwd,
        scenario.harnesses,
    )
    prefix = base.payload[:-1] + b',"x":'
    digits = scenario.payload[len(prefix) : -1]
    if (
        base.base
        or same != mine
        or not base.payload.endswith(b"}")
        or not scenario.payload.startswith(prefix)
        or not scenario.payload.endswith(b"}")
        or not digits
        or set(digits) != {ord("9")}
    ):
        msg = (
            f"{scenario.name}: not its base {base.name} plus one unused integer member"
        )
        raise ValueError(msg)


def classify(
    scenario: Scenario, harness: str, legacy: dict, base: dict | None
) -> tuple[str, dict]:
    """A run's difference ID and the binary's expected behavior, from the
    legacy run, the scenario, and its base's run."""
    payload = scenario.payload
    if not hook_payload_corpus.readable(payload):
        return (
            "unreadable" if legacy != {**NOTHING, "invocations": []} else ""
        ), NOTHING
    if base is not None:
        # As for the base, except that rtk gets this scenario's own payload.
        expected = base["expectedGo"] | {
            "invocations": [
                i if i["stdin"] is None else i | {"stdin": b64(payload)}
                for i in base["expectedGo"]["invocations"]
            ]
        }
        return (
            "reference-limit"
            if legacy["exit"] != base["legacy"]["exit"]
            or legacy["stdout"] != base["legacy"]["stdout"]
            else ""
        ), expected
    if relative_programs(legacy, scenario):
        return "path-relative", NOTHING
    invocations = [expected_invocation(i) for i in legacy["invocations"]]
    if scenario.hook == "rtk":
        if legacy["exit"] != 0 or legacy["stderr"]:
            msg = f"{scenario.name} {harness}: the rtk script failed: {legacy!r}"
            raise ValueError(msg)
        rtk_runs = [
            i for i in legacy["invocations"] if PurePosixPath(i["tool"]).name == "rtk"
        ]
        expected = {
            "exit": 0,
            "stdout": legacy["stdout"],
            "stdoutJSON": bool(legacy["stdout"]),
            "stderr": "",
            "invocations": invocations,
        }
        if rtk_runs and not hook_payload_corpus.readable(
            unb64(rtk_runs[-1]["answer"]["stdout"])
        ):
            expected = expected | {"stdout": "", "stdoutJSON": False}
            return ("rtk-answer-unreadable" if legacy["stdout"] else ""), expected
        return "", expected
    found = notices(legacy["invocations"])
    warned, diagnostic = read_formatter_stderr(legacy["stderr"], found)
    if legacy["exit"] != 0 or legacy["stdout"]:
        msg = f"{scenario.name} {harness}: the formatter did not exit 0 silently: {legacy!r}"
        raise ValueError(msg)
    if diagnostic:
        assert not found and not invocations, scenario.name
        return "pass-diagnostic", NOTHING
    expected = {
        "exit": 0,
        "stdout": "",
        "stdoutJSON": False,
        "stderr": "".join(found),
        "invocations": invocations,
    }
    return ("nul-warning" if warned else ""), expected


# ---- the corpus ----


def legacy_record(scenario: Scenario, legacy: dict) -> dict:
    """What the corpus keeps of a legacy run. The rtk scripts' own stderr (a
    Python traceback) is kept as a flag. In the formatter's, each run of jq's
    errors outside the notices becomes one marker, since how many lines jq
    writes and their text differ between jq versions; the notices and bash's
    warnings stay as they are."""
    stderr = legacy["stderr"]
    if scenario.hook == "rtk":
        stderr = "<diagnostic>" if stderr else ""
    else:
        kept = []
        for kind, text in formatter_stderr_segments(
            stderr, notices(legacy["invocations"])
        ):
            if kind != "jq":
                kept.append(text)
            elif not kept or kept[-1] != JQ_MARKER:
                kept.append(JQ_MARKER)
        stderr = "".join(kept)
    return {
        "exit": legacy["exit"],
        "stdout": legacy["stdout"],
        "stderr": stderr,
        "invocations": legacy["invocations"],
    }


def render_scenario(
    scenario: Scenario, tools: dict[str, str], bases: dict[str, dict]
) -> dict:
    root = build(scenario, tools)
    try:
        the_world = world(scenario, root)
        runs = []
        for harness in scenario.harnesses:
            legacy = run_legacy(scenario, harness, root)
            base = None
            if scenario.base:
                base = next(
                    r for r in bases[scenario.base]["runs"] if r["harness"] == harness
                )
                old_script_fixes.refuse_a_base_that_needs_a_fix(
                    scenario.name, scenario.base, base
                )
            difference, expected = classify(scenario, harness, legacy, base)
            run = {
                "harness": harness,
                "difference": difference,
                "legacy": legacy_record(scenario, legacy),
            }
            fixes = hook_fixes(scenario.hook)
            if fixes and base is None:
                fixed_run = fixed_answer(scenario, harness, tools, frozenset(fixes))
                fixed_difference, fixed_expected = classify(
                    scenario, harness, fixed_run, None
                )
                # The fixed script is the reference: its noise always, and the
                # fixes it needs exactly when its answer differs.
                if (fixed_difference, fixed_expected) != (difference, expected):
                    needed: list[str] = []

                    def expected_with(
                        applied: frozenset[str],
                        harness=harness,
                        legacy_expected=expected,
                        fixed_expected=fixed_expected,
                        fixes=fixes,
                    ) -> dict:
                        if not applied:
                            return legacy_expected
                        if applied == frozenset(fixes):
                            return fixed_expected
                        return classify(
                            scenario,
                            harness,
                            fixed_answer(scenario, harness, tools, applied),
                            None,
                        )[1]

                    if fixed_expected != expected:
                        needed = old_script_fixes.needed(fixes, expected_with)
                    run["difference"] = old_script_fixes.difference(
                        needed, fixed_difference
                    )
                    run["fixed"] = legacy_record(scenario, fixed_run)
                    expected = fixed_expected
            run["expectedGo"] = expected
            runs.append(run)
        return {
            "name": scenario.name,
            "mirrors": list(scenario.mirrors),
            "stdin": b64(scenario.payload),
            "base": scenario.base,
            "environment": {
                "path": scenario.path,
                "fakes": scenario.fakes,
                "files": scenario.files,
                "dirs": scenario.dirs,
                "links": scenario.links,
                "cwd": scenario.cwd,
            },
            "world": the_world,
            "runs": runs,
        }
    finally:
        shutil.rmtree(root, ignore_errors=True)


def hook_fixes(hook: str) -> tuple[str, ...]:
    """The fixes of a hook's old scripts (scripts/old_script_fixes.py)."""
    scripts = {
        script for (h, _), names in SCRIPTS.items() if h == hook for script in names
    }
    return tuple(
        name for name, fix in old_script_fixes.FIXES.items() if fix.script in scripts
    )


def fixed_answer(
    scenario: Scenario, harness: str, tools: dict[str, str], fixes: frozenset[str]
) -> dict:
    """A run of the scenario on the old scripts with the named fixes, in a root
    of its own, so bash's warnings name the same @ROOT@/hooks/ path."""
    root = build(scenario, tools, fixes)
    try:
        return run_legacy(scenario, harness, root)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def render() -> dict[str, list[dict]]:
    """The corpus entries of each hook."""
    require_the_pinned_python()
    tools = sys_tools()
    corpora: dict[str, list[dict]] = {}
    for hook, scenarios in (
        ("rtk", rtk_scenarios()),
        ("formatter", formatter_scenarios()),
    ):
        names = [s.name for s in scenarios]
        assert len(names) == len(set(names)), f"{hook}: scenario names repeat"
        plain = [s for s in scenarios if not s.base]
        with ThreadPoolExecutor(max_workers=min(16, os.cpu_count() or 4)) as pool:
            rendered = dict(
                zip(
                    [s.name for s in plain],
                    pool.map(lambda s: render_scenario(s, tools, {}), plain),
                    strict=True,
                )
            )
        by_name = {s.name: s for s in scenarios}
        for s in scenarios:
            if s.base:
                check_derived(s, by_name[s.base])
                rendered[s.name] = render_scenario(s, tools, rendered)
        corpora[hook] = [rendered[s.name] for s in scenarios]
    return corpora


def main() -> None:
    for hook, entries in render().items():
        CORPORA[hook].write_text(
            "".join(json.dumps(e, ensure_ascii=True) + "\n" for e in entries),
            encoding="utf-8",
            newline="\n",
        )
        print(f"wrote {CORPORA[hook].relative_to(ROOT)} ({len(entries)} scenarios)")


if __name__ == "__main__":
    main()
