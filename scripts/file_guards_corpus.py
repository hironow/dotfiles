#!/usr/bin/env python3
"""Write the corpora the agent-hook Go port of the file and secrets guards is
tested against.

The references are the shell guards ROOT_AGENTS_hooks_block-prohibited-files.sh
and ROOT_AGENTS_hooks_block-secrets.sh, until the agent-hook plan's last PR
removes them (docs/plan/agent-hooks-go.md). This runs each guard with bash on
every input, handed over as Claude Code does (file_path, content) or as Codex
does (an apply_patch patch), and records its exit code and the reason it
blocks. tests/unit/test_file_guards_corpus.py fails when a corpus no longer
matches its guard, and the Go tests fail when the port no longer matches the
corpus. Run `just file-guards-corpus` after changing either guard or its tests.

The files guard calls basename(1), whose BSD and GNU versions differ: GNU's
takes --help and --version (and their prefixes) as options that succeed, so
the guard reads on past such a path, where BSD's fails and the guard stops.
The files corpus records both, so this needs both: on macOS, BSD's is
/usr/bin/basename and GNU's is gbasename (brew install coreutils).

The secrets corpus writes every character of its texts as a JSON \\u escape,
so the file holds no token shapes that a secret scanner would flag.

This is Python, not Go, because it drives the shell references; it goes with them.
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES_GUARD = ROOT / "ROOT_AGENTS_hooks_block-prohibited-files.sh"
SECRETS_GUARD = ROOT / "ROOT_AGENTS_hooks_block-secrets.sh"
CORPUS_DIR = ROOT / "tools/agent-hooks/internal/guardcorpus"
FILES_CORPUS = CORPUS_DIR / "files-guard.jsonl"
SECRETS_CORPUS = CORPUS_DIR / "secrets-guard.jsonl"
# The guards' own tests: every input their parametrized cases use is here.
GUARD_TESTS = (
    ROOT / "tests/unit/test_codex_patch_guards.py",
    ROOT / "tests/unit/test_block_secrets_hook.py",
)
BLOCKED = "BLOCKED: "
# The parametrize argument names of the guard tests, and what each holds.
FIXTURE_ARGS = ("patch", "token", "content")
# An input longer than this is stored as runs of one character, so that a
# 1 MiB test input takes a line, not megabytes.
LONG_INPUT = 1024


def patch(*sections: str) -> str:
    """An apply_patch patch, as Codex hands it over."""
    return "*** Begin Patch\n" + "".join(sections) + "*** End Patch\n"


# Paths aimed at one behavior each, grouped by the part of the guard they test.
FILE_PATHS = [
    # the two rules
    "a.yml",
    "a.yaml",
    "dir/a.yml",
    "/abs/dir/a.yml",
    ".yml",
    "a.YML",
    "a.yml.bak",
    "a.ymlx",
    "docker-compose.yaml",
    "docker-compose.yml",
    "x/docker-compose.yaml",
    "docker-compose.yaml.bak",
    "compose.yaml",
    "compose.yml",
    "Docker-Compose.yaml",
    # the instruction files may name prohibited patterns
    "AGENTS.md",
    "x/AGENTS.md",
    "CLAUDE.md",
    "/r/CLAUDE.md",
    "/repo/docs/agents/x.yml",
    "a/docs/agents/docker-compose.yml",
    "docs/agents/x.yml",
    "a/docs/agents/../x.yml",
    "x/docs/agents/",
    "AGENTS.md/x.yml",
    "x/AGENTS.md.yml",
    "xAGENTS.md",
    # basename's view of the path
    "a.yml/",
    "a.yml//",
    "/",
    "///",
    "dir/",
    "a/.yml",
    "-x.yml",
    "--",
    "a/-x.yml",
    "-",
    # several paths in one, and odd characters
    "a.yaml\nb.yml",
    "b.yml\na.yaml",
    "\na.yml",
    "a.yaml\n",
    "x.yml\r",
    "my file.yml",
    "日本.yml",
    "x\u0000.yml",
    "\t a.yml",
    # basename's options: GNU's succeed on --help and --version and their
    # prefixes, and the guard reads on; every other leading - fails both
    "--help\na.yml",
    "--h\na.yml",
    "--he\ndocker-compose.yaml",
    "--version\na.yml",
    "--v\na.yml",
    "--vers\na.yml",
    "--help=x\na.yml",
    "--hx\na.yml",
    "-a\na.yml",
    "--\na.yml",
    "-\na.yml",
    "--help",
    "a.yml ",
    " ",
    "",
]

FILE_PATCHES = [
    patch("*** Add File: a.yml\n+x\n"),
    patch("*** Add File: a.yaml\n+x\n"),
    patch("*** Update File: a.yml\n@@\n-x\n+y\n"),
    patch("*** Update File: a.yml\n*** Move to: a.yaml\n@@\n-x\n+y\n"),
    patch("*** Update File: a.yaml\n*** Move to: a.yml\n"),
    patch("*** Move to: a.yml\n"),
    patch("*** Update File: a.yml\n*** Move to: \n"),
    patch("*** Add File: \n+x\n"),
    patch("*** Delete File: a.yml\n"),
    patch("*** Update File: a.yml\n*** End of File\n"),
    patch("*** Update File: a.yml\n*** Update File: b.yaml\n"),
    patch("*** Add File: a.yaml\n*** Add File: b.yml\n"),
    patch("*** Update File: x/docs/agents/c.yml\n"),
    patch("***  Add File: a.yml\n"),
    patch("*** add file: a.yml\n"),
    patch("*** Add File:a.yml\n"),
    "*** Add File: a.yml\n",
    "prefix *** Begin Patch\n*** Add File: a.yml\n",
    patch("*** Add File: a.yml\r\n+x\r\n"),
    patch("*** Add File: docker-compose.yml\n"),
    patch("*** Update File: -x.yml\n"),
    patch("*** Update File: --help\n*** Add File: a.yml\n"),
    patch("*** Add File: --version\n*** Add File: b.yml\n"),
    patch("*** Add File: a.yaml\nb\n*** Add File: c.yml\n"),
    patch("*** Add File: a.yml\n+*** Add File: b.yaml\n"),
    patch("*** Add File: 日本.yml\n"),
    patch("*** Update File: a.yaml\n*** Move to: b.yaml\n*** Move to: c.yml\n"),
    patch(""),
]

# A private key header, split so that this file holds none.
PEM = "-----BEGIN "
KEY = "PRIVATE KEY-----"

CONTENTS = [
    # each token shape at its length threshold
    "sk-" + "a" * 19,
    "sk-" + "a" * 20,
    "sk-" + "a-" * 15,
    "sk-ant-" + "a" * 19,
    "sk-ant-" + "a" * 20,
    "sk-proj-" + "a_b-" * 5,
    "sk-admin-" + "x" * 20,
    "sk-svcacct-" + "-" * 20,
    "ghp_" + "a" * 35,
    "ghp_" + "a" * 36,
    "ghp_" + "a" * 37,
    "ghp_" + "a-" * 18,
    "github_pat_" + "a" * 19,
    "github_pat_" + "a" * 20,
    "github_pat_" + "-" * 20,
    "AKIA" + "A" * 15,
    "AKIA" + "A" * 16,
    "AKIA" + "a" * 16,
    "AKIA" + "0" * 16,
    PEM + KEY,
    PEM + "RSA " + KEY,
    PEM + "OPENSSH " + KEY,
    PEM + "ENCRYPTED " + KEY,
    PEM + "rsa " + KEY,
    PEM + "PUBLIC KEY-----",
    PEM + "RSA\n" + KEY,
    "----BEGIN " + KEY,
    "xoxb-" + "1" * 10,
    "xoxb-" + "1" * 9,
    "xoxb-" + "a" + "1" * 9,
    "xoxa-" + "1abcdefghi",
    "xoxs-" + "1-2-3-4-5-6",
    "xoxz-" + "1234567890",
    "XOXB-" + "1234567890",
    "glpat-" + "x" * 19,
    "glpat-" + "x" * 20,
    "glpat-" + "_" * 20,
    "AIza" + "B" * 34,
    "AIza" + "B" * 35,
    "AIza" + "-" * 35,
    # where the shape sits
    "key=AKIA" + "A" * 16 + "!",
    "xAKIA" + "A" * 16,
    "AKIA" + "A" * 8 + "\n" + "A" * 8,
    "AK\u0000IA" + "A" * 16,
    "sk-\n" + "a" * 20,
    "a\n\nsk-" + "a" * 20,
    "日本語 sk-" + "a" * 20,
    # prose that passes
    "risk-assessment-framework-for-the-team",
    "sk-learn is a library",
    "use ghp_ tokens",
    "",
    "\n",
    "  ",
]

CONTENT_PATCHES = [
    patch("*** Add File: c.py\n+KEY = 'AKIA" + "A" * 16 + "'\n"),
    patch("*** Update File: c.py\n@@\n-KEY = 'AKIA" + "A" * 16 + "'\n+KEY = env\n"),
    patch("*** Update File: c.py\n@@\n KEY = 'AKIA" + "A" * 16 + "'\n"),
    patch("*** Add File: c.py\n++AKIA" + "A" * 16 + "\n"),
    patch("*** Add File: c.py\n+AKIA" + "A" * 8 + "\n+" + "A" * 8 + "\n"),
    "*** Add File: c.py\n+AKIA" + "A" * 16 + "\n",
    patch("*** Add File: c.py\nAKIA" + "A" * 16 + "\n"),
    patch("*** Add File: c.py\n+ghp_" + "a" * 36 + "\r\n"),
    patch("*** Add File: c.py\n+sk-ant-" + "a" * 30 + "\n"),
    patch("*** Update File: c.py\n@@\n-ghp_" + "a" * 36 + "\n+KEY = os.environ\n"),
    patch(""),
]

RANDOM_SEED = 20261104
RANDOM_PATHS = 150
RANDOM_CONTENTS = 200
PATH_PARTS = [
    "a",
    "docs",
    "agents",
    "AGENTS.md",
    "CLAUDE.md",
    "x.yml",
    "x.yaml",
    "docker-compose.yaml",
    "docker-compose.yml",
    "compose.yaml",
    ".yml",
    "-x",
    "",
    " ",
    "日本",
    "\n",
    "..",
]
TOKEN_PREFIXES = [
    "sk-",
    "sk-ant-",
    "sk-proj-",
    "ghp_",
    "github_pat_",
    "AKIA",
    "xoxb-",
    "xoxp-",
    "glpat-",
    "AIza",
    PEM,
    KEY,
    "RSA ",
    "",
]
TOKEN_ALPHABETS = ["aZ09", "A0", "a-_", "1", "x", " ", "\n", "-"]


def _rng_inputs() -> tuple[list[str], list[str]]:
    """Random paths and contents, the same on every run (random() is stable)."""
    rng = random.Random(RANDOM_SEED)

    def pick(options: list[str]) -> str:
        return options[int(rng.random() * len(options))]

    paths = []
    for _ in range(RANDOM_PATHS):
        count = 1 + int(rng.random() * 4)
        paths.append(
            "".join(pick(PATH_PARTS) + pick(["/", "/", ""]) for _ in range(count))
        )
    contents = []
    for _ in range(RANDOM_CONTENTS):
        alphabet = pick(TOKEN_ALPHABETS)
        body = "".join(pick(list(alphabet)) for _ in range(int(rng.random() * 45)))
        contents.append(pick(["", "x ", "key="]) + pick(TOKEN_PREFIXES) + body)
    return paths, contents


def _parametrized() -> dict[str, list[str]]:
    """The values each guard test is parametrized with, by argument name.

    A value is a string or a pytest.param of one string. Anything else, or an
    argument name not in FIXTURE_ARGS, fails: an input dropped here in silence
    would leave the port unchecked on it.
    """
    found: dict[str, list[str]] = {}
    # The tests import their helpers (_bash_hook) from their own directory.
    if str(GUARD_TESTS[0].parent) not in sys.path:
        sys.path.insert(0, str(GUARD_TESTS[0].parent))
    for path in GUARD_TESTS:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for name, test in vars(module).items():
            if not name.startswith("test_"):
                continue
            for mark in getattr(test, "pytestmark", []):
                if mark.name != "parametrize":
                    continue
                if mark.args[0] not in FIXTURE_ARGS:
                    msg = (
                        f"{path.name}::{name}: cannot read parametrize {mark.args[0]!r}"
                    )
                    raise ValueError(msg)
                found.setdefault(mark.args[0], []).extend(
                    _fixture_value(f"{path.name}::{name}", value)
                    for value in mark.args[1]
                )
    return found


def _fixture_value(test: str, value: object) -> str:
    """A parametrize value as text: a string, or the one string in a pytest.param."""
    if isinstance(value, str):
        return value
    values = getattr(value, "values", None)
    if isinstance(values, tuple) and len(values) == 1 and isinstance(values[0], str):
        return values[0]
    msg = f"{test}: cannot read parametrize value {value!r}"
    raise ValueError(msg)


def fixtures() -> dict[str, list[str]]:
    """The guard tests' inputs, as file paths, patches, and contents."""
    found = _parametrized()
    return {
        "patch": found.get("patch", []),
        "content": [f"value = '{token}'" for token in found.get("token", [])]
        + found.get("content", []),
    }


