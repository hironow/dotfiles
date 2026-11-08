#!/usr/bin/env python3
"""Bidirectional merge sync for agent instruction directories.

Manifest-based sync algorithm:
    Phase 1: IMPORT  - New items in import sources are copied into dotfiles.
                       Items deleted from dotfiles (tracked in manifest) are skipped.
    Phase 2: PLAN    - Diff dotfiles items against each target directory.
    Phase 3: APPLY   - Full mirror sync: add, update, and delete.

File naming convention:
    ROOT_AGENTS.md                      -> <agent>/AGENT.md (base file)
    ROOT_AGENTS_commands_strict.md      -> <agent>/commands/strict.md
    ROOT_AGENTS_hooks_formatter.py      -> <agent>/hooks/formatter.py
    ROOT_AGENTS_agents_subagent/        -> <agent>/agents/subagent/

The '_' in filenames (after ROOT_AGENTS_) are converted to '/' for target path.

Public API:
    - main(): CLI entry point
    - preview_mode(): Show sync plan without applying
    - sync_mode(): Apply sync with optional auto-confirm
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import platform
import re
import shutil
import sys
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import agent_hook_release as release_tools

if os.name != "nt":
    import agent_hook_sync as hook_sync
    import agent_hook_wiring as hook_wiring

# --- Configuration ---

DOTFILES_DIR = Path.home() / "dotfiles"
BASE_FILE = "ROOT_AGENTS.md"
# Claude-only overlay (imports the base via `@AGENTS.md`). Distributed as the
# main_file for claude-family agents; the base is written alongside as AGENTS.md.
OVERLAY_FILE = "ROOT_CLAUDE.md"
# The one source of the dotfiles hooks: merged into each claude-family agent's
# settings.json, and rendered for every other harness (codex_fragment_from_claude).
HOOK_SETTINGS_FRAGMENT = ".claude/settings.hooks.json"
# Hook commands a third-party installer writes into the agent home that dotfiles
# has since replaced with a managed hook. Their commands do not point at
# <agent>/hooks/, so _is_managed_hook_block would classify them as user blocks
# and preserve them forever — next to the replacement, which is worse than
# either alone. Retired on every sync, so a reinstall/upgrade that re-adds one
# is undone rather than silently resurrecting the old behavior (ADR 0047).
# rtk's `rtk hook claude` / `rtk hook codex`, also as a later rtk may write
# them: the binary by name or by a (quoted) path, with or without .exe, plus
# arguments of its own. A user's wrapper around it does not match.
RETIRED_HOOK_COMMAND = re.compile(
    r'^(?:"[^"]*[/\\])?rtk(?:\.exe)?"?\s+hook\s+(?:claude|codex)(?:\s|$)'
)
# An agent-hook binary, by its absolute path: a home's stable link,
# <data dir>/dotfiles/agent-hooks/current/<home>/agent-hook, where <home> is
# lowercase ASCII letters, digits, and `-`. Sync writes only the stable link,
# so a handler that names a release directly is its user's, in every harness.
# On Windows the name ends in `.exe`, and nowhere else. A Windows path is
# matched after `\` -> `/`; on POSIX `\` is a filename character, so a POSIX
# path is matched as written. The renderer (`agent-hook render`) accepts
# exactly these paths, per harness (its `registration.layouts`); the corpus
# tools/agent-hooks/internal/rendercorpus/render.jsonl holds both sides to it.
_STABLE_PATH = r"/(?:[^/]+/)*dotfiles/agent-hooks/current/[a-z0-9-]+/agent-hook"
POSIX_STABLE = re.compile(_STABLE_PATH)
WINDOWS_STABLE = re.compile(r"[A-Za-z]:" + _STABLE_PATH + r"\.exe")
# The members of a hook handler the renderer writes, per harness. A handler
# with any other member is not one it wrote, and stays its author's: Codex's
# `commandWindows` changes what runs on Windows, `async` changes when it runs,
# and Codex ignores `args`.
_CLAUDE_HANDLER_MEMBERS = frozenset({"type", "command", "args", "timeout", "onFailure"})
_CODEX_HANDLER_MEMBERS = frozenset({"type", "command", "timeout"})


@dataclass(frozen=True)
class _Launcher:
    """A shell-form launcher sync renders for a release binary."""

    start: re.Pattern[str]  # the quoted program path at the start of the command
    escaped_quote: str | None  # how `'` is written inside the quotes
    windows: bool  # the path is a Windows path (else POSIX)
    expanded: tuple[str, ...]  # what the shell still expands inside the quotes


# The forms sync renders for an agent-hook binary: Codex's shell-form
# launchers, and Claude's exec form (`args` set: the command is the path
# itself, with Claude's `${...}` placeholders still substituted). Sync owns a
# hook that runs the binary in the form it renders for that harness, like the
# hooks pointing into <agent>/hooks/: reverting the agent-hook wiring and
# syncing again then replaces them instead of leaving both. Any other command,
# including one that only mentions a release path, stays the user's. A path
# holding something its harness still reads as other than the path does not
# name itself, so it never counts, and the renderer refuses to write one. The
# renderer must write only these forms (plan: docs/plan/agent-hooks-go.md).
AGENT_HOOK_LAUNCHERS = (
    # sh: '<path>', with ' written as '\''; nothing expands
    # Each form is the program exactly as the renderer writes it: at the start
    # of the command, then one ASCII space or the end. sh, bash, and zsh split
    # words on space, tab, and newline only, so any other character after the
    # quote (an NBSP, U+3000) is part of the program's name, not a separator.
    _Launcher(re.compile(r"'((?:[^']|'\\'')*)'(?= |\Z)"), "'\\''", False, ()),
    # PowerShell: & '<path>', with ' written as ''. PowerShell also ends a
    # single-quoted string at ‘ ’ ‚ ‛, and `&` resolves * ? [ ] as wildcards
    # when the literal path is missing, so another program could run.
    _Launcher(
        re.compile(r"& '((?:[^']|'')*)'(?= |\Z)"),
        "''",
        True,
        ("\u2018", "\u2019", "\u201a", "\u201b", "*", "?", "[", "]"),
    ),
    # cmd: "<path>"; %VAR% and, with delayed expansion, !VAR! still expand
    _Launcher(re.compile(r'"([^"]*)"(?= |\Z)'), None, True, ("%", "!")),
)
_CLAUDE_EXEC_EXPANDED = ("${",)
# Header line a third-party installer writes at the top of a hook file it owns
# inside <agent>/hooks/ (herdr: "# installed by herdr"). Such a file is not a
# stale dotfiles hook, and a settings block calling it is not sync's to replace:
# treating either as ours silently uninstalled the integration on every sync.
THIRD_PARTY_HOOK_HEADERS = frozenset({"# installed by herdr"})
# Shared settings fragment merged into each claude-family agent's settings.json:
# the cross-machine env block (owned wholesale) plus curated top-level keys.
SHARED_SETTINGS_FRAGMENT = ".claude/settings.shared.json"
# OS overlay fragments layered on top of the shared fragment, keyed by
# platform.system(). A missing overlay file is simply an empty layer.
OS_SETTINGS_OVERLAYS = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}
# Per-profile fragments (one per claude-family AgentTarget.key) layered on top
# of the OS overlay, capturing intentional per-profile diffs.
PROFILE_SETTINGS_DIR = ".claude/settings.profiles"
# Sync-owned record in the AGENT HOME of the `retired` migrations that home has
# evaluated, so each runs once and a value the user sets later is left alone.
SETTINGS_STATE_FILE = "settings.sync-state.json"
# Machine-local layer read from the AGENT HOME (untracked, user-owned): the
# final override so machine-specific env / permissions.allow survive the
# wholesale env ownership. NOTE: Claude Code reads settings.local.json at
# project scope only, so this file is a sync-side input, not a CC settings file.
MACHINE_LOCAL_SETTINGS = "settings.sync-local.json"

# Directories to sync directly (in addition to ROOT_AGENTS_* files).
# Skills are NOT synced: the bunx skills CLI owns the store and
# scripts/skills_lock.py places them into every consumer home (ADR 0043).
SYNC_DIRECTORIES = ["commands", "agents"]


@dataclass
class AgentTarget:
    """Agent target configuration."""

    directory: Path
    name: str
    key: str = ""
    main_file: str | None = None
    is_import_source: bool = False
    sync_directories: list[str] | None = None
    # Hub-and-spoke distribution:
    #   overlay_main=True  -> main_file gets the OVERLAY (ROOT_CLAUDE.md) and the
    #                         base (ROOT_AGENTS.md) is written to base_secondary.
    #   overlay_main=False -> main_file gets the base directly (codex/gemini).
    # base_secondary       -> extra file that receives the base (e.g. AGENTS.md),
    #                         so a CLAUDE.md `@AGENTS.md` import resolves.
    # receives_hooks       -> hooks/* and the settings.json hook merge apply only
    #                         to claude-family agents (Claude-only mechanism).
    # receives_codex_hooks -> hooks/* (minus the Claude-only *-claude.* files,
    #                         plus *-codex.*) and the hooks.json merge for Codex.
    overlay_main: bool = False
    base_secondary: str | None = None
    receives_hooks: bool = False
    receives_codex_hooks: bool = False

    def get_sync_directories(self) -> list[str]:
        """Return directories to sync for this agent."""
        return (
            self.sync_directories
            if self.sync_directories is not None
            else SYNC_DIRECTORIES
        )


AGENTS: list[AgentTarget] = [
    AgentTarget(
        Path.home() / ".claude",
        "Claude",
        key="claude",
        main_file="CLAUDE.md",
        is_import_source=True,
        overlay_main=True,
        base_secondary="AGENTS.md",
        receives_hooks=True,
    ),
    AgentTarget(
        Path.home() / ".claude-work-a",
        "Claude(Work-A)",
        key="work-a",
        main_file="CLAUDE.md",
        overlay_main=True,
        base_secondary="AGENTS.md",
        receives_hooks=True,
    ),
    AgentTarget(
        Path.home() / ".claude-work-b",
        "Claude(Work-B)",
        key="work-b",
        main_file="CLAUDE.md",
        overlay_main=True,
        base_secondary="AGENTS.md",
        receives_hooks=True,
    ),
    AgentTarget(
        Path.home() / ".claude-work-c",
        "Claude(Work-C)",
        key="work-c",
        main_file="CLAUDE.md",
        overlay_main=True,
        base_secondary="AGENTS.md",
        receives_hooks=True,
    ),
    AgentTarget(
        Path.home() / ".claude-work-d",
        "Claude(Work-D)",
        key="work-d",
        main_file="CLAUDE.md",
        overlay_main=True,
        base_secondary="AGENTS.md",
        receives_hooks=True,
    ),
    AgentTarget(
        Path.home() / ".gemini",
        "Gemini",
        key="gemini",
        main_file="GEMINI.md",
        # ~/.gemini/GEMINI.md is shared: read by Gemini CLI (sunset 2026-06-18)
        # AND Antigravity CLI (agy), so this base sync already serves both.
        # Antigravity skills/settings/mcp live under ~/.gemini/antigravity-cli/
        # and are agy-managed (plugin / import), NOT synced here -- same rationale
        # as deferring skill installs to the bunx skills CLI. See ADR 0026.
    ),
    AgentTarget(
        Path.home() / ".codex",
        "Codex",
        key="codex",
        main_file="AGENTS.md",
        is_import_source=True,
        receives_codex_hooks=True,
    ),
]


# Short and long aliases for selecting targets from the CLI.
# Short aliases mirror the convention used by other recipes
# (`just skills env=...`, `just clean-work-env <target>`).
_TARGET_ALIASES: dict[str, str] = {
    # claude (.claude)
    "p": "claude",
    "claude": "claude",
    # claude-work-* (.claude-work-{a,b,c,d})
    "a": "work-a",
    "work-a": "work-a",
    "b": "work-b",
    "work-b": "work-b",
    "c": "work-c",
    "work-c": "work-c",
    "d": "work-d",
    "work-d": "work-d",
    # gemini (.gemini)
    "g": "gemini",
    "gemini": "gemini",
    # codex (.codex)
    "x": "codex",
    "codex": "codex",
}

# Default selection when no targets are specified.
# By design the personal claude (~/.claude) is the only target touched.
_DEFAULT_TARGETS: tuple[str, ...] = ("claude",)


def _resolve_targets(args: list[str]) -> list[str]:
    """Resolve user-supplied identifiers to canonical AgentTarget keys.

    Rules:
        - Empty args -> default selection (claude only).
        - "all" expands to every defined agent in AGENTS order.
        - Comma-separated values are split (e.g. "p,a,b").
        - Each token is matched against _TARGET_ALIASES.
        - Unknown tokens raise ValueError.
        - Order is preserved; duplicates are removed.
    """
    tokens: list[str] = []
    for raw in args:
        for piece in raw.split(","):
            piece = piece.strip()
            if piece:
                tokens.append(piece)

    if not tokens:
        return list(_DEFAULT_TARGETS)

    if any(t == "all" for t in tokens):
        return [a.key for a in AGENTS]

    resolved: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token not in _TARGET_ALIASES:
            known = ", ".join(sorted(set(_TARGET_ALIASES.keys()) | {"all"}))
            raise ValueError(f"unknown target '{token}'. Known: {known}")
        key = _TARGET_ALIASES[token]
        if key not in seen:
            resolved.append(key)
            seen.add(key)
    return resolved


def _select_agents(keys: list[str]) -> list[AgentTarget]:
    """Filter AGENTS by selected keys, preserving AGENTS order."""
    key_set = set(keys)
    return [a for a in AGENTS if a.key in key_set]


MANIFEST_FILE = ".sync-manifest.json"
MANIFEST_VERSION = 1


@dataclass
class _SyncManifest:
    """Tracks managed items per sync directory."""

    version: int = MANIFEST_VERSION
    items: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class _SyncItem:
    """Item to be synced (internal use)."""

    source: Path
    relative_path: str
    is_directory: bool


@dataclass
class _SyncAction:
    """Single sync action (internal use)."""

    source: Path
    target: Path
    relative_path: str
    is_directory: bool
    status: Literal["new", "changed", "synced"]
    # When True, the target is written as text rendered by _render_for_agent
    # (docs/agents/ references rewritten to the agent's absolute path) instead of
    # a byte-for-byte copy. Set for the base, overlay, and spoke .md files.
    render: bool = False


@dataclass
class _DeleteAction:
    """Single deletion action (internal use)."""

    target: Path
    relative_path: str
    is_directory: bool
    reason: str = "removed"  # "removed" (manifest-tracked) or "orphan" (target-only)


@dataclass
class _SyncPlan:
    """Sync plan for a single agent (internal use)."""

    agent: AgentTarget
    items: list[_SyncAction]
    deletions: list[_DeleteAction] = field(default_factory=list)


# --- Private helper functions ---


def _load_manifest(dotfiles_dir: Path) -> _SyncManifest:
    """Load manifest from disk, or initialize from current dotfiles contents."""
    manifest_path = dotfiles_dir / MANIFEST_FILE
    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        return _SyncManifest(
            version=data.get("version", MANIFEST_VERSION),
            items=data.get("items", {}),
        )
    # Auto-initialize from current dotfiles contents
    items: dict[str, list[str]] = {}
    for dir_name in SYNC_DIRECTORIES:
        dir_path = dotfiles_dir / dir_name
        if not dir_path.is_dir():
            continue
        children = sorted(
            child.name for child in dir_path.iterdir() if not child.name.startswith(".")
        )
        items[dir_name] = children
    return _SyncManifest(items=items)


def _save_manifest(dotfiles_dir: Path, manifest: _SyncManifest) -> None:
    """Persist manifest to disk."""
    manifest_path = dotfiles_dir / MANIFEST_FILE
    data = {
        "version": manifest.version,
        "items": {k: sorted(v) for k, v in manifest.items.items()},
    }
    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _convert_path(source_name: str) -> str:
    """Convert ROOT_AGENTS_xxx_yyy.ext to xxx/yyy.ext."""
    result = source_name.removeprefix("ROOT_AGENTS_")
    result = result.replace("_", "/")
    return result


def _get_directory_items(
    dotfiles_dir: Path, directories: list[str] | None = None
) -> list[_SyncItem]:
    """Get individual items within sync directories as sync items.

    Instead of syncing entire directories (e.g. commands/), syncs each
    child item (e.g. commands/strict.md, agents/reviewer) individually. This preserves unmanaged items in the target.
    """
    sources: list[_SyncItem] = []
    for dir_name in directories or SYNC_DIRECTORIES:
        dir_path = dotfiles_dir / dir_name
        if not dir_path.is_dir():
            continue
        for child in dir_path.iterdir():
            if child.name.startswith("."):
                continue
            if child.is_symlink():
                continue
            rel_path = f"{dir_name}/{child.name}"
            sources.append(
                _SyncItem(
                    source=child,
                    relative_path=rel_path,
                    is_directory=child.is_dir(),
                )
            )
    return sources


def _get_additional_sources(
    dotfiles_dir: Path, directories: list[str] | None = None
) -> list[_SyncItem]:
    """Get all ROOT_AGENTS_* files/directories and sync directory contents."""
    target_dirs = directories or SYNC_DIRECTORIES
    sources: list[_SyncItem] = []

    # Legacy: ROOT_AGENTS_* files and directories
    if directories is None:
        # Only include ROOT_AGENTS_* when using default directories
        for item in dotfiles_dir.iterdir():
            if item.name.startswith("ROOT_AGENTS_"):
                rel_path = _convert_path(item.name)
                sources.append(
                    _SyncItem(
                        source=item,
                        relative_path=rel_path,
                        is_directory=item.is_dir(),
                    )
                )

    # Direct directory structure (commands/, agents/)
    sources.extend(_get_directory_items(dotfiles_dir, target_dirs))

    return sorted(sources, key=lambda x: x.relative_path)


def _compare_files(source: Path, target: Path) -> bool:
    """Compare two files. Returns True if identical."""
    if not target.exists():
        return False
    return filecmp.cmp(source, target, shallow=False)


def _compare_directories(source: Path, target: Path) -> bool:
    """Compare two directories recursively. Returns True if identical."""
    if not target.exists():
        return False

    dcmp = filecmp.dircmp(source, target)

    if dcmp.left_only or dcmp.right_only or dcmp.funny_files:
        return False

    # dircmp.diff_files compares SHALLOWLY (size + mtime stat signature): a
    # same-length change whose mtime collides at the filesystem's timestamp
    # granularity is reported identical and sync silently skips the update
    # (observed on podman's virtiofs). Re-check every common file by content.
    _, mismatch, errors = filecmp.cmpfiles(
        source, target, dcmp.common_files, shallow=False
    )
    if mismatch or errors:
        return False

    for subdir in dcmp.common_dirs:
        if not _compare_directories(source / subdir, target / subdir):
            return False

    return True


def _get_newest_mtime(path: Path) -> float:
    """Get the newest modification time of any file in a path (recursively)."""
    if path.is_file():
        return path.stat().st_mtime
    newest = 0.0
    if not path.is_dir():
        return newest
    for child in path.iterdir():
        if child.is_file():
            newest = max(newest, child.stat().st_mtime)
        elif child.is_dir():
            newest = max(newest, _get_newest_mtime(child))
    return newest


def _build_deletion_plan(
    dotfiles_dir: Path, agent: AgentTarget, manifest: _SyncManifest
) -> list[_DeleteAction]:
    """Detect items in manifest but not in dotfiles: should be deleted from targets."""
    deletions: list[_DeleteAction] = []

    for dir_name in agent.get_sync_directories():
        manifest_items = set(manifest.items.get(dir_name, []))
        dotfiles_dir_path = dotfiles_dir / dir_name
        dotfiles_items: set[str] = set()
        if dotfiles_dir_path.is_dir():
            dotfiles_items = {
                c.name
                for c in dotfiles_dir_path.iterdir()
                if not c.name.startswith(".")
            }

        deleted_items = manifest_items - dotfiles_items

        for item_name in sorted(deleted_items):
            target_path = agent.directory / dir_name / item_name
            if target_path.exists() or target_path.is_symlink():
                deletions.append(
                    _DeleteAction(
                        target=target_path,
                        relative_path=f"{dir_name}/{item_name}",
                        is_directory=target_path.is_dir(),
                    )
                )

    return deletions


def _detect_target_only_items(
    dotfiles_dir: Path, agent: AgentTarget, manifest: _SyncManifest
) -> list[_DeleteAction]:
    """Detect items in target directories that exist only in the target.

    These are items not present in the dotfiles source and not tracked
    in the manifest (manifest-tracked deletions are handled separately
    by _build_deletion_plan).
    """
    orphans: list[_DeleteAction] = []

    for dir_name in agent.get_sync_directories():
        target_dir = agent.directory / dir_name
        source_dir = dotfiles_dir / dir_name

        if not target_dir.is_dir():
            continue

        # All source names (including symlinks — they represent valid items)
        source_names: set[str] = set()
        if source_dir.is_dir():
            for child in source_dir.iterdir():
                if not child.name.startswith("."):
                    source_names.add(child.name)

        # Manifest-tracked items (handled by _build_deletion_plan)
        manifest_items = set(manifest.items.get(dir_name, []))

        for child in sorted(target_dir.iterdir(), key=lambda p: p.name):
            if child.name.startswith("."):
                continue
            # Skip items that exist in source or are manifest-tracked
            if child.name in source_names or child.name in manifest_items:
                continue

            orphans.append(
                _DeleteAction(
                    target=child,
                    relative_path=f"{dir_name}/{child.name}",
                    is_directory=child.is_dir() and not child.is_symlink(),
                    reason="orphan",
                )
            )

    return orphans


def _detect_managed_dir_orphans(
    agent: AgentTarget, additional_sources: list[_SyncItem]
) -> list[_DeleteAction]:
    """Detect distributed spoke/hook files no longer backed by a source.

    `docs/agents/` (synced to every agent) and `hooks/` (claude-family only)
    are fully sync-owned: a file there whose ROOT_AGENTS_* source was renamed or
    removed is an orphan to delete, so stale spokes/hooks do not linger. These
    dirs are NOT manifest-tracked; the current source set is the source of truth.
    """
    managed_dirs = ["docs/agents"]
    if agent.receives_hooks or agent.receives_codex_hooks:
        managed_dirs.append("hooks")

    orphans: list[_DeleteAction] = []
    for mdir in managed_dirs:
        prefix = f"{mdir}/"
        expected = {
            item.relative_path[len(prefix) :]
            for item in additional_sources
            if item.relative_path.startswith(prefix)
            and _wants_hook(agent, item.relative_path)
        }
        target_dir = agent.directory / mdir
        if not target_dir.is_dir():
            continue
        for child in sorted(target_dir.iterdir(), key=lambda p: p.name):
            if child.name.startswith(".") or child.name in expected:
                continue
            if mdir == "hooks" and _is_third_party_hook(child):
                continue
            orphans.append(
                _DeleteAction(
                    target=child,
                    relative_path=f"{mdir}/{child.name}",
                    is_directory=child.is_dir() and not child.is_symlink(),
                    reason="orphan",
                )
            )
    return orphans


def _sync_file(source: Path, target: Path) -> None:
    """Sync a single file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _sync_directory(source: Path, target: Path) -> None:
    """Sync a directory (copy with overwrite)."""
    if target.is_symlink():
        target.unlink()
    elif target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _apply_sync_action(action: _SyncAction, agent: AgentTarget) -> None:
    """Execute one sync action.

    Rendered actions (base/overlay/spokes) are written as text with
    docs/agents/ references rewritten to the agent's absolute path; everything
    else is a byte-for-byte file or directory copy.
    """
    if action.render:
        action.target.parent.mkdir(parents=True, exist_ok=True)
        action.target.write_text(
            _render_for_agent(action.source.read_text(encoding="utf-8"), agent),
            encoding="utf-8",
        )
    elif action.is_directory:
        _sync_directory(action.source, action.target)
    else:
        _sync_file(action.source, action.target)


