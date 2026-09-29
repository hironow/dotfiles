#!/usr/bin/env python3
"""Install declared Pi packages and the dotfiles-owned Jev extension."""

import json
import os
import shutil
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dump/harness/pi-packages.json"
EXTENSION = ROOT / "config/pi/extensions/jev-sonnet-fallback.ts"


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
