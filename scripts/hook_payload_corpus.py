#!/usr/bin/env python3
"""Write the payload corpus the agent-hook binary is tested against.

The references are the old hook scripts, until the agent-hook plan's last PR
removes them (docs/plan/agent-hooks-go.md): the command guard
(ROOT_AGENTS_hooks_block-prohibited-commands.sh and its Python companion), the
files guard, and the secrets guard. This runs every payload through every
guard the way each harness runs them today: Claude Code runs the script, and
Codex runs it through ROOT_AGENTS_hooks_guard-codex.sh. It records what each
run did, and what the binary must answer instead (expectedGo), which it works
out itself, never from Go.

Each run gets a difference ID, or none:

- none: the binary answers exactly as the script did.
- unreadable: stdin is not one JSON value, read strictly (RFC 8259, UTF-8,
  unique names, no unpaired surrogate, at most MAX_DEPTH levels). The binary
  blocks it with a fixed reason; the scripts each read their own extensions of
  JSON, and what they did is recorded.
- reference-limit: the payload is a base payload plus an unused member that a
  reference cannot read (an integer past Python's 4,300 digits). The binary
  answers as for the base.
- pass-diagnostic: the script passed, but exited non-zero or wrote something.
  The binary passes silently.
- nul-warning: the script blocked, and bash warned of a NUL byte, in the guard
  before its BLOCKED line or in guard-codex.sh. The binary writes the block
  without the warning.

The reference environment is fixed. Nothing is inherited but PATH:
LC_ALL=C.UTF-8, Python's stdin strict UTF-8 and its default 4,300-digit
integer limit, and Python 3.14 (Unicode 16.0, as the command guard corpus),
which the command guard's wrapper is made to pick. The files guard runs under each
basename(1) flavor the machine has (on macOS, gbasename gives GNU's).

tests/unit/test_hook_payload_corpus.py fails when the corpus is stale, and
the Go tests fail when the binary no longer answers as it says. Run
`just hook-payload-corpus` after changing a guard, its tests, or the Codex
adapter.

This is Python, not Go, because it drives the script references; it goes
with them.
"""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import command_guard_corpus
import file_guards_corpus
import old_script_fixes

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tools/agent-hooks/internal/guardcorpus/payloads.jsonl"
HARNESS_FIXTURES = ROOT / "tools/agent-hooks/harnesses"
# The scripts, run by these names from the repository root, so that bash's
# warnings name them the same way on every machine.
GUARDS = {
    "command-guard": "ROOT_AGENTS_hooks_block-prohibited-commands.sh",
    "files-guard": "ROOT_AGENTS_hooks_block-prohibited-files.sh",
    "secrets-guard": "ROOT_AGENTS_hooks_block-secrets.sh",
}
CODEX_ADAPTER = "ROOT_AGENTS_hooks_guard-codex.sh"
# The files guard's bugs the binary fixes (scripts/old_script_fixes.py).
FILES_FIXES = tuple(
    name
    for name, fix in old_script_fixes.FIXES.items()
    if fix.script == old_script_fixes.FILES_GUARD
)
HARNESSES = ("claude", "codex")
BLOCKED = "BLOCKED: "
UNREADABLE = (
    "agent-hook could not read the hook input as one JSON value, so no guard ran."
)
DIFFERENCES = ("", "unreadable", "reference-limit", "pass-diagnostic", "nul-warning")
# The binary reads at most this many levels of nesting (go-json's limit).
MAX_DEPTH = 10_000
# A longer stdin is stored as runs of one byte.
LONG_STDIN = 4096
# bash's warning when a command substitution drops a NUL byte. It names the
# script as run: the guard by its name (or ./ and its name, under
# guard-codex.sh), or guard-codex.sh itself. Anchoring on those names keeps a
# reason that only quotes the warning from being taken for one.
_SCRIPTS = "|".join(re.escape(name) for name in [*GUARDS.values(), CODEX_ADAPTER])
NUL_WARNING = (
    f"(?:\\./)?(?:{_SCRIPTS}): line [0-9]+: "
    "warning: command substitution: ignored null byte in input"
)
# In a guard the warnings come before the BLOCKED line, so only a leading run
# of them is taken.
LEADING_NUL_WARNINGS = re.compile(f"(?:{NUL_WARNING}\n)*")
# guard-codex.sh's own warnings on its stderr, when its $(...) drops a NUL
# from the guard's message.
ADAPTER_NUL_WARNINGS = re.compile(f"(?:{NUL_WARNING}\n)+")
# The guard's warnings inside a Codex deny reason, where newlines became spaces.
LEADING_NUL_WARNINGS_ONE_LINE = re.compile(f"(?:{NUL_WARNING} )*")

