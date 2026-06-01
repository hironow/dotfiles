"""Regression tests for justfile deploy/clean Windows native subset (ADR 0018).

What this guards
----------------
ADR 0018 (Accepted 2026-06-02) decides that `just deploy` / `just clean`
on Windows native handle only a *cross-platform subset* of the deploy
targets: `starship.toml` and `dump/gitignore-global`. Unix-only assets
(zsh / sheldon / tmux / ghostty / fzf-tab) are intentionally skipped
because the underlying tools are not present on Windows native.

These tests static-parse the justfile to verify the `deploy` and `clean`
recipes contain the expected MSYS/MINGW/CYGWIN branch and that the branch
body contains the subset (and nothing more). The Linux sandbox tests in
`test_just_sandbox.py` continue to cover the macOS/Linux path end-to-end.

Why these exist
---------------
Running `just deploy` on Windows native cannot be exercised in the Linux
devcontainer sandbox (uname is Linux there), so a regression where the
windows branch is removed / mangled / silently drops the subset would
only surface on a real Windows host. Static-parse guards make that
regression visible at PR-review time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
JUSTFILE = ROOT / "justfile"


@pytest.fixture(scope="module")
def justfile_text() -> str:
    assert JUSTFILE.is_file(), f"justfile missing at {JUSTFILE}"
    return JUSTFILE.read_text(encoding="utf-8")


def _extract_recipe_body(text: str, name: str) -> str:
    """Return the body of a top-level recipe, stopping at the next recipe
    header (a line that starts at column 0 and contains `:`)."""
    # Match `^name:` at column 0, then capture until the next column-0
    # non-comment, non-blank line that looks like a recipe header
    # (`word(s):` optionally followed by deps).
    m = re.search(
        rf"(?ms)^{re.escape(name)}\s*:.*?\n(.*?)(?=^[A-Za-z_][\w-]*\s*(?:[^\n=]*?)?:\s*\n|\Z)",
        text,
    )
    assert m is not None, f"recipe {name!r} not found in justfile"
    return m.group(1)


def _extract_windows_branch(body: str) -> str:
    """Return the body of the `MINGW*|MSYS*|CYGWIN*)` case branch, up to
    the first `;;`."""
    m = re.search(
        r"(?:MINGW\*\|MSYS\*\|CYGWIN\*|MSYS\*\|MINGW\*\|CYGWIN\*)\)([\s\S]*?);;",
        body,
    )
    assert m is not None, "windows (MSYS/MINGW/CYGWIN) case branch not found"
    return m.group(1)


# ---------- deploy --------------------------------------------------


def test_deploy_has_windows_branch(justfile_text: str) -> None:
    """ADR 0018: `just deploy` must dispatch on uname and handle Windows
    native explicitly. Without this branch, deploy would try to symlink
    zsh/sheldon/tmux artifacts on Windows where they make no sense."""
    body = _extract_recipe_body(justfile_text, "deploy")
    assert re.search(
        r'case\s+"\$\(uname\s+-s\)"\s+in',
        body,
    ), "deploy recipe must dispatch on `uname -s`"
    _extract_windows_branch(body)  # raises if missing


def test_deploy_windows_subset_places_cross_platform_only(
    justfile_text: str,
) -> None:
    """The windows branch must place exactly the cross-platform subset:
    starship.toml and gitignore-global. Anything else (zsh, sheldon,
    tmux, ghostty, fzf-tab) is Unix-only and must NOT appear in the
    windows branch — they belong on the Linux/macOS path below."""
    body = _extract_recipe_body(justfile_text, "deploy")
    win = _extract_windows_branch(body)

    # Required cross-platform placements.
    assert "starship.toml" in win, (
        "deploy windows branch must place starship.toml (ADR 0018 subset)"
    )
    assert "gitignore-global" in win, (
        "deploy windows branch must place dump/gitignore-global (ADR 0018 subset)"
    )

    # Forbidden Unix-only placements.
    for forbidden in (
        ".zshrc",
        "sheldon-plugins.toml",
        "tmux.conf",
        "ghostty",
        "fzf-tab",
    ):
        assert forbidden not in win, (
            f"deploy windows branch leaked Unix-only token {forbidden!r}. "
            f"ADR 0018 limits the Windows subset to starship + git ignore."
        )

    # Windows branch must terminate early (exit 0) so the unix code below
    # is not executed on Windows.
    assert re.search(r"\bexit\s+0\b", win), (
        "deploy windows branch must `exit 0` after placing the subset, "
        "otherwise the Unix-only ln -sf block runs and fails on Windows."
    )


# ---------- clean ---------------------------------------------------


def test_clean_has_windows_branch(justfile_text: str) -> None:
    """ADR 0018: `just clean` must mirror deploy and remove only what
    deploy placed on Windows."""
    body = _extract_recipe_body(justfile_text, "clean")
    assert re.search(
        r'case\s+"\$\(uname\s+-s\)"\s+in',
        body,
    ), "clean recipe must dispatch on `uname -s`"
    _extract_windows_branch(body)  # raises if missing


def test_clean_windows_subset_removes_only_what_deploy_placed(
    justfile_text: str,
) -> None:
    """Symmetry with deploy: clean must remove the same files (starship
    + git ignore) and nothing Unix-only."""
    body = _extract_recipe_body(justfile_text, "clean")
    win = _extract_windows_branch(body)

    assert "starship.toml" in win, (
        "clean windows branch must remove ~/.config/starship.toml"
    )
    assert re.search(r"git/ignore|gitignore-global", win), (
        "clean windows branch must remove ~/.config/git/ignore"
    )

    for forbidden in (".zshrc", "sheldon", "tmux", "ghostty"):
        assert forbidden not in win, (
            f"clean windows branch leaked Unix-only token {forbidden!r}. "
            f"ADR 0018 limits the Windows subset to starship + git ignore."
        )

    assert re.search(r"\bexit\s+0\b", win), (
        "clean windows branch must `exit 0` so the Unix-only rm block does not run."
    )
