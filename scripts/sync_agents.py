#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Bidirectional merge sync for agent instruction directories.

Three-phase sync algorithm:
    Phase 1: IMPORT  - Symlinks in import source (~/.claude) are resolved
                       and copied into dotfiles as real files.
    Phase 2: PLAN    - Diff dotfiles items against each target directory.
    Phase 3: APPLY   - Per-item merge sync (unmanaged target items preserved).

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

# Directories to sync directly (in addition to ROOT_AGENTS_* files)
SYNC_DIRECTORIES = ["commands", "skills", "agents"]


@dataclass
class AgentTarget:
    """Agent target configuration."""

    directory: Path
    name: str
    main_file: str
    is_import_source: bool = False


AGENTS: list[AgentTarget] = [
    AgentTarget(Path.home() / ".claude", "Claude", "CLAUDE.md", is_import_source=True),
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


def _get_directory_items(dotfiles_dir: Path) -> list[_SyncItem]:
    """Get individual items within SYNC_DIRECTORIES as sync items.

    Instead of syncing entire directories (e.g. skills/), syncs each
    child item (e.g. skills/tdd-workflow, skills/brand-legal-review)
    individually. This preserves unmanaged items in the target.
    """
    sources: list[_SyncItem] = []
    for dir_name in SYNC_DIRECTORIES:
        dir_path = dotfiles_dir / dir_name
        if not dir_path.is_dir():
            continue
        for child in dir_path.iterdir():
            if child.name == ".git":
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


def _get_additional_sources(dotfiles_dir: Path) -> list[_SyncItem]:
    """Get all ROOT_AGENTS_* files/directories and SYNC_DIRECTORIES contents."""
    sources: list[_SyncItem] = []

    # Legacy: ROOT_AGENTS_* files and directories
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

    # Direct directory structure (commands/, skills/, agents/)
    sources.extend(_get_directory_items(dotfiles_dir))

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
    if target.is_symlink():
        target.unlink()
    elif target.exists():
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


# --- Import (target -> dotfiles) ---


@dataclass
class _ImportAction:
    """Single import action: symlink in target to import into dotfiles."""

    symlink_path: Path
    resolved_path: Path
    dotfiles_dest: Path
    relative_path: str
    is_directory: bool
    status: Literal["import", "conflict", "exists"]


@dataclass
class _ImportPlan:
    """Import plan for a single agent."""

    agent: AgentTarget
    items: list[_ImportAction]


def _build_import_plan(dotfiles_dir: Path, agent: AgentTarget) -> _ImportPlan:
    """Build import plan: detect symlinks in target's SYNC_DIRECTORIES.

    Only symlinks are considered for import (regular files/dirs are ignored
    to prevent re-importing previously deleted items).
    """
    actions: list[_ImportAction] = []

    for dir_name in SYNC_DIRECTORIES:
        target_dir = agent.directory / dir_name
        if not target_dir.is_dir():
            continue

        for child in target_dir.iterdir():
            if not child.is_symlink():
                continue

            rel_path = f"{dir_name}/{child.name}"
            dotfiles_dest = dotfiles_dir / rel_path
            resolved = child.resolve()

            if not resolved.exists():
                # Broken symlink, skip
                continue

            if dotfiles_dest.exists():
                # Already exists in dotfiles
                if resolved.is_dir():
                    if _compare_directories(dotfiles_dest, resolved):
                        status: Literal["import", "conflict", "exists"] = "exists"
                    else:
                        status = "conflict"
                elif _compare_files(dotfiles_dest, resolved):
                    status = "exists"
                else:
                    status = "conflict"
            else:
                status = "import"

            actions.append(
                _ImportAction(
                    symlink_path=child,
                    resolved_path=resolved,
                    dotfiles_dest=dotfiles_dest,
                    relative_path=rel_path,
                    is_directory=resolved.is_dir(),
                    status=status,
                )
            )

    return _ImportPlan(agent=agent, items=actions)


def _apply_import(plan: _ImportPlan) -> None:
    """Apply import plan: resolve symlinks and copy to dotfiles."""
    for action in plan.items:
        if action.status != "import":
            continue

        icon = "📁" if action.is_directory else "📄"

        if action.is_directory:
            action.dotfiles_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(action.resolved_path, action.dotfiles_dest, symlinks=False)
        else:
            action.dotfiles_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(action.resolved_path, action.dotfiles_dest)

        print(f"  ⬅️  {icon} {action.relative_path}: Imported")


def _print_import_plan(plan: _ImportPlan, verbose: bool = False) -> bool:
    """Print import plan. Returns True if there are items to import."""
    has_imports = False

    for action in plan.items:
        icon = "📁" if action.is_directory else "📄"

        if action.status == "import":
            print(
                f"  ⬅️  {icon} {action.relative_path} [IMPORT] <- {action.resolved_path}"
            )
            has_imports = True
        elif action.status == "conflict":
            print(f"  ⚠️  {icon} {action.relative_path} [CONFLICT] (skipped)")
        elif verbose:
            print(f"  ✅ {icon} {action.relative_path} [EXISTS]")

    return has_imports


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

    # Phase 1: Import preview
    has_imports = False
    import_sources = [a for a in AGENTS if a.is_import_source]
    for agent in import_sources:
        import_plan = _build_import_plan(dotfiles_dir, agent)
        if import_plan.items:
            print(f"\n⬅️  Import from {agent.name}: {agent.directory}")
            if _print_import_plan(import_plan, verbose=True):
                has_imports = True

    # Phase 2-3: Forward sync preview
    additional = _get_additional_sources(dotfiles_dir)
    plans = [_build_sync_plan(dotfiles_dir, agent, additional) for agent in AGENTS]

    has_changes = _print_plan(plans, dotfiles_dir, verbose=True)

    if has_imports or has_changes:
        print("\n💡 Run without --preview to apply changes")
    else:
        print("\n✅ All files are already in sync!")


def sync_mode(dotfiles_dir: Path, auto_yes: bool = False) -> None:
    """Sync mode: apply sync to all agent directories.

    Three-phase algorithm:
      Phase 1: IMPORT - symlinks in import sources -> dotfiles
      Phase 2: PLAN  - diff dotfiles vs all targets
      Phase 3: APPLY - dotfiles -> all targets (per-item merge)

    Args:
        dotfiles_dir: Path to dotfiles directory containing ROOT_AGENTS files.
        auto_yes: If True, skip confirmation prompts for changed files.
    """
    print("🔄 Syncing Agent Instructions...")

    source_base = dotfiles_dir / BASE_FILE
    if not source_base.exists():
        print(f"❌ Error: Base file not found: {source_base}")
        sys.exit(1)

    # Phase 1: Import symlinks from import sources into dotfiles
    import_sources = [a for a in AGENTS if a.is_import_source]
    has_imports = False
    for agent in import_sources:
        import_plan = _build_import_plan(dotfiles_dir, agent)
        importable = [a for a in import_plan.items if a.status == "import"]
        if importable:
            print(f"\n⬅️  Importing from {agent.name}...")
            _apply_import(import_plan)
            has_imports = True
        conflicts = [a for a in import_plan.items if a.status == "conflict"]
        for c in conflicts:
            print(f"  ⚠️  {c.relative_path}: Conflict (skipped)")

    if has_imports:
        print()

    # Phase 2-3: Plan and apply forward sync
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
