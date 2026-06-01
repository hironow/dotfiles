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


# ---------- dump (ADR 0019) -----------------------------------------


def test_dump_has_windows_branch(justfile_text: str) -> None:
    """ADR 0019: `just dump` must dispatch on uname and handle Windows
    native explicitly. Without this branch, dump would try to run brew/gcloud
    on Windows where they are absent."""
    body = _extract_recipe_body(justfile_text, "dump")
    assert re.search(
        r'case\s+"\$\(uname\s+-s\)"\s+in',
        body,
    ), "dump recipe must dispatch on `uname -s`"
    _extract_windows_branch(body)  # raises if missing


def test_dump_windows_writes_scoop_json(justfile_text: str) -> None:
    """ADR 0019: the Windows dump branch must invoke `scoop export` and
    write to `dump/scoop.json` — the record-only manifest."""
    body = _extract_recipe_body(justfile_text, "dump")
    win = _extract_windows_branch(body)
    assert "scoop export" in win, (
        "dump windows branch must call `scoop export` (ADR 0019)"
    )
    assert "dump/scoop.json" in win, (
        "dump windows branch must redirect to `dump/scoop.json` (ADR 0019)"
    )


def test_dump_windows_normalizes_with_jq(justfile_text: str) -> None:
    """ADR 0019 diff stability: scoop export emits `Updated` timestamps and
    `Manifests` counts that change on every run. The dump must filter them
    out via jq so the file is committable and reviewable.

    Asserts the jq pipe is present AND that `Updated`/`Manifests` tokens do
    not appear in the Windows branch (a re-include would defeat stability)."""
    body = _extract_recipe_body(justfile_text, "dump")
    win = _extract_windows_branch(body)
    assert re.search(r"\bjq\b", win), (
        "dump windows branch must pipe through jq to normalize scoop export"
    )
    assert "sort_by" in win, (
        "dump windows branch must sort_by(.Name) to stabilize ordering"
    )
    for noise in ("Updated", "Manifests"):
        assert noise not in win, (
            f"dump windows branch must NOT reference {noise!r} — that field "
            f"changes on every scoop export and would make dump/scoop.json "
            f"diff on every run. ADR 0019 specifies the normalized field set."
        )


def test_dump_windows_has_no_install_side(justfile_text: str) -> None:
    """ADR 0019 is *record-only*: the dump branch must NOT call
    `scoop install` (that is the bootstrap layer, deferred per ADR 0018).
    Any `add-scoop`/`scoop install` invocation here would conflate the
    two ADR's scopes."""
    body = _extract_recipe_body(justfile_text, "dump")
    win = _extract_windows_branch(body)
    assert "scoop install" not in win, (
        "dump windows branch must NOT call `scoop install` — ADR 0019 is "
        "record-only; bootstrap remains future work per ADR 0018."
    )


def test_dump_windows_exits_before_unix_path(justfile_text: str) -> None:
    """The Windows branch must `exit 0` so the Mac/Linux tail (brew bundle,
    gcloud components) does not run on Windows where those tools are absent."""
    body = _extract_recipe_body(justfile_text, "dump")
    win = _extract_windows_branch(body)
    assert re.search(r"\bexit\s+0\b", win), (
        "dump windows branch must `exit 0` before the Mac/Linux `brew bundle "
        "dump` block, otherwise scoop hosts will hit brew not-found errors."
    )


# ---------- PowerShell $PROFILE starship init (ADR 0022) ------------


PS_MARKER_BEGIN = "# >>> dotfiles managed block: starship init >>>"
PS_MARKER_END = "# <<< end dotfiles managed block <<<"


def test_deploy_windows_writes_powershell_profile_init(
    justfile_text: str,
) -> None:
    """ADR 0022: deploy Windows branch must wire starship into PowerShell 7's
    $PROFILE. Without this, placing starship.toml is a no-op on Windows
    because the shell never invokes `starship init`."""
    body = _extract_recipe_body(justfile_text, "deploy")
    win = _extract_windows_branch(body)
    assert "Microsoft.PowerShell_profile.ps1" in win, (
        "deploy windows branch must reference the PowerShell 7 profile path "
        "(ADR 0022 targets PS7 only)"
    )
    assert PS_MARKER_BEGIN in win, (
        "deploy windows branch must include the begin marker so the block "
        "can be detected for idempotency and removed by clean"
    )
    assert PS_MARKER_END in win, (
        "deploy windows branch must include the end marker so sed range "
        "deletion in clean has both anchors"
    )
    assert "Invoke-Expression (&starship init powershell)" in win, (
        "deploy windows branch must emit the canonical starship init line"
    )
    assert "Get-Command starship -ErrorAction SilentlyContinue" in win, (
        "deploy windows branch must guard with Get-Command so PowerShell "
        "does not error on hosts where starship is not yet installed "
        "(parity with .zshrc's _cmd_exists guard)"
    )