# A synthetic AWS-style key, built from pieces so this file holds no token.
KEY = "AKIA" + "Q" * 16
NPM_INSTALL = "n" + "pm install"
PATCH_YML = file_guards_corpus.patch("*** Add File: a.yml\n+x\n")
PATCH_KEY = file_guards_corpus.patch("*** Add File: a.txt\n+" + KEY + "\n")
BLOCK_ALL = {
    "tool_input": {"command": NPM_INSTALL, "file_path": "a.yml", "content": KEY}
}
HARMLESS = {"tool_input": {"command": "ls", "file_path": "a.yaml", "content": "plain"}}


@dataclass(frozen=True)
class Payload:
    """One stdin, and the base payload it adds an unused member to, if any."""

    name: str
    stdin: bytes
    base: str = ""


def doc(value: object) -> bytes:
    """A payload as a harness writes it: compact JSON in UTF-8."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def with_member(base: bytes, member: bytes) -> bytes:
    """The base object with one more member at its end."""
    assert base.endswith(b"}"), base
    return base[:-1] + b"," + member + b"}"


def test_payloads() -> list[Payload]:
    """Every input the guards' own tests use, wrapped as those tests wrap it."""
    commands = dict.fromkeys(command_guard_corpus.fixture_commands())
    tests = file_guards_corpus.fixtures()
    payloads = [
        Payload(f"test-command-{i:03d}", doc({"tool_input": {"command": command}}))
        for i, command in enumerate(commands)
    ]
    payloads += [
        Payload(
            f"test-patch-{i:03d}",
            doc({"tool_name": "apply_patch", "tool_input": {"command": patch}}),
        )
        for i, patch in enumerate(dict.fromkeys(tests["patch"]))
    ]
    payloads += [
        Payload(
            f"test-content-{i:03d}",
            doc({"tool_input": {"file_path": "config.py", "content": content}}),
        )
        for i, content in enumerate(dict.fromkeys(tests["content"]))
    ]
    return payloads


def fixture_payloads() -> list[Payload]:
    """The harness definitions' fixtures, byte for byte."""
    return [
        Payload(f"fixture-{harness}-{path.stem}", path.read_bytes())
        for harness in HARNESSES
        for path in sorted((HARNESS_FIXTURES / harness / "fixtures").glob("*.json"))
        if not path.name.endswith(".ir.json")
    ]


# Ways to make a payload unreadable, each applied to a payload that blocks in
# every guard and to one that passes in every guard.
UNREADABLE_VARIANTS: list[tuple[str, bytes]] = [
    ("nan", b'"x":NaN'),
    ("infinity", b'"x":Infinity'),
    ("minus-infinity", b'"x":-Infinity'),
    ("lowercase-nan", b'"x":nan'),
    ("duplicate-name", b'"x":1,"x":2'),
    ("duplicate-escaped-name", b'"x":1,"\\u0078":2'),
    ("unpaired-surrogate", b'"x":"\\ud800"'),
    ("reversed-surrogates", b'"x":"\\udc00\\ud800"'),
    ("invalid-utf8", b'"x":"\xff"'),
    ("raw-nul-in-string", b'"x":"a\x00b"'),
    ("raw-control-in-string", b'"x":"\x01"'),
    ("raw-tab-in-string", b'"x":"\t"'),
]


def unreadable_payloads() -> list[Payload]:
    payloads = []
    for base_name, base in (("block-all", doc(BLOCK_ALL)), ("harmless", doc(HARMLESS))):
        for name, member in UNREADABLE_VARIANTS:
            payloads.append(
                Payload(f"unreadable-{name}-{base_name}", with_member(base, member))
            )
        payloads += [
            Payload(
                f"unreadable-raw-nul-between-tokens-{base_name}", b"{\x00" + base[1:]
            ),
            Payload(f"unreadable-bom-{base_name}", b"\xef\xbb\xbf" + base),
            Payload(f"unreadable-trailing-data-{base_name}", base + b" x"),
            Payload(f"unreadable-two-documents-{base_name}", base + base),
        ]
    payloads += [
        Payload("unreadable-two-documents-mixed", doc(HARMLESS) + doc(BLOCK_ALL)),
        Payload("unreadable-empty", b""),
        Payload("unreadable-white-space", b" \n\t"),
        Payload("unreadable-not-json", b"hello"),
        Payload("unreadable-open-brace", b"{"),
        Payload(
            "unreadable-invalid-utf8-in-path",
            b'{"tool_input":{"file_path":"a\xff.yml"}}',
        ),
        Payload(
            "unreadable-raw-nul-in-path", b'{"tool_input":{"file_path":"a.\x00yml"}}'
        ),
        Payload(
            "unreadable-raw-tab-in-path", b'{"tool_input":{"file_path":"a\tb.yml"}}'
        ),
        Payload(
            "unreadable-unpaired-surrogate-in-command",
            b'{"tool_input":{"command":"' + NPM_INSTALL.encode() + b' \\ud800"}}',
        ),
    ]
    return payloads


