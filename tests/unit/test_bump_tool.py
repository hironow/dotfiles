"""Unit tests for scripts/bump_tool.py (`just bump-tool ruff|ty <ver>`).

ruff and ty are pinned exactly in four declarations (justfile `uvx ruff@<ver>`,
root and emulator dev groups, mise config) that tests/unit/test_ruff_ty_pins.py
requires to agree; Dependabot ignores both. This script is therefore the only
way a pin moves: it rewrites every declaration in one go, re-locks both uv
projects, and prints the hironow/skills follow-up.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bump_tool.py"


def _load():  # noqa: ANN202 - module object
    spec = importlib.util.spec_from_file_location("bump_tool", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # dataclasses resolve `from __future__ import annotations` strings through
    # sys.modules[<module>], so the module must be registered before exec.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "justfile").write_text(
        "fmt:\n    uvx ruff@0.15.22 format .\ncheck:\n    uvx ruff@0.15.22 check .\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = [\n    "pytest>=9.1.1",\n    "ruff==0.15.22",\n    "ty==0.0.77",\n]\n',
        encoding="utf-8",
    )
    (tmp_path / "emulator").mkdir()
    (tmp_path / "emulator" / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = [\n    "ruff==0.15.22",\n    "ty==0.0.77",\n]\n',
        encoding="utf-8",
    )
    (tmp_path / "config" / "mise").mkdir(parents=True)
    (tmp_path / "config" / "mise" / "config.toml").write_text(
        '[tools]\nuv = "latest"\nruff = "0.15.22"\nty = "0.0.77"\n', encoding="utf-8"
    )
    return tmp_path


def test_bump_ruff_rewrites_every_declaration(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load()
    rc = mod.main(["ruff", "0.15.23", "--repo", str(repo), "--no-lock"])
    assert rc == 0
    assert (repo / "justfile").read_text(encoding="utf-8").count(
        "uvx ruff@0.15.23"
    ) == 2
    assert '"ruff==0.15.23"' in (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert '"ruff==0.15.23"' in (repo / "emulator" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert 'ruff = "0.15.23"' in (repo / "config" / "mise" / "config.toml").read_text(
        encoding="utf-8"
    )
    # ty untouched
    assert '"ty==0.0.77"' in (repo / "pyproject.toml").read_text(encoding="utf-8")
    out = capsys.readouterr().out
    assert "hironow/skills" in out and "0.15.23" in out


def test_bump_ty_leaves_the_justfile_alone(repo: Path) -> None:
    mod = _load()
    assert mod.main(["ty", "0.0.79", "--repo", str(repo), "--no-lock"]) == 0
    assert "0.0.79" not in (repo / "justfile").read_text(encoding="utf-8")
    assert '"ty==0.0.79"' in (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert '"ty==0.0.79"' in (repo / "emulator" / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert 'ty = "0.0.79"' in (repo / "config" / "mise" / "config.toml").read_text(
        encoding="utf-8"
    )


def test_dry_run_changes_nothing_but_prints_the_plan(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load()
    before = {p: p.read_text(encoding="utf-8") for p in repo.rglob("*") if p.is_file()}
    assert (
        mod.main(["ty", "0.0.79", "--repo", str(repo), "--no-lock", "--dry-run"]) == 0
    )
    assert {
        p: p.read_text(encoding="utf-8") for p in repo.rglob("*") if p.is_file()
    } == before
    out = capsys.readouterr().out
    assert "config/mise/config.toml" in out and "0.0.79" in out


def test_refuses_when_a_declaration_is_missing_and_writes_nothing(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load()
    mise = repo / "config" / "mise" / "config.toml"
    mise.write_text(
        '[tools]\nuv = "latest"\nruff = "0.15.22"\n', encoding="utf-8"
    )  # no ty pin
    before = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert mod.main(["ty", "0.0.79", "--repo", str(repo), "--no-lock"]) == 1
    assert (repo / "pyproject.toml").read_text(encoding="utf-8") == before
    assert "config/mise/config.toml" in capsys.readouterr().err


def test_refuses_a_non_exact_declaration(repo: Path) -> None:
    mod = _load()
    (repo / "emulator" / "pyproject.toml").write_text(
        '[dependency-groups]\ndev = [\n    "ruff>=0.15",\n    "ty==0.0.77",\n]\n',
        encoding="utf-8",
    )
    assert mod.main(["ruff", "0.15.23", "--repo", str(repo), "--no-lock"]) == 1


@pytest.mark.parametrize(
    "argv", [["mypy", "1.0"], ["ruff", "latest"], ["ruff", "v0.15.23"], ["ruff"]]
)
def test_rejects_unknown_tool_or_bad_version(repo: Path, argv: list[str]) -> None:
    mod = _load()
    with pytest.raises(SystemExit):
        mod.main([*argv, "--repo", str(repo), "--no-lock"])


def test_real_repo_declarations_are_all_present() -> None:
    """The script's file map matches this repo (the pin test covers equality)."""
    mod = _load()
    repo = Path(__file__).resolve().parents[2]
    for tool in ("ruff", "ty"):
        plan = mod.plan(repo, tool, "9.9.9")
        assert {str(edit.path.relative_to(repo)) for edit in plan} >= {
            "pyproject.toml",
            "emulator/pyproject.toml",
            "config/mise/config.toml",
        }
