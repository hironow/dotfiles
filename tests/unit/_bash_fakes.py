"""Preflight for tests that fake commands with bash functions from BASH_ENV.

Why this exists
---------------
bash silently ignores a BASH_ENV file it cannot read. The script under test
then runs the real commands: on Windows the real `uname` reports MINGW and the
script starts the real WSL, PowerShell or registry tools against this machine.
Every replay must therefore prove, before the script runs, that each fake is a
loaded function and that PATH reaches none of the host launchers.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

from _bash_hook import run_bash


def require_bash_fakes(
    cwd: str | os.PathLike[str],
    env: Mapping[str, str],
    fakes: Sequence[str],
    launchers: Sequence[str],
) -> None:
    """Raise unless every name in `fakes` is a bash function under `env` and
    no name in `launchers` resolves to a file on its PATH."""
    probe = Path(cwd) / "fake-preflight.sh"
    probe.write_text(
        f"type -t {' '.join(fakes)}\n"
        f'for launcher in {" ".join(launchers)}; do type -P "$launcher"; done\n'
        "exit 0\n",
        encoding="utf-8",
    )
    proc = run_bash(
        probe,
        cwd=cwd,
        env=dict(env),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    lines = proc.stdout.split()
    kinds, found = lines[: len(fakes)], lines[len(fakes) :]
    if proc.returncode != 0 or kinds != ["function"] * len(fakes):
        raise RuntimeError(f"fake layer not loaded: {proc.stdout!r} {proc.stderr!r}")
    if found:
        raise RuntimeError(f"replay PATH reaches a host launcher: {found}")
