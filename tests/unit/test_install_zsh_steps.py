"""install.sh gets a bare Linux/WSL box to the supported zsh setup.

zsh is the supported interactive shell (.zshrc, USAGE.md, j-cc / j-pi), but a
bare WSL Ubuntu has no zsh, and install.sh (sudo-free by design) neither
installed it nor said so. sheldon comes from mise there, yet step_sheldon only
looked on PATH, which mise has not been activated onto while install.sh runs,
so the plugin lock was skipped with a one-line note. These run the real step
functions, cut out of install.sh, against stub commands.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from _bash_hook import resolve_bash

ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "install.sh"
BASH = resolve_bash()


def _function(name: str) -> str:
    text = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.M | re.S)
    assert match, f"install.sh has no {name}()"
    return match.group(0)


def _stub(bin_dir: Path, name: str, body: str) -> None:
    exe = bin_dir / name
    exe.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8", newline="\n")
    exe.chmod(0o755)


def _run(
    tmp_path: Path, step: str, shell: str = "/bin/bash"
) -> subprocess.CompletedProcess[str]:
    script = (
        "_skip_windows() { :; }\n" + _function(step) + f"DOTFILES_OS=linux\n{step}\n"
    )
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"PATH": str(tmp_path / "bin"), "HOME": str(tmp_path), "SHELL": shell},
        check=False,
    )


@pytest.fixture
def bin_dir(tmp_path: Path) -> Path:
    path = tmp_path / "bin"
    path.mkdir()
    return path


def test_sheldon_is_locked_through_mise_when_not_on_path(
    tmp_path: Path, bin_dir: Path
) -> None:
    # given sheldon only under mise (install.sh runs before mise activate)
    log = tmp_path / "mise.log"
    _stub(bin_dir, "mise", f'echo "$*" >> "{log.as_posix()}"; exit 0')

    # when the sheldon step runs
    result = _run(tmp_path, "step_sheldon")

    # then it locks the plugins through mise instead of skipping
    assert result.returncode == 0, result.stderr
    assert "exec -- sheldon lock --update" in log.read_text(encoding="utf-8")


def test_a_missing_zsh_prints_how_to_install_it(tmp_path: Path, bin_dir: Path) -> None:
    # given a bare Linux box without zsh
    # when the zsh step runs
    result = _run(tmp_path, "step_zsh")

    # then it says exactly what to run (install.sh itself never uses sudo)
    assert result.returncode == 0, result.stderr
    assert "sudo apt-get install -y zsh" in result.stderr
    assert "chsh -s" in result.stderr


def test_zsh_that_is_not_the_login_shell_prints_chsh(
    tmp_path: Path, bin_dir: Path
) -> None:
    # given zsh installed but bash still the login shell
    _stub(bin_dir, "zsh", "exit 0")

    # when the zsh step runs
    result = _run(tmp_path, "step_zsh", shell="/bin/bash")

    # then it points at chsh only
    assert result.returncode == 0, result.stderr
    assert "chsh -s" in result.stderr
    assert "apt-get" not in result.stderr


def test_zsh_as_the_login_shell_is_quiet(tmp_path: Path, bin_dir: Path) -> None:
    _stub(bin_dir, "zsh", "exit 0")
    result = _run(tmp_path, "step_zsh", shell="/usr/bin/zsh")
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


def test_install_sh_runs_the_zsh_step() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    assert re.search(r"^step_zsh$", text, re.M)


def test_doctor_reports_zsh_on_linux() -> None:
    # the doctor is where a box that skipped install.sh's hint finds out
    doctor = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    block = doctor[doctor.index("# zsh is the supported interactive shell") :]
    assert "log_warn 'zsh'" in block
    assert "sudo apt-get install -y zsh" in block
    assert "chsh -s" in block
