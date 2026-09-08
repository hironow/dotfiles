"""Behavioural + wiring tests for `scripts/retired_python_tools.sh` (detect / prune).

ADR 0044 retired mypy and pyright and made mise the single provider of ruff and
ty; a machine that predates the switch still carries the old copies (uv tool
mypy / ruff, a Homebrew ruff, pyright as a rogue npm global under
<prefix>/lib/node_modules, mise versions no config pins, the mypy VS Code
extension). `just doctor` runs `detect` and `just prune-retired-python-tools`
runs `prune`. Everything the script talks to is injected so this runs host-side
with no real uv / brew / mise / code: those four are STUBS on PATH that log
their argv and the uv tool dir is a temp dir; unmanaged mise versions come from
`mise ls <tool>` itself (a row with no config `.toml` source column, exactly what
mise shows for an orphan), so a project-local mise.toml pin is never mistaken
for an orphan. The VS Code extension is reported but never removed, and a
project-local node_modules/pyright is never touched.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from _bash_hook import resolve_bash
from _symlinks import requires_symlinks

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "retired_python_tools.sh"
BASH = resolve_bash()

_STUB = """#!/usr/bin/env bash
printf '%s\\n' "$(basename "$0") $*" >> "$STUB_LOG"
{body}
"""


def _stub(bindir: Path, name: str, body: str) -> None:
    p = bindir / name
    p.write_text(_STUB.format(body=body), encoding="utf-8")
    p.chmod(0o755)


@pytest.fixture
def machine(tmp_path: Path) -> dict[str, Path]:
    """A pre-switch Mac: every retired artefact present, plus things that must survive."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # rogue npm-global pyright: symlinks in bin -> <prefix>/lib/node_modules/pyright
    nm = tmp_path / "prefix" / "lib" / "node_modules" / "pyright"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("stub", encoding="utf-8")
    (nm / "langserver.index.js").write_text("stub", encoding="utf-8")
    (nm / "package.json").write_text('{"name":"pyright"}', encoding="utf-8")
    os.symlink(nm / "index.js", bindir / "pyright")
    os.symlink(nm / "langserver.index.js", bindir / "pyright-langserver")
    keep = tmp_path / "prefix" / "lib" / "node_modules" / "leftpad"
    keep.mkdir()
    (keep / "package.json").write_text('{"name":"leftpad"}', encoding="utf-8")
    # uv tool installs: mypy + ruff (retired), marimo (must survive)
    uvtools = tmp_path / "uv-tools"
    for name in ("mypy", "ruff", "marimo"):
        (uvtools / name).mkdir(parents=True)
    for exe in ("mypy", "dmypy"):
        (bindir / exe).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (bindir / exe).chmod(0o755)
    # stubs
    log = tmp_path / "stub.log"
    _stub(bindir, "uv", "exit 0")
    _stub(bindir, "brew", 'if [ "$1" = list ]; then printf "jq\\nruff\\n"; fi; exit 0')
    # `mise ls <tool>`: managed rows carry the config .toml source column, an
    # orphan row has none (real format, 2026-09-08).
    _stub(
        bindir,
        "mise",
        'if [ "$1" = ls ]; then case "$2" in\n'
        '  ruff) printf "ruff  0.12.7\\nruff  0.15.22  ~/.config/mise/config.toml  0.15.22\\nruff  0.16.6  /work/proj/mise.toml  0.16.6\\n" ;;\n'
        '  ty) printf "ty  0.0.77  ~/.config/mise/config.toml  0.0.77\\n" ;;\n'
        "esac; fi; exit 0",
    )
    _stub(
        bindir,
        "code",
        'if [ "$1" = --list-extensions ]; then printf "esbenp.prettier-vscode\\nms-python.mypy-type-checker\\n"; fi; exit 0',
    )
    return {"bin": bindir, "uvtools": uvtools, "log": log, "nm": nm, "keep": keep}


