#!/usr/bin/env python3
"""Install declared Pi packages and the dotfiles-owned Pi extensions and agents."""

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dump/harness/pi-packages.json"
EXTENSIONS_DIR = ROOT / "config/pi/extensions"
EXTENSION = EXTENSIONS_DIR / "jev-sonnet-fallback.ts"
# A vendored extension (rtk.ts) keeps the upstream file verbatim below this line
VENDORED_SENTINEL = "// --- upstream rtk.ts follows, unmodified ---\n"
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
    # One extension that cannot be placed must not hold back the others
    refused = []
    for extension in sorted(EXTENSIONS_DIR.glob("*.ts")):
        try:
            _place_extension(agent_dir, extension, symlinks=symlinks)
        except RuntimeError as error:
            refused.append(str(error))
    _render_agents(agent_dir)
    if refused:
        raise RuntimeError("; ".join(refused))


def vendored_body(text: str) -> str | None:
    """What the upstream tool itself writes: a vendored file below its header."""
    _header, sentinel, body = text.partition(VENDORED_SENTINEL)
    return body if sentinel else None


@dataclass(frozen=True)
class Placed:
    """What sits at an extension's destination (nothing, by default)."""

    link_to_source: bool | None = None  # a symlink: does it point at our source?
    text: str | None = None  # a regular file: its content


def placement(source_text: str, placed: Placed, *, symlinks: bool) -> str:
    """Functional core: what to do with one extension's destination.

    "keep" (our symlink already), "place" (nothing there), "refresh" (a copy we
    placed: its first line is the source's), "take-over" (exactly what the
    upstream installer wrote, e.g. `rtk init`) or "refuse" (anyone else's).
    """
    if placed.link_to_source is not None:
        return "keep" if placed.link_to_source else "refuse"
    if placed.text is None:
        return "place"
    marker = source_text.splitlines()[0] + "\n"
    if not symlinks and placed.text.startswith(marker):
        return "refresh"
    if placed.text == vendored_body(source_text):
        return "take-over"
    return "refuse"


def _placed(destination: Path, source: Path) -> Placed:
    if destination.is_symlink():
        return Placed(link_to_source=destination.resolve() == source.resolve())
    if destination.exists():
        return Placed(text=destination.read_text(encoding="utf-8"))
    return Placed()


def _place_extension(agent_dir: Path, source: Path, *, symlinks: bool) -> None:
    destination = agent_dir / "extensions" / source.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    placed = _placed(destination, source)
    action = placement(source.read_text(encoding="utf-8"), placed, symlinks=symlinks)
    if action == "keep":
        return
    if action == "refuse":
        what = (
            "unrelated extension symlink"
            if placed.link_to_source is not None
            else "user extension"
        )
        raise RuntimeError(f"refusing to replace {what}: {destination} (not applied)")
    if action == "take-over":
        destination.unlink()
    if symlinks and action != "refresh":
        destination.symlink_to(source)
    else:
        # Native Windows symlinks require developer mode or elevation.
        shutil.copyfile(source, destination)


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
