#!/usr/bin/env python3
"""Install declared Pi packages and the dotfiles-owned Pi extensions and agents."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ollama_host import host_policy

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dump/harness/pi-packages.json"
# The web-search extension talks to a local Ollama (localhost:11434), so the
# package needs the server on every machine that installs it (ADR 0058).
OLLAMA_PACKAGE = "npm:@ollama/pi-web-search"
# Packages dotfiles no longer installs, removed from any settings that still
# declare them (bare name or pin). pi-web-access is replaced by OLLAMA_PACKAGE
# (both register a "web_search" tool and Pi refuses to load the second).
# remote-pi declares the host-provided @earendil-works/* and typebox packages
# in `dependencies` instead of `peerDependencies`, so npm vendors old 0.79.10
# copies into the Pi npm dir that extensions then resolve instead of the
# host's (pi warns about exactly this; ADR 0059).
RETIRED_PACKAGES = ("npm:pi-web-access", "npm:remote-pi")
# Pi's own metrics, off on every machine (ADR 0058): the anonymous
# install/update report to pi.dev and the opt-in analytics share nothing.
TELEMETRY_OFF = {"enableInstallTelemetry": False, "enableAnalytics": False}
EXTENSIONS_DIR = ROOT / "config/pi/extensions"
EXTENSION = EXTENSIONS_DIR / "jev-sonnet-fallback.ts"
# A vendored extension (rtk.ts) keeps the upstream file verbatim below this line
VENDORED_SENTINEL = "// --- upstream rtk.ts follows, unmodified ---\n"
AGENTS_DIR = ROOT / "config/pi/agents"
AGENT_MARKER = "<!-- dotfiles-managed: jev-codex-agent -->"
EGM_AGENT_MARKER = "<!-- dotfiles-managed: egm-reviewer -->"
EGM_SOURCE = "git:github.com/google/elephant-goldfish-model@v0.1.0"
EGM_COMMIT = "b3a35956759bf7f024af2ff061b2e0b44b438e4c"
EGM_RELATIVE = Path("git/github.com/google/elephant-goldfish-model")
EGM_GUIDE = ROOT / "ROOT_AGENTS_docs_agents_egm.md"
EGM_GUIDE_MARKER = "<!-- dotfiles-managed: egm-guide -->\n"
EGM_START = "<!-- dotfiles-managed: egm:start -->"
EGM_END = "<!-- dotfiles-managed: egm:end -->"
EGM_SKILLS = (
    "bootstrap",
    "brainstorm",
    "draft",
    "drift_report",
    "resolve",
    "review",
    "review_loop",
)
EGM_PERSONAS = (
    "bootstrap_orchestrator",
    "codebase_details",
    "comprehension",
    "design_critic",
    "implementation_readiness",
    "structural",
    "style",
    "synthesizer",
    "zoom_out",
)
EGM_STANDARDS = (
    "feature-spec",
    "heilmeier",
    "implementation-readiness",
    "re-implementation",
    "zoom-out",
)


def install(
    agent_dir: Path, *, symlinks: bool = os.name != "nt", egm_only: bool = False
) -> None:
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
    if egm_only:
        if EGM_SOURCE not in sources:
            raise RuntimeError("EGM is not declared")
        sources = [EGM_SOURCE]
    env = os.environ | {"PI_CODING_AGENT_DIR": str(agent_dir.resolve())}
    bundle = agent_dir / EGM_RELATIVE
    if EGM_SOURCE in sources and (bundle.exists() or bundle.is_symlink()):
        verify_egm(bundle)
    for retired in [] if egm_only else retired_configured(settings.get("packages", [])):
        # Bare name: also retires a pin such as npm:pi-web-access@0.37.0.
        subprocess.run(["pi", "remove", retired], check=True, env=env)
    for source in sources:
        if source not in configured or (source == EGM_SOURCE and not bundle.is_dir()):
            subprocess.run(["pi", "install", source], check=True, env=env)
    if EGM_SOURCE in sources:
        verify_egm(bundle)
    # Reconcile a settings entry whose installed files were lost; do not update
    # healthy unpinned packages just because `just deploy` ran again.
    npm = agent_dir / "npm/node_modules"
    if any(
        not (npm / source.removeprefix("npm:")).is_dir()
        for source in sources
        if source.startswith("npm:")
    ):
        subprocess.run(["pi", "update", "--extensions"], check=True, env=env)
        if EGM_SOURCE in sources:
            verify_egm(bundle)  # Recovery also reconciles pinned git packages.
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
    if not egm_only:
        _ensure_ollama(sources)
    # One extension that cannot be placed must not hold back the others
    refused = []
    extensions = [] if egm_only else sorted(EXTENSIONS_DIR.glob("*.ts"))
    for extension in extensions:
        try:
            _place_extension(agent_dir, extension, symlinks=symlinks)
        except RuntimeError as error:
            refused.append(str(error))
    _render_agents(agent_dir, egm_only=egm_only)
    if EGM_SOURCE in sources:
        _place_egm_guide(agent_dir)
    if refused:
        raise RuntimeError("; ".join(refused))


def verify_egm(root: Path) -> None:
    """Accept only the approved complete checkout; never repair over local edits."""
    required = [
        "LICENSE",
        "docs/harnesses.md",
        "docs/claude.md",
        "docs/codex.md",
        "resources/execution_instructions.md",
        ".claude-plugin/plugin.json",
        ".agents/plugins/marketplace.json",
        *(f"skills/egm_{name}/SKILL.md" for name in EGM_SKILLS),
        *(f"agents/{name}.md" for name in EGM_PERSONAS),
        *(f"resources/document_standards/{name}-standard.md" for name in EGM_STANDARDS),
    ]
    if root.is_symlink() or not (root / ".git").is_dir():
        raise RuntimeError(f"EGM is not a managed git checkout: {root}")
    for path in required:
        if not (root / path).is_file():
            raise RuntimeError(f"EGM bundle is incomplete: {root / path}")
    for args, expected in (
        (["rev-parse", "HEAD"], EGM_COMMIT),
        # Include ignored files: an ignored extra skill can still be discovered.
        (["status", "--porcelain=v1", "--untracked-files=all", "--ignored"], ""),
    ):
        done = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if done.stdout.strip() != expected:
            raise RuntimeError(
                f"EGM checkout has the wrong revision or local changes: {root}; "
                "preserve your changes and resolve it before installing (no reset applied)"
            )
    flags = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-v", "-z"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    if any(record and record[0] != "H" for record in flags.split("\0")):
        raise RuntimeError(
            f"EGM checkout has an unsafe index state: {root}; "
            "sparse/skip-worktree and assume-unchanged entries are not accepted"
        )


def egm_context(text: str, guide: Path) -> str:
    """Replace only our context block, preserving user text byte for byte."""
    block = (
        f"{EGM_START}\nWhen invoking EGM, first read `{guide.as_posix()}`.\n{EGM_END}"
    )
    if EGM_START not in text and EGM_END not in text:
        return text + ("\n\n" if text else "") + block + "\n"
    if text.count(EGM_START) != 1 or text.count(EGM_END) != 1:
        raise RuntimeError("malformed EGM context markers (not applied)")
    start, end = text.index(EGM_START), text.index(EGM_END)
    if end < start:
        raise RuntimeError("malformed EGM context markers (not applied)")
    return text[:start] + block + text[end + len(EGM_END) :]


def _place_egm_guide(agent_dir: Path) -> None:
    guide = agent_dir / "docs/agents/egm.md"
    wanted = EGM_GUIDE_MARKER + EGM_GUIDE.read_text(encoding="utf-8")
    if guide.is_symlink() or (
        guide.exists()
        and not guide.read_text(encoding="utf-8").startswith(EGM_GUIDE_MARKER)
    ):
        raise RuntimeError(f"refusing to replace user EGM guide: {guide}")
    # Follow Pi's documented precedence; an override must not hide our pointer.
    candidates = (
        "AGENTS.override.md",
        "AGENTS.md",
        "AGENTS.MD",
        "CLAUDE.md",
        "CLAUDE.MD",
    )
    context = next(
        (agent_dir / name for name in candidates if (agent_dir / name).exists()),
        agent_dir / "AGENTS.md",
    )
    if context.is_symlink():
        raise RuntimeError(f"refusing to edit symlinked Pi context: {context}")
    previous = context.read_text(encoding="utf-8") if context.exists() else ""
    rendered = egm_context(previous, guide.resolve())
    guide.parent.mkdir(parents=True, exist_ok=True)
    if not guide.exists() or guide.read_text(encoding="utf-8") != wanted:
        guide.write_text(wanted, encoding="utf-8")
    if rendered != previous:
        context.write_text(rendered, encoding="utf-8")


def vendored_body(text: str) -> str | None:
    """What the upstream tool itself writes: a vendored file below its header."""
    _header, sentinel, body = text.partition(VENDORED_SENTINEL)
    return body if sentinel else None


def retired_configured(packages: list) -> list[str]:
    """Retired declarations still configured, bare or pinned to a version."""
    names = [
        item if isinstance(item, str) else item.get("source", "") for item in packages
    ]
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


def ollama_command(platform: str) -> list[str] | None:
    """Ollama's own installer per https://ollama.com/download, or None when
    that page has no installer for the platform (then we only report)."""
    if platform in ("darwin", "linux"):
        return ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"]
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


def _ensure_ollama(sources: list) -> None:
    """Install Ollama when the web-search package needs it and it is missing.

    Never fatal: one missing server must not hold back the extension placement,
    the same way one refused extension does not hold back the others.
    """
    if OLLAMA_PACKAGE not in sources:
        return
    # Ownership precedes PATH/HTTP shortcuts: a wrong healthy backend must not
    # legitimize a second install. WSL NEVER falls back to the Linux installer;
    # Windows NEVER falls back to a standalone/WinGet installer.
    if host_policy() is not None:
        failed = True
        try:
            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts/ollama_host.py"), "--setup"],
                check=False,
                timeout=90,
            )
            failed = result.returncode != 0
        except (OSError, subprocess.SubprocessError):
            pass  # A failed setup cannot suppress unrelated extension placement.
        if failed:
            print(
                "WARN: Windows Ollama Full policy/bridge setup incomplete; run just doctor",
                file=sys.stderr,
            )
        return
    ollama = shutil.which("ollama")
    if ollama is not None:
        return
    if not ollama_missing(sources, ollama, _ollama_reachable()):
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


def _render_agents(agent_dir: Path, *, egm_only: bool = False) -> None:
    """Write each agent with this interpreter and script as absolute paths.

    No `sh` and no fixed `$HOME/dotfiles`, so the same agents work on native Windows.
    A file we wrote is refreshed on every run (the interpreter may have moved); a file
    the user owns is never replaced.
    """
    target_dir = agent_dir / "agents"
    script = ROOT / "scripts/jev_codex_exec.py"
    for template in sorted(AGENTS_DIR.glob("*.md")):
        if egm_only and template.stem != "egm-reviewer":
            continue
        marker = EGM_AGENT_MARKER if template.stem == "egm-reviewer" else AGENT_MARKER
        text = template.read_text(encoding="utf-8")
        text = text.replace("@PYTHON@", _yaml_quoted(sys.executable))
        text = text.replace("@SCRIPT@", _yaml_quoted(str(script)))
        rendered = f"{text.rstrip()}\n\n{marker}\n"
        destination = target_dir / template.name
        if destination.exists() or destination.is_symlink():
            if marker not in destination.read_text(encoding="utf-8"):
                raise RuntimeError(f"refusing to replace user agent: {destination}")
            if destination.read_text(encoding="utf-8") == rendered:
                continue
        target_dir.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--egm-only", action="store_true", help="install only EGM and its adapter"
    )
    parser.add_argument(
        "--verify-egm", action="store_true", help="verify the installed bundle only"
    )
    args = parser.parse_args()
    agent_dir = Path(
        os.environ.get("PI_CODING_AGENT_DIR", str(Path.home() / ".pi/agent"))
    )
    try:
        if args.verify_egm:
            verify_egm(agent_dir / EGM_RELATIVE)
        else:
            install(agent_dir, egm_only=args.egm_only)
    except (
        OSError,
        ValueError,
        KeyError,
        subprocess.CalledProcessError,
        RuntimeError,
    ) as error:
        print(f"Pi extension setup failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