def _render_for_agent(text: str, agent: AgentTarget) -> str:
    """Rewrite on-demand spoke references to the agent's absolute location.

    The base/overlay/spoke prose references playbooks as `docs/agents/X.md`
    (relative). When distributed globally, a relative path would resolve against
    the working project, not the agent's home, so it is rewritten to an absolute
    `<agent_home>/docs/agents/X.md`. Deterministic -> idempotent.
    """
    return text.replace("docs/agents/", f"{agent.directory}/docs/agents/")


def _is_spoke(relative_path: str) -> bool:
    """A spoke is a docs/agents/*.md file (its references need rendering)."""
    return relative_path.startswith("docs/agents/") and relative_path.endswith(".md")


def _wants_hook(agent: AgentTarget, relative_path: str) -> bool:
    """Whether this agent receives a distributed item.

    hooks/ goes to claude-family agents and Codex only. `*-claude.*` files
    (the Claude rtk wrapper, which strips an approval Claude would honor) are
    Claude's; `*-codex.*` files are Codex's.
    """
    if not relative_path.startswith("hooks/"):
        return True
    name = relative_path.rsplit("/", 1)[-1]
    if agent.receives_hooks:
        return "-codex." not in name
    if agent.receives_codex_hooks:
        return "-claude." not in name
    return False


