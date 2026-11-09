"""Durable per-home hook changes. Callers hold switch_lock through recovery and apply.

Recovery uses the journal's bytes and release evidence; it never renders a
checkout. A restore changes only hooks, and never removes a home's link.
"""

import base64
import binascii
import errno
import json
import os
import re
import stat
import sys
import time
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from os import open as open_descriptor
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from uuid import uuid4

from agent_hook_release import Outcome, run


def _home_key(key: str) -> str:
    if not re.fullmatch(r"[a-z0-9-]+", key):
        raise ValueError(f"invalid home key: {key!r}")
    return key


@dataclass(frozen=True)
class Roots:
    data: Path
    state: Path

    def __post_init__(self) -> None:
        if not self.data.is_absolute() or not self.state.is_absolute():
            raise ValueError("data and state roots must be absolute")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "Roots":
        def root(variable: str, fallback: str) -> Path:
            xdg = env.get(variable, "")
            if xdg and Path(xdg).is_absolute():
                return Path(xdg) / "dotfiles/agent-hooks"
            home = env.get("HOME", "")
            if home and Path(home).is_absolute():
                return Path(home) / ".local" / fallback / "dotfiles/agent-hooks"
            raise ValueError(f"{variable} or HOME must be usable and absolute")

        return cls(root("XDG_DATA_HOME", "share"), root("XDG_STATE_HOME", "state"))

    def link(self, key: str) -> Path:
        return self.data / "current" / _home_key(key) / "agent-hook"

    def mark(self, key: str) -> Path:
        return self.state / "uninstalled" / _home_key(key)

    def journal(self, key: str) -> Path:
        return self.state / f"switch-{_home_key(key)}.json"

    @property
    def lock(self) -> Path:
        return self.state / "switch.lock"


class Disk(Protocol):
    def read_bytes(self, path: Path) -> bytes: ...
    def read_link(self, path: Path) -> str: ...
    def create(self, path: Path, mode: int) -> None: ...
    def write(self, path: Path, data: bytes) -> None: ...
    def mode(self, path: Path) -> int: ...
    def fsync_file(self, path: Path) -> None: ...
    def fsync_directory(self, path: Path) -> None: ...
    def rename(self, source: Path, target: Path) -> None: ...
    def unlink(self, path: Path) -> None: ...
    def symlink(self, target: str, path: Path) -> None: ...
    def mkdir(self, path: Path, mode: int) -> None: ...
    def exists(self, path: Path) -> bool: ...
    def is_file(self, path: Path) -> bool: ...
    def is_directory(self, path: Path) -> bool: ...
    def resolve(self, path: Path) -> Path: ...
    def journals(self, state: Path) -> list[Path]: ...


def flush(descriptor: int) -> None:
    """Flush what was written all the way to the disk.

    On macOS, fsync(2) stops at the drive's cache, which may reorder writes
    (man 2 fsync), so this asks for F_FULLFSYNC, as Go's File.Sync does, and
    falls back to fsync where the file system does not support it.
    """
    if sys.platform == "darwin":
        import fcntl

        try:
            fcntl.fcntl(descriptor, getattr(fcntl, "F_FULLFSYNC", 51))
            return
        except OSError as exc:
            if exc.errno not in (errno.ENOTSUP, errno.EOPNOTSUPP):
                raise
    os.fsync(descriptor)


