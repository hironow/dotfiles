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
# The posture itself, so a switch added there is immediately one a complete
# setup has to carry (tests/unit/test_agent_tool_telemetry.py owns the values).
TELEMETRY = dict(check.TELEMETRY_OFF)
RTK_HOOK = 'bash "/home/u/.claude/hooks/rtk-hook-claude.sh"'
# Trimmed answers of rtk 0.50.0 and headroom 0.38.0
RTK_HELP = """A high-performance CLI proxy.

Usage: rtk [OPTIONS] <COMMAND>

Commands:
  ls             List directory contents with token-optimized output
  git            Git commands with compact output
  proxy          Execute command without filtering but track usage
  help           Print this message or the help of the given subcommand(s)

Options:
  -v, --verbose...
"""
RTK_TELEMETRY = """Telemetry status:
  consent:       never asked
  enabled:       no
  env override:  RTK_TELEMETRY_DISABLED=1 (blocked)
"""
HEALTH = {"service": "headroom-proxy", "ready": True}
PROXY_HELP = """Usage: headroom proxy [OPTIONS]

  Start the optimization proxy server.

Options:
  --host TEXT      Host to bind to
  --port INTEGER   Port to bind to
"""
MISE_CONFIG_TEXT = '[tools]\nrtk = "latest"\n\n[env]\nDO_NOT_TRACK = "1"\n'


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
        checks={
            "codex": {
                "codex_hooks_trust.py": "OK   codex-hooks - 5 dotfiles hooks trusted and enabled",
                # off Windows the sandbox check has nothing to say
                "codex_sandbox_tools.py": "",
            }
        },
        headroom_proxy=None,
        rtk_help=RTK_HELP,
        rtk_classified=frozenset({"ls", "git", "proxy", "help"}),
        rtk_telemetry=RTK_TELEMETRY,
        headroom_telemetry={"beacon_enabled": False},
        headroom_proxy_help=PROXY_HELP,
        headroom_proxy_flags=("--host", "--port"),
        codex_files={"hooks.json": "{}", "config.toml": 'model = "gpt"'},
        claude_bash=None,
        jev_key=check.JevKey(source=".config/jev/env", private=True, has_key=True),
        mise_config=check.MiseConfig(
            live=MISE_CONFIG_TEXT,
            tracked=MISE_CONFIG_TEXT,
            live_path="/home/u/.config/mise/config.toml",
            symlinked_into=None,
        ),
    )
    return replace(good, **changes)


def _levels(facts: check.Facts) -> dict[str, str]:
    return {name: level for level, name, _detail in check.report(facts)}


def _detail(facts: check.Facts, name: str) -> str:
    return next(detail for _level, n, detail in check.report(facts) if n == name)


def test_a_complete_setup_is_all_ok() -> None:
    assert set(_levels(_facts()).values()) == {"OK"}


# --- the live mise config ---------------------------------------------------
#
# `just deploy` puts ~/.config/mise/config.toml in place, and on this operator's
# Mac it is a SYMLINK into the dotfiles checkout. So the machine's live tool set
# and [env] are whatever the main tree has checked out: detaching it at a
# pre-rtk commit switched rtk and headroom off machine-wide for 40 minutes on
# 2026-10-01, and nothing warned. `cp -f` through that symlink copies the file
# onto itself, so `just deploy` cannot repair it either.


def test_a_live_mise_config_that_matches_origin_main_is_ok() -> None:
    assert _levels(_facts())["mise-config"] == "OK"


def test_a_live_mise_config_that_differs_from_origin_main_warns() -> None:
    facts = _facts(
        mise_config=check.MiseConfig(
            live='[tools]\nbun = "latest"\n',
            tracked=MISE_CONFIG_TEXT,
            live_path="/home/u/.config/mise/config.toml",
            symlinked_into="/home/u/dotfiles/config/mise/config.toml",
        )
    )
    assert _levels(facts)["mise-config"] == "WARN"
    detail = _detail(facts, "mise-config")
    assert "origin/main" in detail
    # the message has to name the actual cause, or the operator reads it as a
    # deploy problem and runs the one command that cannot fix it
    assert "symlink" in detail
    assert "/home/u/dotfiles/config/mise/config.toml" in detail


def test_a_missing_live_mise_config_warns_to_deploy() -> None:
    facts = _facts(
        mise_config=check.MiseConfig(
            live=None,
            tracked=MISE_CONFIG_TEXT,
            live_path="/home/u/.config/mise/config.toml",
            symlinked_into=None,
        )
    )
    assert _levels(facts)["mise-config"] == "WARN"
    assert "just deploy" in _detail(facts, "mise-config")