def _render_hook_command(
    command: str, agent: AgentTarget, system: str | None = None
) -> str:
    """Point a hook command at the agent's global hooks dir, not a project dir.

    Paths render posix-style everywhere (identical to str() on mac/linux,
    ``C:/...`` on Windows). On Windows the ``bash`` prefix becomes ``sh``:
    bare ``bash`` resolves to the System32 WSL bash before Git Bash, while
    ``sh`` has no System32 shadow and resolves to Git for Windows' sh (which
    is bash) — same strategy as the justfile's windows-shell (ADR 0037).
    """
    hooks_prefix = f'"{agent.directory.as_posix()}/hooks/'
    rendered = command.replace(
        '"$CLAUDE_PROJECT_DIR/.claude/hooks/', hooks_prefix
    ).replace('"$CODEX_HOME/hooks/', hooks_prefix)
    if (system or platform.system()) == "Windows":
        rendered = rendered.replace(f"bash {hooks_prefix}", f"sh {hooks_prefix}")
    return rendered


def _is_third_party_hook(path: Path) -> bool:
    """A hooks/ file whose header names a third-party installer as its owner."""
    path = Path(path)  # callers may hold a PurePath stand-in (tests)
    if not path.is_file():
        return False
    try:
        with path.open(encoding="utf-8-sig", errors="replace") as f:
            head = [next(f, "") for _ in range(5)]
    except OSError:
        return False
    return any(line.strip() in THIRD_PARTY_HOOK_HEADERS for line in head)


def _is_stable_link_path(
    path: str, *, windows: bool, expanded: tuple[str, ...]
) -> bool:
    """Is this program path, as its harness runs it, a home's stable link to
    an agent-hook release?"""
    if any(token in path for token in expanded):
        return False
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in path):
        return False  # the renderer never writes a control character
    if windows:
        return WINDOWS_STABLE.fullmatch(path.replace("\\", "/")) is not None
    return POSIX_STABLE.fullmatch(path) is not None


def _has_only_rendered_members(hook: dict, *, codex: bool) -> bool:
    """Is this a command handler holding only members sync writes for this
    harness? Any other member (Codex's commandWindows, async) is its author's."""
    members = _CODEX_HANDLER_MEMBERS if codex else _CLAUDE_HANDLER_MEMBERS
    return hook.get("type") == "command" and set(hook) <= members


def _runs_agent_hook_release(hook: dict, *, codex: bool) -> bool:
    """Does this hook run an agent-hook binary through a home's stable link
    as its program, placed and quoted as sync renders it for this
    harness (Claude's exec form; Codex's AGENT_HOOK_LAUNCHERS), with no member
    the renderer never writes? What follows the program is not compared, so a
    changed template's older handlers are still owned."""
    command = hook.get("command")
    if not isinstance(command, str) or not _has_only_rendered_members(
        hook, codex=codex
    ):
        return False
    if not codex:
        if not isinstance(hook.get("args"), list):  # exec form: the path itself
            return False
        windows = re.match(r"[A-Za-z]:[\\/]", command) is not None
        return _is_stable_link_path(
            command, windows=windows, expanded=_CLAUDE_EXEC_EXPANDED
        )
    for launcher in AGENT_HOOK_LAUNCHERS:
        match = launcher.start.match(command)  # the renderer writes no padding
        if match is None:
            continue
        path = match[1]
        if launcher.escaped_quote is not None:
            path = path.replace(launcher.escaped_quote, "'")
        return _is_stable_link_path(
            path, windows=launcher.windows, expanded=launcher.expanded
        )
    return False


def _is_agent_hook_group(group: object, *, codex: bool) -> bool:
    """A hook group of agent-hook's: at least one handler, and every one runs
    agent-hook as sync renders it (_runs_agent_hook_release). A group that
    mixes it with another command is its user's."""
    handlers = group.get("hooks") if isinstance(group, dict) else None
    return (
        isinstance(handlers, list)
        and bool(handlers)
        and all(
            isinstance(handler, dict) and _runs_agent_hook_release(handler, codex=codex)
            for handler in handlers
        )
    )


