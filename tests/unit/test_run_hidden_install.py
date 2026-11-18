"""`scripts/run_hidden_win.ps1` copies run-hidden.exe for the scheduled tasks.

dotfiles' Windows scheduled tasks start through run-hidden so that a task in
the owner's logon session opens no console window
(docs/plan/windows-headless-tasks.md). A task keeps its launcher running for
as long as its program runs, and the WSL keepalive never ends, so the
launcher's exe stays in use; Windows cannot overwrite a running exe. The copy
therefore lives in a directory named by its content hash: the same content
returns the same path and is never written again, new content gets a new
directory, and the installers point the tasks at it.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest
from _pwsh import resolve_pwsh

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "scripts" / "run_hidden_win.ps1"
PWSH = resolve_pwsh(os.environ)

pwshonly = pytest.mark.skipif(
    PWSH is None, reason="needs pwsh to run the installer function"
)


def _install(source: Path, root: Path) -> subprocess.CompletedProcess[str]:
    script = f". '{LIB}'; Install-RunHidden -Source '{source}' -Root '{root}'"
    return subprocess.run(
        [str(PWSH), "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _installed_path(proc: subprocess.CompletedProcess[str]) -> Path:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return Path(proc.stdout.strip().splitlines()[-1])


def _expected(root: Path, content: bytes) -> Path:
    digest = hashlib.sha256(content).hexdigest()
    return root / digest[:16] / "run-hidden.exe"


@pwshonly
def test_the_copy_lives_in_a_directory_named_by_its_content(tmp_path: Path) -> None:
    source = tmp_path / "build" / "run-hidden.exe"
    source.parent.mkdir()
    source.write_bytes(b"first build")
    root = tmp_path / "installed"
    installed = _installed_path(_install(source, root))
    assert installed == _expected(root, b"first build")
    assert installed.read_bytes() == b"first build"


@pwshonly
def test_the_same_content_is_never_written_again(tmp_path: Path) -> None:
    """A running launcher's exe is locked; rewriting it would fail the install."""
    source = tmp_path / "run-hidden.exe"
    source.write_bytes(b"same build")
    root = tmp_path / "installed"
    first = _installed_path(_install(source, root))
    os.utime(first, ns=(1_000_000_000, 1_000_000_000))
    second = _installed_path(_install(source, root))
    assert second == first
    assert first.stat().st_mtime_ns == 1_000_000_000, "the copy was written again"


@pwshonly
def test_new_content_gets_a_new_directory_and_the_old_copy_stays(
    tmp_path: Path,
) -> None:
    source = tmp_path / "run-hidden.exe"
    root = tmp_path / "installed"
    source.write_bytes(b"old build")
    old = _installed_path(_install(source, root))
    source.write_bytes(b"new build")
    new = _installed_path(_install(source, root))
    assert new != old
    assert new == _expected(root, b"new build")
    assert old.read_bytes() == b"old build", "a task may still run the old copy"


@pwshonly
def test_a_missing_build_names_the_recipe_that_makes_it(tmp_path: Path) -> None:
    proc = _install(tmp_path / "absent.exe", tmp_path / "installed")
    assert proc.returncode != 0
    assert "just run-hidden-build" in proc.stdout + proc.stderr
    assert not (tmp_path / "installed").exists()


@pwshonly
def test_a_copy_that_does_not_match_its_directory_stops_the_install(
    tmp_path: Path,
) -> None:
    source = tmp_path / "run-hidden.exe"
    source.write_bytes(b"real build")
    root = tmp_path / "installed"
    wrong = _expected(root, b"real build")
    wrong.parent.mkdir(parents=True)
    wrong.write_bytes(b"something else")
    proc = _install(source, root)
    assert proc.returncode != 0
    assert wrong.read_bytes() == b"something else", (
        "an unexpected file is not ours to replace"
    )