def inputs() -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """The (kind, text) inputs of each guard, once each, in a fixed order."""
    tests = fixtures()
    random_paths, random_contents = _rng_inputs()
    files = [("patch", text) for text in tests["patch"] + FILE_PATCHES]
    files += [("filePath", text) for text in FILE_PATHS + random_paths]
    secrets = [("patch", text) for text in tests["patch"] + CONTENT_PATCHES]
    secrets += [("content", text) for text in tests["content"] + CONTENTS]
    secrets += [("content", text) for text in random_contents]
    return list(dict.fromkeys(files)), list(dict.fromkeys(secrets))


def _payload(kind: str, text: str) -> dict:
    if kind == "patch":
        return {"tool_name": "apply_patch", "tool_input": {"command": text}}
    if kind == "filePath":
        return {"tool_name": "Write", "tool_input": {"file_path": text}}
    return {"tool_name": "Write", "tool_input": {"file_path": "c.py", "content": text}}


def basename_flavors() -> dict[str, str]:
    """The basename(1) programs here, by flavor: "gnu" if --version succeeds, else "bsd"."""
    found: dict[str, str] = {}
    for candidate in ("basename", "gbasename", "/usr/bin/basename"):
        program = shutil.which(candidate)
        if program is None:
            continue
        version = subprocess.run(
            [program, "--version"], capture_output=True, check=False
        )
        found.setdefault("gnu" if version.returncode == 0 else "bsd", program)
    return found


