"""`fmt`, `lint`, and `check` hand vp the same JS/TS files, and no JS/TS goes unchecked.

The three recipes used to spell the pathspec out on their own, so an exclusion
added to one could be missed in another and the gates would disagree about
which files are ours. One justfile variable holds the list.

vp needs a package to run in. The repo has one JS package, site/ (the Pages
site, ADR-0076), so vp runs there with `-C site` and the list is relative to it.
A JS/TS file anywhere else would be checked by nothing, so the rest of the
tracked JS/TS must be files another gate covers.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"

_VP_LINE = re.compile(
    r"^\s+git -C site --work-tree=\.\. ls-files -z (.+?) \| xargs -0 -r mise x -- vp -C site (\w+)\s*$"
)
_JS_PATTERNS = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs", "*.mts", "*.cts")
# Tracked JS/TS outside vp's package, and the gate that covers each.
_OTHER_GATES = {
    "config/pi/extensions/": "just pi-jev-test (bun build)",
    "tests/unit/jev_sonnet_fallback.test.ts": "just pi-jev-test (bun test)",
    "site/vendor/": "tests/unit/test_site_vendor.py (SHA-256 of npm's bytes)",
}


def _vp_lines() -> dict[str, str]:
    lines = {}
    for raw in JUSTFILE.read_text(encoding="utf-8").splitlines():
        match = _VP_LINE.match(raw)
        if match:
            lines[match.group(2)] = match.group(1)
    return lines


def test_every_vp_gate_reads_the_one_file_list() -> None:
    lines = _vp_lines()
    assert set(lines) == {"fmt", "lint", "check"}, lines
    assert all(spec == "{{ JS_FILES }}" for spec in lines.values()), lines
    assert " vp fmt" not in JUSTFILE.read_text(encoding="utf-8"), "vp outside site/"


def test_the_file_list_is_declared_once() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    assert len(re.findall(r"^JS_FILES := ", text, re.MULTILINE)) == 1
    assert text.count("'*.mts' '*.cts'") == 1, "the pathspec is written out again"
    assert (ROOT / "site" / "package.json").is_file(), "vp's package"


@pytest.mark.skipif(
    shutil.which("git") is None, reason="needs git to list tracked files"
)
def test_every_tracked_js_file_has_a_gate() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--", *_JS_PATTERNS],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.split()
    (js_files,) = re.findall(
        r'^JS_FILES := "(.+)"$', JUSTFILE.read_text(encoding="utf-8"), re.MULTILINE
    )
    checked_by_vp = {
        f"site/{name}"
        for name in subprocess.run(
            ["git", "-C", "site", "ls-files", "--", *shlex.split(js_files)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.split()
    }
    unchecked = [
        name
        for name in tracked
        if name not in checked_by_vp
        and not any(name.startswith(gated) for gated in _OTHER_GATES)
    ]
    assert unchecked == [], (
        f"JS/TS no gate checks; put it in site/ or name its gate: {unchecked}"
    )


@pytest.mark.skipif(
    shutil.which("git") is None, reason="needs git to list tracked files"
)
def test_the_list_holds_inside_a_git_hook() -> None:
    # A git hook runs with GIT_DIR set. `git -C site` then takes site/ as the
    # top of the work tree: paths come back as site/... and `:!vendor/**`
    # matches nothing, so vp got the vendored files (and none it could open).
    # --work-tree=.. keeps the paths relative to site/ either way.
    (js_files,) = re.findall(
        r'^JS_FILES := "(.+)"$', JUSTFILE.read_text(encoding="utf-8"), re.MULTILINE
    )
    git_dir = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    ).stdout.strip()
    command = [
        "git",
        "-C",
        "site",
        "--work-tree=..",
        "ls-files",
        "--",
        *shlex.split(js_files),
    ]
    for env in ({}, {"GIT_DIR": git_dir}):
        listed = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, **env},
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            errors="replace",
        ).stdout.split()
        assert listed == ["copy.js"], (env, listed[:5])
