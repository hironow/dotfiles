#!/usr/bin/env python3
"""Is the AI tooling complete? rtk, headroom, their telemetry and their wiring.

Functional core / imperative shell: gather() collects facts (PATH, versions,
the Windows User env, agent homes, Codex's hook trust, the headroom proxy, and
what rtk and headroom say about themselves) and report() is a pure function
from those facts to doctor's OK/WARN lines, so the rules are unit-tested and
the IO stays thin. Used by `just doctor` and `just status`; always exits 0
(doctor counts the lines).

The upstream checks compare each contract dotfiles relies on with the installed
tool, so an rtk or headroom upgrade that breaks one shows up here: telemetry
off by the tool's own account, every rtk subcommand classified by the command
guard, and the `headroom proxy` flags jev_headroom.proxy_command passes. Each
contract is defined once, where it is used; this only reads it.
"""

from collections.abc import Mapping
import contextlib
from dataclasses import dataclass
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from types import ModuleType

import claude_git_bash
import claude_homes
import doctor_lines
from doctor_lines import Line
import jev_headroom
import jev_launch
import windows_env

ROOT = Path(__file__).resolve().parents[1]
COMMAND_GUARD = ROOT / "ROOT_AGENTS_hooks_block-prohibited-commands.py"
# Two switches for headroom, not one: HEADROOM_BEACON is its own and
# DO_NOT_TRACK the cross-vendor opt-out it also honours. The beacon fails open
# (any value but "off" uploads), so neither stands in for the other.
TELEMETRY_OFF = {
    "RTK_TELEMETRY_DISABLED": "1",
    "HEADROOM_BEACON": "off",
    "DO_NOT_TRACK": "1",
}
PI_EXTENSIONS = ("jev-sonnet-fallback.ts", "rtk.ts")
# What `headroom init` / `headroom wrap` write into an agent's config (headroom
# 0.38 cli/init.py), beside a loopback ANTHROPIC_BASE_URL. j-cc is the only
# headroom route (docs/runbook/jev-launchers.md).
HEADROOM_CLAUDE_MARKERS = ("headroom-init-claude",)
HEADROOM_CODEX_MARKERS = ("headroom-init-codex", "# --- Headroom init provider ---")
CODEX_FILES = ("hooks.json", "config.toml")
# Codex checkers in scripts/, each printing doctor lines for `--check`
# Checkers in scripts/ by the tool they need on PATH, each printing doctor lines
# for `--check`, and the line shown when that tool is missing
CHECKERS = {
    "codex": ("codex-hooks", ("codex_hooks_trust.py", "codex_sandbox_tools.py")),
    "claude": ("claude-plugins", ("claude_plugins.py", "headroom_mcp.py")),
}

# A checker may query several homes (claude_homes.CHECK_BUDGET stays below)
CHECKER_TIMEOUT = 300


@dataclass(frozen=True)
class Tool:
    paths: tuple[str, ...]  # every copy on PATH, in PATH order
    version: str | None
    mise_path: str | None  # what mise would run, if mise manages it


@dataclass(frozen=True)
class ClaudeBash:
    """Windows: the Git Bash Claude Code would run, and what it was told."""

    configured: str | None  # CLAUDE_CODE_GIT_BASH_PATH
    found: str | None  # what claude_git_bash() resolves
    candidate: str | None  # an existing Git Bash to point it at


@dataclass(frozen=True)
class JevKey:
    """Where j-cc / j-pi find the Jev key; never the key itself."""

    source: str | None  # "environment", a KEY_FILES name, or None
    private: bool  # the file passes jev_launch.env_file_is_private
    has_key: bool  # the source holds TYPESAFE_API_KEY


@dataclass(frozen=True)
class MiseConfig:
    """The mise config this machine actually reads, against origin/main's."""

    live: str | None  # the deployed file's text; None when there is none
    tracked: str | None  # origin/main's copy; None when it cannot be read
    live_path: str  # where the deployed file is looked for
    symlinked_into: str | None  # what it is a symlink to, if it is one