def test_line_endings_and_a_trailing_newline_are_not_a_difference() -> None:
    """The two halves arrive differently shaped: `git show` is read through a
    runner that strips its output, and a checked-out file keeps the platform's
    line endings (CRLF on Windows with core.autocrlf). Comparing them raw made
    this check warn on every machine, which it did when first run live."""
    facts = _facts(
        mise_config=check.MiseConfig(
            live=MISE_CONFIG_TEXT.replace("\n", "\r\n") + "\r\n",
            tracked=MISE_CONFIG_TEXT.strip(),
            live_path="/home/u/.config/mise/config.toml",
            symlinked_into="/home/u/dotfiles/config/mise/config.toml",
        )
    )
    assert _levels(facts)["mise-config"] == "OK"


def test_without_origin_main_there_is_nothing_to_compare() -> None:
    """A fresh clone with no fetch, or no git at all: say so rather than claim
    the config is right."""
    facts = _facts(
        mise_config=check.MiseConfig(
            live=MISE_CONFIG_TEXT,
            tracked=None,
            live_path="/home/u/.config/mise/config.toml",
            symlinked_into=None,
        )
    )
    assert _levels(facts)["mise-config"] == "OK"
    assert "not compared" in _detail(facts, "mise-config")


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


@pytest.mark.parametrize("missing", sorted(TELEMETRY))
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
    ) in check.report(_facts(checks={"codex": lines}))


def test_a_codex_check_that_cannot_run_warns() -> None:
    facts = _facts(checks={"codex": {"codex_sandbox_tools.py": None}})
    assert (
        "WARN",
        "codex",
        "codex_sandbox_tools.py --check failed to run",
    ) in check.report(facts)


def test_the_proxy_state_is_shown_but_never_a_problem() -> None:
    running = _facts(headroom_proxy=(4321, HEALTH))
    assert _levels(running)["headroom-proxy"] == "OK"
    assert "4321" in _detail(running, "headroom-proxy")
    assert _levels(_facts(headroom_proxy=(4321, None)))["headroom-proxy"] == "OK"
    assert _levels(_facts(headroom_proxy=None))["headroom-proxy"] == "OK"


def test_the_vendored_version_is_read_from_its_header() -> None:
    header = "// dotfiles-managed: rtk\n// Vendored from rtk 0.50.0 (`rtk init -g --agent pi`), https://x\n"
    assert check.vendored_version(header) == "0.50.0"
    assert check.vendored_version("no header\n") is None


# --- upstream contracts: what an rtk or headroom upgrade could break ---------


def test_rtks_subcommands_come_from_its_help() -> None:
    assert check.rtk_subcommands(RTK_HELP) == {"ls", "git", "proxy", "help"}


def test_an_rtk_subcommand_the_guard_has_not_classified_warns() -> None:
    help_text = RTK_HELP.replace(
        "  help ", "  run            Execute a shell command\n  help "
    )
    facts = _facts(rtk_help=help_text)
    assert _levels(facts)["rtk-guard"] == "WARN"
    detail = _detail(facts, "rtk-guard")
    assert "run" in detail
    assert "RTK_RUN_SUBCOMMANDS" in detail


def test_unreadable_rtk_help_warns() -> None:
    assert _levels(_facts(rtk_help="usage: something else"))["rtk-guard"] == "WARN"


@pytest.mark.parametrize(
    ("answer", "level"),
    [
        (RTK_TELEMETRY, "OK"),
        (RTK_TELEMETRY.replace("enabled:       no", "enabled:       yes"), "WARN"),
        # our variable set, but this rtk no longer reports honouring it
        (
            RTK_TELEMETRY.replace(
                "  env override:  RTK_TELEMETRY_DISABLED=1 (blocked)\n", ""
            ),
            "WARN",
        ),
        ("Telemetry: a new format", "WARN"),
        (None, "WARN"),
    ],
)
def test_rtk_is_asked_whether_its_telemetry_is_off(
    answer: str | None, level: str
) -> None:
    assert _levels(_facts(rtk_telemetry=answer))["rtk-telemetry"] == level


@pytest.mark.parametrize(
    ("answer", "level"),
    [
        ({"beacon_enabled": False}, "OK"),
        ({"beacon_enabled": True}, "WARN"),
        ({"schema_version": 3}, "WARN"),
        (None, "WARN"),
    ],
)
def test_headroom_is_asked_whether_its_beacon_is_off(
    answer: dict | None, level: str
) -> None:
    assert _levels(_facts(headroom_telemetry=answer))["headroom-telemetry"] == level


