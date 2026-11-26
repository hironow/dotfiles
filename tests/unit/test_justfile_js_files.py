"""`fmt` and `check` hand vp the same JS/TS files to format, and no JS/TS goes unchecked.

The recipes used to spell the pathspec out on their own, so an exclusion added
to one could be missed in another and the gates would disagree about which
files are ours. One justfile variable holds the list.

vp only formats (ADR-0079: oxlint lints and bun check type checks, see
test_frontend_ci_conformance.py). It needs a package to run in, so it runs in
site/, the Pages site's package (ADR-0076), with `-C site`, and the list is
relative to it. A JS/TS file anywhere else must be one another gate covers.
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

_JS_PATTERNS = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs", "*.mts", "*.cts")
# Tracked JS/TS outside vp's package, and the gate that covers each.
_OTHER_GATES = {
    "config/pi/extensions/": "just js-lint, js-typecheck, js-build",
    "tests/unit/jev_sonnet_fallback.test.ts": "just js-lint, js-typecheck, js-test",
    "site/vendor/": "tests/unit/test_site_vendor.py (SHA-256 of npm's bytes)",
    ".semgrep/": "just semgrep-test (Semgrep rule fixtures)",
}


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