def _is_managed_hook_block(
    block: dict, agent: AgentTarget, *, third_party: frozenset[str] | None = None
) -> bool:
    """A hook block sync owns: every command points at the agent's hooks dir
    or runs an agent-hook binary in the form sync renders for this harness
    (_runs_agent_hook_release).

    Commands are normalized ``\\`` -> ``/`` before matching so legacy
    Windows-rendered blocks (backslash paths) are recognized as managed and
    replaced on the next sync instead of surviving as duplicates. A command
    calling a third-party-owned hook file (see _is_third_party_hook) is the
    installer's, so a block containing one is not managed.
    """
    inner = block.get("hooks", [])
    marker = f"{agent.directory.as_posix()}/hooks/"

    def managed(hook: dict) -> bool:
        # A member sync never writes makes the handler its author's, whatever
        # its command points at (Codex's commandWindows runs another command).
        if not _has_only_rendered_members(hook, codex=agent.receives_codex_hooks):
            return False
        if _runs_agent_hook_release(hook, codex=agent.receives_codex_hooks):
            return True
        command = hook.get("command", "").replace("\\", "/")
        if marker not in command:
            return False
        prefix, _, suffix = command.partition(marker)
        if prefix[-1:] in {'"', "'"}:
            name = suffix.split(prefix[-1], 1)[0]
        else:
            match = re.match(r'[^"\s]+', suffix)
            name = match[0] if match else ""
        return not (
            name
            and (
                name in third_party
                if third_party is not None
                else _is_third_party_hook(agent.directory / "hooks" / name)
            )
        )

    return bool(inner) and all(managed(h) for h in inner)


def _is_retired_hook_block(block: dict) -> bool:
    """A block owned by a third-party installer that dotfiles has replaced.

    Retired only when EVERY command in the block is a retired one (the same
    all() shape as _is_managed_hook_block), so a hand-written block that merely
    also calls one is the user's and is left alone rather than silently
    trimmed.
    """
    inner = block.get("hooks", [])
    return bool(inner) and all(
        RETIRED_HOOK_COMMAND.match(h.get("command", "").strip()) for h in inner
    )


_CLAUDE_HOOK_COMMAND = re.compile(
    r'^bash "\$CLAUDE_PROJECT_DIR/\.claude/hooks/([\w.-]+)"$'
)


def _codex_hook_command(command: str) -> str:
    """One Claude hook command as Codex runs it.

    The exit-2 guards (`block-*`) go through `guard-codex.sh`, which turns exit 2
    into Codex's deny JSON (pwsh turns exit 2 into 1, and Codex fails open on
    1). A `-claude.` script has a `-codex.` twin. The rest run as they are.
    """
    match = _CLAUDE_HOOK_COMMAND.match(command)
    if match is None:
        msg = f"hook command not in the form the renderer knows: {command}"
        raise ValueError(msg)
    script = match.group(1)
    if script.startswith("block-"):
        return f'bash "$CODEX_HOME/hooks/guard-codex.sh" {script}'
    return f'bash "$CODEX_HOME/hooks/{script.replace("-claude.", "-codex.")}"'


def codex_fragment_from_claude(fragment: dict) -> dict:
    """Codex's hooks.json fragment, rendered from the one Claude source.

    Codex reads Claude-shaped blocks with the same event and matcher names, so
    only the commands change. Keeping no second copy in the repo also keeps
    Codex from loading a project `.codex/hooks.json` there on top of the
    global one, which ran every hook twice inside this repository.
    """
    return {
        "hooks": {
            event: [
                {
                    "matcher": block.get("matcher"),
                    "hooks": [
                        {**hook, "command": _codex_hook_command(hook["command"])}
                        for hook in block.get("hooks", [])
                    ],
                }
                for block in blocks
            ]
            for event, blocks in fragment.get("hooks", {}).items()
        }
    }


def hook_fragment(dotfiles_dir: Path, agent: AgentTarget) -> dict | None:
    """The hook fragment for this agent, from the one source (None without it)."""
    source = dotfiles_dir / HOOK_SETTINGS_FRAGMENT
    if not source.exists():
        return None
    fragment = json.loads(source.read_text(encoding="utf-8"))
    return (
        codex_fragment_from_claude(fragment) if agent.receives_codex_hooks else fragment
    )


def merge_hook_values(
    target: dict,
    desired: dict[str, list[dict]],
    managed: dict[str, set[int]],
) -> tuple[dict, bool]:
    """Compute a hook merge from values, including prior ownership decisions."""
    target = deepcopy(target)
    hooks = target.get("hooks", {})
    changed = False
    for event in set(hooks) | set(desired):
        existing = hooks.get(event, [])
        kept = [
            block
            for index, block in enumerate(existing)
            if index not in managed.get(event, set())
            and not _is_retired_hook_block(block)
        ]
        new_list = kept + deepcopy(desired.get(event, []))
        if new_list != existing:
            changed = True
        if new_list:
            hooks[event] = new_list
        else:
            hooks.pop(event, None)
    if hooks:
        target["hooks"] = hooks
    else:
        target.pop("hooks", None)
    return target, changed


def render_hook_values(fragment: dict, agent: AgentTarget, system: str) -> dict:
    """Render the scripts' fragment from values, with the OS passed explicitly."""
    return {
        "hooks": {
            event: [
                {
                    "matcher": block.get("matcher"),
                    "hooks": [
                        {
                            **handler,
                            "command": _render_hook_command(
                                handler["command"], agent, system=system
                            ),
                        }
                        for handler in block.get("hooks", [])
                    ],
                }
                for block in blocks
            ]
            for event, blocks in fragment.get("hooks", {}).items()
        }
    }