# Values every candidate field takes, as JSON text.
TYPED_VALUES = [
    ("null", "null"),
    ("false", "false"),
    ("true", "true"),
    ("zero", "0"),
    ("negative", "-1"),
    ("huge", "1e400"),
    ("empty-string", '""'),
    ("newline", '"\\n"'),
    ("nul", '"\\u0000"'),
]
# The string each candidate field blocks with.
BLOCKING_STRINGS = {
    "command": NPM_INSTALL,
    "file_path": "a.yml",
    "content": KEY,
    "new_string": KEY,
    "new_source": "key = '" + KEY + "'",
}


def readable_payloads() -> list[Payload]:
    """Readable payloads of every odd shape the scripts read their own way."""
    payloads = [
        Payload(f"root-{name}", text.encode())
        for name, text in [
            ("array", "[1]"),
            ("empty-array", "[]"),
            ("string", '"x"'),
            ("number", "1"),
            ("null", "null"),
            ("true", "true"),
            ("empty-object", "{}"),
        ]
    ]
    payloads += [
        Payload(f"tool-input-{name}", b'{"tool_input":' + text.encode() + b"}")
        for name, text in [
            ("null", "null"),
            ("false", "false"),
            ("zero", "0"),
            ("one", "1"),
            ("empty-string", '""'),
            ("string", '"x"'),
            ("empty-array", "[]"),
            ("array", "[1]"),
            ("empty-object", "{}"),
        ]
    ]
    for field, blocking in BLOCKING_STRINGS.items():
        typed = [(name, text) for name, text in TYPED_VALUES]
        typed += [
            ("string", json.dumps(blocking)),
            ("array", json.dumps([blocking])),
            ("object", json.dumps({"k": blocking})),
            ("member-name", json.dumps({blocking: 1})),
        ]
        payloads += [
            Payload(
                f"field-{field.replace('_', '-')}-{name}",
                b'{"tool_input":{"' + field.encode() + b'":' + text.encode() + b"}}",
            )
            for name, text in typed
        ]
    orders = [
        ("content-false-new-string-key", {"content": False, "new_string": KEY}),
        (
            "content-null-new-source-key",
            {"content": None, "new_string": None, "new_source": KEY},
        ),
        ("content-empty-new-string-key", {"content": "", "new_string": KEY}),
        ("content-newline-patch-key", {"content": "\n", "command": PATCH_KEY}),
        (
            "content-nul-newline-patch-key",
            {"content": "\u0000\n", "command": PATCH_KEY},
        ),
        ("content-plain-patch-key", {"content": "plain", "command": PATCH_KEY}),
        ("file-path-zero-patch-yml", {"file_path": 0, "command": PATCH_YML}),
        ("file-path-false-patch-yml", {"file_path": False, "command": PATCH_YML}),
        ("file-path-empty-patch-yml", {"file_path": "", "command": PATCH_YML}),
        ("file-path-newline-patch-yml", {"file_path": "\n", "command": PATCH_YML}),
        ("file-path-yaml-patch-yml", {"file_path": "a.yaml", "command": PATCH_YML}),
        ("command-array-patch-yml", {"command": [PATCH_YML]}),
        ("command-object-patch-key", {"command": {"p": PATCH_KEY}}),
        ("nul-in-path", {"file_path": "a.\u0000yml"}),
        ("nul-in-path-yaml", {"file_path": "a.\u0000yaml"}),
        ("nul-joins-key", {"content": KEY[:4] + "\u0000" + KEY[4:]}),
        ("nul-in-array-key", {"content": [KEY[:4] + "\u0000" + KEY[4:]]}),
        ("nul-in-member-name-key", {"content": {KEY[:4] + "\u0000" + KEY[4:]: 1}}),
        ("nul-in-command", {"command": "n\u0000pm install"}),
        ("noncharacter-in-path", {"file_path": "a\uffff.yml"}),
        ("non-ascii-path", {"file_path": "déjà/日本.yml"}),
        # Reasons guard-codex.sh has to rewrite or warn about.
        ("multiline-reason", {"command": 'touch "a\nb.yml"'}),
        ("nul-in-reason", {"command": "touch a\u0000.yml"}),
        # Reasons that quote bash's NUL warning, which is not one.
        (
            "warning-quoted-in-reason",
            {
                "command": 'touch "a: line 1: warning: command substitution: '
                'ignored null byte in input\nBLOCKED: b.yml"'
            },
        ),
        (
            "script-warning-quoted-in-reason",
            {
                "command": 'touch "ROOT_AGENTS_hooks_block-secrets.sh: line 1: '
                'warning: command substitution: ignored null byte in input\nb.yml"'
            },
        ),
        # Block reasons that guard-codex.sh rewrites: its tr, sed, and trim.
        ("tab-in-path", {"file_path": "a\tb.yml"}),
        ("carriage-return-in-path", {"file_path": "a\rb.yml"}),
        ("control-in-path", {"file_path": "a\u0001b.yml"}),
        ("delete-in-path", {"file_path": "a\u007fb.yml"}),
        ("c1-control-in-path", {"file_path": "a\u0085b.yml"}),
        ("quote-and-backslash-in-path", {"file_path": 'a\\"b.yml'}),
        ("html-in-path", {"file_path": "<a&b>.yml"}),
        ("line-separator-in-path", {"file_path": "a\u2028b.yml"}),
        ("space-before-extension", {"file_path": "a .yml"}),
    ]
    payloads += [
        Payload(f"order-{name}", doc({"tool_input": fields})) for name, fields in orders
    ]
    # The scripts read the fields whatever the tool is.
    every_field = {"command": NPM_INSTALL, "file_path": "a.yml", "content": KEY}
    payloads += [
        Payload(f"tool-{name}", doc({"tool_name": tool, "tool_input": fields}))
        for name, tool, fields in [
            ("unknown-shell", "future_shell", {"command": NPM_INSTALL}),
            ("unknown-write", "future_write", {"file_path": "a.yml", "content": KEY}),
            ("write-with-command", "Write", {"command": NPM_INSTALL}),
            (
                "bash-with-path-and-content",
                "Bash",
                {"file_path": "a.yml", "content": KEY},
            ),
            ("apply-patch-with-path", "apply_patch", {"file_path": "a.yml"}),
            ("not-a-string", 1, every_field),
            ("null", None, every_field),
        ]
    ]
    payloads.append(
        Payload(
            "escaped-noncharacter-in-path",
            b'{"tool_input":{"file_path":"a\\uffff.yml"}}',
        )
    )
    for i, path in enumerate(
        [
            "--help\na.yml",
            "--h\na.yml",
            "--vers\na.yml",
            "--version\na.yml",
            "--helpx\na.yml",
            "-x\na.yml",
            "-\na.yml",
            "--\na.yml",
            "a.yaml\n--help\nb.yml",
        ]
    ):
        payloads.append(
            Payload(f"dash-path-{i}", doc({"tool_input": {"file_path": path}}))
        )
    payloads.append(
        Payload(
            "dash-path-patch",
            doc(
                {
                    "tool_input": {
                        "command": file_guards_corpus.patch(
                            "*** Add File: --help\n+x\n*** Add File: a.yml\n+x\n"
                        )
                    }
                }
            ),
        )
    )
    return payloads