def run_guard(script: Path, kind: str, text: str, path_dir: str | None = None) -> dict:
    """What the guard does with one input: its exit code, and its reason when it
    blocks. path_dir, when given, goes first on PATH (it holds a basename)."""
    env = dict(os.environ)
    if path_dir is not None:
        env["PATH"] = path_dir + os.pathsep + env["PATH"]
    done = subprocess.run(
        ["bash", str(script)],
        input=json.dumps(_payload(kind, text)),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=ROOT,
    )
    reason = None
    if done.returncode == 2:
        at = done.stderr.rfind(BLOCKED)
        assert at >= 0, f"{script.name} exited 2 without a reason for {text!r}"
        reason = done.stderr[at + len(BLOCKED) :].removesuffix("\n")
    return {"exit": done.returncode, "reason": reason}


def _escaped(value: str | None) -> str:
    """A JSON string with every UTF-16 code unit as a \\u escape, or null."""
    if value is None:
        return "null"
    data = value.encode("utf-16-be", "surrogatepass")
    units = (int.from_bytes(data[i : i + 2], "big") for i in range(0, len(data), 2))
    return '"' + "".join(f"\\u{unit:04x}" for unit in units) + '"'


def stored(kind: str, text: str) -> dict:
    """An input as the corpus stores it: as it is, or, when longer than
    LONG_INPUT, as runs of one character under "<kind>Runs"."""
    if len(text) <= LONG_INPUT:
        return {kind: text}
    runs: list[dict] = []
    for char in text:
        if runs and runs[-1]["char"] == char:
            runs[-1]["count"] += 1
        else:
            runs.append({"char": char, "count": 1})
    return {kind + "Runs": runs}


