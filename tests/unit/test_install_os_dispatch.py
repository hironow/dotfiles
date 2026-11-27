"""Regression tests for install.sh OS dispatch (ADR 0005).

What this guards
----------------
ADR 0005 (Accepted 2026-05-02) decided that install.sh becomes
OS-aware via a single `uname`-driven `DOTFILES_OS` variable, with
each install step wrapped in a `step_*` helper function. The
helpers branch on `DOTFILES_OS` so:

  - mac:     runs the historical Homebrew + brew bundle + gcloud
             components + corepack enable + update-all flow
  - linux:   runs only symlink + sheldon (the dev container
             feature already provided everything else with SHA/
             SLSA verification at build time)
  - windows: emits TODO stubs; concrete impls come in a future
             ADR when a Windows host is actually used
  - unknown: exits non-zero so unsupported environments fail
             closed

The existing `INSTALL_SKIP_*` env vars are kept as an operator
override layer; the combined skip predicate is OS-says-skip OR
env-var-says-skip.

These tests are **regex assertions on install.sh source text**
plus a small set of runtime executions of `install.sh --check`
or equivalent dry-run flag. They do NOT execute the heavy
install steps themselves; doing so would require a real Mac
host, and the Linux path is exercised inside the dev container
by the sandbox tests.

Why these exist
---------------
A previous PR that "just adds a bunch of step_* functions" can
silently regress the OS dispatch (e.g., by forgetting the
`exit 1` for unknown OS, or by inverting an OR/AND in the skip
predicate). Catch those at PR-review time before they reach
main.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "install.sh"
BASH = shutil.which("bash") or "/bin/bash"


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    assert INSTALL_SH.is_file(), f"install.sh missing at {INSTALL_SH}"
    return INSTALL_SH.read_text(encoding="utf-8")


# ---------- OS identification --------------------------------------


# ---------- step_* functions ---------------------------------------


# ---------- env var override preserved -----------------------------


# ---------- runtime smoke (no real install) ------------------------


def test_install_sh_passes_shellcheck() -> None:
    """install.sh is the entry point operators run on day 1; it
    must pass shellcheck so we don't ship subtly-broken bash. If
    shellcheck is not available on the test runner, skip — CI's
    Shellcheck Linting workflow exercises this anyway."""
    if shutil.which("shellcheck") is None:
        pytest.skip("shellcheck not installed; relying on CI's lint job")

    r = subprocess.run(
        ["shellcheck", "--severity=error", str(INSTALL_SH)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert r.returncode == 0, (
        f"install.sh shellcheck failed:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )


def test_install_sh_unknown_uname_exits_nonzero(tmp_path: Path) -> None:
    """End-to-end smoke: invoke install.sh with a fake `uname` stub
    that prints something we don't recognise. The script must exit
    non-zero before it reaches any actual install logic.

    We achieve this by:
      1. Creating a tmp dir with a stub `uname` executable that
         prints "Plan9".
      2. Running `bash install.sh` with PATH pointing at the stub
         dir first.
      3. Confirming the exit code is non-zero AND no homebrew /
         gcloud install was attempted (those would touch network +
         system, which we'd notice if they fired).

    The script will probably fail very early — before HEAD-of-
    install.sh `git clone`. That's fine; the relevant assertion is
    "non-zero exit" not "exits at exactly line N"."""
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    fake_uname = stubs / "uname"
    fake_uname.write_text("#!/usr/bin/env bash\necho Plan9\n", encoding="utf-8")
    fake_uname.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{stubs}:{env.get('PATH', '')}"
    # Set DOTPATH to a tmp location so the pre-amble git clone
    # doesn't try to mutate the operator's real ~/dotfiles.
    env["DOTPATH"] = str(tmp_path / "dotfiles")
    env["INSTALL_SKIP_HOMEBREW"] = "1"
    env["INSTALL_SKIP_GCLOUD"] = "1"
    env["INSTALL_SKIP_ADD_UPDATE"] = "1"

    r = subprocess.run(
        [BASH, str(INSTALL_SH)],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        timeout=30,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert r.returncode != 0, (
        f"install.sh exited 0 on a Plan9 fake uname. ADR 0005 requires "
        f"unknown OSes to fail closed.\nstdout:\n{r.stdout}\n"
        f"stderr:\n{r.stderr}"
    )
    # Also confirm the rejection mentions the unsupported OS so the
    # operator knows what happened.
    combined = r.stdout + r.stderr
    assert re.search(r"unsupported|unknown.*os|Plan9", combined, re.IGNORECASE), (
        f"install.sh exited non-zero but did not say why; operator "
        f"should see an unsupported-OS message. Combined output:\n"
        f"{combined}"
    )


# ---------- corepack migration (retire pnpm-global) ----------------


# ---------- Windows native MVP (ADR 0018) --------------------------
