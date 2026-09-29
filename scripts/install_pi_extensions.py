#!/usr/bin/env python3
"""Install declared Pi packages and the dotfiles-owned Jev extension and agents."""

import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dump/harness/pi-packages.json"
EXTENSION = ROOT / "config/pi/extensions/jev-sonnet-fallback.ts"
AGENTS_DIR = ROOT / "config/pi/agents"
AGENT_MARKER = "<!-- dotfiles-managed: jev-codex-agent -->"


def install(agent_dir: Path, *, symlinks: bool = os.name != "nt") -> None:
    settings_path = agent_dir / "settings.json"
    settings = (
        json.loads(settings_path.read_text(encoding="utf-8"))
        if settings_path.exists()
        else {}
    )
    configured = {
        item if isinstance(item, str) else item["source"]
        for item in settings.get("packages", [])
    }
    sources = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for source in sources:
        if source not in configured:
            subprocess.run(["pi", "install", source], check=True)
    # Reconcile a settings entry whose installed files were lost; do not update
    # healthy unpinned packages just because `just deploy` ran again.
    npm = agent_dir / "npm/node_modules"
    if any(not (npm / source.removeprefix("npm:")).is_dir() for source in sources):
        subprocess.run(["pi", "update", "--extensions"], check=True)
    _place_extension(agent_dir, symlinks=symlinks)
    _render_agents(agent_dir)


def _place_extension(agent_dir: Path, *, symlinks: bool) -> None:
    destination = agent_dir / "extensions/jev-sonnet-fallback.ts"
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() == EXTENSION:
            return
        raise RuntimeError(
            f"refusing to replace unrelated extension symlink: {destination}"
        )
    if destination.exists():
        if not symlinks and destination.read_text(encoding="utf-8").startswith(
            "// dotfiles-managed: jev-sonnet-fallback\n"
        ):
            shutil.copyfile(EXTENSION, destination)
            return
        raise RuntimeError(f"refusing to replace user extension: {destination}")
    if symlinks:
        destination.symlink_to(EXTENSION)
    else:
        # Native Windows symlinks require developer mode or elevation.
        shutil.copyfile(EXTENSION, destination)


def _yaml_quoted(value: str) -> str:
    """The inside of a YAML double-quoted scalar (a JSON string) for this value."""
    return json.dumps(value)[1:-1]


def _render_agents(agent_dir: Path) -> None:
    """Write each agent with this interpreter and script as absolute paths.

    No `sh` and no fixed `$HOME/dotfiles`, so the same agents work on native Windows.
    A file we wrote is refreshed on every run (the interpreter may have moved); a file
    the user owns is never replaced.
    """
    target_dir = agent_dir / "agents"
    script = ROOT / "scripts/jev_codex_exec.py"
    for template in sorted(AGENTS_DIR.glob("*.md")):
        text = template.read_text(encoding="utf-8")
        text = text.replace("@PYTHON@", _yaml_quoted(sys.executable))
        text = text.replace("@SCRIPT@", _yaml_quoted(str(script)))
        rendered = f"{text.rstrip()}\n\n{AGENT_MARKER}\n"
        destination = target_dir / template.name
        if destination.exists() or destination.is_symlink():
            if AGENT_MARKER not in destination.read_text(encoding="utf-8"):
                raise RuntimeError(f"refusing to replace user agent: {destination}")
            if destination.read_text(encoding="utf-8") == rendered:
                continue
        target_dir.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    try:
        install(
            Path(os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi/agent")))
        )
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        RuntimeError,
    ) as error:
        print(f"Pi extension setup failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
