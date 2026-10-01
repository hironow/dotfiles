"""`just doctor` / `just status` show whether the AI tooling is complete.

Functional core: report() turns gathered facts into doctor's OK/WARN lines, so
every rule is tested here without touching PATH, the registry or Codex. The
shell (gather()) only collects facts.
"""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ai_tools_check as check  # noqa: E402

MISE_RTK = "/home/u/.local/share/mise/installs/rtk/0.50.0/rtk"
MISE_HEADROOM = (
    "/home/u/.local/share/mise/installs/pypi-headroom-ai/0.38.0/bin/headroom"
)
TELEMETRY = {"RTK_TELEMETRY_DISABLED": "1", "HEADROOM_BEACON": "off"}
RTK_HOOK = 'bash "/home/u/.claude/hooks/rtk-hook-claude.sh"'


def _facts(**changes: object) -> check.Facts:
    good = check.Facts(
        rtk=check.Tool(paths=(MISE_RTK,), version="0.50.0", mise_path=MISE_RTK),
        headroom=check.Tool(
            paths=(MISE_HEADROOM,), version="0.38.0", mise_path=MISE_HEADROOM
        ),
        vendored_rtk="0.50.0",
        env=TELEMETRY,
        user_env=None,
        claude_homes={
            ".claude": {
                "env": TELEMETRY,
                "hooks": {"PreToolUse": [{"hooks": [{"command": RTK_HOOK}]}]},
            }
        },
        pi_extensions={"jev-sonnet-fallback.ts": True, "rtk.ts": True},
        codex_checks={
            "codex_hooks_trust.py": "OK   codex-hooks - 5 dotfiles hooks trusted and enabled",
            # off Windows the sandbox check has nothing to say
            "codex_sandbox_tools.py": "",
        },
        headroom_proxy=None,
    )
    return replace(good, **changes)


def _levels(facts: check.Facts) -> dict[str, str]:
    return {name: level for level, name, _detail in check.report(facts)}


def _detail(facts: check.Facts, name: str) -> str:
    return next(detail for _level, n, detail in check.report(facts) if n == name)


def test_a_complete_setup_is_all_ok() -> None:
    assert set(_levels(_facts()).values()) == {"OK"}


def test_a_missing_tool_warns_with_the_fix() -> None:
    facts = _facts(rtk=check.Tool(paths=(), version=None, mise_path=None))
    assert _levels(facts)["rtk"] == "WARN"
    assert "mise install" in _detail(facts, "rtk")


def test_a_second_copy_on_path_warns() -> None:
    # e.g. winget's rtk next to mise's: an upgrade lands in one of them only
    winget = "/c/Users/u/AppData/Local/Microsoft/WinGet/Links/rtk"
    facts = _facts(
        rtk=check.Tool(paths=(winget, MISE_RTK), version="0.50.0", mise_path=MISE_RTK)
    )
    assert _levels(facts)["rtk"] == "WARN"
    assert winget in _detail(facts, "rtk")


def test_the_vendored_pi_extension_must_match_the_installed_rtk() -> None:
    facts = _facts(
        rtk=check.Tool(paths=(MISE_RTK,), version="0.51.0", mise_path=MISE_RTK)
    )
    assert _levels(facts)["rtk-pi-extension"] == "WARN"
    assert "just rtk-pi-refresh" in _detail(facts, "rtk-pi-extension")


@pytest.mark.parametrize("missing", ["RTK_TELEMETRY_DISABLED", "HEADROOM_BEACON"])
def test_telemetry_must_be_off_in_the_shell_and_in_claude(missing: str) -> None:
    env = {k: v for k, v in TELEMETRY.items() if k != missing}
    assert _levels(_facts(env=env))["telemetry"] == "WARN"
    homes = {
        ".claude": {"env": env, "hooks": _facts().claude_homes[".claude"]["hooks"]}
    }
    assert _levels(_facts(claude_homes=homes))["telemetry"] == "WARN"


def test_windows_also_needs_the_persisted_user_env() -> None:
    assert _levels(_facts(user_env={}))["telemetry"] == "WARN"
    assert _levels(_facts(user_env=TELEMETRY))["telemetry"] == "OK"


def test_a_claude_home_without_the_rtk_hook_warns() -> None:
    homes = {".claude": {"env": TELEMETRY, "hooks": {}}}
    assert _levels(_facts(claude_homes=homes))["claude-rtk-hook"] == "WARN"


def test_missing_pi_extensions_warn() -> None:
    facts = _facts(pi_extensions={"jev-sonnet-fallback.ts": True, "rtk.ts": False})
    assert _levels(facts)["pi-extensions"] == "WARN"
    assert "rtk.ts" in _detail(facts, "pi-extensions")


def test_codex_problems_are_passed_through() -> None:
    lines = {
        "codex_hooks_trust.py": "WARN codex-hooks - preToolUse Bash rtk-hook-codex.sh: not trusted (run just codex-hooks-trust)"
    }
    assert (
        "WARN",
        "codex-hooks",
        "preToolUse Bash rtk-hook-codex.sh: not trusted (run just codex-hooks-trust)",
    ) in check.report(_facts(codex_checks=lines))


def test_a_codex_check_that_cannot_run_warns() -> None:
    facts = _facts(codex_checks={"codex_sandbox_tools.py": None})
    assert (
        "WARN",
        "codex",
        "codex_sandbox_tools.py --check failed to run",
    ) in check.report(facts)


def test_the_proxy_state_is_shown_but_never_a_problem() -> None:
    assert _levels(_facts(headroom_proxy=(4321, True)))["headroom-proxy"] == "OK"
    assert "4321" in _detail(_facts(headroom_proxy=(4321, True)), "headroom-proxy")
    assert _levels(_facts(headroom_proxy=None))["headroom-proxy"] == "OK"


def test_the_vendored_version_is_read_from_its_header() -> None:
    header = "// dotfiles-managed: rtk\n// Vendored from rtk 0.50.0 (`rtk init -g --agent pi`), https://x\n"
    assert check.vendored_version(header) == "0.50.0"
    assert check.vendored_version("no header\n") is None
