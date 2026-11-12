#!/usr/bin/env python3
"""Install the plugins dotfiles gives Codex and Antigravity: today, EGM.

Claude Code and Pi read EGM from their declarations (claude_plugins.py,
install_pi_extensions.py). Codex and Antigravity have none, so this step
follows the Pi pin: Codex's marketplace at the same tag, and Antigravity from
the verified Pi bundle. `just deploy` runs it after the Pi step; a machine
without the CLI is skipped. --check reports what either lacks and changes
nothing.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from install_pi_extensions import EGM_COMMIT, EGM_RELATIVE, EGM_SOURCE, verify_egm

EGM_REPO = "google/elephant-goldfish-model"
# mise names the Antigravity executable `antigravity` (config/mise/config.toml,
# rename_exe; a test keeps them equal); `agy` is the older name.
ANTIGRAVITY_NAMES = ("antigravity", "agy")
Run = Callable[..., subprocess.CompletedProcess]
Which = Callable[[str], str | None]


def codex_steps(
    head: str | None, installed: dict | None, tag: str, commit: str
) -> list[list[str]]:
    """What Codex needs to hold EGM at the tag. head is the commit of Codex's
    egm marketplace checkout (None when there is none); installed is its
    egm@egm entry (None when absent). Codex keeps a marketplace at the ref it
    was added with, so a moved tag needs remove, then add."""
    plugin = ["plugin", "add", "egm@egm", "--json"]
    if head != commit:
        add = ["plugin", "marketplace", "add", EGM_REPO, "--ref", tag, "--json"]
        remove = (
            []
            if head is None
            else [["plugin", "marketplace", "remove", "egm", "--json"]]
        )
        return [*remove, add, plugin]
    current = (
        installed is not None
        and installed.get("version") == tag.removeprefix("v")
        and installed.get("enabled") is True
    )
    return [] if current else [plugin]


def _out(run: Run, args: list[str]) -> str:
    return run(
        args,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout


def _codex_state(codex: str, run: Run) -> tuple[str | None, dict | None]:
    listed = json.loads(_out(run, [codex, "plugin", "marketplace", "list", "--json"]))
    root = next(
        (
            m.get("root")
            for m in listed.get("marketplaces", [])
            if m.get("name") == "egm"
        ),
        None,
    )
    head = _out(run, ["git", "-C", root, "rev-parse", "HEAD"]).strip() if root else None
    plugins = json.loads(_out(run, [codex, "plugin", "list", "--json", "-m", "egm"]))
    installed = next(
        (p for p in plugins.get("installed", []) if p.get("pluginId") == "egm@egm"),
        None,
    )
    return head, installed


def _tag() -> str:
    return EGM_SOURCE.rpartition("@")[2]


def antigravity_steps(listed: list | None, tag: str, bundle: Path) -> list[list[str]]:
    """What Antigravity needs to hold EGM at the tag. listed is its
    `plugin list --json` (None when it could not be read, which reinstalls).
    An install replaces an existing copy (antigravity 1.5.5)."""
    egm = next((p for p in listed or [] if p.get("name") == "egm"), None)
    if egm is not None and egm.get("version") == tag.removeprefix("v"):
        return [] if egm.get("enabled") is True else [["plugin", "enable", "egm"]]
    return [["plugin", "install", str(bundle)]]


def _antigravity(which: Which) -> tuple[str, str] | None:
    """The first Antigravity executable on PATH, with the name it was found by."""
    for name in ANTIGRAVITY_NAMES:
        path = which(name)
        if path is not None:
            return name, path
    return None


def _antigravity_list(path: str, run: Run) -> list | None:
    done = run(
        [path, "plugin", "list", "--json"],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if done.returncode != 0:
        return None
    try:
        listed = json.loads(done.stdout)
    except ValueError:
        return None
    return listed if isinstance(listed, list) else None


def missing(
    agent_dir: Path, *, which: Which = shutil.which, run: Run = subprocess.run
) -> list[str]:
    """The commands Codex and Antigravity still need; empty when each is
    absent or current."""
    needed = []
    codex = which("codex")
    if codex is not None:
        head, installed = _codex_state(codex, run)
        steps = codex_steps(head, installed, _tag(), EGM_COMMIT)
        needed += ["codex " + " ".join(step) for step in steps]
    found = _antigravity(which)
    if found is not None:
        name, path = found
        listed = _antigravity_list(path, run)
        if listed is None:
            return [
                *needed,
                f"{name} plugin list --json (could not read the installed plugins)",
            ]
        bundle = agent_dir / EGM_RELATIVE
        steps = antigravity_steps(listed, _tag(), bundle)
        needed += [f"{name} " + " ".join(step) for step in steps]
    return needed


def install(
    agent_dir: Path, *, which: Which = shutil.which, run: Run = subprocess.run
) -> None:
    codex = which("codex")
    if codex is None:
        print("==> codex not on PATH; skipping EGM for Codex")
    else:
        head, installed = _codex_state(codex, run)
        for step in codex_steps(head, installed, _tag(), EGM_COMMIT):
            run([codex, *step], check=True)
    found = _antigravity(which)
    if found is None:
        print(
            f"==> {' / '.join(ANTIGRAVITY_NAMES)} not on PATH; skipping EGM for Antigravity"
        )
        return
    _name, path = found
    bundle = agent_dir / EGM_RELATIVE
    for step in antigravity_steps(_antigravity_list(path, run), _tag(), bundle):
        if step[1] == "install":
            verify_egm(bundle)  # Antigravity gets only the approved Pi bundle
        run([path, *step], check=True)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="report only")
    args = parser.parse_args(argv)
    agent_dir = Path(
        os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi/agent"))
    )
    try:
        if args.check:
            needed = missing(agent_dir)
            for step in needed:
                print(f"WARN codex-agy-plugins - needs: {step}")
            return 1 if needed else 0
        install(agent_dir)
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        RuntimeError,
    ) as error:
        print(f"Codex/Antigravity plugin setup failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
