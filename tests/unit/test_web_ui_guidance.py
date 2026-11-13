"""The agent instructions send browser interfaces to the platform first, then ui-sdk.

ADR-0076: the owner recommends ui-sdk (vercel-labs/ui) with plain HTML and web
components when nothing constrains the choice, and web components with Vite when
something does. The upstream setup steps load bare `web.js` (always the newest
release), use npm and npx, and say nothing of the seven-day wait or of who
hosts the files, so the spoke states where it overrides them. Each assertion is
scoped to the paragraph or bullet that carries the rule: moving or dropping the
rule fails the test, a stray mention elsewhere does not pass it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HUB = ROOT / "ROOT_AGENTS.md"
SPOKE = ROOT / "ROOT_AGENTS_docs_agents_web-ui.md"
POLICY = ROOT / "ROOT_AGENTS_docs_agents_dependency-policy.md"


def _blocks(path: Path) -> list[str]:
    """Paragraphs and list items, each on one line."""
    text = path.read_text(encoding="utf-8")
    blocks = re.split(r"\n\s*\n|\n(?=\s*(?:[-*]|\d+\.)\s)", text)
    return [" ".join(block.split()) for block in blocks if block.strip()]


def _block_with(path: Path, needle: str) -> str:
    matching = [block for block in _blocks(path) if needle in block]
    assert len(matching) == 1, f"expected one block in {path.name} with {needle!r}"
    return matching[0]


def test_the_go_rule_leaves_browser_pages_out_and_keeps_their_server() -> None:
    rule = _block_with(HUB, "**New code is Go, newest stable")
    assert "Code that runs in the browser page" in rule
    assert "docs/agents/web-ui.md" in rule
    assert "The server behind it stays Go." in rule


def test_the_hub_lists_the_web_ui_guide() -> None:
    rows = [
        line
        for line in HUB.read_text(encoding="utf-8").splitlines()
        if "docs/agents/web-ui.md" in line
    ]
    assert any(line.startswith("|") and "browser" in line for line in rows), rows


def test_the_platform_comes_first_and_ui_sdk_covers_what_it_lacks() -> None:
    first = _block_with(SPOKE, "Use the platform first.")
    assert "modern-web-guidance" in first
    lacks = _block_with(SPOKE, "Use ui-sdk for behavior the platform lacks")
    assert "vercel-labs/ui" in lacks
    for behavior in ("keyboard", "focus", "ARIA", "pending state", "announcements"):
        assert behavior in lacks, behavior
    assert "Do not hand-roll ARIA" in lacks


def test_the_setup_follows_the_constraints() -> None:
    assert "that framework's ui-sdk package" in _block_with(SPOKE, "names a framework")
    no_build = _block_with(SPOKE, "No such constraint")
    assert "plain HTML" in no_build and "no build step" in no_build
    vite = _block_with(SPOKE, "A smaller constraint")
    assert "web components with Vite" in vite
    for constraint in ("TypeScript", "npm packages", "bundler"):
        assert constraint in vite, constraint


def test_the_guide_wins_over_the_skill_and_the_upstream_steps() -> None:
    read_first = _block_with(SPOKE, "Follow the `ui-sdk` skill")
    assert "https://ui-sdk.dev/web.md" in read_first
    assert "this guide wins" in _block_with(SPOKE, "this guide wins")
    assert "redirect to whatever release is newest" in _block_with(
        SPOKE, "Pin an exact version."
    )
    assert "bunx" in _block_with(SPOKE, "Use bun:")


def test_the_wait_is_set_where_bun_installs() -> None:
    wait = _block_with(SPOKE, "does not reach bun")
    assert "seven" in _block_with(SPOKE, "Class 2 dependency")
    assert "~/.npmrc" in wait
    assert "--minimum-release-age 7d" in _block_with(SPOKE, "With a package:")
    assert 'minimumReleaseAge = "7d"' in _block_with(SPOKE, "With a package:")


def test_pages_host_the_files_and_integrity_is_not_oversold() -> None:
    assert "--ignore-scripts" in _block_with(
        SPOKE, "Host the files yourself by default."
    )
    assert "SHA-256" in _block_with(SPOKE, "Host the files yourself by default.")
    cdn = _block_with(SPOKE, "must host the files itself")
    assert "does not cover the modules" in cdn
    assert "import map" in cdn


def test_examples_never_load_a_moving_release() -> None:
    sources = re.findall(r'(?:src|href)="([^"]+)"', SPOKE.read_text(encoding="utf-8"))
    loads = [s for s in sources if "web.js" in s or "web.css" in s or "web@" in s]
    assert loads, "expected the guide to show how to load ui-sdk"
    for source in loads:
        assert "<version>" in source, source
        assert "web@0" not in source and not source.endswith("ui-sdk.dev/web.js"), (
            source
        )


def test_the_dependency_policy_says_how_bun_waits() -> None:
    rule = _block_with(POLICY, "minimumReleaseAge")
    assert "--minimum-release-age" in rule
    assert "does not apply to bun" in rule
