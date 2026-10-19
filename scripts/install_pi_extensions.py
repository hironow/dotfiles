#!/usr/bin/env python3
"""Install declared Pi packages and the dotfiles-owned Pi extensions and agents."""

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dump/harness/pi-packages.json"
# The web-search extension talks to a local Ollama (localhost:11434), so the
# package needs the server on every machine that installs it (ADR 0058).
OLLAMA_PACKAGE = "npm:@ollama/pi-web-search"
# Replaced by OLLAMA_PACKAGE: both register a "web_search" tool and Pi refuses
# to load the second one. Still configured entries (any pin) are removed.
RETIRED_PACKAGES = ("npm:pi-web-access",)
# Pi's own metrics, off on every machine (ADR 0058): the anonymous
# install/update report to pi.dev and the opt-in analytics share nothing.
TELEMETRY_OFF = {"enableInstallTelemetry": False, "enableAnalytics": False}
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
    for retired in retired_configured(settings.get("packages", [])):
        # Bare name: also retires a pin such as npm:pi-web-access@0.37.0.
        subprocess.run(["pi", "remove", retired], check=True)
    for source in sources:
        if source not in configured:
            subprocess.run(["pi", "install", source], check=True)
    # Reconcile a settings entry whose installed files were lost; do not update
    # healthy unpinned packages just because `just deploy` ran again.
    npm = agent_dir / "npm/node_modules"
    if any(not (npm / source.removeprefix("npm:")).is_dir() for source in sources):
        subprocess.run(["pi", "update", "--extensions"], check=True)
    # `pi` rewrote settings.json above (removals, installs); edit it last so
    # this stays the final word on the telemetry keys.
    settings = (
        json.loads(settings_path.read_text(encoding="utf-8"))
        if settings_path.exists()
        else {}
    )
    edits = telemetry_edits(settings)
    if edits:
        settings.update(edits)
        settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )
    _ensure_ollama(sources)
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


def retired_configured(packages: list) -> list[str]:
    """Retired declarations still configured, bare or pinned to a version."""
    names = (
        item if isinstance(item, str) else item.get("source", "") for item in packages
    )
    return [
        retired
        for retired in RETIRED_PACKAGES
        if any(name == retired or name.startswith(f"{retired}@") for name in names)
    ]


def telemetry_edits(settings: dict) -> dict:
    """The telemetry keys to write; empty when they are already off."""
    return {
        key: value for key, value in TELEMETRY_OFF.items() if settings.get(key) != value
    }


def ollama_missing(sources: list, ollama_on_path: str | None, reachable: bool) -> bool:
    """The Ollama web-search package is declared and no reachable Ollama serves
    localhost:11434 — as a binary on this PATH or over the loopback."""
    return OLLAMA_PACKAGE in sources and ollama_on_path is None and not reachable


def wsl_owns_ollama(
    system: str, wsl_distro: str | None, ollama_on_path: str | None, reachable: bool
) -> bool:
    """A native Windows + WSL machine where the one Ollama lives on the WSL side.

    Windows reaches a WSL server over localhost by default (WSL's NAT mode
    forwards Windows loopback into the distro), while WSL cannot reach Windows
    over localhost — so a native install would be a second server the WSL
    side could not even use. Mirrored-mode machines are caught earlier: their
    Windows-side Ollama answers the loopback probe from WSL (ADR 0058).
    """
    return (
        system == "win32"
        and wsl_distro is not None
        and ollama_on_path is None
        and not reachable
    )


def ollama_command(platform: str) -> list[str] | None:
    """Ollama's own installer per https://ollama.com/download, or None when
    that page has no installer for the platform (then we only report)."""
    if platform in ("darwin", "linux"):
        return ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"]
    if platform == "win32":
        return [
            "powershell",
            "-NoProfile",
            "-Command",
            "irm https://ollama.com/install.ps1 | iex",
        ]
    return None


def _ollama_reachable() -> bool:
    """Does an Ollama already answer on localhost:11434 (any side of it)?"""
    try:
        with urllib.request.urlopen(
            "http://localhost:11434/api/version", timeout=2
        ) as response:
            return response.status == 200
    except OSError:
        return False


def _wsl_distro() -> str | None:
    """A WSL distro name when this Windows machine has WSL (else None).

    `wsl --list --quiet` prints UTF-16LE on some hosts; stripping the NUL
    bytes reads ASCII distro names the same either way. Display-only: a
    garbled non-ASCII name must not change the decision.
    """
    try:
        done = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = done.stdout.replace(b"\x00", b"").decode(encoding="utf-8", errors="replace")
    names = [line.strip() for line in text.splitlines() if line.strip()]
    return names[0] if names else None


def _ensure_ollama(sources: list) -> None:
    """Install Ollama when the web-search package needs it and it is missing.

    Never fatal: one missing server must not hold back the extension placement,
    the same way one refused extension does not hold back the others.
    """
    ollama = shutil.which("ollama")
    if OLLAMA_PACKAGE not in sources or ollama is not None:
        return
    reachable = _ollama_reachable()
    if not ollama_missing(sources, ollama, reachable):
        return
    wsl = _wsl_distro() if sys.platform == "win32" else None
    if wsl_owns_ollama(sys.platform, wsl, ollama, reachable):
        print(
            f"==> NOTE: {OLLAMA_PACKAGE} needs Ollama; on a Windows + WSL"
            f" machine the one Ollama lives on the WSL side ({wsl}) and"
            " Windows reaches it over WSL localhost forwarding"
            " — install it from WSL (https://ollama.com/download)"
        )
        return
    print(f"==> Installing Ollama for {OLLAMA_PACKAGE} (https://ollama.com/download)")
    command = ollama_command(sys.platform)
    if command is None:
        print(
            f"    WARN: no official Ollama installer on {sys.platform};"
            " install one from https://ollama.com/download",
            file=sys.stderr,
        )
        return
    if subprocess.run(command, check=False).returncode != 0:
        print(
            "    WARN: Ollama install failed; the web_search tool needs"
            " `ollama serve` on localhost:11434"
            " (https://ollama.com/download)",
            file=sys.stderr,
        )


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