def limit_payloads() -> list[Payload]:
    """Base payloads, and the same with an unused member near a reference's limit."""
    payloads = []
    for base_name, base in (("block-all", doc(BLOCK_ALL)), ("harmless", doc(HARMLESS))):
        name = f"base-{base_name}"
        payloads.append(Payload(name, base))
        for digits in (4300, 4301):
            member = b'"x":' + b"9" * digits
            payloads.append(
                Payload(
                    f"integer-{digits}-digits-{base_name}",
                    with_member(base, member),
                    name,
                )
            )
        # 255 levels in all: the root object and 254 arrays. jq 1.7.1 reads no deeper.
        nesting = b'"x":' + b"[" * 254 + b"1" + b"]" * 254
        payloads.append(
            Payload(f"nesting-255-levels-{base_name}", with_member(base, nesting), name)
        )
    return payloads


def fix_payloads() -> list[Payload]:
    """The old scripts' bugs that the binary fixes (scripts/old_script_fixes.py),
    as the harnesses hand them over: each, and what must still block."""
    notebook = {"tool_name": "NotebookEdit"}
    cases = {
        # fixed-dash-line: a "-" line stopped the old files guard
        "fix-dash-line-after-ok": {"tool_input": {"file_path": "ok\n--bogus\nbad.yml"}},
        "fix-dash-line-itself": {"tool_input": {"file_path": "--x.yml"}},
        # fixed-notebook-path: the old files guard never read notebook_path
        "fix-notebook-path-alone": notebook
        | {"tool_input": {"notebook_path": "bad.yml", "new_source": "x"}},
        "fix-notebook-path-empty-file-path": notebook
        | {"tool_input": {"file_path": "", "notebook_path": "bad.yml"}},
        "fix-notebook-path-safe-file-path": notebook
        | {"tool_input": {"file_path": "safe.md", "notebook_path": "bad.yml"}},
        "fix-notebook-path-blocked-file-path": notebook
        | {"tool_input": {"file_path": "bad.yml", "notebook_path": "safe.ipynb"}},
        "fix-notebook-path-not-a-string": notebook
        | {"tool_input": {"notebook_path": ["bad.yml"]}},
        # both at once: neither fix alone blocks
        "fix-notebook-path-dash-line": notebook
        | {"tool_input": {"notebook_path": "--x.yml"}},
        # fixed-docs-agents-relative: a relative path under docs/agents/ was
        # not exempt; Codex's patch names its files so
        "fix-docs-agents-relative-file-path": {
            "tool_input": {"file_path": "docs/agents/x.yml"}
        },
        "fix-docs-agents-relative-patch": {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Add File: docs/agents/x.yml\n+a\n*** End Patch\n"
            },
        },
        "fix-docs-agents-relative-then-blocked": {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Add File: docs/agents/x.yml\n+a\n"
                "*** Add File: docs/y.yml\n+b\n*** End Patch\n"
            },
        },
        # ... only where a path starts: a later line is part of the path above
        "fix-docs-agents-relative-later-line": {
            "tool_input": {"file_path": "/w/x\ndocs/agents/y.yml"}
        },
        "fix-docs-agents-relative-notebook-later-line": notebook
        | {"tool_input": {"notebook_path": "x\ndocs/agents/y.yml"}},
        "fix-docs-agents-relative-notebook-own-path": notebook
        | {
            "tool_input": {"file_path": "/w/a.md", "notebook_path": "docs/agents/n.yml"}
        },
        # a notebook_path's first line starts its path after every line of
        # file_path; the lines bash drops (a NUL, trailing newlines) do not count
        "fix-docs-agents-relative-notebook-after-lines": notebook
        | {
            "tool_input": {
                "file_path": "a.md\nb.md",
                "notebook_path": "docs/agents/n.yml",
            }
        },
        "fix-docs-agents-relative-notebook-blank-first-line": notebook
        | {
            "tool_input": {
                "file_path": "a.md\nb.md",
                "notebook_path": "\ndocs/agents/n.yml",
            }
        },
        "fix-docs-agents-relative-notebook-after-dropped-lines": notebook
        | {
            "tool_input": {
                "file_path": "a.md\n\u0000\n",
                "notebook_path": "docs/agents/n.yml",
            }
        },
        "fix-docs-agents-relative-patch-second-file": {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Add File: a.md\n+a\n"
                "*** Add File: docs/agents/y.yml\n+b\n*** End Patch\n"
            },
        },
        "fix-docs-agents-relative-patch-then-notebook": {
            "tool_name": "apply_patch",
            "tool_input": {
                "command": "*** Begin Patch\n*** Add File: a.md\n+a\n*** End Patch\n",
                "notebook_path": "x\ndocs/agents/y.yml",
            },
        },
    }
    return [Payload(name, doc(value)) for name, value in cases.items()]


