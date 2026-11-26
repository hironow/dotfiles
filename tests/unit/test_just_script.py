"""Script recipes run through one interpreter setting per OS.

A `[script]` recipe (the manual's Script Recipes, stable since just 1.33) is
written to a temporary file and run by `script-interpreter`, instead of by the
file's own `#!` line. That gives the native Windows trap one place to fix: a
bare `bash` there resolves to WSL's System32 bash (CreateProcess searches
System32 before PATH), so the Windows interpreter puts Git's /usr/bin first on
PATH and runs Git's bash, as the Windows `set shell` does for linewise recipes
(tests/unit/test_windows_shell_usr_bin_path.py).

The interpreter takes no shell flags: each recipe keeps its own `set` line
(`self-check` uses `set -u` alone and collects failures instead of stopping).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"
WINDOWS_SH = Path(r"C:\Program Files\Git\usr\bin\sh.exe")
# Recipes that CI runs as script recipes on each path: Linux (small-checks),
# Linux and Windows (go-test, in check.yaml and the Windows Go job), and
# Windows PowerShell 5.1 (test-windows-powershell).


def _setting(os_attr: str, path: Path = JUSTFILE) -> list[str]:
    text = path.read_text(encoding="utf-8")
    m = re.search(
        rf"^\[{os_attr}\]\nset script-interpreter := \[(.+)\]$", text, re.MULTILINE
    )
    assert m, f"justfile must set script-interpreter under [{os_attr}]"
    return [a or b for a, b in re.findall(r"\"([^\"]*)\"|'([^']*)'", m.group(1))]


@pytest.mark.skipif(sys.platform == "win32", reason="runs the Unix setting")
def test_the_unix_interpreter_leaves_errexit_to_the_recipe(tmp_path: Path) -> None:
    just = shutil.which("just")
    if just is None:
        pytest.skip("needs just")
    justfile = tmp_path / "justfile"
    justfile.write_text(
        'set script-interpreter := ["bash"]\n\n'
        "[positional-arguments]\n[script]\n"
        "demo arg:\n"
        "    set -u\n"
        "    false\n"
        '    echo "reached $1"\n',
        encoding="utf-8",
        newline="\n",
    )
    result = subprocess.run(
        [just, "--justfile", str(justfile), "demo", "x y"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "reached x y"


def _host_bash() -> str:
    if sys.platform == "win32":
        bash = WINDOWS_SH.with_name("bash.exe")
        if not bash.exists():
            pytest.skip("Git for Windows bash.exe not found")
        return str(bash)
    return shutil.which("bash") or "/usr/bin/bash"


def test_windows_mechanism_runs_the_script_with_usr_bin_first(tmp_path: Path) -> None:
    # Portable: the msys sh and /usr/bin/bash exist only on Windows, so a real
    # bash stands in; what is under test is the prelude and how it forwards
    # the script path and the arguments.
    bash = _host_bash()
    argv = _setting("windows")
    argv[0] = bash
    argv[2] = argv[2].replace("exec /usr/bin/bash", f'exec "{bash}"')
    script = tmp_path / "recipe"
    script.write_text('printf "%s|%s|%s" "${PATH%%:*}" "$#" "$1"\n', encoding="utf-8")
    result = subprocess.run(
        [*argv, str(script), "a b"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "/usr/bin|1|a b"


@pytest.mark.skipif(
    sys.platform != "win32" or not WINDOWS_SH.exists(),
    reason="needs Git for Windows' raw usr/bin sh.exe",
)
def test_real_msys_sh_runs_a_script_that_finds_git_bash(tmp_path: Path) -> None:
    """The live regression: from a System32-first PATH, not WSL's bash."""
    argv = _setting("windows")
    argv[0] = str(WINDOWS_SH)
    script = tmp_path / "recipe"
    script.write_text("command -v bash && bash -c 'echo $OSTYPE'\n", encoding="utf-8")
    result = subprocess.run(
        [*argv, str(script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        env={"PATH": r"C:\Windows\System32", "SYSTEMROOT": r"C:\Windows"},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == "/usr/bin/bash"
    assert result.stdout.splitlines()[1] in ("msys", "cygwin")