def test_deploy_windows_powershell_init_is_idempotent(
    justfile_text: str,
) -> None:
    """ADR 0022 requires the deploy block to be idempotent: running `just
    deploy` twice must not duplicate the marker block in $PROFILE.

    Asserts a `grep -qF` marker check exists AND that the writing path uses
    append (`>>`) rather than overwrite (`>`), so other operator content in
    $PROFILE is preserved."""
    body = _extract_recipe_body(justfile_text, "deploy")
    win = _extract_windows_branch(body)
    assert "grep -qF" in win, (
        "deploy windows branch must `grep -qF` for the marker before "
        "writing, to make the block placement idempotent"
    )
    # The append redirection should target $ps_profile. Allow optional
    # whitespace between `>>` and the variable.
    assert re.search(r'>>\s*"\$ps_profile"', win), (
        "deploy windows branch must append (>>) to $ps_profile, not "
        "overwrite (>), so existing operator content is preserved"
    )


def test_clean_windows_removes_powershell_profile_init(
    justfile_text: str,
) -> None:
    """ADR 0022 symmetry: clean must remove the marker block from $PROFILE
    so a deploy/clean roundtrip leaves the file in its pre-deploy state
    (minus the managed block)."""
    body = _extract_recipe_body(justfile_text, "clean")
    win = _extract_windows_branch(body)
    assert "Microsoft.PowerShell_profile.ps1" in win, (
        "clean windows branch must reference the PowerShell 7 profile path"
    )
    assert "sed -i" in win, (
        "clean windows branch must use `sed -i` to delete the marker block "
        "range in-place"
    )
    assert PS_MARKER_BEGIN in win and PS_MARKER_END in win, (
        "clean windows branch must reference both markers so the sed range "
        "deletion has both anchors"
    )
    # Original `exit 0` from ADR 0018 must still be present after the
    # PowerShell block is removed, otherwise Unix-only rm lines would run.
    assert re.search(r"\bexit\s+0\b", win), (
        "clean windows branch must keep `exit 0` after the PowerShell "
        "cleanup so the Unix-only rm block does not run on Windows"
    )


# ---------- PowerShell $PROFILE mise activate (ADR 0024) ------------


PS_MISE_MARKER_BEGIN = "# >>> dotfiles managed block: mise activate >>>"


def test_deploy_windows_writes_powershell_mise_activate(
    justfile_text: str,
) -> None:
    """ADR 0024: deploy Windows branch must wire mise into PowerShell 7's
    $PROFILE so the mise-managed node/just/etc resolve correctly on
    Windows. Without this, PATH resolution falls back to whatever Program
    Files / scoop installed (per the ADR 0024 context)."""
    body = _extract_recipe_body(justfile_text, "deploy")
    win = _extract_windows_branch(body)
    assert PS_MISE_MARKER_BEGIN in win, (
        "deploy windows branch must include the mise-activate begin marker "
        "so the block can be detected for idempotency and removed by clean"
    )
    assert "Invoke-Expression (&mise activate pwsh | Out-String)" in win, (
        "deploy windows branch must emit the canonical mise activate line "
        "for PowerShell"
    )
    assert "Get-Command mise -ErrorAction SilentlyContinue" in win, (
        "deploy windows branch must guard with Get-Command so PowerShell "
        "does not error on hosts where mise is not yet installed "
        "(parity with .zshrc's _cmd_exists mise guard)"
    )


def test_deploy_windows_mise_activate_is_idempotent(
    justfile_text: str,
) -> None:
    """ADR 0024 requires the mise block to be idempotent: a `grep -qF`
    on the mise marker must guard the append. Since the starship block
    (ADR 0022) also uses `grep -qF`, the deploy Windows branch must
    contain at least TWO `grep -qF` calls — one per managed block."""
    body = _extract_recipe_body(justfile_text, "deploy")
    win = _extract_windows_branch(body)
    grep_calls = re.findall(r"grep -qF", win)
    assert len(grep_calls) >= 2, (
        f"deploy windows branch must have at least 2 `grep -qF` calls "
        f"(one per managed block: starship + mise). Found {len(grep_calls)}."
    )
    # The append redirection should target $ps_profile (same variable both
    # blocks reuse). At least 2 append redirections must exist.
    appends = re.findall(r'>>\s*"\$ps_profile"', win)
    assert len(appends) >= 2, (
        f"deploy windows branch must have at least 2 append (>>) redirections "
        f"to $ps_profile (one per managed block). Found {len(appends)}."
    )


def test_clean_windows_removes_powershell_mise_activate(
    justfile_text: str,
) -> None:
    """ADR 0024 symmetry: clean must remove the mise marker block from
    $PROFILE via a sed range deletion. The starship sed (ADR 0022)
    already exists; clean must therefore have at least TWO `sed -i`
    invocations."""
    body = _extract_recipe_body(justfile_text, "clean")
    win = _extract_windows_branch(body)
    sed_calls = re.findall(r"sed -i", win)
    assert len(sed_calls) >= 2, (
        f"clean windows branch must have at least 2 `sed -i` invocations "
        f"(one per managed block: starship + mise). Found {len(sed_calls)}."
    )
    assert PS_MISE_MARKER_BEGIN in win, (
        "clean windows branch must reference the mise begin marker so the "
        "sed range deletion targets the right block"
    )
    assert "mise activate" in win, (
        "clean windows branch must remove the mise-activate block per ADR 0024"
    )
    # `exit 0` must still terminate the branch after both removals.
    assert re.search(r"\bexit\s+0\b", win), (
        "clean windows branch must keep `exit 0` after both PowerShell "
        "block removals so the Unix-only rm block does not run on Windows"
    )