def payloads() -> list[Payload]:
    """Every payload, once each, in a fixed order."""
    found = (
        limit_payloads()
        + fixture_payloads()
        + test_payloads()
        + unreadable_payloads()
        + readable_payloads()
        + fix_payloads()
    )
    seen: dict[bytes, str] = {}
    unique = []
    for payload in found:
        if payload.stdin in seen:
            continue
        seen[payload.stdin] = payload.name
        unique.append(payload)
    names = [p.name for p in unique]
    assert len(names) == len(set(names)), "payload names repeat"
    return unique


def _reject_constant(name: str) -> None:
    msg = f"{name} is not JSON"
    raise ValueError(msg)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    names = [name for name, _ in pairs]
    if len(names) != len(set(names)):
        msg = "duplicate member name"
        raise ValueError(msg)
    return dict(pairs)


def readable(stdin: bytes) -> bool:
    """Whether stdin is one JSON value as the binary reads it: RFC 8259 in
    UTF-8, unique names, no unpaired surrogate, at most MAX_DEPTH levels.
    Numbers stay text, so Python's int limit does not apply."""
    try:
        text = stdin.decode("utf-8")
    except UnicodeDecodeError:
        return False
    try:
        value = json.loads(
            text,
            parse_int=str,
            parse_float=str,
            parse_constant=_reject_constant,
            object_pairs_hook=_unique_object,
        )
    except (ValueError, RecursionError):
        return False
    pending: list[tuple[object, int]] = [(value, 1)]
    while pending:
        item, depth = pending.pop()
        if isinstance(item, str):
            if any(0xD800 <= ord(char) <= 0xDFFF for char in item):
                return False
        elif isinstance(item, (dict, list)):
            if depth > MAX_DEPTH:
                return False
            members = (
                list(item.items())
                if isinstance(item, dict)
                else [(None, v) for v in item]
            )
            for name, member in members:
                if name is not None:
                    pending.append((name, depth))
                pending.append((member, depth + 1))
    return True


