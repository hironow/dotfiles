"""Behavioural tests for `scripts/rogue_npm_globals.sh` (detect / prune).

A stray `npm install -g` of a mise-managed AI CLI (codex's `codex update`
above all) lands in the active node version's global and shadows the mise
npm-backend copy on PATH — per node version, so cleaning one leaves others.
This script scans every node version's global and removes those rogue copies.

`ROGUE_NODE_INSTALLS_DIR` overrides the scanned `installs/node` dir so these
run host-side with no mise/node/Docker. They assert BOTH npm global layouts
(Windows prefix-root `<ver>/node_modules/<pkg>` + bin `<ver>/<bin>{.cmd}`, and
Unix `<ver>/lib/node_modules/<pkg>` + bin `<ver>/bin/<bin>`), that a
non-managed package is never touched, and that an unresolvable installs dir
makes prune REFUSE (never delete) rather than fall through to the CWD.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "rogue_npm_globals.sh"
BASH = shutil.which("bash") or "/bin/bash"


def _run(mode: str, installs_dir: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, str(SCRIPT), mode],
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/tmp",
            "ROGUE_NODE_INSTALLS_DIR": installs_dir,
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _make_windows_rogue(installs: Path, ver: str, pkg: str, bin_name: str) -> None:
    """npm global on Windows: package under <ver>/node_modules, bins in <ver>/."""
    pkgdir = installs / ver / "node_modules" / pkg
    pkgdir.mkdir(parents=True, exist_ok=True)
    (pkgdir / "package.json").write_text('{"name":"%s"}' % pkg, encoding="utf-8")
    for suffix in ("", ".cmd", ".ps1"):
        (installs / ver / f"{bin_name}{suffix}").write_text("stub", encoding="utf-8")


def _make_unix_rogue(installs: Path, ver: str, pkg: str, bin_name: str) -> None:
    """npm global on Unix: package under <ver>/lib/node_modules, bin in <ver>/bin."""
    pkgdir = installs / ver / "lib" / "node_modules" / pkg
    pkgdir.mkdir(parents=True, exist_ok=True)
    (pkgdir / "package.json").write_text('{"name":"%s"}' % pkg, encoding="utf-8")
    bindir = installs / ver / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    (bindir / bin_name).write_text("stub", encoding="utf-8")


@pytest.fixture
def installs(tmp_path: Path) -> Path:
    """Two node versions with rogue codex (win layout) + claude (unix layout),
    plus a non-managed `leftpad` that must survive."""
    d = tmp_path / "installs" / "node"
    _make_windows_rogue(d, "24.15.0", "@openai/codex", "codex")
    _make_unix_rogue(d, "22.9.0", "@anthropic-ai/claude-code", "claude")
    # non-managed package — must never be pruned
    lp = d / "24.15.0" / "node_modules" / "leftpad"
    lp.mkdir(parents=True, exist_ok=True)
    (lp / "package.json").write_text('{"name":"leftpad"}', encoding="utf-8")
    return d


def test_detect_reports_both_layouts_not_unmanaged(installs: Path) -> None:
    r = _run("detect", str(installs))
    assert r.returncode == 0, r.stderr
    lines = {ln for ln in r.stdout.splitlines() if ln}
    assert "24.15.0:@openai/codex:codex" in lines, r.stdout
    assert "22.9.0:@anthropic-ai/claude-code:claude" in lines, r.stdout
    assert not any("leftpad" in ln for ln in lines), (
        f"non-managed package must not be reported: {lines}"
    )


def test_prune_removes_rogue_both_layouts_keeps_unmanaged(installs: Path) -> None:
    r = _run("prune", str(installs))
    assert r.returncode == 0, r.stderr
    # rogue codex (win layout) gone: package dir + all bin shims
    assert not (installs / "24.15.0" / "node_modules" / "@openai" / "codex").exists()
    for suffix in ("", ".cmd", ".ps1"):
        assert not (installs / "24.15.0" / f"codex{suffix}").exists()
    # rogue claude (unix layout) gone: lib/node_modules pkg + bin/claude
    assert not (
        installs / "22.9.0" / "lib" / "node_modules" / "@anthropic-ai" / "claude-code"
    ).exists()
    assert not (installs / "22.9.0" / "bin" / "claude").exists()
    # non-managed package preserved
    assert (installs / "24.15.0" / "node_modules" / "leftpad" / "package.json").exists()
    # a second prune is a clean no-op (idempotent)
    r2 = _run("prune", str(installs))
    assert r2.returncode == 0 and "pruned: 0" in r2.stdout, r2.stdout


def test_prune_refuses_when_installs_dir_unresolvable(tmp_path: Path) -> None:
    """A non-existent override must make prune REFUSE (non-zero, delete
    nothing) — never fall through to `dirname ''` == CWD."""
    missing = tmp_path / "does-not-exist"
    r = _run("prune", str(missing))
    assert r.returncode != 0, (
        f"prune must refuse an unresolvable installs dir; got rc=0\n{r.stdout}"
    )
    assert "pruned" not in r.stdout.lower() or "pruned: 0" not in r.stdout


def test_detect_nonzero_when_unresolvable(tmp_path: Path) -> None:
    """detect must exit non-zero (not a false 'clean') when the dir is
    unresolvable, so the doctor warns instead of reporting OK."""
    r = _run("detect", str(tmp_path / "nope"))
    assert r.returncode != 0, f"detect must not report clean on error: {r.stdout!r}"
