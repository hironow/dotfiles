#!/usr/bin/env python3
"""Declarative management of agent skills (store + consumers).

The bunx skills CLI owns the store ~/.agents/skills and records installs in
~/.agents/.skill-lock.json. That lock is not usable raw (display-name keys,
duplicate registrations, frontmatter-name installs whose dir differs from the
repo path), so this script normalizes it into a committed declaration:

    dump/harness/skill-lock.json

Self-authored skills (hironow/skills) go through the same path as third-party
ones; when two sources resolve to the same skill name, hironow/skills wins.
The CLI is only ever asked to write the store (`-a universal`); every consumer
home is populated by `place` below, never by the CLI.

Subcommands:
    dump     normalize the machine lock into the committed declaration; fails
             when a previously declared hironow/skills record vanished or was
             re-sourced (the CLI's lock replaces a same-named key silently)
    restore  install into the store every declared skill that is missing or
             whose machine-lock source is not the declared one (hironow/skills
             last, so ours wins), then `place`
    update   refresh the store with the pinned CLI (`update -g -y`), then `place`
    place    make every consumer home (~/.claude, ~/.claude-work-*, ~/.codex,
             ~/.gemini) carry each declared skill as a relative symlink into
             the store; where symlinks cannot be created the consumer gets a
             copy that is refreshed while it stays unedited (tracked in
             `<home>/skills/.skills-lock-state.json`)
    check    fail when the committed declaration carries a third-party skill
             whose name collides with a hironow/skills skill

SKILLS_LOCK_HOME points every path at another home directory and is handed
to the child CLI as HOME (agent-specific env such as CLAUDE_CONFIG_DIR and
XDG_* is dropped for it). A full restore rehearsal still belongs in a
container or a dedicated user; the override only redirects this process and
its direct children.
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Pinned like every bunx-run CLI here: an unpinned CLI would make restore
# behavior drift between machines.
SKILLS_CLI_VERSION = "1.5.22"

# Skills sourced from this repo are ours; they win any name collision.
SELF_SOURCE = "hironow/skills"

DUMP_RELATIVE = Path("dump/harness/skill-lock.json")

# Homes (relative to the user's home) that read skills from `<home>/skills`.
# pi reads the store itself. A home that does not exist is left alone; an
# existing home without a skills/ dir gets one.
CONSUMER_HOMES = (
    ".claude",
    ".claude-work-a",
    ".claude-work-b",
    ".claude-work-c",
    ".claude-work-d",
    ".codex",
    ".gemini",
)

# Placement state kept next to the consumer's skills (copy fallback tracking).
STATE_FILE = ".skills-lock-state.json"

# Environment the child CLI must not inherit when the home is overridden.
_AGENT_ENV_PREFIXES = ("CLAUDE_CONFIG_DIR", "XDG_", "CODEX_HOME", "GEMINI_")


def home_dir() -> Path:
    return Path(os.environ.get("SKILLS_LOCK_HOME") or Path.home())


def machine_lock(home: Path | None = None) -> Path:
    return (home or home_dir()) / ".agents" / ".skill-lock.json"


def agents_store(home: Path | None = None) -> Path:
    return (home or home_dir()) / ".agents" / "skills"


def cli_env() -> dict[str, str]:
    """Environment for the child CLI: the overridden home, and none of the
    agent-specific variables that would point it back at the real homes."""
    env = dict(os.environ)
    override = os.environ.get("SKILLS_LOCK_HOME")
    if override:
        env["HOME"] = override
        for key in list(env):
            if key.startswith(_AGENT_ENV_PREFIXES):
                del env[key]
    return env


@dataclass(frozen=True)
class SkillRecord:
    """One declared skill (normalized from the machine lock)."""

    installed_dir: str
    upstream_name: str
    lock_key: str
    source: str
    skill_path: str
    skill_folder_hash: str
    resolved_by: str  # "installed" | "skillPath"


def _upstream_name(skill_path: str) -> str:
    parts = skill_path.rstrip("/").split("/")
    return parts[-2] if len(parts) >= 2 else parts[-1]


def normalize_lock(
    raw_skills: dict[str, dict[str, str]],
    installed_dirs: set[str],
) -> list[SkillRecord]:
    """Two-stage resolution: lock key if it is an installed dir (frontmatter-name
    installs land under the key), else the skillPath parent. Deduped by
    installed_dir: a hironow/skills record beats any other source, then the
    entry whose key is the installed dir itself. Unresolved entries are
    dropped with a warning."""
    by_dir: dict[str, SkillRecord] = {}
    for key, entry in raw_skills.items():
        upstream = _upstream_name(entry["skillPath"])
        if key in installed_dirs:
            installed, resolved_by = key, "installed"
        elif upstream in installed_dirs:
            installed, resolved_by = upstream, "skillPath"
        else:
            print(f"⚠️  skipping unresolved lock entry: {key!r}", file=sys.stderr)
            continue
        record = SkillRecord(
            installed_dir=installed,
            upstream_name=upstream,
            lock_key=key,
            source=entry["source"],
            skill_path=entry["skillPath"],
            skill_folder_hash=entry.get("skillFolderHash", ""),
            resolved_by=resolved_by,
        )
        existing = by_dir.get(installed)
        if existing is None or _outranks(record, existing):
            if existing is not None and existing.source != record.source:
                print(
                    f"⚠️  {installed}: {record.source} wins over {existing.source}",
                    file=sys.stderr,
                )
            by_dir[installed] = record
    return sorted(by_dir.values(), key=lambda r: r.installed_dir)


def _outranks(candidate: SkillRecord, existing: SkillRecord) -> bool:
    if (candidate.source == SELF_SOURCE) != (existing.source == SELF_SOURCE):
        return candidate.source == SELF_SOURCE
    return candidate.resolved_by == "installed" and existing.resolved_by != "installed"


def check_collisions(records: list[SkillRecord]) -> list[str]:
    """Names of hironow/skills skills that a third-party record would shadow
    (by installed dir or by upstream name). Non-empty means the declaration
    would let another source win a name it must not."""
    ours = {r.installed_dir for r in records if r.source == SELF_SOURCE}
    collisions: set[str] = set()
    for rec in records:
        if rec.source == SELF_SOURCE:
            continue
        for name in (rec.installed_dir, rec.upstream_name):
            if name in ours:
                collisions.add(name)
    return sorted(collisions)


def find_dropped_self_records(
    previous: list[SkillRecord], current: list[SkillRecord]
) -> list[str]:
    """hironow/skills records that the previous declaration had and the new
    one does not carry with the same source. The CLI's machine lock replaces
    a same-named key, so a third-party install can erase ours silently."""
    now = {r.installed_dir: r.source for r in current}
    return sorted(
        r.installed_dir
        for r in previous
        if r.source == SELF_SOURCE and now.get(r.installed_dir) != SELF_SOURCE
    )


def restore_order(records: list[SkillRecord]) -> list[SkillRecord]:
    """Third-party records first, hironow/skills last, so that whatever the
    CLI does with a same-named directory, the store ends up with ours."""
    others = [r for r in records if r.source != SELF_SOURCE]
    ours = [r for r in records if r.source == SELF_SOURCE]
    return others + ours


def needs_reinstall(
    record: SkillRecord, *, installed: bool, machine_source: str | None
) -> bool:
    """Missing from the store, or (for ours) present under another source."""
    if not installed:
        return True
    return record.source == SELF_SOURCE and machine_source != SELF_SOURCE


def build_restore_command(record: SkillRecord) -> list[str]:
    """The CLI accepts the frontmatter name it recorded as the lock key
    (spike-verified: `-s composition-patterns` fails, the listed and accepted
    name is `vercel-composition-patterns`). `-a universal` limits the write
    to the store: the CLI would otherwise install into every agent it
    detects and delete a same-named directory there without comparing it."""
    return [
        "bunx",
        f"skills@{SKILLS_CLI_VERSION}",
        "add",
        record.source,
        "-g",
        "-s",
        record.lock_key,
        "-y",
        "-a",
        "universal",
    ]


def build_update_command() -> list[str]:
    """Refresh every skill in the store from its source with the pinned CLI."""
    return ["bunx", f"skills@{SKILLS_CLI_VERSION}", "update", "-g", "-y"]


# --- place: consumer homes mirror the store ---


@dataclass
class PlaceResult:
    linked: list[str] = field(default_factory=list)
    copied: list[str] = field(default_factory=list)
    refreshed: list[str] = field(default_factory=list)
    replaced: list[str] = field(default_factory=list)
    kept: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    symlinks_unavailable: bool = False

    @property
    def unresolved(self) -> bool:
        return bool(self.kept or self.missing)


def _trees_equal(a: Path, b: Path) -> bool:
    """Byte-for-byte equality of two directory trees. Any entry that cannot
    be compared (type mismatch, unreadable) counts as a difference."""
    cmp = filecmp.dircmp(a, b, ignore=[".DS_Store"])
    if cmp.left_only or cmp.right_only or cmp.funny_files or cmp.common_funny:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(_trees_equal(a / d, b / d) for d in cmp.common_dirs)


def _fingerprint(path: Path) -> str:
    """Content hash of a directory tree (relative paths + file bytes)."""
    digest = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        if file.name == ".DS_Store":
            continue
        digest.update(str(file.relative_to(path)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(file.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _same_entity(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve() or os.path.samefile(a, b)
    except OSError:
        return False


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    else:
        shutil.rmtree(path)


def _try_symlink(target: Path, relative_store: str) -> bool:
    try:
        os.symlink(relative_store, target, target_is_directory=True)
    except OSError:
        return False
    return True


def _symlinks_supported(skills_dir: Path) -> bool:
    """Probe once per consumer dir whether this process may create symlinks."""
    probe = skills_dir / ".skills-lock-probe"
    if probe.is_symlink():
        probe.unlink()
    ok = _try_symlink(probe, ".")
    if ok:
        probe.unlink()
    return ok


def _load_state(skills_dir: Path) -> dict[str, dict[str, str]]:
    state_file = skills_dir / STATE_FILE
    if not state_file.is_file():
        return {}
    data = json.loads(state_file.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _save_state(skills_dir: Path, state: dict[str, dict[str, str]]) -> None:
    state_file = skills_dir / STATE_FILE
    if state:
        state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    elif state_file.exists():
        state_file.unlink()


def _swap_in(skills_dir: Path, name: str, build: Callable[[Path], bool]) -> bool:
    """Build the new entry under a temporary name, then move the old entry
    aside and rename the new one into place; on failure the old entry comes
    back. Returns what `build` returned (True when it made a symlink)."""
    target = skills_dir / name
    tmp = skills_dir / f".{name}.skills-lock-tmp"
    backup = skills_dir / f".{name}.skills-lock-old"
    for stale in (tmp, backup):
        if stale.exists() or stale.is_symlink():
            _remove(stale)
    made_link = build(tmp)
    had_old = target.exists() or target.is_symlink()
    if had_old:
        os.rename(target, backup)
    try:
        os.rename(tmp, target)
    except OSError:
        if had_old:
            os.rename(backup, target)
        _remove(tmp)
        raise
    if had_old:
        _remove(backup)
    return made_link


def place(
    records: list[SkillRecord],
    home: Path,
    *,
    force: bool = False,
    link: bool = True,
) -> PlaceResult:
    """Mirror the store into every existing consumer home.

    Symlink mode (default): `<home>/skills/<name>` becomes a relative symlink
    to `../../.agents/skills/<name>`. A real directory in the way is replaced
    when it is byte-identical to the store or when it is a copy this tool
    placed and nobody edited; a differing one is kept and reported unless
    `force`. When the OS refuses to create a symlink the consumer gets a
    copy instead and the placement is recorded, so later runs keep refreshing
    that copy while it stays unedited.

    Copy mode (`link=False`): the same, but copies are made on purpose.
    """
    result = PlaceResult()
    store = agents_store(home)
    relative_store = os.path.join("..", "..", ".agents", "skills")
    states: dict[Path, dict[str, dict[str, str]]] = {}
    can_link: dict[Path, bool] = {}
    for rec in records:
        name = rec.installed_dir
        source = store / name
        if not source.is_dir():
            result.missing.append(name)
            continue
        for rel in CONSUMER_HOMES:
            consumer_home = home / rel
            if not consumer_home.is_dir():
                continue
            skills_dir = consumer_home / "skills"
            skills_dir.mkdir(exist_ok=True)
            target = skills_dir / name
            label = f"{rel}/{name}"
            expected = os.path.join(relative_store, name)
            state = states.setdefault(skills_dir, _load_state(skills_dir))
            if link and skills_dir not in can_link:
                can_link[skills_dir] = _symlinks_supported(skills_dir)
                if not can_link[skills_dir]:
                    result.symlinks_unavailable = True
            will_link = link and can_link.get(skills_dir, False)
            exists = target.exists() or target.is_symlink()
            if exists and _same_entity(source, target):
                continue  # the store itself, seen through a link: never touch
            if target.is_symlink():
                if link and os.readlink(target) == expected:
                    continue
                verb = "replaced"
            elif exists:
                own_copy = (
                    state.get(name, {}).get("mode") == "copy"
                    and target.is_dir()
                    and state[name].get("fingerprint") == _fingerprint(target)
                )
                identical = target.is_dir() and _trees_equal(source, target)
                if not (own_copy or identical or force):
                    result.kept.append(label)
                    continue
                if identical and not will_link:
                    # an up-to-date copy and no symlink to upgrade it to
                    state[name] = {"mode": "copy", "fingerprint": _fingerprint(source)}
                    continue
                verb = "replaced" if will_link else "refreshed"
            else:
                verb = "linked" if will_link else "copied"

            def _build(tmp: Path) -> bool:
                if will_link and _try_symlink(tmp, expected):
                    return True
                shutil.copytree(source, tmp, symlinks=False)
                return False

            made_link = _swap_in(skills_dir, name, _build)
            if made_link:
                state.pop(name, None)
            else:
                verb = {"linked": "copied", "replaced": "refreshed"}.get(verb, verb)
                state[name] = {"mode": "copy", "fingerprint": _fingerprint(source)}
            getattr(result, verb).append(label)
    for skills_dir, state in states.items():
        _save_state(skills_dir, state)
    return result


# --- commands ---


def _list_dirs(path: Path) -> set[str]:
    if not path.is_dir():
        return set()
    return {c.name for c in path.iterdir() if c.is_dir() and not c.name.startswith(".")}


def _load_dump(dotfiles_dir: Path) -> list[SkillRecord]:
    data = json.loads((dotfiles_dir / DUMP_RELATIVE).read_text())
    return [SkillRecord(**item) for item in data["skills"]]


def _load_machine_sources(home: Path) -> dict[str, str]:
    """installed dir (or lock key) -> source, from the CLI's machine lock."""
    lock = machine_lock(home)
    if not lock.is_file():
        return {}
    raw = json.loads(lock.read_text())["skills"]
    sources: dict[str, str] = {}
    for key, entry in raw.items():
        sources[key] = entry["source"]
        sources.setdefault(_upstream_name(entry["skillPath"]), entry["source"])
    return sources