def _run(
    mode: str, m: dict[str, Path], *, drop: tuple[str, ...] = ()
) -> subprocess.CompletedProcess[str]:
    for name in drop:
        (m["bin"] / name).unlink()
    return subprocess.run(
        [BASH, str(SCRIPT), mode],
        env={
            "PATH": f"{m['bin']}:/usr/bin:/bin",
            "HOME": str(m["bin"].parent),
            "STUB_LOG": str(m["log"]),
            "UV_TOOL_DIR": str(m["uvtools"]),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


@requires_symlinks
def test_detect_reports_every_retired_artefact(machine: dict[str, Path]) -> None:
    r = _run("detect", machine)
    assert r.returncode == 0, r.stderr
    lines = set(r.stdout.splitlines())
    assert f"path:pyright:{machine['bin'] / 'pyright'}" in lines
    assert f"path:mypy:{machine['bin'] / 'mypy'}" in lines
    assert "uv-tool:mypy" in lines and "uv-tool:ruff" in lines
    assert "brew:ruff" in lines
    assert "mise-unmanaged:ruff@0.12.7" in lines
    assert "mise-unmanaged:ruff@0.16.6" not in lines  # pinned by a project mise.toml
    assert "vscode:ms-python.mypy-type-checker" in lines
    assert not [
        line
        for line in lines
        if "marimo" in line or "0.15.22" in line or "ty@" in line or "latest" in line
    ]


def test_detect_is_silent_and_zero_on_a_clean_machine(tmp_path: Path) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (tmp_path / "uv-tools" / "marimo").mkdir(parents=True)
    cfg = tmp_path / "mise-config.toml"
    cfg.write_text('[tools]\nruff = "0.15.22"\nty = "0.0.77"\n', encoding="utf-8")
    installs = tmp_path / "mise-installs"
    (installs / "ruff" / "0.15.22").mkdir(parents=True)
    (installs / "ty" / "0.0.77").mkdir(parents=True)
    m = {
        "bin": bindir,
        "uvtools": tmp_path / "uv-tools",
        "mise_cfg": cfg,
        "installs": installs,
        "log": tmp_path / "log",
    }
    r = _run("detect", m)  # no brew / code / uv / mise on PATH at all
    assert r.returncode == 0 and r.stdout.strip() == "", (r.stdout, r.stderr)


@requires_symlinks
def test_prune_removes_the_retired_copies_and_nothing_else(
    machine: dict[str, Path],
) -> None:
    r = _run("prune", machine)
    assert r.returncode == 0, r.stderr
    calls = machine["log"].read_text(encoding="utf-8").splitlines()
    assert "uv tool uninstall mypy" in calls and "uv tool uninstall ruff" in calls
    assert "brew uninstall ruff" in calls
    assert "mise uninstall ruff@0.12.7" in calls
    assert not [c for c in calls if "0.15.22" in c or "ty@" in c or "marimo" in c]
    assert not [c for c in calls if c.startswith("code --uninstall")]
    assert not machine["nm"].exists() and machine["keep"].exists()
    assert (
        not (machine["bin"] / "pyright").exists()
        and not (machine["bin"] / "pyright-langserver").exists()
    )
    assert (
        "vscode:ms-python.mypy-type-checker" in r.stdout
    )  # reported, left to the human


@requires_symlinks
def test_prune_and_detect_survive_missing_brew_and_code(
    machine: dict[str, Path],
) -> None:
    r = _run("prune", machine, drop=("brew", "code"))
    assert r.returncode == 0, r.stderr
    calls = machine["log"].read_text(encoding="utf-8").splitlines()
    assert "uv tool uninstall mypy" in calls and not [
        c for c in calls if c.startswith("brew")
    ]


@requires_symlinks
def test_prune_leaves_a_project_local_node_modules_pyright_alone(
    machine: dict[str, Path],
) -> None:
    """A repo with node_modules/.bin on PATH must not lose its own pyright."""
    proj = machine["bin"].parent / "proj"
    local = proj / "node_modules" / "pyright"
    local.mkdir(parents=True)
    (local / "index.js").write_text("stub", encoding="utf-8")
    dotbin = proj / "node_modules" / ".bin"
    dotbin.mkdir()
    os.symlink(local / "index.js", dotbin / "pyright")
    # put the project bin FIRST on PATH and drop the global pyright
    (machine["bin"] / "pyright").unlink()
    (machine["bin"] / "pyright-langserver").unlink()
    r = subprocess.run(
        [BASH, str(SCRIPT), "prune"],
        env={
            "PATH": f"{dotbin}:{machine['bin']}:/usr/bin:/bin",
            "HOME": str(machine["bin"].parent),
            "STUB_LOG": str(machine["log"]),
            "UV_TOOL_DIR": str(machine["uvtools"]),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 0, r.stderr
    assert local.exists() and (dotbin / "pyright").exists()
    assert f"left path:pyright:{dotbin / 'pyright'}" in r.stdout


def test_unknown_mode_is_a_usage_error() -> None:
    r = subprocess.run(
        [BASH, str(SCRIPT), "bogus"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert r.returncode == 2 and "usage" in r.stderr


# --- wiring guards (static parse, like test_doctor_npm_rogue.py) ---------------


def test_doctor_runs_the_detector_cross_platform() -> None:
    doctor = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    assert "retired_python_tools.sh detect" in doctor
    assert "python-retired" in doctor, "doctor must label the check 'python-retired'"
    assert "just prune-retired-python-tools" in doctor, (
        "doctor must hint the fix recipe"
    )
    assert doctor.index("retired_python_tools.sh detect") < doctor.index(
        'case "$(uname -s)" in'
    )


def test_justfile_has_the_prune_recipe() -> None:
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "\nprune-retired-python-tools:\n" in justfile
    assert "retired_python_tools.sh prune" in justfile
