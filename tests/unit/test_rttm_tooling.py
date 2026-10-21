"""RTTM uses the same synchronized, cooldown-exempt lint tools as the repo."""

import re
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


def test_synchronized_tools_cannot_be_bumped_by_one_dependabot_entry() -> None:
    text = (ROOT / ".github/dependabot.yaml").read_text(encoding="utf-8")
    blocks = re.split(r"^  - package-ecosystem: ", text, flags=re.MULTILINE)[1:]
    uv: dict[str, str] = {}
    for block in blocks:
        if not block.startswith('"uv"'):
            continue
        directory = re.search(r'^    directory: "([^"]+)"', block, re.MULTILINE)
        assert directory is not None, block
        uv[directory[1]] = block
    for project in ("/", "/emulator", "/tools/rttm"):
        ignored = uv[project].split("    ignore:\n", 1)[1]
        for tool in ("ruff", "ty"):
            assert f'- dependency-name: "{tool}"' in ignored


def test_rttm_tasks_are_reached_by_root_gates() -> None:
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    for root_task, nested_task in (
        ("fmt", "rttm-fmt"),
        ("lint", "rttm-lint"),
        ("check", "rttm-check"),
    ):
        block = text.split(f"\n{root_task}:\n", 1)[1].split("\n\n", 1)[0]
        assert f"just {nested_task}" in block
    for task in ("rttm-fmt", "rttm-lint", "rttm-typecheck", "rttm-check"):
        assert f"\n{task}:" in text
    typecheck = text.split("\nrttm-typecheck:", 1)[1].split("\n\n", 1)[0]
    assert "--group lint ty check" in typecheck
    assert "--only-group lint ty" not in typecheck
    check = text.split("\nrttm-check:", 1)[1].split("\n\n", 1)[0]
    assert "rttm-typecheck" in check
    assert "--group lint python -m pytest" in check