def test_a_headroom_proxy_without_host_and_port_flags_warns() -> None:
    facts = _facts(
        headroom_proxy_help=PROXY_HELP.replace("--port INTEGER", "--listen ADDR")
    )
    assert _levels(facts)["headroom-cli"] == "WARN"
    assert "proxy_command" in _detail(facts, "headroom-cli")


def test_upstream_checks_wait_for_the_tool_itself() -> None:
    absent = check.Tool(paths=(), version=None, mise_path=None)
    facts = _facts(
        rtk=absent,
        headroom=absent,
        rtk_help=None,
        rtk_telemetry=None,
        headroom_telemetry=None,
        headroom_proxy_help=None,
    )
    names = _levels(facts)
    for name in ("rtk-guard", "rtk-telemetry", "headroom-telemetry", "headroom-cli"):
        assert name not in names


def test_the_guard_records_each_rtk_subcommand_once() -> None:
    guard = check._load_command_guard()
    assert not guard.RTK_RUN_SUBCOMMANDS & guard.RTK_FILTER_SUBCOMMANDS
    assert {"run", "proxy", "git", "help"} <= check._guard_rtk_classified()


def test_a_proxy_answering_health_in_a_new_shape_warns() -> None:
    # j-cc would never recognise it: each launch waits, then goes direct
    facts = _facts(headroom_proxy=(4321, {"status": "ok"}))
    assert _levels(facts)["headroom-proxy"] == "WARN"
    assert "jev_headroom.is_headroom" in _detail(facts, "headroom-proxy")


def test_only_jcc_routes_through_headroom_by_default() -> None:
    assert _levels(_facts())["headroom-routing"] == "OK"


@pytest.mark.parametrize(
    ("changes", "where", "fix"),
    [
        (
            {
                "claude_homes": {
                    ".claude": {
                        "env": {
                            **TELEMETRY,
                            "ANTHROPIC_BASE_URL": "http://127.0.0.1:8787",
                        }
                    }
                }
            },
            "~/.claude",
            "headroom unwrap claude",
        ),
        (
            {
                "claude_homes": {
                    ".claude": {
                        "env": TELEMETRY,
                        "hooks": {
                            "SessionStart": [
                                {
                                    "hooks": [
                                        {
                                            "command": "headroom init hook ensure --marker headroom-init-claude"
                                        }
                                    ]
                                }
                            ]
                        },
                    }
                }
            },
            "~/.claude",
            "headroom unwrap claude",
        ),
        (
            {
                "codex_files": {
                    "hooks.json": '{"hooks": {"x": "headroom-init-codex"}}',
                    "config.toml": "",
                }
            },
            "~/.codex",
            "headroom unwrap codex",
        ),
        (
            {
                "codex_files": {
                    "hooks.json": "{}",
                    "config.toml": "# --- Headroom init provider ---\nopenai_base_url = 1\n",
                }
            },
            "~/.codex",
            "headroom unwrap codex",
        ),
    ],
)
def test_headroom_init_or_wrap_rewiring_an_agent_warns(
    changes: dict, where: str, fix: str
) -> None:
    facts = _facts(**changes)
    assert _levels(facts)["headroom-routing"] == "WARN"
    detail = _detail(facts, "headroom-routing")
    assert where in detail
    assert fix in detail


# --- what j-cc / j-pi need from this machine --------------------------------

GIT = r"C:\Program Files\Git"
SCOOP_GIT = r"C:\Users\u\scoop\apps\git\current"


def test_a_missing_git_bash_warns_with_the_path_to_set() -> None:
    facts = _facts(
        claude_bash=check.ClaudeBash(
            configured=None, found=None, candidate=SCOOP_GIT + r"\bin\bash.exe"
        )
    )
    assert _levels(facts)["claude-git-bash"] == "WARN"
    detail = _detail(facts, "claude-git-bash")
    assert "CLAUDE_CODE_GIT_BASH_PATH=" + SCOOP_GIT + r"\bin\bash.exe" in detail


def test_a_wrong_git_bash_setting_warns_even_when_claude_falls_back() -> None:
    facts = _facts(
        claude_bash=check.ClaudeBash(
            configured=r"D:\nowhere\bash.exe",
            found=GIT + r"\bin\bash.exe",
            candidate=None,
        )
    )
    assert _levels(facts)["claude-git-bash"] == "WARN"


