"""`just agent-hooks-build` hands its arguments to hookrelease.

The recipe once pasted its arguments into the command line unquoted, so a
release path holding a space split in two (PR 3c's design review). On Unix it
now takes them as positional arguments. Native Windows keeps the pasted form
in a `[windows]` recipe of the same name, since windows-shell hands a recipe
no positional arguments (its -c contract); there `id` and a plain `check`
path must still pass through (PR 3c's code review). The unit-test workflow's
windows-jev job runs this file on Windows.

A stub `mise` first on PATH, a POSIX sh script that Git's sh also runs,
records the argv the recipe gives it, so no Go and no build run here.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HOOKRELEASE = ["x", "--", "go", "run", "./cmd/hookrelease"]

pytestmark = pytest.mark.skipif(
    shutil.which("just") is None, reason="just is not installed"
)


def _just(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    record = tmp_path / "argv.txt"
    stub = bin_dir / "mise"
    # LF only: a CR after the shebang would name another interpreter.
    stub.write_bytes(b'#!/bin/sh\nprintf \'%s\\n\' "$@" > "$AGENT_HOOKS_ARGV"\n')
    stub.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "AGENT_HOOKS_ARGV": record.as_posix(),
    }
    done = subprocess.run(
        ["just", "--justfile", str(ROOT / "justfile"), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done, record


def _recipe_argv(tmp_path: Path, *args: str) -> list[str]:
    """The argv `just agent-hooks-build ARGS` gives mise."""
    done, record = _just(tmp_path, "agent-hooks-build", *args)
    assert done.returncode == 0, done.stderr
    return record.read_text(encoding="utf-8").splitlines()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="the Windows recipe pastes its arguments into the line (Windows plan, B5)",
)
def test_a_path_with_a_space_quote_and_dollar_stays_one_argument(
    tmp_path: Path,
) -> None:
    path = "/a b/o'brien $x/dotfiles/agent-hooks/current/codex/agent-hook"
    argv = _recipe_argv(tmp_path, "check", path)
    assert argv == [*HOOKRELEASE, "check", path]


def test_id_and_a_plain_check_path_pass_through(tmp_path: Path) -> None:
    # given each subcommand that works on every OS, when the recipe runs it
    path = "/x/dotfiles/agent-hooks/current/codex/agent-hook"
    # then hookrelease gets it, and not `build` in its place
    assert _recipe_argv(tmp_path, "id") == [*HOOKRELEASE, "id"]
    assert _recipe_argv(tmp_path, "check", path) == [*HOOKRELEASE, "check", path]


def test_no_argument_builds(tmp_path: Path) -> None:
    assert _recipe_argv(tmp_path) == [*HOOKRELEASE, "build"]


def test_the_list_describes_the_recipe(tmp_path: Path) -> None:
    # just lists a recipe with the comment line right above it: the usage,
    # not a note about how the arguments travel
    done, _ = _just(tmp_path, "--list")
    assert done.returncode == 0, done.stderr
    listed = [line for line in done.stdout.splitlines() if "agent-hooks-build" in line]
    usage = "# Windows: id" if sys.platform == "win32" else "# Build a host release"
    assert len(listed) == 1, listed
    assert usage in listed[0], listed
