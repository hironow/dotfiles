"""`just dump` must treat Homebrew as optional on the Mac/Linux path.

Why this exists
---------------
The `dump` recipe's Unix path called `brew bundle dump` unconditionally.
Under `set -eu`, that aborts the whole recipe on any host without Homebrew
— e.g. a WSL/mise-managed box where packages come from apt + mise, not
brew. The Windows-subset branch of the very same recipe already guards its
tools (`command -v scoop` / `command -v jq`); the Linux path should be just
as forgiving: skip the Brewfile dump with a WARN and still emit the gcloud
+ gitignore manifests.

Two checks:
1. Static — the real recipe must guard `brew bundle dump` behind a
   `command -v brew` test (this is the Red driver: the pre-fix recipe has no
   such guard).
2. Behavioural — the guard pattern, run with brew absent from PATH, must
   exit 0, emit the skip WARN, and continue to the next step (not abort).

Host-side, no Docker (part of `tests/unit/`), so it honours WSL-only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"


def _dump_recipe(text: str) -> str:
    """Slice out the `dump` recipe body (dump: -> the next recipe, set-host)."""
    start = text.index("\ndump:")
    end = text.index("\nset-host", start)
    return text[start:end]


def test_dump_guards_brew_behind_command_check() -> None:
    """The Mac/Linux path must not call `brew bundle dump` unconditionally."""
    body = _dump_recipe(JUSTFILE.read_text())
    assert "brew bundle dump" in body, "dump no longer dumps a Brewfile at all?"
    assert "command -v brew" in body, (
        "dump calls `brew bundle dump` without a `command -v brew` guard; on a "
        "brew-less host (WSL/mise) `set -eu` aborts the whole recipe."
    )
    assert body.index("command -v brew") < body.index("brew bundle dump"), (
        "the `command -v brew` guard must precede the `brew bundle dump` call."
    )


@pytest.fixture
def just_binary() -> str:
    if sys.platform == "win32":
        pytest.skip(
            "native Windows: runs a `just` shebang recipe via cygpath + a "
            "Unix-style restricted PATH that Git-Bash can't resolve; runs on "
            "Linux/WSL/CI (the static command-check test still runs everywhere)"
        )
    just = shutil.which("just")
    if just is None:
        pytest.skip("just not on PATH")
    return just


def test_brew_absent_skips_without_aborting(just_binary: str, tmp_path: Path) -> None:
    """The guard pattern: brew absent -> exit 0, WARN, and continue."""
    tmp = tmp_path / "d.just"
    tmp.write_text(
        "dump-linux:\n"
        "  #!/usr/bin/env bash\n"
        "  set -eu\n"
        "  if command -v brew >/dev/null 2>&1; then\n"
        "    echo 'brew present: would dump Brewfile'\n"
        "  else\n"
        "    echo '==> WARN: brew not on PATH; skipping Brewfile dump' >&2\n"
        "  fi\n"
        "  echo 'reached gcloud step'\n"
    )
    # Minimal PATH: bash/coreutils resolve, but brew is guaranteed absent.
    env = {"PATH": "/usr/bin:/bin", "HOME": os.environ.get("HOME", "/root")}
    result = subprocess.run(
        [just_binary, "-f", str(tmp), "dump-linux"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"recipe aborted with brew absent (expected graceful skip).\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "skipping Brewfile dump" in result.stderr
    assert "reached gcloud step" in result.stdout, "did not continue past the brew step"