def test_a_found_git_bash_is_ok_and_off_windows_there_is_no_line() -> None:
    facts = _facts(
        claude_bash=check.ClaudeBash(
            configured=None, found=GIT + r"\bin\bash.exe", candidate=None
        )
    )
    assert _levels(facts)["claude-git-bash"] == "OK"
    assert "claude-git-bash" not in _levels(_facts())


@pytest.mark.parametrize(
    ("key", "level", "hint"),
    [
        (check.JevKey(source=".config/jev/env", private=True, has_key=True), "OK", ""),
        (check.JevKey(source="environment", private=True, has_key=True), "OK", ""),
        (
            check.JevKey(source=None, private=False, has_key=False),
            "WARN",
            "jev-launchers.md",
        ),
        (
            check.JevKey(source=".config/jev/env", private=False, has_key=True),
            "WARN",
            "readable by others",
        ),
        (
            check.JevKey(source=".config/jev/env", private=True, has_key=False),
            "WARN",
            "TYPESAFE_API_KEY",
        ),
        # the old place: Codex's Windows sandbox reads files directly under the profile
        (
            check.JevKey(source=".env", private=True, has_key=True),
            "WARN",
            ".config/jev/env",
        ),
    ],
)
def test_the_jev_key_is_checked_without_showing_it(
    key: object, level: str, hint: str
) -> None:
    facts = _facts(jev_key=key)
    assert _levels(facts)["jev-key"] == level
    assert hint in _detail(facts, "jev-key")


@pytest.mark.parametrize(
    ("returncode", "stdout", "answer"),
    [
        (0, "OK   codex-hooks - fine\n", "OK   codex-hooks - fine"),
        (1, "WARN codex-hooks - untrusted\n", "WARN codex-hooks - untrusted"),
        # nothing to say (the sandbox check off Windows)
        (0, "", ""),
        # died before printing (a traceback on stderr): doctor must not drop it
        (1, "", None),
    ],
)
def test_a_checker_that_dies_silently_counts_as_not_run(
    returncode: int, stdout: str, answer: str | None
) -> None:
    assert check.checker_output(returncode, stdout) == answer


def test_a_missing_tool_skips_its_checkers() -> None:
    assert ("OK", "codex-hooks", "codex not on PATH") in check.report(
        _facts(checks={"codex": None})
    )


# --- copies of a tool: mise's shim and mise's install are one copy ---------

WIN_MISE = "C:/Users/u/AppData/Local/mise"
WIN_INSTALL = f"{WIN_MISE}/installs/rtk/0.50.0/rtk.exe"


@pytest.mark.parametrize(
    ("paths", "mise_path", "level"),
    [
        # a stale shell had both mise's shims dir and the install dir on PATH
        ((f"{WIN_MISE}/shims/rtk.exe", WIN_INSTALL), WIN_INSTALL, "OK"),
        ((WIN_INSTALL, f"{WIN_MISE}/shims/rtk.exe"), WIN_INSTALL, "OK"),
        # PATH with mise's shims alone (a runner, an IDE): still mise's rtk
        ((f"{WIN_MISE}/shims/rtk.exe",), WIN_INSTALL, "OK"),
        (
            ("/home/u/.local/share/mise/shims/rtk", MISE_RTK),
            MISE_RTK,
            "OK",
        ),
        # a copy mise does not manage is still a second copy
        (
            ("C:/Users/u/AppData/Local/Microsoft/WinGet/Links/rtk.exe", WIN_INSTALL),
            WIN_INSTALL,
            "WARN",
        ),
        (("/home/u/.local/bin/rtk", MISE_RTK), MISE_RTK, "WARN"),
    ],
)
def test_mises_shim_and_install_count_as_one_copy(
    paths: tuple[str, ...], mise_path: str, level: str
) -> None:
    facts = _facts(rtk=check.Tool(paths=paths, version="0.50.0", mise_path=mise_path))
    assert _levels(facts)["rtk"] == level


def test_the_duplicate_warning_names_only_the_copies_to_remove() -> None:
    winget = "C:/Users/u/AppData/Local/Microsoft/WinGet/Links/rtk.exe"
    facts = _facts(
        rtk=check.Tool(
            paths=(f"{WIN_MISE}/shims/rtk.exe", winget, WIN_INSTALL),
            version="0.50.0",
            mise_path=WIN_INSTALL,
        )
    )
    detail = _detail(facts, "rtk")
    assert winget in detail
    assert "shims" not in detail