def _merge_hook_settings(
    dotfiles_dir: Path,
    agent: AgentTarget,
    dry_run: bool = False,
    system: str | None = None,
) -> bool:
    """Merge the hook fragment into the agent's settings.json, update-in-place.

    NOT manifest-tracked: settings.json is a user-owned shared file, so the
    item-granular manifest (whole-file add/delete) would clobber user hooks on an
    orphan sweep. Instead, sync OWNS exactly the hook blocks whose commands all
    point at ``<agent>/hooks/`` (see _is_managed_hook_block): on each run those
    managed blocks are replaced by the current fragment (so a changed/removed
    hook command does not leave a stale duplicate), while user-authored blocks
    and other settings keys are preserved untouched. The one exception to
    "preserve user blocks" is RETIRED_HOOK_COMMAND (see _is_retired_hook_block):
    third-party installer blocks dotfiles now replaces, dropped on every run so a
    reinstall cannot resurrect them. Re-running with an unchanged fragment is a
    no-op. With dry_run=True nothing is written. Returns True if the file would
    change.
    """
    fragment = hook_fragment(dotfiles_dir, agent)
    if fragment is None:
        return False
    target_path = agent.directory / (
        "hooks.json" if agent.receives_codex_hooks else "settings.json"
    )
    target = (
        json.loads(target_path.read_text(encoding="utf-8"))
        if target_path.exists()
        else {}
    )

    # Desired managed blocks per event, rendered to the agent's absolute hooks path.
    desired = render_hook_values(fragment, agent, system or platform.system())["hooks"]

    managed = {
        event: {
            index
            for index, block in enumerate(blocks)
            if _is_managed_hook_block(block, agent)
        }
        for event, blocks in target.get("hooks", {}).items()
    }
    target, changed = merge_hook_values(target, desired, managed)

    if changed and not dry_run:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(target, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return changed


def _settings_layer_paths(
    dotfiles_dir: Path, agent: AgentTarget, system: str
) -> list[Path]:
    os_name = OS_SETTINGS_OVERLAYS.get(system)
    return [
        dotfiles_dir / SHARED_SETTINGS_FRAGMENT,
        *(
            [dotfiles_dir / f".claude/settings.shared.{os_name}.json"]
            if os_name
            else []
        ),
        *(
            [dotfiles_dir / PROFILE_SETTINGS_DIR / f"{agent.key}.json"]
            if agent.key
            else []
        ),
        agent.directory / MACHINE_LOCAL_SETTINGS,
    ]


def validate_hook_layers(
    dotfiles_dir: Path, agents: list[AgentTarget], system: str
) -> None:
    """Refuse hooks in every settings layer before sync writes anything."""
    for agent in agents:
        if not agent.receives_hooks:
            continue
        for path in _settings_layer_paths(dotfiles_dir, agent, system):
            if not path.exists():
                continue
            layer = json.loads(path.read_text(encoding="utf-8"))
            if "hooks" in layer.get("settings", {}) or any(
                "hooks" in keys for keys in layer.get("retired", {}).values()
            ):
                raise ValueError(f"{path}: hooks in a settings layer are not allowed")


def hook_home(
    dotfiles_dir: Path, agent: AgentTarget, roots: hook_wiring.Roots, system: str
) -> hook_sync.HookHome:
    """Read fragments and ownership once per fresh home plan, under the lock."""

    def read_rules() -> hook_sync.HomeRules:
        validate_hook_layers(dotfiles_dir, [agent], system)
        script_fragment = hook_fragment(dotfiles_dir, agent)
        scripts = (
            None
            if script_fragment is None
            else render_hook_values(script_fragment, agent, system)
        )
        shared = _compose_settings_fragments(dotfiles_dir, agent, system)
        hooks_dir = agent.directory / "hooks"
        third_party = frozenset(
            path.relative_to(hooks_dir).as_posix()
            for path in hooks_dir.rglob("*")
            if _is_third_party_hook(path)
        )

        def owned(block: dict) -> bool:
            if (
                not isinstance(block, dict)
                or not isinstance(block.get("hooks"), list)
                or not all(isinstance(h, dict) for h in block["hooks"])
            ):
                return False
            # Sync's own rule, as doctor reads it: a block that runs any
            # home's stable link is sync's, and gives way to this home's.
            return _is_managed_hook_block(block, agent, third_party=third_party)

        def managed_from(settings: dict) -> dict:
            return {
                event: kept
                for event, blocks in settings.get("hooks", {}).items()
                if (kept := [block for block in blocks if owned(block)])
            }

        def hook_merge(settings: dict, desired: dict) -> dict:
            managed = {
                event: {i for i, b in enumerate(blocks) if owned(b)}
                for event, blocks in settings.get("hooks", {}).items()
            }
            return merge_hook_values(settings, desired.get("hooks", {}), managed)[0]

        def shared_merge(settings: dict, state: dict) -> tuple[dict, dict]:
            if shared is None:
                return deepcopy(settings), deepcopy(state)
            merged, next_state, _, _ = merge_settings_values(settings, shared, state)
            return merged, next_state

        def wired_from(settings: dict) -> bool:
            return any(
                _runs_agent_hook_release(h, codex=False)
                for blocks in managed_from(settings).values()
                for block in blocks
                for h in block["hooks"]
            )

        def retired_from(settings: dict) -> bool:
            return any(
                isinstance(block, dict) and _is_retired_hook_block(block)
                for blocks in settings.get("hooks", {}).values()
                for block in blocks
            )

        return hook_sync.HomeRules(
            scripts, hook_merge, shared_merge, managed_from, wired_from, retired_from
        )

    return hook_sync.HookHome(agent.key, agent.directory, read_rules)


def hook_configuration(
    dotfiles_dir: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    source: hook_sync.ReleaseSource | None = None,
    all_agents: list[AgentTarget] | None = None,
    system: str | None = None,
    processes: hook_sync.CodexProcesses | None = None,
) -> hook_sync.HookConfiguration:
    """Connect the hook commands to the same targets, aliases, and value merges."""
    dotfiles_dir = DOTFILES_DIR if dotfiles_dir is None else dotfiles_dir
    env = dict(os.environ if env is None else env)
    agents = AGENTS if all_agents is None else all_agents
    system = system or platform.system()
    roots = hook_wiring.Roots.from_env(env)
    return hook_sync.HookConfiguration(
        roots=roots,
        homes=tuple(
            hook_home(dotfiles_dir, agent, roots, system)
            for agent in agents
            if agent.receives_hooks
        ),
        registrations=tuple(
            agent.directory
            / ("hooks.json" if agent.receives_codex_hooks else "settings.json")
            for agent in agents
            if agent.receives_hooks or agent.receives_codex_hooks
        ),
        source=hook_sync.GoReleaseSource(env) if source is None else source,
        processes=hook_sync.PgrepCodex(env) if processes is None else processes,
        resolve=_resolve_targets,
        validate=lambda keys: validate_hook_layers(
            dotfiles_dir, [agent for agent in agents if agent.key in keys], system
        ),
        system=system,
    )


def _compose_settings_fragments(
    dotfiles_dir: Path, agent: AgentTarget, system: str | None = None
) -> dict | None:
    """Compose the settings fragment layers into one effective desired state.

    Layers, later wins (see repo CLAUDE.md and ADR 0037):
      1. ``.claude/settings.shared.json``            all OS / all profiles
      2. ``.claude/settings.shared.<os>.json``       running OS (macos/linux/windows)
      3. ``.claude/settings.profiles/<key>.json``    per profile (AgentTarget.key)
      4. ``<agent_home>/settings.sync-local.json``   machine-local, untracked

    ``env`` composes key-wise; ``settings`` composes key-wise with a one-level
    deep-merge when both sides are dicts (so shared can own ``permissions.deny``
    while a profile owns ``permissions.defaultMode``). Missing layer files are
    empty layers. ``retired`` (migration id -> {key: [values]}) composes per id,
    key-wise. ``system`` (a ``platform.system()`` value) is injectable for
    tests. Returns the composed ``{"env": ..., "settings": ..., "retired": ...}``
    dict, or None when no fragment layer exists (merge is then a no-op).
    """
    layer_paths = _settings_layer_paths(
        dotfiles_dir, agent, system or platform.system()
    )
    layers = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in layer_paths
        if path is not None and path.exists()
    ]
    if not layers:
        return None

    composed: dict = {}
    for layer in layers:
        if "env" in layer:
            composed.setdefault("env", {}).update(layer["env"])
        for key, value in layer.get("settings", {}).items():
            settings = composed.setdefault("settings", {})
            if isinstance(value, dict) and isinstance(settings.get(key), dict):
                settings[key] = {**settings[key], **value}
            else:
                settings[key] = value
        for migration, keys in layer.get("retired", {}).items():
            composed.setdefault("retired", {}).setdefault(migration, {}).update(keys)
    return composed


