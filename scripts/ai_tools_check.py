#!/usr/bin/env python3
"""Is the AI tooling complete? rtk, headroom, their telemetry and their wiring.

Functional core / imperative shell: gather() collects facts (PATH, versions,
the Windows User env, agent homes, Codex's hook trust, the headroom proxy) and
report() is a pure function from those facts to doctor's OK/WARN lines, so the
rules are unit-tested and the IO stays thin. Used by `just doctor` and
`just status`; always exits 0 (doctor counts the lines).
"""

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TELEMETRY_OFF = {"RTK_TELEMETRY_DISABLED": "1", "HEADROOM_BEACON": "off"}
CLAUDE_HOMES = (
    ".claude",
    ".claude-work-a",
    ".claude-work-b",
    ".claude-work-c",
    ".claude-work-d",
)
PI_EXTENSIONS = ("jev-sonnet-fallback.ts", "rtk.ts")
# Codex checkers in scripts/, each printing doctor lines for `--check`
CODEX_CHECKS = ("codex_hooks_trust.py", "codex_sandbox_tools.py")

Line = tuple[str, str, str]  # (level, name, detail)


@dataclass(frozen=True)
class Tool:
    paths: tuple[str, ...]  # every copy on PATH, in PATH order
    version: str | None
    mise_path: str | None  # what mise would run, if mise manages it


@dataclass(frozen=True)
class Facts:
    rtk: Tool
    headroom: Tool
    vendored_rtk: str | None  # rtk version config/pi/extensions/rtk.ts came from
    env: Mapping[str, str]  # this shell
    user_env: Mapping[str, str] | None  # persisted Windows User env; None elsewhere
    claude_homes: Mapping[str, dict]  # existing home -> its settings.json
    pi_extensions: Mapping[str, bool]  # name -> placed
    # CODEX_CHECKS' --check output by script (None: it did not run); None without codex
    codex_checks: Mapping[str, str | None] | None
    headroom_proxy: tuple[int, bool] | None  # (recorded port, healthy); None: no record


# ---- Functional core ----


def vendored_version(text: str) -> str | None:
    match = re.search(r"Vendored from rtk (\d+\.\d+\.\d+)", text)
    return match[1] if match else None


def _same(a: str, b: str) -> bool:
    norm = lambda p: os.path.normcase(os.path.normpath(p)).removesuffix(".exe")  # noqa: E731
    return norm(a) == norm(b)


def _tool(name: str, tool: Tool, package: str) -> Line:
    if not tool.paths:
        return ("WARN", name, f"not on PATH: mise install {package}")
    if len(tool.paths) > 1:
        return (
            "WARN",
            name,
            f"{len(tool.paths)} copies on PATH ({', '.join(tool.paths)}): keep the mise one "
            "(e.g. winget uninstall rtk-ai.rtk, or remove a hand-placed ~/.local/bin copy)",
        )
    if tool.mise_path is None or not _same(tool.paths[0], tool.mise_path):
        return ("WARN", name, f"{tool.paths[0]} is not mise's: mise install {package}")
    return ("OK", name, f"{tool.version or '?'} via mise")


def _missing_telemetry(env: Mapping[str, str]) -> list[str]:
    return [f"{k}={v}" for k, v in TELEMETRY_OFF.items() if env.get(k) != v]


