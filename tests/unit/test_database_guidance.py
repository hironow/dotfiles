"""Keep database selection evidence-scoped without changing maps/fake defaults."""

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from sync_agents import AgentTarget, _render_for_agent


def _selection() -> str:
    text = (REPO / "ROOT_AGENTS_docs_agents_go-tooling.md").read_text(encoding="utf-8")
    heading = "## Database selection"
    assert heading in text, "database selection needs an explicit conditional policy"
    return " ".join(text.split(heading, 1)[1].split())


def test_base_routes_database_selection_to_the_policy() -> None:
    text = (REPO / "ROOT_AGENTS.md").read_text(encoding="utf-8")
    assert "choosing an embedded or in-memory database" in text
    assert "docs/agents/go-tooling.md#database-selection" in text


@pytest.mark.parametrize("home", ["claude", "codex", "gemini", "pi"])
def test_database_pointer_renders_for_isolated_agent_targets(
    tmp_path: Path, home: str
) -> None:
    target = tmp_path / home
    base = (REPO / "ROOT_AGENTS.md").read_text(encoding="utf-8")
    rendered = _render_for_agent(base, AgentTarget(directory=target, name=home))
    assert f"{target}/docs/agents/go-tooling.md#database-selection" in rendered
    assert not target.exists(), "rendering must not deploy to any agent home"


def test_redb_is_conditional_not_a_default_database() -> None:
    text = _selection()
    assert "Only when a database is needed" in text
    assert "cberner/redb" in text
    assert "Prefer redb only when matching evidence demonstrates an advantage" in text
    assert "Otherwise compare SQLite case by case" in text


@pytest.mark.parametrize(
    "axis",
    ["version", "workload", "API", "storage backend", "durability", "concurrency"],
)
def test_priority_requires_applicability_matched_evidence(axis: str) -> None:
    assert axis in _selection()


def test_memory_and_multiprocess_claims_are_not_conflated() -> None:
    text = _selection()
    for term in ("InMemoryBackend", "process-local", "file-backed", "multiprocess"):
        assert term in text
    assert "one write transaction at a time" in text
    assert "does not establish general in-memory or multiprocess superiority" in text


def test_database_guidance_preserves_existing_design_and_test_defaults() -> None:
    text = _selection()
    assert "Go-first" in text
    assert "Rust or FFI solely to obtain redb" in text
    go = (REPO / "ROOT_AGENTS_docs_agents_go-tooling.md").read_text(encoding="utf-8")
    assert "Keep hot state in plain in-memory data structures" in go
    base = (REPO / "ROOT_AGENTS.md").read_text(encoding="utf-8")
    assert "in-memory version of the port" in base
    testing = (REPO / "ROOT_AGENTS_docs_agents_testing.md").read_text(encoding="utf-8")
    assert "Required: real DB connections" in testing


def test_database_policy_links_immutable_research_evidence() -> None:
    text = _selection()
    assert re.search(
        r"https://github\.com/hironow/dotfiles/blob/[a-f0-9]{40}/"
        r"docs/research/2026-11-redb-sqlite\.md",
        text,
    )
