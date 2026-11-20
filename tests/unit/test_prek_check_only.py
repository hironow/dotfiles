"""Configuration seam: nine read-only hooks, no whole-project hooks (0085)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".pre-commit-config.yaml"
EXPECTED = [
    "forbidden-tokens-staged",
    "forbidden-tokens-commit-msg",
    "check-yaml",
    "check-toml",
    "check-json",
    "check-added-large-files",
    "check-merge-conflict",
    "detect-private-key",
    "mise-versions-check",
]


def hooks() -> dict[str, str]:
    text = CONFIG.read_text(encoding="utf-8")
    blocks = re.findall(
        r"(?ms)^      - id: ([\w-]+)\n(.*?)(?=^      - id: |^  - repo: |\Z)", text
    )
    return dict(blocks)


def test_exactly_nine_hooks_and_confidentiality_guards_first() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert re.findall(r"(?m)^      - id: ([\w-]+)$", text) == EXPECTED


def test_only_the_dedicated_fast_recipe_is_a_hook() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert re.findall(r"(?m)^        entry: (.+)$", text) == [
        "python3 scripts/check_forbidden_tokens.py staged --require-list --min-tokens 11",
        "python3 scripts/check_forbidden_tokens.py commit-msg --require-list --min-tokens 11",
        "just mise-versions-check",
    ]
    fast = hooks()["mise-versions-check"]
    for line in (
        "        pass_filenames: false",
        "        always_run: true",
        "        stages: [pre-commit]",
        "        language: system",
    ):
        assert line in fast
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    match = re.search(r"(?m)^mise-versions-check:(.*)\n((?:[ \t]+.*\n)+)", justfile)
    assert match
    assert match.group(1).strip() == "", "fast recipe must have no dependencies"
    assert (
        match.group(2).strip()
        == "@mise exec -- go run tools/mise-versions/main.go check"
    )


def test_no_push_stage_and_both_guard_shims_stay_installed() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "default_install_hook_types: [pre-commit, commit-msg]" in text
    assert not re.search(r"(?m)^\s+stages:.*pre-push", text)
    assert "stages: [commit-msg]" in hooks()["forbidden-tokens-commit-msg"]


def test_hygiene_is_a_leg_of_check_not_a_new_recipe() -> None:
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    check = text.split("\ncheck:\n", 1)[1].split("\n[group(", 1)[0]
    assert "@mise exec -- go run tools/text-hygiene/main.go" in check
    assert "--fix" not in "\n".join(
        line
        for line in check.splitlines()
        if not line.lstrip().startswith("#") and "echo" not in line
    )
