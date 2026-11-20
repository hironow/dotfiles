"""Keep database selection evidence-scoped without changing maps/fake defaults."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from sync_agents import AgentTarget, _render_for_agent


@pytest.mark.parametrize("home", ["claude", "codex", "gemini", "pi"])
def test_database_pointer_renders_for_isolated_agent_targets(
    tmp_path: Path, home: str
) -> None:
    target = tmp_path / home
    base = (REPO / "ROOT_AGENTS.md").read_text(encoding="utf-8")
    rendered = _render_for_agent(base, AgentTarget(directory=target, name=home))
    assert f"{target}/docs/agents/go-tooling.md#database-selection" in rendered
    assert not target.exists(), "rendering must not deploy to any agent home"
