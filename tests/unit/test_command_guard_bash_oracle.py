"""The fixed command guard against bash itself.

The command guard's fixes (scripts/old_script_fixes.py: command-split,
command-start, shell-string) make the guard find the commands where bash
finds them. Each input of BASH_ORACLE (scripts/command_guard_corpus.py) runs
in bash, in an empty directory, with stub programs on PATH that log their
names; what bash ran is the oracle, not the guard's own lexer:

- "runs": bash runs a banned program or writes a .yml file, and the fixed
  guard blocks the input;
- "quiet": bash runs and writes none, and the fixed guard passes it;
- "over": bash runs none, and the fixed guard blocks it on purpose.

POSIX only: it runs bash. An input whose shell is not installed (zsh) is
skipped.
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import command_guard_corpus as corpus
import old_script_fixes

GUARD = "ROOT_AGENTS_hooks_block-prohibited-commands.py"
COMMAND_FIXES = frozenset(
    name for name, fix in old_script_fixes.FIXES.items() if fix.script == GUARD
)
BANNED = ("npm", "yarn", "pnpm", "pip", "pip3", "poetry", "pipenv", "make", "corepack")

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("bash") is None,
    reason="the oracle runs bash on a POSIX system",
)


class Blocked(Exception):
    """The guard blocked."""


@pytest.fixture(scope="module")
def fixed(tmp_path_factory: pytest.TempPathFactory) -> ModuleType:
    """The Python guard with every one of its fixes, whose block() raises."""
    directory = old_script_fixes.write_scripts(
        tmp_path_factory.mktemp("fixed"), COMMAND_FIXES
    )
    spec = importlib.util.spec_from_file_location("fixed_guard", directory / GUARD)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def block(reason: str) -> None:
        raise Blocked(reason)

    vars(module)["block"] = block
    return module


def blocks(guard: ModuleType, text: str) -> bool:
    try:
        guard.analyze(text)
    except Blocked:
        return True
    return False


def bash_runs(text: str, tmp_path: Path) -> tuple[list[str], list[str]]:
    """The banned programs bash ran for the text, and the .yml files it wrote."""
    stubs, work = tmp_path / "stubs", tmp_path / "work"
    stubs.mkdir()
    work.mkdir()
    log = tmp_path / "ran.log"
    for name in BANNED:
        stub = stubs / name
        stub.write_text(f'#!/bin/sh\necho {name} >> "{log}"\n', encoding="utf-8")
        stub.chmod(0o755)
    subprocess.run(
        [shutil.which("bash") or "bash", "--norc", "--noprofile", "-c", text],
        cwd=work,
        env={"PATH": f"{stubs}:/usr/bin:/bin", "HOME": str(tmp_path), "LC_ALL": "C"},
        capture_output=True,
        timeout=20,
        check=False,
    )
    ran = log.read_text(encoding="utf-8").split() if log.exists() else []
    written = sorted(str(path.relative_to(work)) for path in work.rglob("*.yml"))
    return ran, written


def test_every_oracle_input_is_in_the_corpus():
    assert {text for text, _ in corpus.BASH_ORACLE} <= set(corpus.inputs())
    assert {kind for _, kind in corpus.BASH_ORACLE} <= {"runs", "quiet", "over"}


@pytest.mark.parametrize(("text", "kind"), corpus.BASH_ORACLE)
def test_the_fixed_guard_blocks_what_bash_runs(
    fixed: ModuleType, tmp_path: Path, text: str, kind: str
):
    if text.startswith("zsh ") and shutil.which("zsh") is None:
        pytest.skip("zsh is not installed")
    ran, written = bash_runs(text, tmp_path)
    assert bool(ran or written) == (kind == "runs"), (ran, written)
    assert blocks(fixed, text) == (kind != "quiet")