def _write_settings(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def _retire_settings(fragment: dict, target: dict, applied: set[str]) -> list[str]:
    """Delete retired keys still holding a value the fragments wrote; return the
    migrations evaluated now. A migration runs once per home, and a key the
    composed settings still set is theirs, not retired."""
    evaluated = sorted(set(fragment.get("retired", {})) - applied)
    for migration in evaluated:
        for key, values in fragment["retired"][migration].items():
            if (
                key not in fragment.get("settings", {})
                and key in target
                and target[key] in values
            ):
                del target[key]
    return evaluated


def merge_settings_values(
    target: dict, fragment: dict, state: dict
) -> tuple[dict, dict, bool, bool]:
    """Compute shared settings and retirement state without reading or writing."""
    target, fragment, state = deepcopy((target, fragment, state))
    before = json.dumps(target, sort_keys=True, ensure_ascii=False)
    if "env" in fragment:
        target["env"] = fragment["env"]
    for key, value in fragment.get("settings", {}).items():
        target[key] = value
    applied = set(state.get("retired", []))
    evaluated = _retire_settings(fragment, target, applied)
    if evaluated:
        state["retired"] = sorted(applied | set(evaluated))
    changed = json.dumps(target, sort_keys=True, ensure_ascii=False) != before
    return target, state, changed, bool(evaluated)


def _merge_settings_fragment(
    dotfiles_dir: Path,
    agent: AgentTarget,
    dry_run: bool = False,
    system: str | None = None,
) -> bool:
    """Merge the composed settings fragments into the agent's settings.json.

    Update-in-place, parallel to _merge_hook_settings but with a STRONGER
    ownership model: the composed ``env`` block is owned wholesale (the
    target's env is replaced, so keys dropped from the fragments are removed) --
    machine-local env therefore belongs in the agent home's
    ``settings.sync-local.json`` layer (composed last; sync never edits it).
    The composed ``settings`` object holds curated top-level keys that are
    upserted (add/update only); every other target key (enabledPlugins, hooks,
    statusLine, ...) is preserved untouched. A key the fragments stop writing
    is removed only through ``retired`` (see _retire_settings); the evaluated
    migrations are recorded in the home's settings.sync-state.json BEFORE
    settings.json is written, so a failure in between leaves the old value
    rather than a later retry over a value the user set again. Idempotent;
    dry_run=True writes nothing. Returns True if settings.json would change.
    """
    fragment = _compose_settings_fragments(dotfiles_dir, agent, system=system)
    if fragment is None:
        return False
    target_path = agent.directory / "settings.json"
    target = (
        json.loads(target_path.read_text(encoding="utf-8"))
        if target_path.exists()
        else {}
    )

    state_path = agent.directory / SETTINGS_STATE_FILE
    state = (
        json.loads(state_path.read_text(encoding="utf-8"))
        if state_path.exists()
        else {}
    )
    target, state, changed, state_changed = merge_settings_values(
        target, fragment, state
    )

    if dry_run:
        return changed
    if state_changed:
        _write_settings(state_path, state)
    if changed:
        _write_settings(target_path, target)
    return changed


def _plan_text_file(
    source: Path, target: Path, relative_path: str, agent: AgentTarget
) -> _SyncAction:
    """Plan a rendered text file: status uses the rendered expected content."""
    rendered = _render_for_agent(source.read_text(encoding="utf-8"), agent)
    if not target.exists():
        status: Literal["new", "changed", "synced"] = "new"
    elif target.read_text(encoding="utf-8") == rendered:
        status = "synced"
    else:
        status = "changed"
    return _SyncAction(
        source=source,
        target=target,
        relative_path=relative_path,
        is_directory=False,
        status=status,
        render=True,
    )


def _build_sync_plan(
    dotfiles_dir: Path, agent: AgentTarget, additional_sources: list[_SyncItem]
) -> _SyncPlan:
    """Build sync plan for an agent."""
    actions: list[_SyncAction] = []

    # Base + overlay (skip for agents without a main_file, e.g. .agents global).
    if agent.main_file is not None:
        base_src = dotfiles_dir / BASE_FILE
        if agent.overlay_main:
            # claude-family: main_file <- overlay; base written alongside.
            overlay_src = dotfiles_dir / OVERLAY_FILE
            actions.append(
                _plan_text_file(
                    overlay_src,
                    agent.directory / agent.main_file,
                    agent.main_file,
                    agent,
                )
            )
            if agent.base_secondary is not None:
                actions.append(
                    _plan_text_file(
                        base_src,
                        agent.directory / agent.base_secondary,
                        agent.base_secondary,
                        agent,
                    )
                )
        else:
            # codex/gemini: main_file <- base directly.
            actions.append(
                _plan_text_file(
                    base_src,
                    agent.directory / agent.main_file,
                    agent.main_file,
                    agent,
                )
            )

    # Additional sources (filtered by agent's sync_directories if customized)
    for item in additional_sources:
        # Skip items outside this agent's custom sync directories
        if agent.sync_directories is not None:
            item_dir = item.relative_path.split("/")[0]
            if item_dir not in agent.sync_directories:
                continue
        # hooks/ goes to claude-family agents and Codex only (see _wants_hook).
        if not _wants_hook(agent, item.relative_path):
            continue

        # Spokes (docs/agents/*.md) are rendered like the base/overlay.
        if not item.is_directory and _is_spoke(item.relative_path):
            actions.append(
                _plan_text_file(
                    item.source,
                    agent.directory / item.relative_path,
                    item.relative_path,
                    agent,
                )
            )
            continue

        target_path = agent.directory / item.relative_path

        status: Literal["new", "changed", "synced"]
        if target_path.is_symlink():
            # Symlinks in targets should always be replaced with real copies
            status = "changed"
        elif item.is_directory:
            if not target_path.exists():
                status = "new"
            elif _compare_directories(item.source, target_path):
                status = "synced"
            else:
                status = "changed"
        else:
            if not target_path.exists():
                status = "new"
            elif _compare_files(item.source, target_path):
                status = "synced"
            else:
                status = "changed"

        actions.append(
            _SyncAction(
                source=item.source,
                target=target_path,
                relative_path=item.relative_path,
                is_directory=item.is_directory,
                status=status,
            )
        )

    return _SyncPlan(agent=agent, items=actions)


def _print_header(text: str) -> None:
    """Print a header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def _print_plan(
    plans: list[_SyncPlan],
    dotfiles_dir: Path,
    verbose: bool = False,
    hook_session: hook_sync.SyncSession | None = None,
    system: str | None = None,
) -> bool:
    """Print sync plan. Returns True if there are changes to apply."""
    # A recovery, or any Claude home that changes or stops, is a change.
    has_changes = bool(hook_session and hook_session.changed)

    print("📁 Source:", dotfiles_dir)
    print(f"   Base: {BASE_FILE}")

    additional = _get_additional_sources(dotfiles_dir)
    if additional:
        print("   Additional:")
        for item in additional:
            icon = "📁" if item.is_directory else "📄"
            print(f"     {icon} {item.source.name} → {item.relative_path}")

    print("\n" + "-" * 60)

    for plan in plans:
        print(f"\n📋 {plan.agent.name}: {plan.agent.directory}")

        for action in plan.items:
            icon = "📁" if action.is_directory else "📄"

            if action.status == "new":
                print(f"  🆕 {icon} {action.relative_path} [NEW]")
                has_changes = True
            elif action.status == "changed":
                print(f"  📝 {icon} {action.relative_path} [CHANGED]")
                has_changes = True
            elif verbose:
                print(f"  ✅ {icon} {action.relative_path} [SYNCED]")

        if plan.agent.receives_hooks and hook_session is not None:
            hook_plan = hook_session.plans[plan.agent.key].plan
            print(
                f"  📄 settings.json [agent-hook: {hook_plan.action}]"
                + (f" {hook_plan.reason}" if hook_plan.reason else "")
            )
        elif (
            plan.agent.receives_hooks or plan.agent.receives_codex_hooks
        ) and _merge_hook_settings(
            dotfiles_dir, plan.agent, dry_run=True, system=system
        ):
            hooks_file = (
                "hooks.json" if plan.agent.receives_codex_hooks else "settings.json"
            )
            print(f"  📝 📄 {hooks_file} [HOOKS MERGE]")
            has_changes = True

        if (
            plan.agent.receives_hooks
            and hook_session is None
            and _merge_settings_fragment(
                dotfiles_dir, plan.agent, dry_run=True, system=system
            )
        ):
            print("  📝 📄 settings.json [SHARED MERGE]")
            has_changes = True

        for deletion in plan.deletions:
            icon = "📁" if deletion.is_directory else "📄"
            if deletion.reason == "orphan":
                print(
                    f"  🗑️  {icon} {deletion.relative_path}"
                    " [TARGET-ONLY → will be removed]"
                )
            else:
                print(f"  🗑️  {icon} {deletion.relative_path} [DELETE]")
            has_changes = True

    return has_changes


def _confirm(prompt: str) -> bool:
    """Ask for confirmation."""
    try:
        response = input(f"{prompt} [y/N] ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# --- Import (target -> dotfiles) ---


@dataclass
class _ImportAction:
    """Single import action: item in target to import into dotfiles."""

    source_path: Path
    resolved_path: Path
    dotfiles_dest: Path
    relative_path: str
    is_directory: bool
    is_symlink: bool
    status: Literal["import", "conflict", "exists", "deleted"]


@dataclass
class _ImportPlan:
    """Import plan for a single agent."""

    agent: AgentTarget
    items: list[_ImportAction]


def _build_import_plan(
    dotfiles_dir: Path,
    agent: AgentTarget,
    manifest: _SyncManifest,
) -> _ImportPlan:
    """Build import plan: detect importable items in target's SYNC_DIRECTORIES.

    Uses manifest to distinguish genuinely new items from previously deleted ones.
    Both symlinks and regular directories/files are considered for import.
    """
    actions: list[_ImportAction] = []

    for dir_name in agent.get_sync_directories():
        target_dir = agent.directory / dir_name
        if not target_dir.is_dir():
            continue

        manifest_items = set(manifest.items.get(dir_name, []))
        dotfiles_dir_path = dotfiles_dir / dir_name
        dotfiles_items: set[str] = set()
        if dotfiles_dir_path.is_dir():
            dotfiles_items = {
                c.name
                for c in dotfiles_dir_path.iterdir()
                if not c.name.startswith(".")
            }

        for child in target_dir.iterdir():
            if child.name.startswith("."):
                continue

            rel_path = f"{dir_name}/{child.name}"
            dotfiles_dest = dotfiles_dir / rel_path
            is_symlink = child.is_symlink()
            resolved = child.resolve() if is_symlink else child

            if not resolved.exists():
                # Broken symlink, skip
                continue

            if child.name in dotfiles_items:
                # Already exists in dotfiles
                if resolved.is_dir():
                    if _compare_directories(dotfiles_dest, resolved):
                        status: Literal["import", "conflict", "exists", "deleted"] = (
                            "exists"
                        )
                    elif _get_newest_mtime(resolved) > _get_newest_mtime(dotfiles_dest):
                        # Import source is newer: update dotfiles
                        status = "import"
                    else:
                        # Dotfiles is newer or same age: keep dotfiles
                        status = "conflict"
                elif _compare_files(dotfiles_dest, resolved):
                    status = "exists"
                elif resolved.stat().st_mtime > dotfiles_dest.stat().st_mtime:
                    # Import source file is newer: update dotfiles
                    status = "import"
                else:
                    # Dotfiles file is newer or same age: keep dotfiles
                    status = "conflict"
            elif child.name in manifest_items:
                # Was managed but removed from dotfiles: intentional deletion
                status = "deleted"
            else:
                # Not in dotfiles AND not in manifest: genuinely new
                status = "import"

            actions.append(
                _ImportAction(
                    source_path=child,
                    resolved_path=resolved,
                    dotfiles_dest=dotfiles_dest,
                    relative_path=rel_path,
                    is_directory=resolved.is_dir(),
                    is_symlink=is_symlink,
                    status=status,
                )
            )

    return _ImportPlan(agent=agent, items=actions)


def _apply_import(plan: _ImportPlan) -> None:
    """Apply import plan: copy items to dotfiles."""
    for action in plan.items:
        if action.status != "import":
            continue

        icon = "📁" if action.is_directory else "📄"
        is_update = action.dotfiles_dest.exists()

        if action.is_directory:
            action.dotfiles_dest.parent.mkdir(parents=True, exist_ok=True)
            if action.dotfiles_dest.exists():
                shutil.rmtree(action.dotfiles_dest)
            shutil.copytree(
                action.resolved_path,
                action.dotfiles_dest,
                symlinks=False,
            )
        else:
            action.dotfiles_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(action.resolved_path, action.dotfiles_dest)

        source_type = "symlink" if action.is_symlink else "directory"
        verb = "Updated (newer)" if is_update else "Imported"
        print(f"  ⬅️  {icon} {action.relative_path}: {verb} ({source_type})")


def _print_import_plan(plan: _ImportPlan, verbose: bool = False) -> bool:
    """Print import plan. Returns True if there are items to import."""
    has_imports = False

    for action in plan.items:
        icon = "📁" if action.is_directory else "📄"
        source_note = "(symlink)" if action.is_symlink else "(regular)"

        if action.status == "import":
            print(
                f"  ⬅️  {icon} {action.relative_path} [IMPORT] {source_note}"
                f" <- {action.resolved_path}"
            )
            has_imports = True
        elif action.status == "deleted":
            if verbose:
                print(
                    f"  ⏭️  {icon} {action.relative_path} [SKIP: deleted from dotfiles]"
                )
        elif action.status == "conflict":
            print(f"  ⚠️  {icon} {action.relative_path} [CONFLICT] (skipped)")
        elif verbose:
            print(f"  ✅ {icon} {action.relative_path} [EXISTS]")

    return has_imports


# --- Public API ---


def import_only_mode(
    dotfiles_dir: Path,
    agents: list[AgentTarget] | None = None,
    preview: bool = False,
) -> None:
    """Run Phase 1 (target -> dotfiles) only; skip forward sync and deletions.

    Differs from sync_mode in two ways:
      - Phase 2-3 (dotfiles -> target, orphan removal) is NOT executed.
      - The `is_import_source` filter is dropped: every selected agent is
        treated as a candidate import source.

    Args:
        dotfiles_dir: Path to dotfiles directory.
        agents: Filtered subset of AGENTS to import from. None means default
            selection (claude only).
        preview: If True, only print the plan without applying changes.
    """
    if agents is None:
        agents = _select_agents(list(_DEFAULT_TARGETS))

    header = "Import Preview (Dry Run)" if preview else "Import (target -> dotfiles)"
    _print_header(header)
    print(f"🎯 Targets: {', '.join(a.key for a in agents) or '(none)'}")

    manifest = _load_manifest(dotfiles_dir)

    has_imports = False
    for agent in agents:
        plan = _build_import_plan(dotfiles_dir, agent, manifest)
        if not plan.items:
            continue

        print(f"\n⬅️  Import from {agent.name}: {agent.directory}")
        if preview:
            if _print_import_plan(plan, verbose=True):
                has_imports = True
            continue

        importable = [a for a in plan.items if a.status == "import"]
        if importable:
            _apply_import(plan)
            for imported in importable:
                dir_name = imported.relative_path.split("/")[0]
                item_name = imported.relative_path.split("/", 1)[1]
                manifest.items.setdefault(dir_name, [])
                if item_name not in manifest.items[dir_name]:
                    manifest.items[dir_name].append(item_name)
            has_imports = True
        for d in (a for a in plan.items if a.status == "deleted"):
            print(f"  ⏭️  {d.relative_path}: Skipped (deleted from dotfiles)")
        for c in (a for a in plan.items if a.status == "conflict"):
            print(f"  ⚠️  {c.relative_path}: Conflict (skipped)")

    if not preview:
        # Persist manifest with newly imported items.
        for dir_name in SYNC_DIRECTORIES:
            current = set(manifest.items.get(dir_name, []))
            manifest.items[dir_name] = sorted(current)
        _save_manifest(dotfiles_dir, manifest)

    if has_imports:
        if preview:
            print("\n💡 Run without --preview to apply imports")
        else:
            print("\n✨ Import completed!")
    else:
        print("\n✅ Nothing to import.")


def preview_mode(
    dotfiles_dir: Path,
    agents: list[AgentTarget] | None = None,
    *,
    hook_source: hook_sync.ReleaseSource | None = None,
    env: Mapping[str, str] | None = None,
    system: str | None = None,
    hook_disk: hook_wiring.Disk | None = None,
) -> None:
    """Preview existing releases and fresh settings; never take switch.lock."""
    agents = _select_agents(list(_DEFAULT_TARGETS)) if agents is None else agents
    system = system or platform.system()
    claude = [agent for agent in agents if agent.receives_hooks]
    if not claude or system == "Windows":
        if claude:
            print(
                "agent-hook: native Windows keeps today's scripts; binary wiring is not available"
            )
        _preview_files(dotfiles_dir, agents, system=system)
        return
    try:
        selected_env = dict(os.environ if env is None else env)
        roots = hook_wiring.Roots.from_env(selected_env)
        validate_hook_layers(dotfiles_dir, claude, system)
        source = (
            hook_source
            if hook_source is not None
            else hook_sync.GoReleaseSource(selected_env)
        )
        prepared = hook_sync.preview_plans(
            [hook_home(dotfiles_dir, agent, roots, system) for agent in claude],
            roots,
            source,
            disk=hook_disk,
            system=system,
        )
        print(
            "agent-hook preview: "
            + (prepared.offer.reason or "verification unknown until sync")
        )
        _preview_files(dotfiles_dir, agents, hook_session=prepared, system=system)
    except (ValueError, OSError) as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)


def _preview_files(
    dotfiles_dir: Path,
    agents: list[AgentTarget] | None = None,
    *,
    hook_session: hook_sync.SyncSession | None = None,
    system: str | None = None,
) -> None:
    """Preview mode: show what would be synced without applying changes.

    Args:
        dotfiles_dir: Path to dotfiles directory containing ROOT_AGENTS files.
        agents: Filtered subset of AGENTS to operate on. None means default
            selection (claude only).
    """
    if agents is None:
        agents = _select_agents(list(_DEFAULT_TARGETS))
    _print_header("Sync Preview (Dry Run)")

    source_base = dotfiles_dir / BASE_FILE
    if not source_base.exists():
        print(f"❌ Error: Base file not found: {source_base}")
        sys.exit(1)

    print(f"🎯 Targets: {', '.join(a.key for a in agents) or '(none)'}")

    manifest = _load_manifest(dotfiles_dir)

    # Phase 1: Import preview (only from selected import sources)
    has_imports = False
    import_sources = [a for a in agents if a.is_import_source]
    for agent in import_sources:
        import_plan = _build_import_plan(dotfiles_dir, agent, manifest)
        if import_plan.items:
            print(f"\n⬅️  Import from {agent.name}: {agent.directory}")
            if _print_import_plan(import_plan, verbose=True):
                has_imports = True

    # Phase 2-3: Forward sync + deletion + orphan preview
    additional = _get_additional_sources(dotfiles_dir)
    plans: list[_SyncPlan] = []
    for agent in agents:
        sync_plan = _build_sync_plan(dotfiles_dir, agent, additional)
        sync_plan.deletions = _build_deletion_plan(dotfiles_dir, agent, manifest)
        sync_plan.deletions.extend(
            _detect_target_only_items(dotfiles_dir, agent, manifest)
        )
        sync_plan.deletions.extend(_detect_managed_dir_orphans(agent, additional))
        plans.append(sync_plan)

    has_changes = _print_plan(
        plans, dotfiles_dir, verbose=True, hook_session=hook_session, system=system
    )

    if has_imports or has_changes:
        print("\n💡 Run without --preview to apply changes")
    else:
        print("\n✅ All files are already in sync!")


def sync_mode(
    dotfiles_dir: Path,
    auto_yes: bool = False,
    agents: list[AgentTarget] | None = None,
    *,
    hook_source: hook_sync.ReleaseSource | None = None,
    env: Mapping[str, str] | None = None,
    system: str | None = None,
    hook_disk: hook_wiring.Disk | None = None,
    hook_steps: hook_wiring.Steps | None = None,
) -> None:
    """Hold the common lock from recovery through the manifest and Codex steps."""
    agents = _select_agents(list(_DEFAULT_TARGETS)) if agents is None else agents
    system = system or platform.system()
    claude = [agent for agent in agents if agent.receives_hooks]
    if not (dotfiles_dir / BASE_FILE).exists():
        print(f"❌ Error: Base file not found: {dotfiles_dir / BASE_FILE}")
        sys.exit(1)
    if not claude or system == "Windows":
        try:
            validate_hook_layers(dotfiles_dir, claude, system)
        except ValueError as exc:
            print(f"❌ Error: {exc}")
            sys.exit(1)
        if claude:
            print(
                "agent-hook: native Windows keeps today's scripts; binary wiring is not available"
            )
        _sync_mode_files(dotfiles_dir, auto_yes, agents, system=system)
        return
    selected_env = dict(os.environ if env is None else env)
    try:
        roots = hook_wiring.Roots.from_env(selected_env)
        source = (
            hook_source
            if hook_source is not None
            else hook_sync.GoReleaseSource(selected_env)
        )
        homes = [hook_home(dotfiles_dir, agent, roots, system) for agent in claude]
        with hook_sync.open_session(
            "sync",
            homes,
            roots,
            source,
            disk=hook_disk,
            steps=hook_steps,
            system=system,
            validate=lambda: validate_hook_layers(dotfiles_dir, claude, system),
        ) as session:
            _sync_mode_files(
                dotfiles_dir, auto_yes, agents, hook_session=session, system=system
            )
    except (hook_sync.SyncStopped, hook_wiring.LockBusy, ValueError, OSError) as exc:
        print(f"❌ Error: {exc}")
        sys.exit(1)


def _sync_mode_files(
    dotfiles_dir: Path,
    auto_yes: bool = False,
    agents: list[AgentTarget] | None = None,
    *,
    hook_session: hook_sync.SyncSession | None = None,
    system: str | None = None,
) -> None:
    """Sync mode: apply sync to selected agent directories.

    Manifest-based algorithm:
      Phase 1: IMPORT - new items in import sources -> dotfiles
      Phase 2: PLAN  - diff dotfiles vs all targets + detect deletions
      Phase 3: APPLY - dotfiles -> all targets (full mirror sync)

    Args:
        dotfiles_dir: Path to dotfiles directory containing ROOT_AGENTS files.
        auto_yes: If True, skip confirmation prompts for changed files.
        agents: Filtered subset of AGENTS to operate on. None means default
            selection (claude only).
    """
    if agents is None:
        agents = _select_agents(list(_DEFAULT_TARGETS))
    print("🔄 Syncing Agent Instructions...")
    print(f"🎯 Targets: {', '.join(a.key for a in agents) or '(none)'}")

    source_base = dotfiles_dir / BASE_FILE
    if not source_base.exists():
        print(f"❌ Error: Base file not found: {source_base}")
        sys.exit(1)

    manifest = _load_manifest(dotfiles_dir)

    # Phase 1: Import from selected import sources into dotfiles
    import_sources = [a for a in agents if a.is_import_source]
    has_imports = False
    for agent in import_sources:
        import_plan = _build_import_plan(dotfiles_dir, agent, manifest)
        importable = [a for a in import_plan.items if a.status == "import"]
        if importable:
            print(f"\n⬅️  Importing from {agent.name}...")
            _apply_import(import_plan)
            # Add newly imported items to manifest
            for imported in importable:
                dir_name = imported.relative_path.split("/")[0]
                item_name = imported.relative_path.split("/", 1)[1]
                manifest.items.setdefault(dir_name, [])
                if item_name not in manifest.items[dir_name]:
                    manifest.items[dir_name].append(item_name)
            has_imports = True
        deleted = [a for a in import_plan.items if a.status == "deleted"]
        for d in deleted:
            print(f"  ⏭️  {d.relative_path}: Skipped (deleted from dotfiles)")
        conflicts = [a for a in import_plan.items if a.status == "conflict"]
        for c in conflicts:
            print(f"  ⚠️  {c.relative_path}: Conflict (skipped)")

    if has_imports:
        print()

    # Phase 2-3: Plan and apply forward sync + deletions + orphans
    additional = _get_additional_sources(dotfiles_dir)
    plans: list[_SyncPlan] = []
    for agent in agents:
        sync_plan = _build_sync_plan(dotfiles_dir, agent, additional)
        sync_plan.deletions = _build_deletion_plan(dotfiles_dir, agent, manifest)
        sync_plan.deletions.extend(
            _detect_target_only_items(dotfiles_dir, agent, manifest)
        )
        sync_plan.deletions.extend(_detect_managed_dir_orphans(agent, additional))
        plans.append(sync_plan)

    has_changes = _print_plan(
        plans, dotfiles_dir, verbose=False, hook_session=hook_session, system=system
    )

    if not has_changes:
        print("\n✅ All files are already in sync!")
        _save_manifest(dotfiles_dir, manifest)
        # Nothing to copy, but a trust or grant that failed last time retries
        _run_codex_steps_for(plans)
        return

    print()

    stopped: list[str] = []
    for plan in plans:
        print(f"\n📋 Processing {plan.agent.name}...")

        plan.agent.directory.mkdir(parents=True, exist_ok=True)

        for action in plan.items:
            if action.status == "synced":
                continue

            icon = "📁" if action.is_directory else "📄"

            if action.status == "new":
                _apply_sync_action(action, plan.agent)
                print(f"  ✅ {icon} {action.relative_path}: Created")

            elif action.status == "changed":
                if auto_yes or _confirm(f"  Overwrite {action.relative_path}?"):
                    _apply_sync_action(action, plan.agent)
                    print(f"  ✅ {icon} {action.relative_path}: Updated")
                else:
                    print(f"  ⏭️  {icon} {action.relative_path}: Skipped")

        # Merge the Claude hook fragment into the agent's settings.json
        # (claude-family only; idempotent, manifest-independent).
        if plan.agent.receives_hooks and hook_session is not None:
            # A home that stops keeps its state; the other homes go on, and
            # the run exits 1 after the manifest and the Codex steps.
            result = hook_session.apply_home(plan.agent.key)
            print(f"  {result.message}")
            if result.status != "committed":
                # Nothing more of that home is written: its deletions could
                # take a script the registration it kept still runs.
                stopped.append(result.message)
                continue
        elif (
            plan.agent.receives_hooks or plan.agent.receives_codex_hooks
        ) and _merge_hook_settings(dotfiles_dir, plan.agent, system=system):
            hooks_file = (
                "hooks.json" if plan.agent.receives_codex_hooks else "settings.json"
            )
            print(f"  ✅ 📄 {hooks_file}: hooks merged")

        # Merge the shared settings fragment (env owned wholesale + curated
        # top-level keys; claude-family only). Sequential after the hook merge so
        # each reads the freshly written settings.json -- no lost update.
        if (
            plan.agent.receives_hooks
            and hook_session is None
            and _merge_settings_fragment(dotfiles_dir, plan.agent, system=system)
        ):
            print("  ✅ 📄 settings.json: shared settings merged")

        # Apply deletions
        for deletion in plan.deletions:
            icon = "📁" if deletion.is_directory else "📄"
            if deletion.reason == "orphan":
                prompt = (
                    f"  Delete {deletion.relative_path} (target-only, not in dotfiles)?"
                )
            else:
                prompt = f"  Delete {deletion.relative_path}?"
            if auto_yes or _confirm(prompt):
                if deletion.target.is_symlink():
                    deletion.target.unlink()
                elif deletion.is_directory:
                    shutil.rmtree(deletion.target)
                else:
                    deletion.target.unlink()
                print(f"  🗑️  {icon} {deletion.relative_path}: Deleted")
            else:
                print(f"  ⏭️  {icon} {deletion.relative_path}: Skipped")

    # Update manifest: union of current dotfiles + existing manifest
    for dir_name in SYNC_DIRECTORIES:
        dir_path = dotfiles_dir / dir_name
        current_items = set(manifest.items.get(dir_name, []))
        if dir_path.is_dir():
            dotfiles_names = {
                c.name for c in dir_path.iterdir() if not c.name.startswith(".")
            }
            current_items = current_items | dotfiles_names
        manifest.items[dir_name] = sorted(current_items)
    # Directories no longer synced (skills, before ADR 0043) drop out of the
    # manifest so nothing can ever turn them into deletions.
    for stale in [d for d in manifest.items if d not in SYNC_DIRECTORIES]:
        del manifest.items[stale]

    _save_manifest(dotfiles_dir, manifest)

    # Codex runs a hook only once it is trusted: trust the ones just synced
    # (exactly the fragment's, through Codex's app-server; best effort).
    _run_codex_steps_for(plans)
    if stopped:
        raise hook_sync.SyncStopped("; ".join(stopped))

    print("\n✨ Sync completed!")


# Steps for ~/.codex after its files are synced: (script, what failed, what to
# run by hand). Each runs as a separate process: the steps import this module,
# so importing them here would create an import cycle. A step past
# CODEX_STEP_TIMEOUT is killed with its process group (its app-server too).
CODEX_STEP_TIMEOUT = 120
CODEX_STEPS = (
    (
        "codex_hooks_trust.py",
        "Codex hooks not trusted automatically",
        "just codex-hooks-trust (or trust them in Codex's /hooks)",
    ),
    (
        "codex_sandbox_tools.py",
        "Codex's Windows sandbox not given the mise tools automatically",
        "just codex-sandbox-tools",
    ),
)


def _run_codex_steps_for(plans: list[_SyncPlan]) -> None:
    for plan in plans:
        if plan.agent.receives_codex_hooks:
            print(f"\n📋 {plan.agent.name}: hook trust and sandbox")
            _run_codex_steps(plan.agent)


def _run_codex_steps(agent: AgentTarget) -> None:
    """Run CODEX_STEPS for this Codex home; never fail the sync."""
    if agent.directory != Path.home() / ".codex":
        return  # the steps read CODEX_HOME / ~/.codex only
    for script, failure, fallback in CODEX_STEPS:
        outcome = release_tools.run(
            [sys.executable, str(Path(__file__).parent / script)],
            timeout=CODEX_STEP_TIMEOUT,
        )
        for line in (outcome.stdout + outcome.stderr).splitlines():
            print(f"  {line}")
        if outcome.exit_code is None:  # it did not start, or ran out of time
            print(f"  ⚠️  {failure} ({outcome.reason}); run: {fallback}")


def orphans_mode(dotfiles_dir: Path, agents: list[AgentTarget] | None = None) -> None:
    """Show target-only items across selected agent directories.

    Lists items that exist in targets but not in the dotfiles source
    or manifest. These would be removed during a full override sync.

    Args:
        dotfiles_dir: Path to dotfiles directory.
        agents: Filtered subset of AGENTS to operate on. None means default
            selection (claude only).
    """
    if agents is None:
        agents = _select_agents(list(_DEFAULT_TARGETS))
    _print_header("Target-Only Items (Orphans)")
    print(f"🎯 Targets: {', '.join(a.key for a in agents) or '(none)'}")

    manifest = _load_manifest(dotfiles_dir)
    total = 0

    for agent in agents:
        orphans = _detect_target_only_items(dotfiles_dir, agent, manifest)
        if not orphans:
            continue

        print(f"📋 {agent.name}: {agent.directory}")
        for orphan in orphans:
            icon = "📁" if orphan.is_directory else "📄"
            print(f"  🗑️  {icon} {orphan.relative_path}")
            total += 1
        print()

    if total == 0:
        print("✅ No target-only items found. All targets match dotfiles.")
    else:
        print(f"Found {total} target-only item(s).")
        print("💡 Run 'just sync-agents' to sync and confirm deletions.")


def main() -> None:
    """CLI entry point for sync-agents."""
    # Native Windows consoles default stdout/stderr to cp932, which cannot
    # encode the emoji this script prints (🔄, ⬅️, ⚠️, ...). Force UTF-8 so
    # `just sync-agents*` runs there regardless of console code page.
    for _stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(_stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description=(
            "Sync ROOT_AGENTS files to agent instruction directories. "
            "By default ONLY ~/.claude is touched; pass targets to widen scope."
        )
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Preview mode: show what would be synced without making changes",
    )
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Auto-confirm all changes (no prompts)",
    )
    parser.add_argument(
        "--orphans",
        action="store_true",
        help="Show target-only items (not in dotfiles or manifest)",
    )
    parser.add_argument(
        "--override",
        action="store_true",
        help="Full override: sync all items and remove orphans without prompts",
    )
    parser.add_argument(
        "--import-only",
        action="store_true",
        help=(
            "Import only (target -> dotfiles); skip forward sync. "
            "All selected agents are treated as import sources, "
            "regardless of the is_import_source flag."
        ),
    )
    parser.add_argument(
        "--dotfiles",
        "-d",
        type=Path,
        default=DOTFILES_DIR,
        help=f"Path to dotfiles directory (default: {DOTFILES_DIR})",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        help=(
            "Targets to sync. Aliases: p=claude, a/b/c/d=work-a..d, g=gemini, "
            "x=codex. Special: 'all'. "
            "Default: claude (only ~/.claude is touched)."
        ),
    )

    args = parser.parse_args()

    try:
        keys = _resolve_targets(args.targets)
    except ValueError as e:
        print(f"❌ Error: {e}")
        sys.exit(2)

    selected = _select_agents(keys)

    if args.import_only:
        import_only_mode(args.dotfiles, agents=selected, preview=args.preview)
    elif args.orphans:
        orphans_mode(args.dotfiles, agents=selected)
    elif args.preview:
        preview_mode(args.dotfiles, agents=selected)
    elif args.override:
        print("⚡ Override mode: dotfiles → targets (no prompts)")
        sync_mode(args.dotfiles, auto_yes=True, agents=selected)
    else:
        sync_mode(args.dotfiles, auto_yes=args.yes, agents=selected)


if __name__ == "__main__":
    main()