def unstored(entry: dict) -> tuple[str, str]:
    """The (kind, text) input of a corpus entry, its runs joined back."""
    for key, value in entry.items():
        if key.endswith("Runs"):
            return key.removesuffix("Runs"), "".join(
                r["char"] * r["count"] for r in value
            )
        if key in ("filePath", "patch", "content"):
            return key, value
    msg = f"no input in {entry!r}"
    raise ValueError(msg)


def secrets_line(entry: dict) -> str:
    """One secrets corpus line, every character of its texts as a \\u escape."""
    fields = []
    for key, value in entry.items():
        if key == "exit":
            fields.append(f'"exit": {value}')
        elif key.endswith("Runs"):
            runs = ", ".join(
                f'{{"char": {_escaped(r["char"])}, "count": {r["count"]}}}'
                for r in value
            )
            fields.append(f'"{key}": [{runs}]')
        else:
            fields.append(f'"{key}": {_escaped(value)}')
    return "{" + ", ".join(fields) + "}\n"


def render(flavors: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """The corpus entries: the files guard under each basename flavor given
    (flavor name to program), and the secrets guard."""
    files, secrets = inputs()
    with (
        tempfile.TemporaryDirectory() as shims,
        ThreadPoolExecutor(max_workers=min(16, os.cpu_count() or 4)) as pool,
    ):
        dirs: dict[str, str] = {}
        for flavor, program in flavors.items():
            shim = Path(shims) / flavor
            shim.mkdir()
            (shim / "basename").symlink_to(program)
            dirs[flavor] = str(shim)
        columns = {
            flavor: list(
                pool.map(lambda kt, d=d: run_guard(FILES_GUARD, *kt, d), files)
            )
            for flavor, d in dirs.items()
        }
        secret_results = list(
            pool.map(lambda kt: run_guard(SECRETS_GUARD, *kt), secrets)
        )
    file_entries = [
        stored(kind, text) | {flavor: columns[flavor][i] for flavor in sorted(columns)}
        for i, (kind, text) in enumerate(files)
    ]
    secret_entries = [
        stored(kind, text) | result
        for (kind, text), result in zip(secrets, secret_results, strict=True)
    ]
    return file_entries, secret_entries


def main() -> None:
    flavors = basename_flavors()
    if set(flavors) != {"bsd", "gnu"}:
        raise SystemExit(
            f"the files corpus needs BSD and GNU basename; found {sorted(flavors)}"
            " (on macOS: brew install coreutils for gbasename)"
        )
    files, secrets = render(flavors)
    FILES_CORPUS.write_text(
        "".join(json.dumps(e, ensure_ascii=True) + "\n" for e in files),
        encoding="utf-8",
        newline="\n",
    )
    SECRETS_CORPUS.write_text(
        "".join(secrets_line(e) for e in secrets), encoding="utf-8", newline="\n"
    )
    for path in (FILES_CORPUS, SECRETS_CORPUS):
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
