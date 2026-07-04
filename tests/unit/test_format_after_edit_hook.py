"""Unit tests for the PostToolUse hook ROOT_AGENTS_hooks_format-after-edit.sh.

The hook receives Write|Edit tool input as JSON on stdin and formats the
edited file in place. It must only ever touch the edited file: the original
TS/JS branch ran `just fmt` (a project-wide format) on every single edit,
polluting unrelated diffs — these tests pin that the hook never invokes a
project-wide formatter and that the Python/Go branches stay single-file.

Formatters are stubbed: each stub records its argv to a log file so the
tests can assert exactly what the hook ran.
"""

import json
import shutil
import sys
from pathlib import Path

import pytest

from _bash_hook import run_bash

HOOK = Path(__file__).resolve().parents[2] / "ROOT_AGENTS_hooks_format-after-edit.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32"
    or shutil.which("bash") is None
    or shutil.which("jq") is None,
    reason=(
        "Linux/WSL/CI only: the stub PATH uses drive-lettered (C:\\...) entries "
        "that collide with bash's ':' separator, and the formatter stubs need "
        "POSIX symlinks — not a harness-fixable issue on native Windows"
    ),
)


def _make_stub(bindir: Path, name: str, log: Path) -> None:
    stub = bindir / name
    stub.write_text(f'#!/usr/bin/env bash\necho "{name} $*" >> "{log}"\n')
    stub.chmod(0o755)


def _run_hook(cwd: Path, file_path: Path, stubs: list[str]) -> Path:
    """Run the hook with stubbed formatters; return the invocation log."""
    bindir = cwd / "stub-bin"
    bindir.mkdir()
    log = cwd / "invocations.log"
    log.touch()
    for name in stubs:
        _make_stub(bindir, name, log)
    jq = shutil.which("jq")
    assert jq is not None
    (bindir / "jq").symlink_to(jq)  # jq may live outside /usr/bin (homebrew)
    payload = json.dumps({"tool_input": {"file_path": str(file_path)}})
    env = {"PATH": f"{bindir}:{Path('/usr/bin')}:{Path('/bin')}"}
    result = run_bash(
        HOOK,
        cwd=cwd,
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return log


@pytest.mark.parametrize("suffix", [".ts", ".tsx", ".js", ".jsx"])
def test_ts_js_edit_never_runs_project_wide_format(tmp_path: Path, suffix: str) -> None:
    """Editing one TS/JS file must not trigger `just fmt` (whole project)."""
    target = tmp_path / f"component{suffix}"
    target.write_text("export {}\n")
    log = _run_hook(tmp_path, target, stubs=["just", "uv", "gofmt"])
    assert log.read_text() == "", (
        "format-after-edit invoked a formatter for a TS/JS edit; the project-"
        "wide `just fmt` branch must stay removed (it polluted unrelated diffs)"
    )


def test_python_edit_formats_only_the_edited_file(tmp_path: Path) -> None:
    target = tmp_path / "module.py"
    target.write_text("x = 1\n")
    log = _run_hook(tmp_path, target, stubs=["just", "uv", "gofmt"])
    lines = log.read_text().splitlines()
    assert lines, "expected the Python branch to invoke uv"
    for line in lines:
        assert line.startswith("uv run ruff "), line
        assert str(target) in line, f"ruff must target the edited file: {line}"
    assert not any(line.startswith("just") for line in lines)


def test_go_edit_formats_only_the_edited_file(tmp_path: Path) -> None:
    target = tmp_path / "main.go"
    target.write_text("package main\n")
    log = _run_hook(tmp_path, target, stubs=["just", "uv", "gofmt"])
    assert log.read_text().splitlines() == [f"gofmt -w {target}"]