def one_line(text: str) -> str:
    """The reason as guard-codex.sh puts it in Codex's deny JSON: tabs, carriage
    returns, and newlines become spaces, other control bytes go, and trailing
    spaces go."""
    kept = bytearray()
    for byte in text.encode("utf-8"):
        if byte in (0x09, 0x0A, 0x0D):
            kept.append(0x20)
        elif byte >= 0x20:
            kept.append(byte)
    return kept.decode("utf-8").rstrip(" ")


def deny(reason: str) -> str:
    """guard-codex.sh's deny JSON for a reason already made one line."""
    return (
        '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",'
        '"permissionDecisionReason":' + json.dumps(reason, ensure_ascii=False) + "}}\n"
    )


PASS = {"exit": 0, "stdout": "", "stderr": ""}


def block_answer(harness: str, message: str) -> dict:
    """The binary's block, for a message that starts with BLOCKED: and ends
    with a newline."""
    if harness == "claude":
        return {"exit": 2, "stdout": "", "stderr": message}
    return {"exit": 0, "stdout": deny(one_line(message)), "stderr": ""}


def blocks(harness: str, run: dict) -> bool:
    """Whether a legacy run blocked, as its harness reads it."""
    if harness == "claude":
        return run["exit"] == 2
    if run["exit"] != 0 or not run["stdout"]:
        return False
    answer = json.loads(run["stdout"])
    return answer["hookSpecificOutput"]["permissionDecision"] == "deny"


def legacy_record(harness: str, run: dict) -> dict:
    """What the corpus keeps of a legacy run: on a block, the answer in full;
    on a pass, the exit code and whether anything was written (a diagnostic's
    text differs between machines)."""
    if blocks(harness, run):
        return {"exit": run["exit"], "stdout": run["stdout"], "stderr": run["stderr"]}
    return {"exit": run["exit"], "diagnostic": bool(run["stdout"] or run["stderr"])}


def claude_message(record: dict) -> tuple[str, bool]:
    """A Claude block's message: everything after bash's leading NUL warnings,
    starting with BLOCKED: and ending with a newline (a reason may hold more
    lines). Also whether there were warnings."""
    match = LEADING_NUL_WARNINGS.match(record["stderr"])
    warnings = match.group() if match else ""
    message = record["stderr"][len(warnings) :]
    if (
        record["stdout"]
        or not message.startswith(BLOCKED)
        or not message.endswith("\n")
    ):
        msg = f"unexpected Claude block: {record!r}"
        raise ValueError(msg)
    return message, bool(warnings)


def classify(
    harness: str, stdin: bytes, legacy: dict, base: dict | None
) -> tuple[str, dict]:
    """The difference ID of one run and the binary's expected answer, from the
    legacy record, the stdin, and, for a derived payload, its base's run
    ({"legacy": ..., "expectedGo": ...})."""
    if not readable(stdin):
        return "unreadable", block_answer(harness, BLOCKED + UNREADABLE + "\n")
    if base is not None:
        return ("reference-limit" if legacy != base["legacy"] else ""), base[
            "expectedGo"
        ]
    if "diagnostic" in legacy:
        if legacy["exit"] != 0 or legacy["diagnostic"]:
            return "pass-diagnostic", PASS
        return "", PASS
    if harness == "claude":
        message, warned = claude_message(legacy)
        return ("nul-warning" if warned else ""), block_answer(harness, message)
    if legacy["stderr"] and not ADAPTER_NUL_WARNINGS.fullmatch(legacy["stderr"]):
        msg = f"unexpected Codex block: {legacy!r}"
        raise ValueError(msg)
    reason = json.loads(legacy["stdout"])["hookSpecificOutput"][
        "permissionDecisionReason"
    ]
    match = LEADING_NUL_WARNINGS_ONE_LINE.match(reason)
    warnings = match.group() if match else ""
    expected = {"exit": 0, "stdout": deny(reason[len(warnings) :]), "stderr": ""}
    warned = bool(warnings or legacy["stderr"])
    if not warned and expected != legacy:
        msg = f"guard-codex.sh's answer is not deny(reason): {legacy!r}"
        raise ValueError(msg)
    return ("nul-warning" if warned else ""), expected


