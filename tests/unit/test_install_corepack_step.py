"""install.sh keeps going when `corepack enable` fails (step_corepack).

On a box with mise, `corepack` on PATH is a mise shim, so it runs the node that
the deployed ~/.config/mise/config.toml asks for (`node = "lts"`). When that
node is not installed (a rerun with INSTALL_SKIP_ADD_UPDATE=1, or the day Node
moves its LTS line to a new major), the shim exits 1 with "Tool not installed
for shim: corepack". install.sh runs under `set -e`, so that one convenience
step stopped the whole installer before the dotfiles were deployed. These run
the real step function, cut out of install.sh, under the same `set -eu`.
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
    os.name == "nt", reason="this branch of step_corepack runs on mac and linux"
)


def _function(name: str) -> str:
    text = INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(rf"^{name}\(\) \{{\n.*?^\}}\n", text, re.MULTILINE | re.DOTALL)
    assert match, f"install.sh has no {name}()"
    return match.group(0)


def _run(tmp_path: Path, corepack_body: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    corepack = bin_dir / "corepack"
    corepack.write_text(f"#!/bin/sh\n{corepack_body}\n", encoding="utf-8", newline="\n")
    corepack.chmod(0o755)
    script = "set -eu\n_skip_windows() { :; }\n" + _function("step_corepack")
    script += "DOTFILES_OS=linux\nstep_corepack\necho next-step-ran\n"
    return subprocess.run(
        [BASH, "-c", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(tmp_path)},
        check=False,
    )


def test_a_failing_corepack_enable_does_not_stop_the_installer(
    tmp_path: Path,
) -> None:
    # given a corepack shim whose node version is not installed
    shim_error = 'echo "mise ERROR Tool not installed for shim: corepack" >&2; exit 1'

    # when the corepack step runs under set -e
    result = _run(tmp_path, shim_error)

    # then the installer goes on and says how to fix it
    assert result.returncode == 0, result.stderr
    assert "next-step-ran" in result.stdout
    assert "step_corepack: WARN" in result.stderr
    assert "mise install" in result.stderr


def test_a_working_corepack_is_enabled_quietly(tmp_path: Path) -> None:
    # given a corepack that works
    log = tmp_path / "corepack.log"

    # when the corepack step runs
    result = _run(tmp_path, f'echo "$*" >> "{log.as_posix()}"')

    # then it enables corepack and warns about nothing
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").strip() == "enable"
    assert "WARN" not in result.stderr