@dataclass(frozen=True)
class Facts:
    rtk: Tool
    headroom: Tool
    vendored_rtk: str | None  # rtk version config/pi/extensions/rtk.ts came from
    env: Mapping[str, str]  # this shell
    user_env: Mapping[str, str] | None  # persisted Windows User env; None elsewhere
    claude_homes: Mapping[str, dict]  # existing home -> its settings.json
    pi_extensions: Mapping[str, bool]  # name -> placed
    # CHECKERS' --check output: tool -> script -> output (None: it did not run);
    # a tool not on PATH maps to None
    checks: Mapping[str, Mapping[str, str | None] | None]
    # (recorded port, its /health answer or None); None: no record
    headroom_proxy: tuple[int, Mapping[str, object] | None] | None
    codex_files: Mapping[str, str]  # CODEX_FILES in ~/.codex ("" when absent)
    # What the tools say about themselves (None: no answer)
    rtk_help: str | None  # `rtk --help`
    rtk_telemetry: str | None  # `rtk telemetry status`
    headroom_telemetry: Mapping[str, object] | None  # `headroom telemetry --json`
    headroom_proxy_help: str | None  # `headroom proxy --help`
    # The contracts, from where they are defined
    rtk_classified: frozenset[str]  # rtk subcommands the command guard classifies
    headroom_proxy_flags: tuple[str, ...]  # flags jev_headroom.proxy_command passes
    # What j-cc / j-pi need from this machine
    claude_bash: ClaudeBash | None  # None off Windows
    jev_key: JevKey
    mise_config: MiseConfig


# ---- Functional core ----


def _claude_git_bash(facts: Facts) -> list[Line]:
    bash = facts.claude_bash
    if bash is None:
        return []
    if bash.found is None:
        fix = (
            f"just harden-env (sets CLAUDE_CODE_GIT_BASH_PATH={bash.candidate} "
            "for the User)"
            if bash.candidate
            else r"install Git for Windows, or set CLAUDE_CODE_GIT_BASH_PATH to its bin\bash.exe"
        )
        return [
            (
                "WARN",
                "claude-git-bash",
                "Claude Code finds no Git Bash, so its Bash tool is off and j-cc "
                f"fails: {fix}",
            )
        ]
    if bash.configured and bash.configured != bash.found:
        return [
            (
                "WARN",
                "claude-git-bash",
                f"CLAUDE_CODE_GIT_BASH_PATH={bash.configured} is not an existing "
                f"bash, so Claude Code falls back to {bash.found}: fix or unset it",
            )
        ]
    return [("OK", "claude-git-bash", f"Claude Code runs {bash.found}")]


def _jev_key(facts: Facts) -> Line:
    key = facts.jev_key
    runbook = "docs/runbook/jev-launchers.md"
    if key.source is None:
        return (
            "WARN",
            "jev-key",
            f"none: j-cc / j-pi start without Jev's routing ({runbook})",
        )
    shown = "the environment" if key.source == "environment" else f"~/{key.source}"
    if key.source != "environment" and not key.private:
        rule = (
            "icacls: no entry for other accounts"
            if facts.user_env is not None
            else "chmod 600"
        )
        return (
            "WARN",
            "jev-key",
            f"{shown} is readable by others, so Jev ignores it ({rule})",
        )
    if not key.has_key:
        return ("WARN", "jev-key", f"{shown} has no TYPESAFE_API_KEY= line ({runbook})")
    if key.source == ".env":
        return (
            "WARN",
            "jev-key",
            "in ~/.env, the old place: move it to ~/.config/jev/env, which Codex's "
            f"Windows sandbox does not read ({runbook})",
        )
    return ("OK", "jev-key", f"from {shown}")


