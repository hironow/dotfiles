"""emulator/ applies the canonical ruff rules the python-tooling spoke states.

The spoke (distributed to every agent home) is the written standard;
emulator/pyproject.toml is the one package in this repo that adopts it. A
rule added to one and not the other means agents are told one gate while
the repo runs another.
"""

import re
import tomllib
from pathlib import Path

DOTFILES = Path(__file__).resolve().parents[2]
SPOKE = DOTFILES / "ROOT_AGENTS_docs_agents_python-tooling.md"


def _spoke_lint() -> dict[str, list[str]]:
    text = SPOKE.read_text(encoding="utf-8")
    section = text.split("## ruff configuration", 1)[1]
    block = re.search(r"```toml\n(.*?)```", section, re.DOTALL)
    assert block, "the spoke's canonical ruff block moved"
    return tomllib.loads(block.group(1))["tool"]["ruff"]["lint"]


def _emulator_lint() -> dict[str, list[str]]:
    pyproject = tomllib.loads(
        (DOTFILES / "emulator/pyproject.toml").read_text(encoding="utf-8")
    )
    return pyproject["tool"]["ruff"]["lint"]


def test_emulator_selects_the_canonical_rules() -> None:
    assert sorted(_emulator_lint()["select"]) == sorted(_spoke_lint()["select"])


def test_emulator_ignores_only_what_the_canonical_ignores() -> None:
    assert sorted(_emulator_lint()["extend-ignore"]) == sorted(
        _spoke_lint()["extend-ignore"]
    )
