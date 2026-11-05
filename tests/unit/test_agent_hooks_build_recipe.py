"""`just agent-hooks-build` hands each argument to hookrelease as it was given.

The recipe once pasted its arguments into the command line unquoted, so a
release path holding a space split in two (PR 3c's design review). It now
takes them as positional arguments. A stub `mise` first on PATH records the
argv the recipe gives it, so no Go and no build run here.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.skipif(
        sys.platform == "win32",
        reason="windows-shell hands a recipe no positional arguments (its -c contract)",
    ),
    pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed"),
]


def _recipe_argv(tmp_path: Path, *args: str) -> list[str]:
    """The argv `just agent-hooks-build ARGS` gives mise."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    record = tmp_path / "argv.json"
    stub = bin_dir / "mise"
    stub.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        f"open({str(record)!r}, 'w', encoding='utf-8').write(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    done = subprocess.run(
        ["just", "--justfile", str(ROOT / "justfile"), "agent-hooks-build", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(record.read_text(encoding="utf-8"))


def test_a_path_with_a_space_quote_and_dollar_stays_one_argument(
    tmp_path: Path,
) -> None:
    path = "/a b/o'brien $x/dotfiles/agent-hooks/current/codex/agent-hook"
    argv = _recipe_argv(tmp_path, "check", path)
    assert argv == ["x", "--", "go", "run", "./cmd/hookrelease", "check", path]


def test_no_argument_builds(tmp_path: Path) -> None:
    argv = _recipe_argv(tmp_path)
    assert argv == ["x", "--", "go", "run", "./cmd/hookrelease", "build"]