def checker_output(returncode: int, stdout: str) -> str | None:
    """A doctor-line checker's answer: its lines (exit 1 carries WARNs), or
    None when it died before printing any, so the failure is not dropped."""
    lines = stdout.strip()
    return lines if lines or returncode == 0 else None


def vendored_version(text: str) -> str | None:
    match = re.search(r"Vendored from rtk (\d+\.\d+\.\d+)", text)
    return match[1] if match else None


def _same(a: str, b: str) -> bool:
    norm = lambda p: os.path.normcase(os.path.normpath(p)).removesuffix(".exe")  # noqa: E731
    return norm(a) == norm(b)


def _parts(path: str) -> list[str]:
    return [part for part in re.split(r"[\\/]+", os.path.normcase(path)) if part]


def _is_mise_copy(path: str, mise_path: str | None) -> bool:
    """path is mise's own copy: the install mise resolves, or its shim (a
    shim in <mise data>/shims runs that install)."""
    if mise_path is None:
        return False
    if _same(path, mise_path):
        return True
    install = _parts(mise_path)
    if "installs" not in install:
        return False
    root = install[: len(install) - 1 - install[::-1].index("installs")]
    return _parts(path)[:-1] == [*root, "shims"]


def _tool(name: str, tool: Tool, package: str) -> Line:
    if not tool.paths:
        return ("WARN", name, f"not on PATH: mise install {package}")
    others = [path for path in tool.paths if not _is_mise_copy(path, tool.mise_path)]
    if others and len(tool.paths) > 1:
        return (
            "WARN",
            name,
            f"copies on PATH that mise does not manage ({', '.join(others)}): "
            "remove them, keeping mise's (a winget package, a hand-placed "
            "~/.local/bin copy)",
        )
    if others:
        return ("WARN", name, f"{tool.paths[0]} is not mise's: mise install {package}")
    return ("OK", name, f"{tool.version or '?'} via mise")


