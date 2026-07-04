"""`.gitattributes` must pin generated, diff-checked artifacts to LF on every OS.

`docs/portless-urls.md` is produced by `just portless-doc` (LF, from a bash
generator) and verified by `just portless-doc-check` with a raw `diff` in `ci`.
Without an `eol=lf` pin a Windows checkout yields CRLF, and the raw diff reports
the doc stale even though the committed blob is LF — git normalizes on compare,
so `git status` stays clean and the breakage surfaces only in the recipe's diff.
Mirrors the `dump/scoop.json` pin (ADR 0019) and `*.sh` / `*.bash` (ADR 0020).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or not (ROOT / ".git").exists(),
    reason="needs git + a real repo to evaluate .gitattributes",
)


@pytest.mark.parametrize("path", ["docs/portless-urls.md", "dump/windows/scoop.json"])
def test_generated_artifact_is_lf_pinned(path: str) -> None:
    """The artifact must resolve to `eol=lf` via .gitattributes so every
    platform (esp. Windows, where core.autocrlf can introduce CRLF) checks it
    out as LF and the diff-based check stays stable."""
    out = subprocess.run(
        ["git", "check-attr", "eol", "--", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    # git check-attr format: "<path>: eol: <value>"
    assert out.endswith(": lf"), (
        f"{path} must be pinned `text eol=lf` in .gitattributes so a Windows "
        f"checkout keeps LF (it is a generated, diff-checked artifact); "
        f"git check-attr reported: {out!r}"
    )
