"""`.gitattributes` must pin generated, diff-checked artifacts to LF on every OS.

`dump/windows/scoop.json` is a generated artifact that recipes diff byte for
byte. Without an `eol=lf` pin a Windows checkout yields CRLF, and the raw diff
reports it stale even though the committed blob is LF — git normalizes on
compare, so `git status` stays clean and the breakage surfaces only in the diff.
See ADR 0019, and `*.sh` / `*.bash` (ADR 0020).
Go sources are pinned for a different tool: gofmt / gofumpt — reached through
`golangci-lint run` and `golangci-lint fmt --diff` in `go-lint` — report a CRLF
working tree as "File is not properly formatted", so an untouched `.go` file
fails `just check` on a Windows host while the committed blob is LF.
The `tools/*-doctor` modules embed their own data files and compare the
embedded bytes with the working tree to detect a stale binary, so those files
need the same pin: a CRLF checkout would report a stale build that does not
exist. That set is derived from the `//go:embed` directives, so a new doctor is
covered without editing this file.
"""

from __future__ import annotations

import re
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


@pytest.mark.parametrize("path", ["dump/windows/scoop.json"])
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


_EMBED = re.compile(r"^//go:embed (.+)$", re.MULTILINE)


def _embedded_data_patterns(module: Path) -> list[str]:
    """The non-Go patterns in a module's `//go:embed` directives."""
    text = (module / "integrity.go").read_text(encoding="utf-8")
    patterns = [
        pattern for match in _EMBED.finditer(text) for pattern in match.group(1).split()
    ]
    return [pattern for pattern in patterns if not pattern.endswith(".go")]


def test_embedded_data_files_are_lf_pinned() -> None:
    """Data embedded for byte comparison must be LF on every OS.

    `SourceMatches` compares the embedded bytes against the working tree, so a
    CRLF checkout reports a stale binary for a commit that did not change —
    exactly the false alarm the LF pin exists to prevent. The set is read from
    the embed directives rather than listed here, so a future doctor module is
    covered on arrival instead of on its first Windows failure.
    """
    modules = sorted(p.parent for p in (ROOT / "tools").glob("*/integrity.go"))
    assert modules, "expected a tools/*/integrity.go to check"
    checked = 0
    for module in modules:
        patterns = _embedded_data_patterns(module)
        assert patterns, f"{module.name} embeds no data file to pin"
        for pattern in patterns:
            pathspec = f"{module.relative_to(ROOT).as_posix()}/{pattern}"
            files = _tracked(pathspec)
            assert files, f"nothing tracked matches {pathspec}"
            offenders = [
                line for line in _eol_attr_lines(files) if not line.endswith(": lf")
            ]
            assert not offenders, (
                f"{pathspec} must be pinned `text eol=lf` in .gitattributes: "
                f"{module.name} embeds these bytes and compares them with the "
                f"working tree, so CRLF reports a stale build for an unchanged "
                f"commit; offenders: {offenders[:5]!r}"
            )
            checked += len(files)
    assert checked > 0
