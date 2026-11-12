#!/usr/bin/env python3
"""Install the plugins dotfiles gives Codex and Antigravity: today, EGM.

Claude Code and Pi read EGM from their declarations (claude_plugins.py,
install_pi_extensions.py). Codex and Antigravity have none, so this step
follows the Pi pin: Codex's marketplace at the same tag, and Antigravity from
the verified Pi bundle. `just deploy` runs it after the Pi step; a machine
without the CLI is skipped. --check reports what Codex lacks and changes
nothing (Antigravity has no way to ask).
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


def missing(
    agent_dir: Path, *, which: Which = shutil.which, run: Run = subprocess.run
) -> list[str]:
    """The Codex commands still needed; empty when Codex is absent or current."""
    codex = which("codex")
    if codex is None:
        return []
    head, installed = _codex_state(codex, run)
    return [" ".join(step) for step in codex_steps(head, installed, _tag(), EGM_COMMIT)]


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
    agy = which("agy")
    if agy is None:
        print("==> agy not on PATH; skipping EGM for Antigravity")
        return
    bundle = agent_dir / EGM_RELATIVE
    verify_egm(bundle)  # Antigravity gets only the approved Pi bundle
    run([agy, "plugin", "install", str(bundle)], check=True)


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
                print(f"WARN codex-agy-plugins - codex needs: codex {step}")
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
