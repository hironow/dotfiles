"""The rtk hook's shim runs a real Python, never the Microsoft Store stub.

rtk-hook-claude.sh only hands over to its Python companion. On Windows
`python3` can resolve to the Store stub under WindowsApps
(AppInstallerPythonRedirector.exe), which runs nothing and can open the Store.
The shim must skip WindowsApps and try python3 then python, as the command
guard and the Codex rtk shim do. Unlike the guard, this hook fails OPEN: with
no usable Python it exits 0 and leaves the command untouched.
"""

import subprocess
from pathlib import Path

from _bash_hook import resolve_bash

ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / "ROOT_AGENTS_hooks_rtk-hook-claude.sh"


def _fake(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fake = directory / name
    fake.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8", newline="\n")
    fake.chmod(0o755)


def _run(tmp_path: Path, dirs: list[Path]) -> subprocess.CompletedProcess[str]:
    # bash's own view of each dir: a C:/ path would split PATH at the colon.
    # /usr/bin last, for dirname: Git Bash's has no Python, Linux's may, so
    # the fake dirs come first.
    path = ":".join([*(f"$(cd '{d.as_posix()}' && pwd)" for d in dirs), "/usr/bin"])
    return subprocess.run(
        [resolve_bash(), "-c", f'PATH="{path}"; . "{SHIM.as_posix()}"'],
        input='{"tool_input":{"command":"ls"}}',
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=tmp_path,
    )


def test_the_store_stub_is_skipped_for_a_real_python(tmp_path: Path) -> None:
    stub_dir = tmp_path / "WindowsApps"
    real_dir = tmp_path / "py"
    _fake(stub_dir, "python3", 'echo "stub ran"; exit 49')
    _fake(real_dir, "python", 'echo "ran $1"; exit 0')
    result = _run(tmp_path, [stub_dir, real_dir])
    assert result.returncode == 0, result.stdout + result.stderr
    assert "stub ran" not in result.stdout
    assert "rtk-hook-claude.py" in result.stdout


def test_no_usable_python_fails_open(tmp_path: Path) -> None:
    stub_dir = tmp_path / "WindowsApps"
    _fake(stub_dir, "python3", 'echo "stub ran"; exit 49')
    _fake(stub_dir, "python", 'echo "stub ran"; exit 49')
    result = _run(tmp_path, [stub_dir])
    assert result.returncode == 0, "an output optimiser must not block the command"
    assert result.stdout == ""