def report(facts: Facts) -> list[Line]:
    lines = [
        _tool("rtk", facts.rtk, "rtk"),
        _tool("headroom", facts.headroom, "pypi:headroom-ai"),
    ]

    # rtk upgrades can change its own Pi extension; ours is a vendored copy
    if (
        facts.rtk.version
        and facts.vendored_rtk
        and facts.rtk.version != facts.vendored_rtk
    ):
        lines.append(
            (
                "WARN",
                "rtk-pi-extension",
                f"config/pi/extensions/rtk.ts is from rtk {facts.vendored_rtk}, "
                f"installed is {facts.rtk.version}: just rtk-pi-refresh",
            )
        )
    else:
        lines.append(
            ("OK", "rtk-pi-extension", f"vendored from rtk {facts.vendored_rtk or '?'}")
        )

    gaps = []
    if missing := _missing_telemetry(facts.env):
        gaps.append(f"this shell lacks {', '.join(missing)} (mise env)")
    for home, settings in facts.claude_homes.items():
        if missing := _missing_telemetry(settings.get("env", {})):
            gaps.append(f"~/{home} lacks {', '.join(missing)} (just sync-agents)")
    if facts.user_env is not None and (missing := _missing_telemetry(facts.user_env)):
        gaps.append(f"Windows User env lacks {', '.join(missing)} (just harden-env)")
    lines.append(
        ("WARN", "telemetry", "; ".join(gaps))
        if gaps
        else ("OK", "telemetry", "rtk and headroom telemetry off")
    )

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
    lines.append(
        (
            "WARN",
            "claude-rtk-hook",
            f"missing in ~/{', ~/'.join(unhooked)}: just sync-agents",
        )
        if unhooked
        else ("OK", "claude-rtk-hook", f"in {len(facts.claude_homes)} Claude home(s)")
    )

    absent = [name for name, placed in facts.pi_extensions.items() if not placed]
    lines.append(
        (
            "WARN",
            "pi-extensions",
            f"missing {', '.join(absent)}: just pi-extensions-install",
        )
        if absent
        else ("OK", "pi-extensions", ", ".join(facts.pi_extensions))
    )

    if facts.codex_checks is None:
        lines.append(("OK", "codex-hooks", "codex not on PATH"))
    for script, out in (facts.codex_checks or {}).items():
        if out is None:
            lines.append(("WARN", "codex", f"{script} --check failed to run"))
            continue
        for raw in out.splitlines():
            level, _, rest = raw.partition(" ")
            name, _, detail = rest.strip().partition(" - ")
            lines.append((level.strip(), name, detail))

    if facts.headroom_proxy is None:
        lines.append(("OK", "headroom-proxy", "not running; j-cc starts one on demand"))
    else:
        port, healthy = facts.headroom_proxy
        state = (
            "running"
            if healthy
            else "recorded but not answering (j-cc starts a new one)"
        )
        lines.append(("OK", "headroom-proxy", f"127.0.0.1:{port} {state}"))
    return lines


# ---- Imperative shell ----


def _run(args: list[str], *, any_exit: bool = False) -> str | None:
    """stdout of a command, or None when it cannot run (or fails, unless any_exit)."""
    try:
        done = subprocess.run(
            args,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if any_exit or done.returncode == 0 else None


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


def _windows_user_env() -> dict[str, str] | None:
    if sys.platform != "win32":
        return None
    import winreg  # noqa: PLC0415 - Windows only

    values = {}
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        for name in TELEMETRY_OFF:
            try:
                values[name] = str(winreg.QueryValueEx(key, name)[0])
            except OSError:
                continue
    return values


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def gather(home: Path) -> Facts:
    sys.path.insert(0, str(Path(__file__).parent))
    import jev_headroom  # noqa: PLC0415 - sibling script

    pi_dir = (
        Path(os.environ.get("PI_CODING_AGENT_DIR") or home / ".pi/agent") / "extensions"
    )
    port = jev_headroom.read_state(jev_headroom.state_path(home))
    codex_checks = None
    if shutil.which("codex"):
        codex_checks = {
            script: _run(
                [sys.executable, str(ROOT / "scripts" / script), "--check"],
                any_exit=True,  # exit 1 carries the WARN lines
            )
            for script in CODEX_CHECKS
        }
    return Facts(
        rtk=_tool_facts("rtk", ["--version"]),
        headroom=_tool_facts("headroom", ["--version"]),
        vendored_rtk=vendored_version(
            (ROOT / "config/pi/extensions/rtk.ts").read_text(encoding="utf-8")
        ),
        env=dict(os.environ),
        user_env=_windows_user_env(),
        claude_homes={
            name: _json(home / name / "settings.json")
            for name in CLAUDE_HOMES
            if (home / name).is_dir()
        },
        pi_extensions={name: (pi_dir / name).is_file() for name in PI_EXTENSIONS},
        codex_checks=codex_checks,
        headroom_proxy=None
        if port is None
        else (port, jev_headroom.is_headroom(jev_headroom.probe(port))),
    )


def main() -> int:
    for level, name, detail in report(gather(Path.home())):
        print(f"{level:<4} {name} - {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