def _configure_output() -> None:
    # Windows Git Bash hands Python a cp932 stdout; the emoji progress lines
    # then raise UnicodeEncodeError and kill the whole command. Re-encode to
    # UTF-8 where supported, degrade to replacement characters elsewhere.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _cmd_dump(dotfiles_dir: Path, *, allow_self_drop: bool) -> int:
    raw = json.loads(machine_lock().read_text())["skills"]
    records = normalize_lock(raw, _list_dirs(agents_store()))
    dump_path = dotfiles_dir / DUMP_RELATIVE
    if dump_path.is_file():
        dropped = find_dropped_self_records(_load_dump(dotfiles_dir), records)
        if dropped and not allow_self_drop:
            print(
                "❌ hironow/skills records missing or re-sourced in the machine lock "
                f"(refusing to commit the loss; --allow-self-drop overrides): "
                f"{', '.join(dropped)}",
                file=sys.stderr,
            )
            return 1
    dump_path.write_text(
        json.dumps(
            {"version": 1, "skills": [asdict(r) for r in records]},
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    ours = sum(1 for r in records if r.source == SELF_SOURCE)
    print(f"✅ dumped {len(records)} skills ({ours} from {SELF_SOURCE}) -> {dump_path}")
    collisions = check_collisions(records)
    if collisions:
        print(f"❌ name collisions: {', '.join(collisions)}", file=sys.stderr)
        return 1
    return 0


def _report_place(result: PlaceResult) -> None:
    for verb in ("linked", "copied", "refreshed", "replaced"):
        for label in getattr(result, verb):
            print(f"   {verb:9s} {label}")
    for label in result.kept:
        print(f"⚠️  kept (differs from the store; --force replaces): {label}")
    for name in result.missing:
        print(f"❌ not in the store (run restore): {name}", file=sys.stderr)
    if result.symlinks_unavailable:
        print("⚠️  symlinks unavailable here; consumers hold tracked copies instead")
    counts = {
        v: len(getattr(result, v))
        for v in ("linked", "copied", "refreshed", "replaced", "kept", "missing")
    }
    print("   " + ", ".join(f"{k} {n}" for k, n in counts.items()))


def _cmd_place(dotfiles_dir: Path, *, force: bool, copy: bool) -> int:
    result = place(_load_dump(dotfiles_dir), home_dir(), force=force, link=not copy)
    _report_place(result)
    return 1 if result.unresolved else 0


def _cmd_restore(dotfiles_dir: Path, *, force: bool, copy: bool) -> int:
    home = home_dir()
    records = restore_order(_load_dump(dotfiles_dir))
    installed = _list_dirs(agents_store(home))
    machine_sources = _load_machine_sources(home)
    failures = 0
    for rec in records:
        if not needs_reinstall(
            rec,
            installed=rec.installed_dir in installed,
            machine_source=machine_sources.get(rec.installed_dir),
        ):
            continue
        cmd = build_restore_command(rec)
        print(f"⬇️  {rec.installed_dir} <- {rec.source}")
        result = subprocess.run(cmd, check=False, env=cli_env())
        if result.returncode != 0:
            failures += 1
            print(f"❌ restore failed: {rec.installed_dir}", file=sys.stderr)
    print(f"{'⚠️' if failures else '✅'} store restore done ({failures} failures)")
    placed = place(records, home, force=force, link=not copy)
    _report_place(placed)
    return 1 if failures or placed.unresolved else 0


def _cmd_update(dotfiles_dir: Path, *, force: bool, copy: bool) -> int:
    print("🔄 refreshing the store with the pinned skills CLI")
    result = subprocess.run(build_update_command(), check=False, env=cli_env())
    if result.returncode != 0:
        print("❌ skills update failed", file=sys.stderr)
        return 1
    placed = place(_load_dump(dotfiles_dir), home_dir(), force=force, link=not copy)
    _report_place(placed)
    return 1 if placed.unresolved else 0


def _cmd_check(dotfiles_dir: Path) -> int:
    collisions = check_collisions(_load_dump(dotfiles_dir))
    if collisions:
        print(
            "❌ the declaration lets a third-party skill shadow a hironow/skills "
            f"name: {', '.join(collisions)}",
            file=sys.stderr,
        )
        return 1
    print("✅ no third-party skill collides with a hironow/skills name")
    return 0


def main() -> int:
    _configure_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["dump", "restore", "place", "update", "check"]
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="place/restore: replace consumer entries that differ from the store",
    )
    parser.add_argument(
        "--copy",
        action="store_true",
        help="place/restore: copy instead of symlinking (tracked, refreshed on change)",
    )
    parser.add_argument(
        "--allow-self-drop",
        action="store_true",
        help="dump: accept that a declared hironow/skills record disappeared",
    )
    args = parser.parse_args()
    dotfiles_dir = Path(__file__).resolve().parent.parent
    if args.command == "dump":
        return _cmd_dump(dotfiles_dir, allow_self_drop=args.allow_self_drop)
    if args.command == "restore":
        return _cmd_restore(dotfiles_dir, force=args.force, copy=args.copy)
    if args.command == "place":
        return _cmd_place(dotfiles_dir, force=args.force, copy=args.copy)
    if args.command == "update":
        return _cmd_update(dotfiles_dir, force=args.force, copy=args.copy)
    return _cmd_check(dotfiles_dir)


if __name__ == "__main__":
    sys.exit(main())
