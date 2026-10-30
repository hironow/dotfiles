"""install.sh links the mise-managed prek into ~/.local/bin (step_prek_shim).

git hooks fall back to a bare `prek` on PATH, and mise keeps prek where only an
activated shell sees it, so install.sh symlinks it into ~/.local/bin. mise makes
`installs/prek/latest` a symlink to the version directory, and `find` does not
follow a symlink given as its starting point unless asked to. The step looked
there without following it, found nothing, and skipped the shim on every fresh
box. These run the real step function, cut out of install.sh, against a fake
mise install tree.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from _bash_hook import resolve_bash

ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "install.sh"
BASH = resolve_bash()

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="step_prek_shim runs on mac and linux only"
)


def _function(name: str) -> str:
    text = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.MULTILINE | re.DOTALL)
    assert match, f"install.sh has no {name}()"
    return match.group(0)


def _run(home: Path) -> subprocess.CompletedProcess[str]:
    script = "_skip_windows() { :; }\n" + _function("step_prek_shim")
    script += "DOTFILES_OS=linux\nstep_prek_shim\n"
    # system dirs only: no prek on PATH, as on a box where mise is not activated
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"PATH": "/usr/bin:/bin", "HOME": str(home)},
        check=False,
    )


def _mise_prek(home: Path, version: str = "0.5.7") -> Path:
    """The layout mise writes: a version dir, and `latest` as a symlink to it."""
    installs = home / ".local" / "share" / "mise" / "installs" / "prek"
    binary = installs / version / "prek-x86_64-unknown-linux-gnu" / "prek"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\necho prek\n", encoding="utf-8", newline="\n")
    binary.chmod(0o755)
    (installs / "latest").symlink_to(f"./{version}", target_is_directory=True)
    return binary


def test_links_prek_through_the_latest_symlink(tmp_path: Path) -> None:
    # given prek installed by mise, whose `latest` is a symlink
    binary = _mise_prek(tmp_path)

    # when the prek shim step runs
    result = _run(tmp_path)

    # then ~/.local/bin/prek points at that binary
    assert result.returncode == 0, result.stderr
    shim = tmp_path / ".local" / "bin" / "prek"
    assert shim.is_symlink(), result.stdout
    assert shim.resolve() == binary.resolve()


def test_shim_goes_through_latest_so_an_upgrade_follows(tmp_path: Path) -> None:
    # given prek installed by mise
    _mise_prek(tmp_path)

    # when the prek shim step runs
    _run(tmp_path)

    # then the link names latest/, not the version directory
    shim = tmp_path / ".local" / "bin" / "prek"
    assert "/prek/latest/" in str(shim.readlink())


def test_skips_without_a_link_when_prek_is_not_installed(tmp_path: Path) -> None:
    # given no prek under mise and none on PATH
    # when the prek shim step runs
    result = _run(tmp_path)

    # then it says so and creates nothing
    assert result.returncode == 0, result.stderr
    assert "prek not found under mise" in result.stdout
    assert not (tmp_path / ".local" / "bin" / "prek").exists()
