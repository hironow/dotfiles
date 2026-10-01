#!/usr/bin/env python3
"""Install the Claude Code plugins dotfiles requires in every Claude home.

j-cc hands Codex work to `codex:codex-rescue`, which exists only with the Codex
plugin. The required plugins are declared in dump/harness/claude-plugins.json,
each marketplace pinned to a tag, and installed through Claude Code's own
plugin CLI with CLAUDE_CONFIG_DIR set per home (ADR 0048; ADR 0037 keeps
enabledPlugins and extraKnownMarketplaces out of the settings fragments). Only
homes that exist are touched, and only the user scope counts.

Functional core / imperative shell: the steps come from the declaration and the
CLI's own --json inventory; reconcile() runs them through an injected CLI and
reads the inventory again before judging. A marketplace step runs first, since
replacing a marketplace uninstalls its plugins. An inventory that cannot be read
stops that home, and is never taken for "missing".

Usage: claude_plugins.py [--check]   (--check reports without changing)
Prints doctor-style OK/WARN lines; exit 1 on a WARN.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DECLARATION = ROOT / "dump/harness/claude-plugins.json"
CLAUDE_HOMES = (
    ".claude",
    ".claude-work-a",
    ".claude-work-b",
    ".claude-work-c",
    ".claude-work-d",
)
MARKETPLACE_LIST = ["plugin", "marketplace", "list", "--json"]
PLUGIN_LIST = ["plugin", "list", "--json"]

Step = tuple[list[str], str]  # (claude argv, what is wrong until it runs)
Cli = Callable[[list[str]], str | None]  # claude argv -> stdout, None on failure


@dataclass(frozen=True)
class Declaration:
    marketplaces: Mapping[str, str]  # name -> "owner/repo#ref"
    plugins: tuple[str, ...]  # "plugin@marketplace"


# ---- Functional core ----


def parse_source(source: str) -> tuple[str, str | None]:
    repo, _, ref = source.partition("#")
    return repo, ref or None


def _version(ref: str | None) -> str | None:
    """The plugin version a release tag stands for (v1.0.6 -> 1.0.6)."""
    match = re.fullmatch(r"v?(\d+\.\d+\.\d+)", ref or "")
    return match[1] if match else None


def marketplace_steps(
    declared: Mapping[str, str], listed: Sequence[Mapping[str, object]]
) -> list[Step]:
    steps: list[Step] = []
    for name, source in declared.items():
        repo, ref = parse_source(source)
        add = ["plugin", "marketplace", "add", source, "--scope", "user"]
        current = next((m for m in listed if m.get("name") == name), None)
        if current is None:
            steps.append((add, f"marketplace {name} is missing"))
        elif current.get("repo") != repo or current.get("ref") != ref:
            why = f"marketplace {name} is not {source}"
            steps += [(["plugin", "marketplace", "remove", name], why), (add, why)]
    return steps


def plugin_steps(
    declaration: Declaration, listed: Sequence[Mapping[str, object]]
) -> list[Step]:
    steps: list[Step] = []
    for pid in declaration.plugins:
        install = ["plugin", "install", pid, "--scope", "user"]
        user = next(
            (p for p in listed if p.get("id") == pid and p.get("scope") == "user"), None
        )
        source = declaration.marketplaces.get(pid.partition("@")[2], "")
        want = _version(parse_source(source)[1])
        if user is None:
            steps.append((install, f"{pid} is not installed for the user"))
        elif want and user.get("version") != want:
            why = f"{pid} is {user.get('version')}, not {want}"
            steps += [
                (["plugin", "uninstall", pid, "--scope", "user"], why),
                (install, why),
            ]
        elif user.get("enabled") is not True:
            steps.append(
                (["plugin", "enable", pid, "--scope", "user"], f"{pid} is disabled")
            )
    return steps


def _listed(out: str | None) -> list[dict] | None:
    try:
        listed = json.loads(out or "")
    except ValueError:
        return None
    if not isinstance(listed, list) or not all(isinstance(i, dict) for i in listed):
        return None
    return listed


def reconcile(
    declaration: Declaration, cli: Cli, *, check: bool
) -> tuple[list[str], list[str]]:
    """(what was fixed, what is still wrong) for one Claude home."""
    done: list[str] = []
    found: list[str] = []
    phases: list[tuple[list[str], Callable[[list[dict]], list[Step]]]] = [
        (
            MARKETPLACE_LIST,
            lambda listed: marketplace_steps(declaration.marketplaces, listed),
        ),
        (PLUGIN_LIST, lambda listed: plugin_steps(declaration, listed)),
    ]
    for inventory, steps_for in phases:
        listed = _listed(cli(inventory))
        if listed is None:
            return done, [f"cannot read `claude {' '.join(inventory)}`"]
        steps = steps_for(listed)
        if check:
            found += [why for _, why in steps if why not in found]
            continue
        for argv, why in steps:
            if cli(argv) is None:
                return done, [f"`claude {' '.join(argv)}` failed ({why})"]
            if why not in done:
                done.append(why)
        if steps:
            listed = _listed(cli(inventory))
            if listed is None:
                return done, [f"cannot read `claude {' '.join(inventory)}`"]
            if left := steps_for(listed):
                return done, list(dict.fromkeys(why for _, why in left))
    return done, found


# ---- Imperative shell ----


def load(path: Path) -> Declaration:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Declaration(
        marketplaces=dict(data["marketplaces"]), plugins=tuple(data["plugins"])
    )


def _cli(claude: str, home: Path) -> Cli:
    # A native path in a copied environment: one home per subprocess
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(home)}

    def run(args: list[str]) -> str | None:
        try:
            done = subprocess.run(
                [claude, *args],
                cwd=home,  # no project or local plugin scope applies here
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return done.stdout if done.returncode == 0 else None

    return run


def main(argv: Sequence[str]) -> int:
    check = "--check" in argv
    claude = shutil.which("claude")
    if not claude:
        print("WARN claude-plugins - claude not on PATH: mise install")
        return 1
    declaration = load(DECLARATION)
    homes = [
        Path.home() / name for name in CLAUDE_HOMES if (Path.home() / name).is_dir()
    ]
    failed = False
    for home in homes:
        done, problems = reconcile(declaration, _cli(claude, home), check=check)
        for fixed in done:
            print(f"OK   claude-plugins - ~/{home.name}: fixed: {fixed}")
        for problem in problems:
            failed = True
            fix = "just claude-plugins-install" if check else "see the line above"
            print(f"WARN claude-plugins - ~/{home.name}: {problem}: {fix}")
    if not failed:
        print(
            f"OK   claude-plugins - {', '.join(declaration.plugins)} "
            f"in {len(homes)} Claude home(s)"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
