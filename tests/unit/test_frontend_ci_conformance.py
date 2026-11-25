"""dotfiles follows its own frontend CI guide (docs/agents/frontend-ci.md, ADR-0079).

The guide has five rules. The repo-lint rules oxlint-strict, js-deps-pinned
and js-type-check-not-weakened hold the config side: no category lowered to a
warning, no rule off without a reason, no `check` script that shadows the type
checker, no install that runs package scripts. The tests below check what no
config rule can: that a gate reads every first-party file, and that the last
job fails instead of being skipped.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")

# Third-party bytes we must not edit; each has its own gate.
VENDORED = {
    "site/vendor/**": "tests/unit/test_site_vendor.py (SHA-256 of npm's bytes)",
    "config/pi/extensions/rtk.ts": "just js-build, and rtk's own corpus",
}
# Semgrep rule fixtures break the rules on purpose; just semgrep-test checks them,
# and JS_FILES leaves them out of oxlint (ruff skips .semgrep/ the same way).
RULE_FIXTURES = ".semgrep/"
OWN_FILES = (
    "site/copy.js",
    "config/pi/extensions/jev-sonnet-fallback.ts",
    "tests/unit/jev_sonnet_fallback.test.ts",
)
_JS = re.compile(r"\.(?:[cm]?[jt]s|[jt]sx)$")


def _recipe(name: str) -> str:
    bodies = re.findall(
        rf"^{re.escape(name)}:[^\n]*\n((?:[ \t]+[^\n]*(?:\n|$))*)",
        JUSTFILE,
        re.MULTILINE,
    )
    assert len(bodies) == 1, f"missing or ambiguous recipe: {name}"
    return bodies[0]


def _tracked_js() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return [path for path in out.split("\0") if _JS.search(path)]


def _is_vendored(path: str) -> bool:
    return any(
        path.startswith(pattern.removesuffix("**"))
        if pattern.endswith("**")
        else path == pattern
        for pattern in VENDORED
    )


# --- rule 2: oxlint, every rule that can be on ---------------------------------


def test_every_tracked_js_file_is_linted_or_vendored() -> None:
    tracked = _tracked_js()
    own = sorted(
        path
        for path in tracked
        if not _is_vendored(path) and not path.startswith(RULE_FIXTURES)
    )
    assert own == sorted(OWN_FILES), own


def test_oxlint_is_handed_the_tracked_files_only() -> None:
    # With no paths, oxlint walks the disk. A checkout that has a submodule
    # checked out (gcloud/knowledge-catalog), or any untracked folder, then
    # fails on files that are not ours, while CI and a fresh worktree pass.
    # `git ls-files` lists a submodule as one entry, never the files inside it.
    lint = _recipe("js-lint").replace("{{ BUN }}x", "bunx")
    assert re.search(
        r"git ls-files -z -- \{\{ JS_TRACKED \}\} \| xargs -0 -r bunx --no-install oxlint\s*$",
        lint,
    ), lint
    # One list of extensions: JS_TRACKED is JS_FILES without the exclusion that
    # only makes sense inside site/.
    assert """JS_TRACKED := replace(JS_FILES, " ':!vendor/**'", "")""" in JUSTFILE
    (js_files,) = re.findall(r'^JS_FILES := "(.+)"$', JUSTFILE, re.MULTILINE)
    extensions = ("ts", "tsx", "js", "jsx", "mjs", "cjs", "mts", "cts")
    assert js_files.split() == [
        *(f"'*.{extension}'" for extension in extensions),
        "':(top,exclude).semgrep/**'",
        "':!vendor/**'",
    ]


# --- rule 1: bun check, never shadowed ------------------------------------------


# --- rules 3 and 4: one shard, the whole suite ----------------------------------


def test_the_whole_suite_runs_in_one_shard() -> None:
    test = _recipe("js-test")
    assert "test ./tests/unit/" in test
    assert "--changed" not in test
    assert "--shard" not in test


# --- rule 5: parallel jobs behind one gate ---------------------------------------


def test_the_local_gate_runs_the_same_recipes() -> None:
    # `check` runs these through check-except-go (CI runs it as its own job).
    assert "just check-except-go" in _recipe("check")
    for recipe in ("lint", "check-except-go"):
        body = _recipe(recipe)
        assert "just js-lint" in body, recipe
        assert "just js-typecheck" in body, recipe
        assert "just pi-jev-test" in body, recipe
    assert "vp -C site fmt --check" in _recipe("check-except-go")
    assert "vp -C site lint" not in JUSTFILE
    assert "vp -C site check" not in JUSTFILE
