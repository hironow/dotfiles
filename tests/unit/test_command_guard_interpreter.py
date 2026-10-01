"""The command guard's shim finds a real Python or fails closed.

block-prohibited-commands.sh only hands over to its Python companion. On Windows
`python3` can resolve to the Microsoft Store stub under WindowsApps, which runs
nothing; exec'ing it ended the hook with that stub's exit code, which Claude
Code and Codex both read as "allow". The shim skips WindowsApps, tries python3
then python, and blocks (exit 2) when neither exists.
"""

import subprocess
from pathlib import Path

from _bash_hook import resolve_bash

ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / "ROOT_AGENTS_hooks_block-prohibited-commands.sh"


def _fake(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    fake = directory / name
    fake.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8", newline="\n")
    fake.chmod(0o755)


def _run(tmp_path: Path, dirs: list[Path]) -> subprocess.CompletedProcess[str]:
    # bash's own view of each dir: a C:/ path would split PATH at the colon
    path = ":".join(f"$(cd '{d.as_posix()}' && pwd)" for d in dirs)
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
    _fake(stub_dir, "python3", "exit 49")
    _fake(real_dir, "python", 'echo "ran $1"; exit 0')
    result = _run(tmp_path, [stub_dir, real_dir])
    assert result.returncode == 0
    assert "block-prohibited-commands.py" in result.stdout


def test_no_usable_python_blocks(tmp_path: Path) -> None:
    stub_dir = tmp_path / "WindowsApps"
    _fake(stub_dir, "python3", "exit 49")
    _fake(stub_dir, "python", "exit 49")
    result = _run(tmp_path, [stub_dir])
    assert result.returncode == 2
    assert "Python" in result.stderr
