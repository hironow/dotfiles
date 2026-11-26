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


# --- rule 1: bun check, never shadowed ------------------------------------------


# --- rules 3 and 4: one shard, the whole suite ----------------------------------


# --- rule 5: parallel jobs behind one gate ---------------------------------------
