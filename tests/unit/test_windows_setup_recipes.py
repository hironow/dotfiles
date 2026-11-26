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
    # deploy/clean bodies live in scripts/*.sh (linewise wrappers; shebang
    # recipes break from PowerShell — tests/unit/test_deploy_clean_linewise.py).
    if name in ("deploy", "clean"):
        scripts = JUSTFILE.parent / "scripts" / f"{name}.sh"
        return scripts.read_text(encoding="utf-8")
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