class RealDisk:
    """POSIX filesystem adapter. No environment or user-home discovery."""

    def read_bytes(self, path: Path) -> bytes:
        return path.read_bytes()

    def read_link(self, path: Path) -> str:
        return str(path.readlink())

    def create(self, path: Path, mode: int) -> None:
        if sys.platform == "win32":
            raise NotImplementedError("RealDisk is POSIX only")
        descriptor = open_descriptor(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        try:
            os.fchmod(descriptor, mode)
        finally:
            os.close(descriptor)

    def write(self, path: Path, data: bytes) -> None:
        path.write_bytes(data)

    def mode(self, path: Path) -> int:
        return stat.S_IMODE(path.stat().st_mode)

    def fsync_file(self, path: Path) -> None:
        with path.open("rb") as stream:
            flush(stream.fileno())

    def fsync_directory(self, path: Path) -> None:
        if sys.platform == "win32":
            raise NotImplementedError("RealDisk is POSIX only")
        descriptor = open_descriptor(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            flush(descriptor)
        finally:
            os.close(descriptor)

    def rename(self, source: Path, target: Path) -> None:
        source.replace(target)

    def unlink(self, path: Path) -> None:
        path.unlink()

    def symlink(self, target: str, path: Path) -> None:
        path.symlink_to(target)

    def mkdir(self, path: Path, mode: int) -> None:
        path.mkdir(mode=mode)

    def exists(self, path: Path) -> bool:
        return path.exists() or path.is_symlink()

    def is_file(self, path: Path) -> bool:
        return path.is_file()

    def is_directory(self, path: Path) -> bool:
        return path.is_dir()

    def resolve(self, path: Path) -> Path:
        return path.resolve(strict=True)

    def journals(self, state: Path) -> list[Path]:
        return sorted(state.glob("switch-*.json"))


def _temporary(path: Path) -> Path:
    return path.with_name(f".{path.name}-{uuid4().hex}")


def _discard_temporary(disk: Disk, path: Path) -> None:
    try:
        disk.unlink(path)
    except FileNotFoundError:
        pass


def write_whole(disk: Disk, path: Path, data: bytes) -> None:
    """Atomically replace a file, preserving its mode and fsync order."""
    try:
        mode = disk.mode(path)
    except FileNotFoundError:
        mode = 0o600
    temporary = _temporary(path)
    renamed = False
    try:
        disk.create(temporary, mode)
        disk.write(temporary, data)
        disk.fsync_file(temporary)
        disk.rename(temporary, path)
        renamed = True
        disk.fsync_directory(path.parent)
    finally:
        if not renamed:
            _discard_temporary(disk, temporary)


# Directories below the state root are the owner's only, as the file log's
# are; a link's directory under the data root is readable, as Go's switch
# makes it.
STATE_MODE = 0o700
LINK_MODE = 0o755


def ensure_directories(disk: Disk, path: Path, *, mode: int) -> None:
    """Create each missing directory, with mode (less the umask), and durably
    publish it in its parent."""
    if disk.is_directory(path):
        return
    if path == path.parent:
        raise OSError(f"not a directory: {path}")
    ensure_directories(disk, path.parent, mode=mode)
    try:
        disk.mkdir(path, mode)
    except FileExistsError:
        if not disk.is_directory(path):
            raise
    disk.fsync_directory(path.parent)


def release_target(data_root: Path, target: Path, *, disk: Disk | None = None) -> Path:
    """Go's isRelease rule, compared against the resolved data root."""
    disk = RealDisk() if disk is None else disk
    resolved = disk.resolve(target.absolute())
    if resolved.name != "agent-hook" or not disk.is_file(resolved):
        raise ValueError(f"not a release binary: {resolved}")
    if not re.fullmatch(r"[0-9a-f]{16}", resolved.parent.name):
        raise ValueError(f"not in a release directory: {resolved}")
    releases = disk.resolve(data_root.absolute()) / "releases"
    if resolved.parent.parent != releases:
        raise ValueError(f"not one of {releases}'s releases: {resolved}")
    return resolved


def _read_link(disk: Disk, path: Path) -> str | None:
    try:
        return disk.read_link(path)
    except FileNotFoundError:
        return None


def _replace_link(disk: Disk, path: Path, target: str) -> None:
    ensure_directories(disk, path.parent, mode=LINK_MODE)
    temporary = _temporary(path)
    renamed = False
    try:
        disk.symlink(target, temporary)
        disk.rename(temporary, path)
        renamed = True
        disk.fsync_directory(path.parent)
    finally:
        if not renamed:
            _discard_temporary(disk, temporary)


def switch_link(disk: Disk, data_root: Path, key: str, target: Path) -> str | None:
    path = data_root / "current" / _home_key(key) / "agent-hook"
    resolved = release_target(data_root, target, disk=disk)
    previous = _read_link(disk, path)
    _replace_link(disk, path, str(resolved))
    return previous


class LockBusy(RuntimeError):
    def __init__(self, holder: object) -> None:
        self.holder = holder
        super().__init__(f"switch.lock busy; holder: {holder}")


@contextmanager
def switch_lock(
    roots: Roots, *, wait_limit: float = 30, argv: Sequence[str] | None = None
) -> Generator[None]:
    """Hold the lock shared with Go. Closing on exit or death releases it."""
    if sys.platform == "win32":
        raise NotImplementedError("the switch lock is POSIX only (flock)")
    if wait_limit < 0:
        raise ValueError("wait limit must not be negative")
    # POSIX only, imported here so that doctor can read the roots on Windows.
    import fcntl

    disk = RealDisk()
    ensure_directories(disk, roots.state, mode=STATE_MODE)
    descriptor = open_descriptor(roots.lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + wait_limit
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    holder_bytes = os.pread(descriptor, 65536, 0)
                    try:
                        holder = json.loads(holder_bytes)
                    except (ValueError, UnicodeError):
                        holder = holder_bytes.decode("utf-8", errors="replace")
                    raise LockBusy(holder) from None
                time.sleep(min(0.01, remaining))
        holder_bytes = (
            json.dumps(
                {
                    "pid": os.getpid(),
                    "argv": list(sys.argv if argv is None else argv),
                    "started": datetime.now(UTC).isoformat(),
                }
            )
            + "\n"
        ).encode("utf-8")
        os.ftruncate(descriptor, 0)
        with os.fdopen(os.dup(descriptor), "wb") as stream:
            stream.write(holder_bytes)
            stream.flush()
            flush(stream.fileno())
        disk.fsync_directory(roots.state)
        yield
    finally:
        os.close(descriptor)


HOMES = frozenset({"claude", "work-a", "work-b", "work-c", "work-d", "codex"})
FORWARD = {
    "register": ("link", "file", "verify"),
    "install": ("link", "file", "mark", "verify"),
    "unregister": ("file", "mark", "verify"),
}
RESTORE = {
    "register": ("restore-file", "restore-link"),
    "install": ("restore-mark", "restore-file", "restore-link"),
    "unregister": ("restore-mark", "restore-file"),
}


class JournalUnreadable(ValueError):
    """The journal is kept for a person to inspect."""


@dataclass(frozen=True)
class Release:
    path: Path
    id: str
    sha256: str


@dataclass(frozen=True)
class LinkChange:
    path: Path
    old: str | None
    new: str


@dataclass(frozen=True)
class FileChange:
    path: Path
    old: bytes | None
    new: bytes


@dataclass(frozen=True)
class MarkChange:
    path: Path
    old: bool
    new: bool


@dataclass(frozen=True)
class Journal:
    home: str
    kind: str
    stage: str
    release: Release | None
    link: LinkChange | None
    file: FileChange
    mark: MarkChange | None
    version: int = 1
    trust: None = None


@dataclass(frozen=True)
class Change:
    roots: Roots
    journal: Journal

    def __post_init__(self) -> None:
        _parse_journal(_journal_document(self.journal))
        if self.journal.link and self.journal.link.path != self.roots.link(
            self.journal.home
        ):
            raise JournalUnreadable("link.path differs from this home's link")
        if self.journal.mark and self.journal.mark.path != self.roots.mark(
            self.journal.home
        ):
            raise JournalUnreadable("mark.path differs from this home's mark")


def _fields(value: object, names: str, component: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise JournalUnreadable(f"{component}: expected fields {names}")
    return cast(dict[str, Any], value)


def _path(value: object, component: str) -> Path:
    if (
        not isinstance(value, str)
        or not value
        or "\0" in value
        or not Path(value).is_absolute()
    ):
        raise JournalUnreadable(f"{component}: expected absolute path")
    return Path(value)


def _settings(raw: bytes | None) -> dict[str, Any]:
    if raw is None:
        return {}
    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_unique_fields,
        parse_constant=_bad_constant,
    )
    if not isinstance(value, dict):
        raise JournalUnreadable("settings must be a JSON object")
    return value


def _decode_bytes(
    value: object, component: str, *, nullable: bool = False
) -> bytes | None:
    if value is None and nullable:
        return None
    if not isinstance(value, str):
        raise JournalUnreadable(f"{component}: expected base64 bytes")
    try:
        raw = base64.b64decode(value, validate=True)
        _settings(raw)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise JournalUnreadable(f"{component}: {exc}") from exc
    return raw


def _parse_journal(value: object) -> Journal:
    document = _fields(
        value, "version home kind stage release link file mark trust", "journal"
    )
    if type(document["version"]) is not int or document["version"] != 1:
        raise JournalUnreadable("unknown journal version")
    home, kind, stage = document["home"], document["kind"], document["stage"]
    if not isinstance(home, str) or home not in HOMES:
        raise JournalUnreadable("unknown journal home")
    if not isinstance(kind, str) or kind not in FORWARD:
        raise JournalUnreadable("unknown journal kind")
    if not isinstance(stage, str) or stage not in (
        *FORWARD[kind],
        *RESTORE[kind],
        "abandon",
    ):
        raise JournalUnreadable("unknown journal stage for kind")
    if document["trust"] is not None:
        raise JournalUnreadable("trust must be null in 3d.1")
    release = None
    if kind == "unregister":
        if document["release"] is not None or document["link"] is not None:
            raise JournalUnreadable("unregister must have null release and link")
    else:
        record = _fields(document["release"], "path id sha256", "release")
        release_path = _path(record["path"], "release.path")
        for name, width in (("id", 16), ("sha256", 64)):
            if not isinstance(record[name], str) or not re.fullmatch(
                f"[0-9a-f]{{{width}}}", record[name]
            ):
                raise JournalUnreadable(
                    f"release.{name}: expected {width} lowercase hex digits"
                )
        if (
            release_path.name != "agent-hook"
            or release_path.parent.name != record["id"]
        ):
            raise JournalUnreadable("release.path does not match release.id")
        release = Release(release_path, record["id"], record["sha256"])
    link = None
    if document["link"] is not None:
        record = _fields(document["link"], "path old new", "link")
        if record["old"] is not None and (
            not isinstance(record["old"], str)
            or not record["old"]
            or "\0" in record["old"]
        ):
            raise JournalUnreadable("link.old: expected target or null")
        new = _path(record["new"], "link.new")
        if release is None or new != release.path:
            raise JournalUnreadable("link.new differs from release.path")
        link = LinkChange(_path(record["path"], "link.path"), record["old"], str(new))
    record = _fields(document["file"], "path old new", "file")
    old = _decode_bytes(record["old"], "file.old", nullable=True)
    new_bytes = _decode_bytes(record["new"], "file.new")
    assert new_bytes is not None
    file = FileChange(_path(record["path"], "file.path"), old, new_bytes)
    # Every kind names the mark's state, so every step can check it (a
    # register's is absent before and after).
    if document["mark"] is None:
        raise JournalUnreadable("mark: expected its old and new states")
    record = _fields(document["mark"], "path old new", "mark")
    if type(record["old"]) is not bool or type(record["new"]) is not bool:
        raise JournalUnreadable("mark.old and mark.new must be booleans")
    mark = MarkChange(_path(record["path"], "mark.path"), record["old"], record["new"])
    return Journal(home, kind, stage, release, link, file, mark)


def _journal_document(journal: Journal) -> dict[str, Any]:
    release, link, file, mark = (
        journal.release,
        journal.link,
        journal.file,
        journal.mark,
    )
    return {
        "version": journal.version,
        "home": journal.home,
        "kind": journal.kind,
        "stage": journal.stage,
        "release": None
        if release is None
        else {"path": str(release.path), "id": release.id, "sha256": release.sha256},
        "link": None
        if link is None
        else {"path": str(link.path), "old": link.old, "new": link.new},
        "file": {
            "path": str(file.path),
            "old": None
            if file.old is None
            else base64.b64encode(file.old).decode("ascii"),
            "new": base64.b64encode(file.new).decode("ascii"),
        },
        "mark": None
        if mark is None
        else {"path": str(mark.path), "old": mark.old, "new": mark.new},
        "trust": journal.trust,
    }


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for name, value in pairs:
        if name in document:
            raise ValueError(f"duplicate field: {name}")
        document[name] = value
    return document


def _bad_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def read_journal(disk: Disk, path: Path) -> Journal:
    try:
        document = json.loads(
            disk.read_bytes(path).decode("utf-8"),
            object_pairs_hook=_unique_fields,
            parse_constant=_bad_constant,
        )
        journal = _parse_journal(document)
        if path.name != f"switch-{journal.home}.json":
            raise JournalUnreadable("journal filename differs from home")
        return journal
    except (ValueError, UnicodeError, OSError) as exc:
        raise JournalUnreadable(f"{path}: {exc}") from exc


def write_journal(disk: Disk, path: Path, journal: Journal) -> None:
    document = _journal_document(journal)
    _parse_journal(document)
    if path.name != f"switch-{journal.home}.json":
        raise JournalUnreadable("journal filename differs from home")
    if disk.exists(path):
        previous = read_journal(disk, path)
        if replace(previous, stage=journal.stage) != journal:
            raise JournalUnreadable("journal old and new values are immutable")
    ensure_directories(disk, path.parent, mode=STATE_MODE)
    write_whole(disk, path, (json.dumps(document) + "\n").encode("utf-8"))


class Steps(Protocol):
    def before(self, key: str, stage: str) -> None: ...


class NoSteps:
    def before(self, key: str, stage: str) -> None:
        pass


class Verifier(Protocol):
    def selftest(self, link: Path) -> Outcome: ...


class ReleaseVerifier:
    def selftest(self, link: Path) -> Outcome:
        return run([str(link), "selftest"], timeout=30)


@dataclass(frozen=True)
class ChangeResult:
    status: Literal["committed", "abandoned", "restored", "stopped"]
    home: str
    error: str | None = None
    component: str | None = None
    found: object = None
    expected: object = None


class _MissingHooks(Enum):
    ABSENT = "absent hooks"


class _StateMismatch(Exception):
    def __init__(self, component: str, found: object, expected: object) -> None:
        self.component, self.found, self.expected = component, found, expected
        super().__init__(f"{component}: found {found!r}; expected {expected!r}")


class _VerificationFailed(Exception):
    pass


def _read_file(disk: Disk, path: Path) -> bytes | None:
    try:
        return disk.read_bytes(path)
    except FileNotFoundError:
        return None


def _hooks(raw: bytes | None) -> object:
    return _settings(raw).get("hooks", _MissingHooks.ABSENT)


def _equal_hooks(first: object, second: object) -> bool:
    if first is _MissingHooks.ABSENT or second is _MissingHooks.ABSENT:
        return first is second
    return json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def _file_hooks(disk: Disk, file: FileChange) -> tuple[bytes | None, object]:
    current = _read_file(disk, file.path)
    try:
        hooks = _hooks(current)
    except (ValueError, UnicodeError) as exc:
        raise _StateMismatch(
            "file.hooks", str(exc), [_hooks(file.old), _hooks(file.new)]
        ) from exc
    if not any(
        _equal_hooks(hooks, expected)
        for expected in (_hooks(file.old), _hooks(file.new))
    ):
        raise _StateMismatch("file.hooks", hooks, [_hooks(file.old), _hooks(file.new)])
    return current, hooks


def _guard_components(journal: Journal, disk: Disk) -> None:
    if journal.link:
        link = journal.link
        try:
            found = _read_link(disk, link.path)
        except OSError as exc:
            if exc.errno == errno.EINVAL:
                raise _StateMismatch(
                    "link", "not a symlink", [link.old, link.new]
                ) from exc
            raise
        if found not in (link.old, link.new):
            raise _StateMismatch("link", found, [link.old, link.new])
    if journal.mark:
        mark = journal.mark
        found_mark = disk.exists(mark.path)
        if found_mark and not disk.is_file(mark.path):
            raise _StateMismatch("mark", "not a file", [mark.old, mark.new])
        if found_mark not in (mark.old, mark.new):
            raise _StateMismatch("mark", found_mark, [mark.old, mark.new])


def _delete_file(disk: Disk, path: Path) -> None:
    disk.unlink(path)
    disk.fsync_directory(path.parent)


def _delete_journal(change: Change, disk: Disk) -> None:
    path = change.roots.journal(change.journal.home)
    disk.unlink(path)
    try:
        disk.fsync_directory(path.parent)
    except OSError:
        # A stopped restore must retain its evidence even if unlink worked
        # and only the directory fsync failed. A later run can finish it.
        write_journal(disk, path, change.journal)
        raise


def set_mark(disk: Disk, mark: MarkChange, present: bool) -> None:
    """Create (empty) or remove the uninstall mark, durably."""
    if disk.exists(mark.path) == present:
        return
    if present:
        ensure_directories(disk, mark.path.parent, mode=STATE_MODE)
        write_whole(disk, mark.path, b"")
    else:
        _delete_file(disk, mark.path)


def _restore_file(disk: Disk, file: FileChange) -> None:
    current, hooks = _file_hooks(disk, file)
    old_hooks = _hooks(file.old)
    if _equal_hooks(hooks, old_hooks):
        return
    # A change's scope is the hooks value: even a file the change created
    # stays, with every other key as it is now (the shared settings sync
    # wrote with it, and any key another program wrote since).
    settings = _settings(current)
    if old_hooks is _MissingHooks.ABSENT:
        settings.pop("hooks", None)
    else:
        settings["hooks"] = old_hooks
    restored = (json.dumps(settings, ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )
    if file.old is not None and settings == _settings(file.old):
        restored = file.old
    write_whole(disk, file.path, restored)


def _stage(change: Change, stage: str, disk: Disk, steps: Steps) -> Change:
    advanced = Change(change.roots, replace(change.journal, stage=stage))
    write_journal(disk, change.roots.journal(change.journal.home), advanced.journal)
    steps.before(change.journal.home, stage)
    _guard_components(advanced.journal, disk)
    return advanced


def _verify_state(change: Change, disk: Disk) -> None:
    journal = change.journal
    _guard_components(journal, disk)
    _, hooks = _file_hooks(disk, journal.file)
    if not _equal_hooks(hooks, _hooks(journal.file.new)):
        raise _VerificationFailed("file.hooks differs from the new value")
    if journal.mark and disk.exists(journal.mark.path) != journal.mark.new:
        raise _VerificationFailed("mark differs from the new state")
    if journal.release:
        link = change.roots.link(journal.home)
        try:
            resolved = release_target(change.roots.data, link, disk=disk)
        except (OSError, ValueError) as exc:
            raise _VerificationFailed(f"release: {exc}") from exc
        if resolved != journal.release.path:
            raise _VerificationFailed(
                f"link resolves to {resolved}, expected {journal.release.path}"
            )
        if sha256(disk.read_bytes(resolved)).hexdigest() != journal.release.sha256:
            raise _VerificationFailed("release SHA-256 differs from the journal")


def _verify(change: Change, disk: Disk, verifier: Verifier) -> None:
    _verify_state(change, disk)
    if change.journal.release:
        outcome = verifier.selftest(change.roots.link(change.journal.home))
        if not outcome.ok:
            raise _VerificationFailed(
                f"selftest: {outcome.reason or outcome.stderr or outcome.exit_code}"
            )
        # A bounded selftest can still take 30 seconds. Recheck the evidence
        # after it, before deleting the journal, to catch edits while it ran.
        _verify_state(change, disk)


def _stopped(change: Change, exc: Exception) -> ChangeResult:
    if isinstance(exc, _StateMismatch):
        return ChangeResult(
            "stopped",
            change.journal.home,
            str(exc),
            exc.component,
            exc.found,
            exc.expected,
        )
    return ChangeResult(
        "stopped", change.journal.home, str(exc), "io", str(exc), "durable restore"
    )


def _restore_order(journal: Journal) -> tuple[str, ...]:
    if journal.stage == "abandon":
        return ("restore-link",) if journal.link else ()
    order = RESTORE[journal.kind]
    if journal.stage in order:
        return order[order.index(journal.stage) :]
    reached = FORWARD[journal.kind][: FORWARD[journal.kind].index(journal.stage) + 1]
    return tuple(stage for stage in order if stage.removeprefix("restore-") in reached)


def _check_restored(journal: Journal, disk: Disk, stages: tuple[str, ...]) -> None:
    if "restore-file" in stages:
        _, hooks = _file_hooks(disk, journal.file)
        if not _equal_hooks(hooks, _hooks(journal.file.old)):
            raise _StateMismatch("file.hooks", hooks, _hooks(journal.file.old))
    if "restore-mark" in stages and journal.mark:
        present = disk.exists(journal.mark.path)
        if present != journal.mark.old:
            raise _StateMismatch("mark", present, journal.mark.old)


def _restore(change: Change, disk: Disk, steps: Steps, error: str) -> ChangeResult:
    abandoned = change.journal.stage == "abandon"
    order = _restore_order(change.journal)
    try:
        if abandoned:
            # Abandon is the durable decision to leave the file alone. Keep
            # that stage through the link restore, including after a crash.
            change = _stage(change, "abandon", disk, steps)
        for stage in order:
            _guard_components(change.journal, disk)
            if not abandoned:
                _file_hooks(disk, change.journal.file)
                previous = RESTORE[change.journal.kind][
                    : RESTORE[change.journal.kind].index(stage)
                ]
                _check_restored(change.journal, disk, previous)
                change = _stage(change, stage, disk, steps)
                _check_restored(change.journal, disk, previous)
            else:
                _guard_components(change.journal, disk)
            journal = change.journal
            if stage == "restore-mark" and journal.mark:
                set_mark(disk, journal.mark, journal.mark.old)
            elif stage == "restore-file":
                _restore_file(disk, journal.file)
            elif stage == "restore-link" and journal.link:
                link = journal.link
                if link.old is not None and _read_link(disk, link.path) != link.old:
                    _replace_link(disk, link.path, link.old)
        _guard_components(change.journal, disk)
        journal = change.journal
        if not abandoned:
            _check_restored(journal, disk, RESTORE[journal.kind])
        if "restore-link" in order and journal.link:
            restored_link = journal.link.old or journal.link.new
            found_link = _read_link(disk, journal.link.path)
            # Before the first link write, None is also already restored.
            if found_link != restored_link and (
                journal.link.old is not None or found_link is not None
            ):
                raise _StateMismatch("link", found_link, restored_link)
        _delete_journal(change, disk)
        return ChangeResult(
            "abandoned" if abandoned else "restored", journal.home, error
        )
    except (OSError, _StateMismatch, JournalUnreadable) as exc:
        return _stopped(change, exc)


def apply_change(
    change: Change, disk: Disk, steps: Steps, verifier: Verifier
) -> ChangeResult:
    """Apply one preplanned change. The caller holds switch_lock."""
    path = change.roots.journal(change.journal.home)
    if disk.exists(path):
        return ChangeResult(
            "stopped",
            change.journal.home,
            "pending journal; recover first",
            "journal",
            str(path),
            "no pending journal",
        )
    try:
        for stage in FORWARD[change.journal.kind]:
            _guard_components(change.journal, disk)
            # Keep the attempted stage locally if its durable write fails.
            change = Change(change.roots, replace(change.journal, stage=stage))
            change = _stage(change, stage, disk, steps)
            journal = change.journal
            if stage == "link" and journal.link:
                if _read_link(disk, journal.link.path) != journal.link.new:
                    switch_link(
                        disk, change.roots.data, journal.home, Path(journal.link.new)
                    )
            elif stage == "file":
                if _read_file(disk, journal.file.path) != journal.file.old:
                    change = Change(change.roots, replace(journal, stage="abandon"))
                    return _restore(
                        change, disk, steps, "settings changed before the file step"
                    )
                if journal.file.new != journal.file.old:
                    write_whole(disk, journal.file.path, journal.file.new)
            elif stage == "mark" and journal.mark:
                set_mark(disk, journal.mark, journal.mark.new)
            elif stage == "verify":
                _verify(change, disk, verifier)
        _delete_journal(change, disk)
        return ChangeResult("committed", change.journal.home)
    except _StateMismatch as exc:
        return _stopped(change, exc)
    except (OSError, ValueError, _VerificationFailed) as exc:
        # An initial publication may fail before any component moved.
        if (
            not disk.exists(path)
            and change.journal.stage == FORWARD[change.journal.kind][0]
        ):
            return ChangeResult("restored", change.journal.home, str(exc))
        return _restore(change, disk, steps, str(exc))


def recover(
    roots: Roots, disk: Disk, steps: Steps, verifier: Verifier
) -> list[ChangeResult]:
    """Resolve pending journals in name order; stop at the first ambiguity.

    The caller holds switch_lock. Nothing reads a checkout or a render.
    """
    outcomes: list[ChangeResult] = []
    for path in sorted(disk.journals(roots.state)):
        try:
            journal = read_journal(disk, path)
            change = Change(roots, journal)
        except JournalUnreadable as exc:
            outcomes.append(
                ChangeResult(
                    "stopped",
                    path.stem.removeprefix("switch-"),
                    str(exc),
                    "journal",
                    str(exc),
                    "readable version 1 journal",
                )
            )
            break
        if journal.stage == "verify":
            try:
                _verify(change, disk, verifier)
                _delete_journal(change, disk)
                outcome = ChangeResult("committed", journal.home)
            except _StateMismatch as exc:
                outcome = _stopped(change, exc)
            except (OSError, ValueError, _VerificationFailed) as exc:
                outcome = _restore(change, disk, steps, str(exc))
        else:
            outcome = _restore(change, disk, steps, "recovering interrupted change")
        outcomes.append(outcome)
        if outcome.status == "stopped":
            break
    return outcomes


class ChangedSinceRead(RuntimeError):
    pass


def write_if_unchanged(
    disk: Disk, path: Path, expected: bytes | None, data: bytes
) -> None:
    if _read_file(disk, path) != expected:
        raise ChangedSinceRead(f"{path} changed since it was read")
    write_whole(disk, path, data)