def _missing_telemetry(env: Mapping[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in TELEMETRY_OFF.items() if env.get(k) != v]


def _rtk_pi_extension(facts: Facts) -> Line:
    # rtk upgrades can change its own Pi extension; ours is a vendored copy
    installed, vendored = facts.rtk.version, facts.vendored_rtk
    if installed and vendored and installed != vendored:
        return (
            "WARN",
            "rtk-pi-extension",
            f"config/pi/extensions/rtk.ts is from rtk {vendored}, "
            f"installed is {installed}: just rtk-pi-refresh",
        )
    return ("OK", "rtk-pi-extension", f"vendored from rtk {vendored or '?'}")


def _telemetry(facts: Facts) -> Line:
    gaps = []
    if missing := _missing_telemetry(facts.env):
        gaps.append(f"this shell lacks {', '.join(missing)} (mise env)")
    for home, settings in facts.claude_homes.items():
        if missing := _missing_telemetry(settings.get("env", {})):
            gaps.append(f"~/{home} lacks {', '.join(missing)} (just sync-agents)")
    if facts.user_env is not None and (missing := _missing_telemetry(facts.user_env)):
        gaps.append(f"Windows User env lacks {', '.join(missing)} (just harden-env)")
    if gaps:
        return ("WARN", "telemetry", "; ".join(gaps))
    where = "this shell and the Claude homes"
    if facts.user_env is not None:
        where += " and the Windows User env"
    return ("OK", "telemetry", f"off switches set in {where}")


def _claude_rtk_hook(facts: Facts) -> Line:
    unhooked = [
        home
        for home, settings in facts.claude_homes.items()
        if not any(
            "rtk-hook-claude" in hook.get("command", "")
            for blocks in settings.get("hooks", {}).values()
            for block in blocks
            for hook in block.get("hooks", [])
        )
    ]
    if unhooked:
        return (
            "WARN",
            "claude-rtk-hook",
            f"missing in ~/{', ~/'.join(unhooked)}: just sync-agents",
        )
    return ("OK", "claude-rtk-hook", f"in {len(facts.claude_homes)} Claude home(s)")


def _pi_extensions(facts: Facts) -> Line:
    absent = [name for name, placed in facts.pi_extensions.items() if not placed]
    if absent:
        return (
            "WARN",
            "pi-extensions",
            f"missing {', '.join(absent)}: just pi-extensions-install",
        )
    return ("OK", "pi-extensions", ", ".join(facts.pi_extensions))


def _checkers(facts: Facts) -> list[Line]:
    lines: list[Line] = []
    for tool, outputs in facts.checks.items():
        if outputs is None:
            absent = CHECKERS[tool][0] if tool in CHECKERS else f"{tool}-checks"
            lines.append(("OK", absent, f"{tool} not on PATH"))
            continue
        for script, out in outputs.items():
            if out is None:
                lines.append(("WARN", tool, f"{script} --check failed to run"))
                continue
            lines += doctor_lines.parse(out)
    return lines


def _headroom_proxy(facts: Facts) -> Line:
    if facts.headroom_proxy is None:
        return ("OK", "headroom-proxy", "not running; j-cc starts one on demand")
    port, answer = facts.headroom_proxy
    if jev_headroom.is_headroom(answer):
        return ("OK", "headroom-proxy", f"127.0.0.1:{port} running")
    if answer is None:
        return (
            "OK",
            "headroom-proxy",
            f"127.0.0.1:{port} recorded but not answering (j-cc starts a new one)",
        )
    return (
        "WARN",
        "headroom-proxy",
        f"127.0.0.1:{port} answers /health with keys {', '.join(sorted(answer))}, "
        "not the shape jev_headroom.is_headroom expects: j-cc would wait for it, "
        "then go direct",
    )


def _routes_claude(settings: Mapping[str, object]) -> bool:
    env = settings.get("env")
    base_url = str(env.get("ANTHROPIC_BASE_URL", "")) if isinstance(env, dict) else ""
    loopback = base_url.startswith(("http://127.0.0.1", "http://localhost"))
    text = json.dumps(settings)
    return loopback or any(marker in text for marker in HEADROOM_CLAUDE_MARKERS)


def _headroom_routing(facts: Facts) -> Line:
    claude = [
        f"~/{home}" for home, s in facts.claude_homes.items() if _routes_claude(s)
    ]
    codex = any(
        marker in text
        for text in facts.codex_files.values()
        for marker in HEADROOM_CODEX_MARKERS
    )
    if not claude and not codex:
        return ("OK", "headroom-routing", "only j-cc and its Codex workers use it")
    fixes = (["headroom unwrap claude"] if claude else []) + (
        ["headroom unwrap codex"] if codex else []
    )
    return (
        "WARN",
        "headroom-routing",
        f"headroom init/wrap routes {', '.join([*claude, *(['~/.codex'] if codex else [])])} "
        "through a local proxy, so plain claude/codex fail while it is down (and "
        f"Claude loses Remote Control): {' and '.join(fixes)}, then just sync-agents",
    )


def rtk_subcommands(help_text: str) -> frozenset[str]:
    """The names in the Commands: section of `rtk --help`."""
    _, found, rest = help_text.partition("\nCommands:\n")
    names = set()
    for line in rest.splitlines() if found else []:
        if not line.strip():
            break
        if match := re.match(r"  (\S+)", line):
            names.add(match[1])
    return frozenset(names)


def _rtk_guard(facts: Facts) -> list[Line]:
    if not facts.rtk.paths:
        return []
    found = rtk_subcommands(facts.rtk_help or "")
    if not found:
        return [("WARN", "rtk-guard", "cannot read the subcommands in `rtk --help`")]
    if unclassified := sorted(found - facts.rtk_classified):
        return [
            (
                "WARN",
                "rtk-guard",
                f"rtk {facts.rtk.version or '?'} has subcommands the command guard "
                f"has not classified ({', '.join(unclassified)}): add each to "
                "RTK_RUN_SUBCOMMANDS if it runs its operands, else to "
                "RTK_FILTER_SUBCOMMANDS (ROOT_AGENTS_hooks_block-prohibited-commands.py)",
            )
        ]
    return [
        (
            "OK",
            "rtk-guard",
            f"the command guard classifies all {len(found)} rtk subcommands",
        )
    ]


def _rtk_telemetry(facts: Facts) -> list[Line]:
    if not facts.rtk.paths:
        return []
    status = facts.rtk_telemetry or ""
    enabled = re.search(r"^\s*enabled:\s*(\S+)", status, re.MULTILINE)
    if enabled is None:
        return [("WARN", "rtk-telemetry", "cannot read `rtk telemetry status`")]
    if enabled[1] != "no":
        return [("WARN", "rtk-telemetry", "rtk reports it on: rtk telemetry disable")]
    if (
        facts.env.get("RTK_TELEMETRY_DISABLED") == "1"
        and "RTK_TELEMETRY_DISABLED" not in status
    ):
        return [
            (
                "WARN",
                "rtk-telemetry",
                "off, but this rtk no longer reports honouring RTK_TELEMETRY_DISABLED: "
                "find its switch (rtk telemetry --help) before consent turns it on",
            )
        ]
    return [("OK", "rtk-telemetry", "off by rtk's own account")]


def _headroom_telemetry(facts: Facts) -> list[Line]:
    if not facts.headroom.paths:
        return []
    enabled = (facts.headroom_telemetry or {}).get("beacon_enabled")
    if enabled is False:
        return [("OK", "headroom-telemetry", "beacon off by headroom's own account")]
    if enabled is True:
        honoured = facts.env.get("HEADROOM_BEACON") == "off"
        return [
            (
                "WARN",
                "headroom-telemetry",
                "headroom reports its beacon on"
                + (
                    " although HEADROOM_BEACON=off: find its switch (headroom telemetry)"
                    if honoured
                    else ": HEADROOM_BEACON=off (mise env)"
                ),
            )
        ]
    return [("WARN", "headroom-telemetry", "cannot read `headroom telemetry --json`")]


def _headroom_cli(facts: Facts) -> list[Line]:
    if not facts.headroom.paths:
        return []
    usage = facts.headroom_proxy_help or ""
    if missing := [flag for flag in facts.headroom_proxy_flags if flag not in usage]:
        return [
            (
                "WARN",
                "headroom-cli",
                f"`headroom proxy --help` lacks {', '.join(missing)}: update "
                "jev_headroom.proxy_command, or j-cc goes direct",
            )
        ]
    return [
        (
            "OK",
            "headroom-cli",
            f"headroom proxy takes {', '.join(facts.headroom_proxy_flags)}",
        )
    ]


def _comparable(text: str) -> str:
    """A config's text in comparable form: LF line endings, no trailing blanks.

    Both halves of the comparison arrive differently shaped. `git show` is read
    through a runner that strips its output, while a checked-out file keeps the
    platform's line endings -- on Windows with core.autocrlf that is CRLF. Left
    raw, every machine would report a difference, and a check that always warns
    is a check nobody reads.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _mise_config(facts: Facts) -> Line:
    """The live mise config against origin/main's.

    mise's global config decides which tools exist and what `[env]` every shell
    gets, so a live copy that differs from origin/main's silently changes the
    machine. `just deploy` writes that file; on this operator's Mac it is a
    SYMLINK into the dotfiles checkout, which makes the live tool set whatever
    the main tree has checked out -- detaching it at a pre-rtk commit switched
    rtk and headroom off machine-wide for 40 minutes (2026-10-01), and nothing
    warned. Worse, `cp -f` through that symlink copies the file onto itself, so
    `just deploy` cannot repair it: the fix is to put the checkout back on main.
    """
    config = facts.mise_config
    if config.live is None:
        return (
            "WARN",
            "mise-config",
            f"no {config.live_path}: no tool or [env] of this repo is active -- "
            "run: just deploy",
        )
    if config.tracked is None:
        return (
            "OK",
            "mise-config",
            f"{config.live_path} present, not compared (origin/main's copy is "
            "unreadable: no git, or no fetch yet)",
        )
    if _comparable(config.live) == _comparable(config.tracked):
        return ("OK", "mise-config", f"{config.live_path} matches origin/main")
    if config.symlinked_into:
        return (
            "WARN",
            "mise-config",
            f"{config.live_path} differs from origin/main's and is a symlink to "
            f"{config.symlinked_into}, so this machine's tools and [env] are "
            "whatever that checkout holds -- put it back on main (`just deploy` "
            "copies the file onto itself through the symlink and cannot fix it)",
        )
    return (
        "WARN",
        "mise-config",
        f"{config.live_path} differs from origin/main's: the deployed copy is "
        "stale or edited by hand -- run: just deploy",
    )


def report(facts: Facts) -> list[Line]:
    return [
        _mise_config(facts),
        _tool("rtk", facts.rtk, "rtk"),
        _tool("headroom", facts.headroom, "pypi:headroom-ai"),
        _rtk_pi_extension(facts),
        _telemetry(facts),
        *_rtk_telemetry(facts),
        *_headroom_telemetry(facts),
        *_rtk_guard(facts),
        *_headroom_cli(facts),
        _claude_rtk_hook(facts),
        _pi_extensions(facts),
        *_checkers(facts),
        _headroom_proxy(facts),
        _headroom_routing(facts),
        *_claude_git_bash(facts),
        _jev_key(facts),
    ]


# ---- Imperative shell ----


def _run(args: list[str], *, checker: bool = False) -> str | None:
    """stdout of a command, or None when it cannot run or fails (a checker's
    exit 1 still carries its WARN lines: see checker_output)."""
    try:
        done = subprocess.run(
            args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=CHECKER_TIMEOUT if checker else 60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if checker:
        return checker_output(done.returncode, done.stdout)
    return done.stdout.strip() if done.returncode == 0 else None


def _all_on_path(name: str) -> tuple[str, ...]:
    found: list[str] = []
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        for candidate in (name, f"{name}.exe", f"{name}.cmd"):
            path = Path(directory) / candidate
            if path.is_file() and not any(_same(str(path), seen) for seen in found):
                found.append(str(path))
                break
    return tuple(found)


def _tool_facts(name: str, version_args: list[str]) -> Tool:
    paths = _all_on_path(name)
    raw = _run([paths[0], *version_args]) if paths else None
    version = re.search(r"\d+\.\d+\.\d+", raw or "")
    mise = shutil.which("mise")
    mise_path = _run([mise, "which", name]) if mise else None
    return Tool(
        paths=paths, version=version[0] if version else None, mise_path=mise_path
    )


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_command_guard() -> ModuleType:
    spec = importlib.util.spec_from_file_location("command_guard", COMMAND_GUARD)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {COMMAND_GUARD}")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


def _guard_rtk_classified() -> frozenset[str]:
    guard = _load_command_guard()
    return frozenset(guard.RTK_RUN_SUBCOMMANDS | guard.RTK_FILTER_SUBCOMMANDS)


def _json_answer(text: str | None) -> dict | None:
    try:
        answer = json.loads(text or "")
    except ValueError:
        return None
    return answer if isinstance(answer, dict) else None


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _mise_config_facts(home: Path) -> MiseConfig:
    config_dir = os.environ.get("MISE_CONFIG_DIR") or (
        Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config") / "mise"
    )
    live = Path(config_dir) / "config.toml"
    target: str | None = None
    if live.is_symlink():
        with contextlib.suppress(OSError):
            target = str(live.resolve())
    return MiseConfig(
        live=live.read_text(encoding="utf-8") if live.is_file() else None,
        tracked=_run(
            ["git", "-C", str(ROOT), "show", "origin/main:config/mise/config.toml"]
        ),
        live_path=str(live),
        symlinked_into=target,
    )


def _claude_bash(home: Path, settings: Mapping[str, object]) -> ClaudeBash | None:
    if sys.platform != "win32":
        return None
    env = settings.get("env")
    configured = os.environ.get("CLAUDE_CODE_GIT_BASH_PATH") or (
        str(env.get("CLAUDE_CODE_GIT_BASH_PATH") or "") if isinstance(env, dict) else ""
    )
    exists = lambda path: Path(path).exists()  # noqa: E731
    return ClaudeBash(
        configured=configured or None,
        found=claude_git_bash.claude_git_bash(
            configured or None, shutil.which("git"), exists
        ),
        candidate=next(
            (
                c
                for c in claude_git_bash.candidates(shutil.which("sh"), str(home))
                if exists(c)
            ),
            None,
        ),
    )


def _jev_key_facts(home: Path) -> JevKey:
    if os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_AI_API_KEY"):
        return JevKey(source="environment", private=True, has_key=True)
    for name in jev_launch.KEY_FILES:
        path = home / name
        if path.is_file():
            return JevKey(
                source=name.as_posix(),
                private=jev_launch.env_file_is_private(path),
                has_key=jev_launch.key_in(_text(path)) is not None,
            )
    return JevKey(source=None, private=False, has_key=False)


def gather(home: Path) -> Facts:
    pi_dir = (
        Path(os.environ.get("PI_CODING_AGENT_DIR") or home / ".pi/agent") / "extensions"
    )
    port = jev_headroom.read_state(jev_headroom.state_path(home))
    codex_home = Path(os.environ.get("CODEX_HOME") or home / ".codex")
    checks = {
        tool: {
            script: _run(
                [sys.executable, str(ROOT / "scripts" / script), "--check"],
                checker=True,
            )
            for script in scripts
        }
        if shutil.which(tool)
        else None
        for tool, (_absent, scripts) in CHECKERS.items()
    }
    rtk = _tool_facts("rtk", ["--version"])
    headroom = _tool_facts("headroom", ["--version"])
    rtk_exe = rtk.paths[0] if rtk.paths else None
    headroom_exe = headroom.paths[0] if headroom.paths else None
    homes = {
        path.name: _json(path / "settings.json") for path in claude_homes.existing(home)
    }
    return Facts(
        rtk=rtk,
        headroom=headroom,
        vendored_rtk=vendored_version(
            (ROOT / "config/pi/extensions/rtk.ts").read_text(encoding="utf-8")
        ),
        env=dict(os.environ),
        user_env=windows_env.persisted(TELEMETRY_OFF),
        claude_homes=homes,
        pi_extensions={name: (pi_dir / name).is_file() for name in PI_EXTENSIONS},
        checks=checks,
        headroom_proxy=None if port is None else (port, jev_headroom.probe(port)),
        codex_files={name: _text(codex_home / name) for name in CODEX_FILES},
        rtk_help=_run([rtk_exe, "--help"]) if rtk_exe else None,
        rtk_telemetry=_run([rtk_exe, "telemetry", "status"]) if rtk_exe else None,
        headroom_telemetry=_json_answer(
            _run([headroom_exe, "telemetry", "--json"]) if headroom_exe else None
        ),
        headroom_proxy_help=_run([headroom_exe, "proxy", "--help"])
        if headroom_exe
        else None,
        rtk_classified=_guard_rtk_classified(),
        headroom_proxy_flags=tuple(
            arg
            for arg in jev_headroom.proxy_command("headroom", 0)
            if arg.startswith("--")
        ),
        claude_bash=_claude_bash(home, homes.get(".claude", {})),
        jev_key=_jev_key_facts(home),
        mise_config=_mise_config_facts(home),
    )


def main() -> int:
    for line in report(gather(Path.home())):
        print(doctor_lines.fmt(line))
    return 0  # doctor counts the lines; this never fails the run


if __name__ == "__main__":
    raise SystemExit(main())