def require_the_pinned_python() -> None:
    have = unicodedata.unidata_version
    if have != command_guard_corpus.PYTHON_UNICODE:
        msg = (
            f"this Python has Unicode {have}; the corpus follows "
            f"{command_guard_corpus.PYTHON_UNICODE} (Python 3.14)"
        )
        raise SystemExit(msg)


def reference_env(tools: str) -> dict[str, str]:
    """The environment the scripts run in. Only PATH is the caller's, with
    tools first, so no Python or locale setting of the caller changes what a
    script does; HOME is tools, so jq loads no ~/.jq."""
    return {
        "PATH": tools + os.pathsep + os.environ["PATH"],
        "HOME": tools,
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8:strict",
        "PYTHONINTMAXSTRDIGITS": "4300",
    }


def make_tools(root: Path, flavor_program: str | None) -> str:
    """A directory with python3 and python for this interpreter and, if given,
    a basename(1); the wrapper's own lookup must pick this python3."""
    root.mkdir()
    for name in ("python3", "python"):
        (root / name).symlink_to(sys.executable)
    if flavor_program is not None:
        (root / "basename").symlink_to(flavor_program)
    picked = subprocess.run(
        ["bash", "-c", "type -aP python3 python | head -n 1"],
        env=reference_env(str(root)),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.strip()
    if picked != str(root / "python3"):
        msg = f"the command guard's wrapper would pick {picked}, not {root / 'python3'}"
        raise SystemExit(msg)
    return str(root)


def run_script(
    harness: str, hook: str, stdin: bytes, tools: str, scripts: Path = ROOT
) -> dict:
    """One legacy run: the script as the harness runs it today, from the
    repo's scripts, or from a directory of fixed copies (same names)."""
    argv = ["bash", GUARDS[hook]]
    if harness == "codex":
        argv = ["bash", CODEX_ADAPTER, GUARDS[hook]]
    done = subprocess.run(
        argv,
        input=stdin,
        env=reference_env(tools),
        capture_output=True,
        check=False,
        cwd=scripts,
    )
    return {
        "exit": done.returncode,
        "stdout": done.stdout.decode("utf-8", "replace"),
        "stderr": done.stderr.decode("utf-8", "replace"),
    }


def run_keys(flavors: list[str]) -> list[tuple[str, str, str]]:
    """The (harness, hook, basename flavor) runs of every payload, in order."""
    keys = []
    for harness in HARNESSES:
        for hook in GUARDS:
            if hook == "files-guard":
                keys += [(harness, hook, flavor) for flavor in flavors]
            else:
                keys.append((harness, hook, ""))
    return keys


def stored_stdin(stdin: bytes) -> dict:
    """stdin as the corpus stores it: base64, or, when longer than LONG_STDIN,
    runs, each a base64 chunk and how many times it repeats."""
    if len(stdin) <= LONG_STDIN:
        return {"stdin": base64.b64encode(stdin).decode()}
    runs: list[dict] = []
    literal = bytearray()
    i = 0
    while i < len(stdin):
        j = i
        while j < len(stdin) and stdin[j] == stdin[i]:
            j += 1
        if j - i >= 64:
            if literal:
                runs.append(
                    {"bytes": base64.b64encode(bytes(literal)).decode(), "count": 1}
                )
                literal.clear()
            runs.append(
                {"bytes": base64.b64encode(stdin[i : i + 1]).decode(), "count": j - i}
            )
        else:
            literal += stdin[i:j]
        i = j
    if literal:
        runs.append({"bytes": base64.b64encode(bytes(literal)).decode(), "count": 1})
    return {"stdinRuns": runs}


def unstored_stdin(entry: dict) -> bytes:
    """The stdin of a corpus entry, its runs joined back."""
    if "stdin" in entry:
        return base64.b64decode(entry["stdin"])
    return b"".join(
        base64.b64decode(run["bytes"]) * run["count"] for run in entry["stdinRuns"]
    )


def render(flavors: dict[str, str]) -> list[dict]:
    """The corpus entries, with the files guard under each flavor given
    (flavor name to basename program)."""
    require_the_pinned_python()
    order = sorted(flavors)
    keys = run_keys(order)
    found = payloads()
    with (
        tempfile.TemporaryDirectory() as scratch,
        ThreadPoolExecutor(max_workers=min(16, os.cpu_count() or 4)) as pool,
    ):
        tools = {"": make_tools(Path(scratch) / "any", None)}
        for flavor in order:
            tools[flavor] = make_tools(Path(scratch) / flavor, flavors[flavor])
        jobs = [(p, key) for p in found for key in keys]
        results = list(
            pool.map(
                lambda job: run_script(
                    job[1][0], job[1][1], job[0].stdin, tools[job[1][2]]
                ),
                jobs,
            )
        )
        # The files guard with every fix, and with each left out of that set.
        everything = frozenset(FILES_FIXES)
        variants = {
            applied: old_script_fixes.write_scripts(
                Path(scratch)
                / ("fixed-" + "+".join(sorted(applied)) if applied else "old"),
                applied,
            )
            for applied in [everything, *(everything - {name} for name in FILES_FIXES)]
        }
        fixed_jobs = [
            (index, k)
            for index, payload in enumerate(found)
            for k, key in enumerate(keys)
            if key[1] == "files-guard" and not payload.base
        ]
        full_results = dict(
            zip(
                fixed_jobs,
                pool.map(
                    lambda job: run_script(
                        keys[job[1]][0],
                        keys[job[1]][1],
                        found[job[0]].stdin,
                        tools[keys[job[1]][2]],
                        variants[everything],
                    ),
                    fixed_jobs,
                ),
                strict=True,
            )
        )
        by_payload: dict[str, dict] = {}
        entries = []
        for index, payload in enumerate(found):
            runs = []
            for k, (harness, hook, flavor) in enumerate(keys):
                legacy = legacy_record(harness, results[index * len(keys) + k])
                base = (
                    by_payload[payload.base][(harness, hook, flavor)]
                    if payload.base
                    else None
                )
                if base is not None:
                    old_script_fixes.refuse_a_base_that_needs_a_fix(
                        payload.name, payload.base, base
                    )
                difference, expected = classify(harness, payload.stdin, legacy, base)
                run: dict[str, object] = {"harness": harness, "hook": hook}
                if flavor:
                    run["basename"] = flavor
                fixed = None
                if (index, k) in full_results:
                    full = legacy_record(harness, full_results[(index, k)])
                    full_difference, full_expected = classify(
                        harness, payload.stdin, full, None
                    )
                    # The fixed script is the reference: its noise always, and
                    # the fixes it needs exactly when its answer differs.
                    if (full_difference, full_expected) != (difference, expected):
                        needed: list[str] = []

                        def expected_with(
                            applied: frozenset[str],
                            harness=harness,
                            hook=hook,
                            flavor=flavor,
                            stdin=payload.stdin,
                            legacy_expected=expected,
                            full_expected=full_expected,
                        ) -> dict:
                            if not applied:
                                return legacy_expected
                            if applied == everything:
                                return full_expected
                            record = legacy_record(
                                harness,
                                run_script(
                                    harness,
                                    hook,
                                    stdin,
                                    tools[flavor],
                                    variants[applied],
                                ),
                            )
                            return classify(harness, stdin, record, None)[1]

                        if full_expected != expected:
                            needed = old_script_fixes.needed(FILES_FIXES, expected_with)
                        difference = old_script_fixes.difference(
                            needed, full_difference
                        )
                        expected, fixed = full_expected, full
                run |= {"difference": difference, "legacy": legacy}
                if fixed is not None:
                    run["fixed"] = fixed
                run["expectedGo"] = expected
                runs.append(run)
            by_payload[payload.name] = {
                (r["harness"], r["hook"], r.get("basename", "")): r for r in runs
            }
            entry = {"name": payload.name} | stored_stdin(payload.stdin)
            if payload.base:
                entry["base"] = payload.base
            entries.append(entry | {"runs": runs})
    return entries


def main() -> None:
    flavors = file_guards_corpus.basename_flavors()
    if set(flavors) != {"bsd", "gnu"}:
        msg = (
            f"the corpus needs BSD and GNU basename; found {sorted(flavors)}"
            " (on macOS: brew install coreutils for gbasename)"
        )
        raise SystemExit(msg)
    entries = render(flavors)
    CORPUS.write_text(
        "".join(json.dumps(e, ensure_ascii=True) + "\n" for e in entries),
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {CORPUS.relative_to(ROOT)} ({len(entries)} payloads)")


if __name__ == "__main__":
    main()
