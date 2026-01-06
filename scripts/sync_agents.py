#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Sync ROOT_AGENTS files to agent instruction directories.

File naming convention:
    ROOT_AGENTS.md                      -> <agent>/AGENT.md (base file)
    ROOT_AGENTS_commands_strict.md      -> <agent>/commands/strict.md
    ROOT_AGENTS_skills_my-skill/        -> <agent>/skills/my-skill/
    ROOT_AGENTS_hooks_formatter.py      -> <agent>/hooks/formatter.py
    ROOT_AGENTS_agents_subagent/        -> <agent>/agents/subagent/

The '_' in filenames (after ROOT_AGENTS_) are converted to '/' for target path.

Public API:
    - main(): CLI entry point
    - preview_mode(): Show sync plan without applying
    - sync_mode(): Apply sync with optional auto-confirm
"""

import argparse
import filecmp
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# --- Configuration ---

DOTFILES_DIR = Path.home() / "dotfiles"
BASE_FILE = "ROOT_AGENTS.md"


@dataclass
class AgentTarget:
    """Agent target configuration."""

    directory: Path
    name: str
    main_file: str


AGENTS: list[AgentTarget] = [
    AgentTarget(Path.home() / ".claude", "Claude", "CLAUDE.md"),
    AgentTarget(Path.home() / ".claude-work-a", "Claude(Work-A)", "CLAUDE.md"),
    AgentTarget(Path.home() / ".claude-work-b", "Claude(Work-B)", "CLAUDE.md"),
    AgentTarget(Path.home() / ".claude-work-c", "Claude(Work-C)", "CLAUDE.md"),
    AgentTarget(Path.home() / ".gemini", "Gemini", "GEMINI.md"),
    AgentTarget(Path.home() / ".codex", "Codex", "AGENTS.md"),
]


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


@dataclass
class _SyncPlan:
    """Sync plan for a single agent (internal use)."""

    agent: AgentTarget
    items: list[_SyncAction]


# --- Private helper functions ---


def _convert_path(source_name: str) -> str:
    """Convert ROOT_AGENTS_xxx_yyy.ext to xxx/yyy.ext."""
    result = source_name.removeprefix("ROOT_AGENTS_")
    result = result.replace("_", "/")
    return result


def _get_additional_sources(dotfiles_dir: Path) -> list[_SyncItem]:
    """Get all ROOT_AGENTS_* files and directories."""
    sources: list[_SyncItem] = []

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
    if dcmp.left_only or dcmp.right_only or dcmp.diff_files:
        return False

    for subdir in dcmp.common_dirs:
        if not _compare_directories(source / subdir, target / subdir):
            return False

    return True


def _sync_file(source: Path, target: Path) -> None:
    """Sync a single file."""
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _sync_directory(source: Path, target: Path) -> None:
    """Sync a directory (copy with overwrite)."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


def _build_sync_plan(
    dotfiles_dir: Path, agent: AgentTarget, additional_sources: list[_SyncItem]
) -> _SyncPlan:
    """Build sync plan for an agent."""
    actions: list[_SyncAction] = []

    # Base file
    source_base = dotfiles_dir / BASE_FILE
    target_base = agent.directory / agent.main_file

    if not target_base.exists():
        status: Literal["new", "changed", "synced"] = "new"
    elif _compare_files(source_base, target_base):
        status = "synced"
    else:
        status = "changed"

    actions.append(
        _SyncAction(
            source=source_base,
            target=target_base,
            relative_path=agent.main_file,
            is_directory=False,
            status=status,
        )
    )

    # Additional sources
    for item in additional_sources:
        target_path = agent.directory / item.relative_path

        if item.is_directory:
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
    plans: list[_SyncPlan], dotfiles_dir: Path, verbose: bool = False
) -> bool:
    """Print sync plan. Returns True if there are changes to apply."""
    has_changes = False

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

    return has_changes


def _confirm(prompt: str) -> bool:
    """Ask for confirmation."""
    try:
        response = input(f"{prompt} [y/N] ").strip().lower()
        return response in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


# --- Public API ---


def preview_mode(dotfiles_dir: Path) -> None:
    """Preview mode: show what would be synced without applying changes.

    Args:
        dotfiles_dir: Path to dotfiles directory containing ROOT_AGENTS files.
    """
    _print_header("Sync Preview (Dry Run)")

    source_base = dotfiles_dir / BASE_FILE
    if not source_base.exists():
        print(f"❌ Error: Base file not found: {source_base}")
        sys.exit(1)

    additional = _get_additional_sources(dotfiles_dir)
    plans = [_build_sync_plan(dotfiles_dir, agent, additional) for agent in AGENTS]

    has_changes = _print_plan(plans, dotfiles_dir, verbose=True)

    if has_changes:
        print("\n💡 Run without --preview to apply changes")
    else:
        print("\n✅ All files are already in sync!")


def sync_mode(dotfiles_dir: Path, auto_yes: bool = False) -> None:
    """Sync mode: apply sync to all agent directories.

    Args:
        dotfiles_dir: Path to dotfiles directory containing ROOT_AGENTS files.
        auto_yes: If True, skip confirmation prompts for changed files.
    """
    print("🔄 Syncing Agent Instructions...")

    source_base = dotfiles_dir / BASE_FILE
    if not source_base.exists():
        print(f"❌ Error: Base file not found: {source_base}")
        sys.exit(1)

    additional = _get_additional_sources(dotfiles_dir)
    plans = [_build_sync_plan(dotfiles_dir, agent, additional) for agent in AGENTS]

    has_changes = _print_plan(plans, dotfiles_dir, verbose=False)

    if not has_changes:
        print("\n✅ All files are already in sync!")
        return

    print()

    for plan in plans:
        print(f"\n📋 Processing {plan.agent.name}...")

        plan.agent.directory.mkdir(parents=True, exist_ok=True)

        for action in plan.items:
            if action.status == "synced":
                continue

            icon = "📁" if action.is_directory else "📄"

            if action.status == "new":
                if action.is_directory:
                    _sync_directory(action.source, action.target)
                else:
                    _sync_file(action.source, action.target)
                print(f"  ✅ {icon} {action.relative_path}: Created")

            elif action.status == "changed":
                if auto_yes or _confirm(f"  Overwrite {action.relative_path}?"):
                    if action.is_directory:
                        _sync_directory(action.source, action.target)
                    else:
                        _sync_file(action.source, action.target)
                    print(f"  ✅ {icon} {action.relative_path}: Updated")
                else:
                    print(f"  ⏭️  {icon} {action.relative_path}: Skipped")

    print("\n✨ Sync completed!")


def main() -> None:
    """CLI entry point for sync-agents."""
    parser = argparse.ArgumentParser(
        description="Sync ROOT_AGENTS files to agent instruction directories."
    )
    parser.add_argument(
        "--preview",
        "-p",
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
        "--dotfiles",
        "-d",
        type=Path,
        default=DOTFILES_DIR,
        help=f"Path to dotfiles directory (default: {DOTFILES_DIR})",
    )

    args = parser.parse_args()

    if args.preview:
        preview_mode(args.dotfiles)
    else:
        sync_mode(args.dotfiles, auto_yes=args.yes)


if __name__ == "__main__":
    main()
