"""Image-local health contracts and the public fast Go gate (no engine)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
HEALTH = ROOT / "emulator/healthcheck"


def test_health_build_context_only_allows_production_sources() -> None:
    ignore = HEALTH / ".dockerignore"
    assert ignore.is_file(), "build context must fail closed on secrets and dist"
    assert ignore.read_text(encoding="utf-8").splitlines() == [
        "*",
        "!Dockerfile",
        "!go.mod",
        "!main.go",
    ]
    assert (HEALTH / ".gitignore").read_text(encoding="utf-8").splitlines() == [
        "/dist/"
    ]


def _run_go_gate(tmp_path: Path, justfile: str) -> list[str]:
    """Only git/go are substituted at the recipe's SYSTEM boundary."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    git = bin_dir / "git"
    git.write_text(
        '#!/bin/sh\n[ "$1" = ls-files ] && [ "$2" = -z ] || exit 91\n'
        'shift 2\nfor selector do\n  case "$selector" in\n'
        "    'tools/**/go.mod') printf 'tools/fixture/go.mod\\0' ;;\n"
        "    'emulator/healthcheck/go.mod') printf 'emulator/healthcheck/go.mod\\0' ;;\n"
        "    *) exit 92 ;;\n  esac\ndone\n",
        encoding="utf-8",
        newline="\n",
    )
    go = bin_dir / "go-boundary"
    go.write_text(
        '#!/bin/sh\n[ "$*" = "test -short ./..." ] || exit 93\n'
        'printf "%s\\n" "$PWD" >> "$GATE_LOG"\n',
        encoding="utf-8",
        newline="\n",
    )
    git.chmod(0o755)
    go.chmod(0o755)
    for directory in (
        "tools/fixture",
        "emulator/healthcheck",
        "emulator/unrelated-cli",
    ):
        (tmp_path / directory).mkdir(parents=True)
    recipe = tmp_path / "justfile"
    recipe.write_text(justfile, encoding="utf-8")
    log = tmp_path / "gate.log"
    just = shutil.which("just")
    assert just, "public gate test requires the permanent just CLI"
    result = subprocess.run(
        [
            just,
            "--justfile",
            str(recipe),
            "--working-directory",
            str(tmp_path),
            "go-test",
            str(go),
        ],
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "GATE_LOG": str(log),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return [
        Path(line).relative_to(tmp_path).as_posix()
        for line in log.read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX SYSTEM boundary; run shebang recipes from Git Bash"
)
def test_public_go_test_selects_healthcheck_and_tools_only(tmp_path: Path) -> None:
    assert _run_go_gate(tmp_path, (ROOT / "justfile").read_text(encoding="utf-8")) == [
        "tools/fixture",
        "emulator/healthcheck",
    ]


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX SYSTEM boundary; run shebang recipes from Git Bash"
)
def test_public_go_test_selector_mutation_loses_healthcheck(tmp_path: Path) -> None:
    source = (ROOT / "justfile").read_text(encoding="utf-8")
    selector = " 'emulator/healthcheck/go.mod'"
    assert source.count(selector) == 1, "mutation must remove a real, unique selector"
    assert _run_go_gate(tmp_path, source.replace(selector, "")) == ["tools/fixture"]
