"""Unit tests for scripts/check_effective_settings.py generation.

claudelint only auto-detects `.claude/settings.json`, so the fragment layers
(`{env, settings}` wrappers) cannot be validated directly. The checker
composes the effective settings.json for every claude-family profile x OS and
writes them out for claudelint to validate (ADR 0037). These tests cover the
generation step against the repo's real fragments (no bunx invocation).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_effective_settings import generate

DOTFILES = Path(__file__).resolve().parents[2]
PROFILE_KEYS = {"claude", "work-a", "work-b", "work-c", "work-d"}
OS_NAMES = {"macos", "linux", "windows"}


def test_generates_all_profiles_times_os(tmp_path: Path) -> None:
    """One effective settings.json per claude-family profile x OS."""
    generated = generate(DOTFILES, tmp_path)

    labels = set(generated)
    assert labels == {f"{k}-{o}" for k in PROFILE_KEYS for o in OS_NAMES}
    for path in generated.values():
        assert path.name == "settings.json"
        assert path.parent.name == ".claude"
        assert json.loads(path.read_text(encoding="utf-8"))


def test_effective_settings_reflect_layering(tmp_path: Path) -> None:
    """Spot-check composed output: shared + OS overlay + profile all land."""
    generated = generate(DOTFILES, tmp_path)

    work_c_mac = json.loads(generated["work-c-macos"].read_text(encoding="utf-8"))
    assert work_c_mac["effortLevel"] == "xhigh"
    assert "Bash(npm:*)" in work_c_mac["permissions"]["deny"]
    assert work_c_mac["preferredNotifChannel"] == "ghostty"
    assert work_c_mac["skillOverrides"]["yeet"] == "name-only"
    assert work_c_mac["env"]["CLAUDE_CODE_SUBAGENT_MODEL"] == "claude-opus-5"
    # env is the original git-managed fragment set only -- per-home tuning
    # values were never promoted into shared (user decision on PR #281)
    assert "MAX_THINKING_TOKENS" not in work_c_mac["env"]

    work_c_linux = json.loads(generated["work-c-linux"].read_text(encoding="utf-8"))
    assert "preferredNotifChannel" not in work_c_linux

    claude_mac = json.loads(generated["claude-macos"].read_text(encoding="utf-8"))
    assert claude_mac["effortLevel"] == "medium"
    assert claude_mac["permissions"]["defaultMode"] == "auto"
