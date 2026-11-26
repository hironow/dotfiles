"""deploy/clean must be linewise `bash scripts/*.sh` wrappers (no shebang).

Why this guard exists
---------------------
On native Windows, shebang recipes (`#!/usr/bin/env bash`) are OUTSIDE the
the `[windows]` `set shell := ["sh", ...]` protection: just executes `env bash
<tempfile>`, `env`'s PATH search resolves `bash` to WSL's
C:\\Windows\\System32\\bash.exe (System32 precedes Git usr\\bin in the
machine PATH), and WSL bash cannot open the backslashed Windows temp path —
`just deploy` dies with `/bin/bash: C:Users...deploy: No such file or
directory` from PowerShell.

Plain (linewise) recipes DO go through the `[windows]` `set shell := ["sh", ...]`:
`sh` is not in System32 so it resolves to Git Bash's sh, whose prelude
prepends /usr/bin so the inner `bash` resolves to Git Bash's (raw non-login
msys sh preserves the caller's PATH order and would otherwise let System32's
WSL bash win from a fresh persisted PATH — see
test_windows_shell_usr_bin_path.py). This is the #231 precedent
(doctor/harden-env -> `bash scripts/*.sh`), also guarded for
prune-rogue-npm-globals in test_doctor_npm_rogue.py.

deploy/clean are the ADR 0018 Windows-native entry points (bootstrap.ps1
chains `just deploy` from PowerShell), so they must stay linewise wrappers
around scripts/deploy.sh / scripts/clean.sh forever.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"


@pytest.fixture(scope="module")
def justfile_text() -> str:
    return JUSTFILE.read_text(encoding="utf-8")


@pytest.mark.parametrize("script", ["deploy.sh", "clean.sh"])
def test_recipe_script_exists_and_is_bash(script: str) -> None:
    path = ROOT / "scripts" / script
    assert path.is_file(), f"scripts/{script} must exist (body of the recipe)"
    first = path.read_text(encoding="utf-8").splitlines()[0]
    assert first.startswith("#!/usr/bin/env bash"), (
        f"scripts/{script} must start with a bash shebang — invoked as "
        f"`bash scripts/{script}` from just, and directly executable from "
        f"Git Bash"
    )
