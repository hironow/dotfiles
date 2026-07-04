"""Windows-native fresh-machine setup recipes (static-parse guards).

The Linux sandbox can't exercise a `uname`=MINGW branch, so these guard the
Windows setup additions against regression at PR-review time:

- `add-scoop` restores scoop apps from dump/<host>/scoop.json (ADR 0032, supersedes
  0019's record-only stance) via native `scoop import` — no jq (jq is itself a
  recorded app, so a jq-parsing restore would be self-defeating).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

JUSTFILE = Path(__file__).resolve().parents[2] / "justfile"


@pytest.fixture(scope="module")
def justfile_text() -> str:
    return JUSTFILE.read_text(encoding="utf-8")


def _recipe_body(text: str, name: str) -> str:
    m = re.search(
        rf"(?ms)^{re.escape(name)}[^:\n]*:.*?\n(.*?)(?=^[A-Za-z_][\w-]*[^:\n]*:|\Z)",
        text,
    )
    assert m is not None, f"recipe {name!r} not found in justfile"
    return m.group(1)


def test_add_scoop_restores_from_dump_via_scoop_import(justfile_text: str) -> None:
    body = _recipe_body(justfile_text, "add-scoop")
    assert "scoop.json" in body and "resolve-restore" in body, (
        "add-scoop must read the per-host dump/<host>/scoop.json, resolving the "
        "host via scripts/dump_host.sh resolve-restore (ADR 0030 per-host layout)"
    )
    assert "scoop import" in body, (
        "add-scoop must restore via native `scoop import` (ADR 0032)"
    )
    assert re.search(r'case\s+"\$\(uname\s+-s\)"\s+in', body) and "MINGW" in body, (
        "add-scoop must be Windows-guarded (scoop is Windows-only)"
    )


def test_add_scoop_has_no_jq_dependency(justfile_text: str) -> None:
    """jq is one of the recorded apps, so a jq-parsing restore would be
    self-defeating on a fresh host (ADR 0032). Restore must use scoop import."""
    body = _recipe_body(justfile_text, "add-scoop")
    assert "jq" not in body, (
        "add-scoop must not depend on jq — it is one of the apps being restored"
    )


def test_deploy_windows_installs_global_mise_tools(justfile_text: str) -> None:
    """ADR 0033: the deploy Windows branch must install the global mise toolset
    (not just copy the config), with the corepack guard so the node install does
    not EPERM (ADR 0031). The `MISE_NODE_COREPACK=0 mise -C / install` form is
    unique to the Windows branch (the Unix path omits the env prefix)."""
    body = _recipe_body(justfile_text, "deploy")
    assert "MISE_NODE_COREPACK=0 mise -C / install" in body, (
        "deploy Windows branch must run `MISE_NODE_COREPACK=0 mise -C / install` "
        "so global tools (starship/fzf/eza/portless/...) actually install on "
        "Windows and node does not hit the corepack EPERM (ADR 0031/0033)"
    )


def test_deploy_wires_git_aliases_only_never_shared(justfile_text: str) -> None:
    """ADR 0033/0021: deploy wires ONLY aliases.gitconfig into ~/.gitconfig, and
    must NEVER re-include shared.gitconfig — re-including shared after a manual
    PC-local override (e.g. gpgsign=false on a keyless host) would clobber it.
    clean must remove the managed block."""
    deploy = _recipe_body(justfile_text, "deploy")
    assert "aliases.gitconfig" in deploy, (
        "deploy Windows branch must include aliases.gitconfig (the observed gap)"
    )
    assert not re.search(r"path\s*=\s*\S*shared\.gitconfig", deploy), (
        "deploy must NOT `[include]` shared.gitconfig — re-including it after a "
        "manual PC-local gpgsign override would clobber it (ADR 0033/0021). "
        "(A comment mentioning shared.gitconfig is fine; an include path is not.)"
    )
    clean = _recipe_body(justfile_text, "clean")
    assert "git aliases include" in clean, (
        "clean must remove the git-aliases managed block (deploy/clean symmetry)"
    )
