"""`.gitattributes` must pin generated, diff-checked artifacts to LF on every OS.

`docs/portless-urls.md` is produced by `just portless-doc` (LF, from a bash
generator) and verified by `just portless-doc-check` with a raw `diff` in `ci`.
Without an `eol=lf` pin a Windows checkout yields CRLF, and the raw diff reports
the doc stale even though the committed blob is LF — git normalizes on compare,
so `git status` stays clean and the breakage surfaces only in the recipe's diff.
Mirrors the `dump/scoop.json` pin (ADR 0019) and `*.sh` / `*.bash` (ADR 0020).
Go sources are pinned for a different tool: gofmt / gofumpt — reached through
`golangci-lint run` and `golangci-lint fmt --diff` in `go-lint` — report a CRLF
working tree as "File is not properly formatted", so an untouched `.go` file
fails `just check` on a Windows host while the committed blob is LF.
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


def _eol_attr_lines(paths: list[str]) -> list[str]:
    """`git check-attr eol` per path, as `"<path>: eol: <value>"` lines."""
    out = subprocess.run(
        ["git", "check-attr", "eol", "--", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return [line for line in out.splitlines() if line.strip()]


def _tracked(pattern: str) -> list[str]:
    """Every tracked path matching a git pathspec."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--", pattern],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    return [name for name in out.decode("utf-8").split("\0") if name]


@pytest.mark.parametrize("path", ["docs/portless-urls.md", "dump/windows/scoop.json"])
def test_generated_artifact_is_lf_pinned(path: str) -> None:
    """The artifact must resolve to `eol=lf` via .gitattributes so every
    platform (esp. Windows, where core.autocrlf can introduce CRLF) checks it
    out as LF and the diff-based check stays stable."""
    (line,) = _eol_attr_lines([path])
    # git check-attr format: "<path>: eol: <value>"
    assert line.endswith(": lf"), (
        f"{path} must be pinned `text eol=lf` in .gitattributes so a Windows "
        f"checkout keeps LF (it is a generated, diff-checked artifact); "
        f"git check-attr reported: {line!r}"
    )


def test_go_sources_are_lf_pinned() -> None:
    """Every tracked Go source must resolve to `eol=lf`.

    `go-lint` runs `golangci-lint fmt --diff` (and gofumpt as a linter) over
    each module, and both call a CRLF working tree "File is not properly
    formatted". Nothing upstream of the working tree notices: the blob is LF
    and `git status` stays clean, so only the Windows host fails. Asserting the
    whole set rather than a sample means a new `.go` file is covered on
    arrival."""
    files = _tracked("*.go")
    assert files, "expected tracked Go sources to check the *.go pin against"
    lines = _eol_attr_lines(files)
    offenders = [line for line in lines if not line.endswith(": lf")]
    assert len(lines) == len(files) and not offenders, (
        f"every tracked *.go file must be pinned `text eol=lf` in "
        f".gitattributes (gofmt / gofumpt reject a CRLF working tree); "
        f"git check-attr returned {len(lines)} lines for {len(files)} files, "
        f"offenders: {offenders[:5]!r}"
    )
