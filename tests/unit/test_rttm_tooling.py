"""RTTM uses the same synchronized, cooldown-exempt lint tools as the repo."""

import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(relative: str) -> dict:
    return tomllib.loads((ROOT / relative).read_text(encoding="utf-8"))


@pytest.mark.parametrize("tool", ["ruff", "ty"])
def test_rttm_lint_pin_and_cooldown_match_root(tool: str) -> None:
    root = load("pyproject.toml")
    rttm = load("tools/rttm/pyproject.toml")
    pin = next(
        p for p in root["dependency-groups"]["lint"] if p.startswith(f"{tool}==")
    )
    assert pin in rttm["dependency-groups"]["lint"]
    assert not any(p.startswith(tool) for p in rttm["project"]["dependencies"])
    assert rttm["tool"]["uv"]["exclude-newer"] == "7 days"
    assert rttm["tool"]["uv"]["exclude-newer-package"][tool] is False


def test_rttm_ty_has_its_own_scope_and_import_path() -> None:
    config = load("tools/rttm/pyproject.toml")["tool"]["ty"]
    assert config["src"]["include"] == ["to_eaf.py", "visualize.py", "tests"]
    assert config["environment"]["extra-paths"] == ["."]
    assert config["terminal"]["error-on-warning"] is True
