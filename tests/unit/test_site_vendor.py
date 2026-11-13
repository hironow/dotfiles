"""The site's copy of ui-sdk stays the bytes npm published (ADR-0076).

The Pages site hands out install commands, so it loads no third-party script
from a CDN: `just site-vendor-ui-sdk` copies the browser build of
`@ui-sdk/web` from a bun install (which checks the registry's integrity) into
site/vendor/ui-sdk/<version>/, with a SHA-256 for every file and a record of
where the bytes came from. The formatters and the end-of-file and whitespace
hooks leave the folder alone, so these checks stand in for them: any edit, a
formatter run, or a CRLF checkout on Windows fails here.
`just site-vendor-ui-sdk-check` compares the copy with the registry again.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VENDOR = ROOT / "site" / "vendor" / "ui-sdk"
_SUM_LINE = re.compile(r"^([0-9a-f]{64})  \./(.+)$")


def _version_folder() -> Path:
    folders = [p for p in VENDOR.iterdir() if p.is_dir()]
    assert len(folders) == 1, f"expected one vendored version, found {folders}"
    return folders[0]


def _sums(folder: Path) -> dict[str, str]:
    sums = {}
    for line in (folder / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = _SUM_LINE.match(line)
        assert match, f"not a `shasum -a 256` line: {line!r}"
        sums[match.group(2)] = match.group(1)
    return sums


def test_one_version_is_vendored_with_its_license_and_provenance() -> None:
    folder = _version_folder()
    provenance = json.loads((folder / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert provenance["package"] == "@ui-sdk/web"
    assert provenance["version"] == folder.name
    assert provenance["integrity"].startswith("sha512-")
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z", provenance["published"]
    )
    assert provenance["min_release_age"]
    assert (folder / "LICENSE").is_file()
    for entry in ("web.js", "web.css", "web/core.js", "web/button.js"):
        assert (folder / entry).is_file(), entry


def test_every_vendored_file_has_its_recorded_sha256() -> None:
    folder = _version_folder()
    sums = _sums(folder)
    on_disk = {
        p.relative_to(folder).as_posix()
        for p in folder.rglob("*")
        if p.is_file() and p.name != "SHA256SUMS"
    }
    assert set(sums) == on_disk, {
        "missing from SHA256SUMS": sorted(on_disk - set(sums)),
        "listed but gone": sorted(set(sums) - on_disk),
    }
    changed = [
        name
        for name, digest in sums.items()
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest
    ]
    assert changed == [], (
        f"vendored bytes changed since `just site-vendor-ui-sdk`: {changed}"
    )


@pytest.mark.skipif(
    shutil.which("git") is None, reason="needs git to read .gitattributes"
)
def test_git_never_converts_the_vendored_bytes() -> None:
    files = sorted(
        p.relative_to(ROOT).as_posix()
        for p in _version_folder().rglob("*")
        if p.is_file()
    )
    out = subprocess.run(
        ["git", "check-attr", "text", "--", *files],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.splitlines()
    converted = [line for line in out if not line.endswith(": text: unset")]
    assert len(out) == len(files) and converted == [], converted[:5]


def test_only_the_rewriting_hooks_skip_the_vendored_folder() -> None:
    config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    top_level = config.split("\nrepos:", 1)[0]
    assert "site/" not in top_level, (
        "the other hooks must still read the vendored files"
    )
    for hook in ("trailing-whitespace", "end-of-file-fixer"):
        block = re.search(rf"- id: {hook}\n((?:\s+[a-z_]+:.*\n)*)", config)
        assert block and "exclude: '^site/vendor/'" in block.group(1), hook


def test_vp_skips_the_vendored_folder_but_reads_the_site() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    (js_files,) = re.findall(r"^JS_FILES := (.+)$", justfile, re.MULTILINE)
    # JS_FILES is relative to site/, where vp runs
    assert "':!vendor/**'" in js_files
    assert "'*.js'" in js_files
