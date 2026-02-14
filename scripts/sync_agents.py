#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Bidirectional merge sync for agent instruction directories.

Manifest-based sync algorithm:
    Phase 1: IMPORT  - New items in import sources are copied into dotfiles.
                       Items deleted from dotfiles (tracked in manifest) are skipped.
    Phase 2: PLAN    - Diff dotfiles items against each target directory.
    Phase 3: APPLY   - Full mirror sync: add, update, and delete.

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
import json
import shutil
import sys
from dataclasses import dataclass, field
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
    AgentTarget(Path.home() / ".codex", "Codex", "AGENTS.md", is_import_source=True),
]

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


@dataclass
class _DeleteAction:
    """Single deletion action (internal use)."""

    target: Path
    relative_path: str
    is_directory: bool


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
        data = json.loads(manifest_path.read_text())
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
            child.name
            for child in dir_path.iterdir()
            if not child.name.startswith(".")
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
    manifest_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


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
            if child.name.startswith("."):
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


def _get_newest_mtime(path: Path) -> float:
    """Get the newest modification time of any file in a path (recursively)."""
    if path.is_file():
        return path.stat().st_mtime
    newest = 0.0
    for child in path.rglob("*"):
        if child.is_file():
            mtime = child.stat().st_mtime
            if mtime > newest:
                newest = mtime
    return newest


def _build_deletion_plan(
    dotfiles_dir: Path, agent: AgentTarget, manifest: _SyncManifest
) -> list[_DeleteAction]:
    """Detect items in manifest but not in dotfiles: should be deleted from targets."""
    deletions: list[_DeleteAction] = []

    for dir_name in SYNC_DIRECTORIES:
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

        for deletion in plan.deletions:
            icon = "📁" if deletion.is_directory else "📄"
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
    dotfiles_dir: Path, agent: AgentTarget, manifest: _SyncManifest
) -> _ImportPlan:
    """Build import plan: detect importable items in target's SYNC_DIRECTORIES.

    Uses manifest to distinguish genuinely new items from previously deleted ones.
    Both symlinks and regular directories/files are considered for import.
    """
    actions: list[_ImportAction] = []

    for dir_name in SYNC_DIRECTORIES:
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
                        status: Literal[
                            "import", "conflict", "exists", "deleted"
                        ] = "exists"
                    elif _get_newest_mtime(resolved) > _get_newest_mtime(
                        dotfiles_dest
                    ):
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
            shutil.copytree(action.resolved_path, action.dotfiles_dest, symlinks=False)
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
                    f"  ⏭️  {icon} {action.relative_path}"
                    " [SKIP: deleted from dotfiles]"
                )
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

    manifest = _load_manifest(dotfiles_dir)

    # Phase 1: Import preview
    has_imports = False
    import_sources = [a for a in AGENTS if a.is_import_source]
    for agent in import_sources:
        import_plan = _build_import_plan(dotfiles_dir, agent, manifest)
        if import_plan.items:
            print(f"\n⬅️  Import from {agent.name}: {agent.directory}")
            if _print_import_plan(import_plan, verbose=True):
                has_imports = True

    # Phase 2-3: Forward sync + deletion preview
    additional = _get_additional_sources(dotfiles_dir)
    plans: list[_SyncPlan] = []
    for agent in AGENTS:
        sync_plan = _build_sync_plan(dotfiles_dir, agent, additional)
        sync_plan.deletions = _build_deletion_plan(dotfiles_dir, agent, manifest)
        plans.append(sync_plan)

    has_changes = _print_plan(plans, dotfiles_dir, verbose=True)

    if has_imports or has_changes:
        print("\n💡 Run without --preview to apply changes")
    else:
        print("\n✅ All files are already in sync!")


def sync_mode(dotfiles_dir: Path, auto_yes: bool = False) -> None:
    """Sync mode: apply sync to all agent directories.

    Manifest-based algorithm:
      Phase 1: IMPORT - new items in import sources -> dotfiles
      Phase 2: PLAN  - diff dotfiles vs all targets + detect deletions
      Phase 3: APPLY - dotfiles -> all targets (full mirror sync)

    Args:
        dotfiles_dir: Path to dotfiles directory containing ROOT_AGENTS files.
        auto_yes: If True, skip confirmation prompts for changed files.
    """
    print("🔄 Syncing Agent Instructions...")

    source_base = dotfiles_dir / BASE_FILE
    if not source_base.exists():
        print(f"❌ Error: Base file not found: {source_base}")
        sys.exit(1)

    manifest = _load_manifest(dotfiles_dir)

    # Phase 1: Import from import sources into dotfiles
    import_sources = [a for a in AGENTS if a.is_import_source]
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

    # Phase 2-3: Plan and apply forward sync + deletions
    additional = _get_additional_sources(dotfiles_dir)
    plans: list[_SyncPlan] = []
    for agent in AGENTS:
        sync_plan = _build_sync_plan(dotfiles_dir, agent, additional)
        sync_plan.deletions = _build_deletion_plan(dotfiles_dir, agent, manifest)
        plans.append(sync_plan)

    has_changes = _print_plan(plans, dotfiles_dir, verbose=False)

    if not has_changes:
        print("\n✅ All files are already in sync!")
        _save_manifest(dotfiles_dir, manifest)
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

        # Apply deletions
        for deletion in plan.deletions:
            icon = "📁" if deletion.is_directory else "📄"
            if auto_yes or _confirm(f"  Delete {deletion.relative_path}?"):
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
                c.name
                for c in dir_path.iterdir()
                if not c.name.startswith(".")
            }
            current_items = current_items | dotfiles_names
        manifest.items[dir_name] = sorted(current_items)

    _save_manifest(dotfiles_dir, manifest)
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
