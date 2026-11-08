"""POSIX shell for Claude hook planning, checked writes, and journal recovery."""

from __future__ import annotations

import argparse
import errno
import fcntl
import json
import os
import re
import shutil
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, replace
from hashlib import sha256
from os import open as open_descriptor
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol

import agent_hook_release as release_tools
import agent_hook_wiring as wiring
from agent_hook_plan import (
    UNCHANGED,
    HomeFacts,
    HomePlan,
    ReleaseEvidence,
    plan_home,
    settings_value,
)
from agent_hook_release import Outcome

if __name__ == "__main__":
    import sync_agents as cli_sync


@dataclass(frozen=True)
class ReleaseOffer:
    release: ReleaseEvidence | None
    reason: str = ""


class ReleaseSource(Protocol):
    def prepare(self, roots: wiring.Roots) -> ReleaseOffer: ...
    def preview(self, roots: wiring.Roots) -> ReleaseOffer: ...
    def render(self, evidence: ReleaseEvidence, link: Path, system: str) -> Outcome: ...
    def selftest(self, link: Path) -> Outcome: ...


class GoReleaseSource:
    """Build/check through the shared bounded runner, with explicit environment."""

    def __init__(self, env: Mapping[str, str]) -> None:
        self.env = dict(env)

    def _release(self, roots: wiring.Roots, *, preview: bool) -> ReleaseOffer:
        env, found = release_tools.go_environment(self.env)
        if not found.ok:
            return ReleaseOffer(
                None, ("unknown: " if preview else "") + (found.reason or "missing Go")
            )
        try:
            with TemporaryDirectory(prefix="agent-hook-source-") as temporary:
                checker, built = release_tools.build_hookrelease(Path(temporary), env)
                if not built.ok:
                    return ReleaseOffer(None, f"hookrelease build tool: {built.reason}")
                published_path = None
                if not preview:
                    published = release_tools.run(
                        [checker, "build", "--into", str(roots.data / "releases")],
                        cwd=release_tools.MODULE,
                        env=env,
                        timeout=release_tools.CHECK_TIMEOUT,
                    )
                    if not published.ok:
                        return ReleaseOffer(
                            None, f"hookrelease build: {published.reason}"
                        )
                    published_path = Path(published.stdout.strip())
                identified = release_tools.run(
                    [checker, "id"],
                    cwd=release_tools.MODULE,
                    env=env,
                    timeout=release_tools.PROGRAM_TIMEOUT,
                )
                release_id = identified.stdout.strip()
                if not identified.ok or not re.fullmatch(r"[0-9a-f]{16}", release_id):
                    return ReleaseOffer(
                        None,
                        f"hookrelease id: {identified.reason or 'invalid release ID'}",
                    )
                path = (
                    roots.data / "releases" / release_id / "agent-hook"
                    if preview
                    else published_path
                )
                assert path is not None
                if preview and not path.is_file():
                    return ReleaseOffer(
                        None,
                        f"unknown: release {release_id} is not built; build and check wait for sync",
                    )
                path = wiring.release_target(roots.data, path)
                if path.parent.name != release_id:
                    return ReleaseOffer(
                        None, "published release differs from hookrelease id"
                    )
                if not preview:
                    checked = release_tools.check_release(checker, str(path), env)
                    if not checked.ok:
                        return ReleaseOffer(
                            None,
                            f"hookrelease check: {checked.reason or checked.stdout.strip()}",
                        )
                evidence = ReleaseEvidence(
                    path, release_id, sha256(path.read_bytes()).hexdigest()
                )
                return ReleaseOffer(
                    evidence, "verification unknown until sync" if preview else ""
                )
        except (OSError, ValueError) as exc:
            return ReleaseOffer(None, f"release: {exc}")

    def prepare(self, roots: wiring.Roots) -> ReleaseOffer:
        return self._release(roots, preview=False)

    def preview(self, roots: wiring.Roots) -> ReleaseOffer:
        return self._release(roots, preview=True)

    def render(self, evidence: ReleaseEvidence, link: Path, system: str) -> Outcome:
        return release_tools.run(
            [
                str(evidence.path),
                "render",
                "--harness",
                "claude",
                "--os",
                {"Darwin": "darwin", "Linux": "linux"}.get(system, system.lower()),
                "--binary",
                str(link),
            ],
            cwd=release_tools.MODULE,
            env=self.env,
            timeout=release_tools.PROGRAM_TIMEOUT,
        )

    def selftest(self, link: Path) -> Outcome:
        return release_tools.run(
            [str(link), "selftest"],
            cwd=release_tools.MODULE,
            env=self.env,
            timeout=release_tools.PROGRAM_TIMEOUT,
        )


@dataclass(frozen=True)
class HomeRules:
    scripts: dict | None
    hook_merge: Callable[[dict, dict], dict]
    shared_merge: Callable[[dict, dict], tuple[dict, dict]]
    managed_from: Callable[[dict], dict]
    wired_from: Callable[[dict], bool]
    retired_from: Callable[[dict], bool] = lambda _: False


@dataclass(frozen=True)
class HookHome:
    key: str
    directory: Path
    read_rules: Callable[[], HomeRules]


@dataclass(frozen=True)
class PlannedHome:
    home: HookHome
    facts: HomeFacts | None  # None: the home's state could not be read
    plan: HomePlan


@dataclass(frozen=True)
class HomeResult:
    key: str
    action: str
    status: str
    reason: str = ""
    release_id: str = ""

    @property
    def message(self) -> str:
        if self.status == "restored":
            return (
                f"agent-hook: {self.key} restored: {self.reason}; "
                "its registration is as it was"
            )
        if self.status == "abandoned":
            return (
                f"agent-hook: {self.key} stopped: {self.reason}; "
                "nothing of the change remains; run sync again"
            )
        if self.status != "committed" or self.action == "stop":
            return f"agent-hook: {self.key} stopped: {self.reason}"
        detail = {
            "register": f"wired ({self.release_id})",
            "install": f"wired ({self.release_id})",
            "link": f"link moved to {self.release_id}",
            "nothing": "unchanged",
            "keep": f"kept: {self.reason}",
            "scripts": f"scripts: {self.reason}",
            "uninstalled": "uninstalled",
            "unregister": "uninstalled",
        }[self.action]
        return f"agent-hook: {self.key} {detail}"


class SyncStopped(RuntimeError):
    pass


class PosixDisk(wiring.RealDisk):
    """The filesystem adapter used by sync; all paths come from its caller."""

    def entries(self, path: Path) -> list[Path]:
        try:
            return sorted(path.iterdir())
        except FileNotFoundError:
            return []

    def remove_release(self, path: Path) -> None:
        shutil.rmtree(path)
        self.fsync_directory(path.parent)

    @contextmanager
    def lock_releases(self, path: Path) -> Generator[None]:
        descriptor = open_descriptor(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)


class ReleaseDisk(wiring.Disk, Protocol):
    def entries(self, path: Path) -> list[Path]: ...
    def remove_release(self, path: Path) -> None: ...
    def lock_releases(self, path: Path) -> AbstractContextManager[None]: ...


class CodexProcesses(Protocol):
    def running(self) -> bool: ...


class PgrepCodex:
    def __init__(self, env: Mapping[str, str]) -> None:
        self.env = dict(env)

    def running(self) -> bool:
        outcome = release_tools.run(
            ["pgrep", "-x", "codex"],
            env=self.env,
            timeout=release_tools.PROGRAM_TIMEOUT,
        )
        if outcome.exit_code not in {0, 1} or outcome.timed_out:
            raise SyncStopped(f"cannot check running Codex processes: {outcome.reason}")
        return outcome.exit_code == 0


@dataclass(frozen=True)
class HookConfiguration:
    roots: wiring.Roots
    homes: tuple[HookHome, ...]
    registrations: tuple[Path, ...]
    source: ReleaseSource
    processes: CodexProcesses
    resolve: Callable[[list[str]], list[str]]
    validate: Callable[[list[str]], None]
    system: str


def _read_optional(disk: wiring.Disk, path: Path) -> bytes | None:
    try:
        return disk.read_bytes(path)
    except FileNotFoundError:
        return None


def _read_target(disk: wiring.Disk, path: Path) -> str | None:
    try:
        return disk.read_link(path)
    except FileNotFoundError:
        return None


class HomeStateUnreadable(ValueError):
    """A home's settings.json or settings.sync-state.json has a shape the
    merges cannot read: that home stops, alone."""


def check_shapes(settings: dict, state: dict) -> None:
    """Refuse what the merges cannot read, as a ValueError, so that home
    stops alone: hooks an object of event lists of block objects, each
    block's hooks a list of handler objects, a handler's command a string
    and its args a list of strings (what the ownership rule reads); the
    state's retired a list of migration names."""
    hooks = settings.get("hooks", {})
    if not isinstance(hooks, dict):
        raise HomeStateUnreadable("settings.json: hooks must be an object")
    for event, blocks in hooks.items():
        if not isinstance(blocks, list) or not all(
            isinstance(block, dict) for block in blocks
        ):
            raise HomeStateUnreadable(
                f"settings.json: hooks.{event} must be a list of objects"
            )
        for block in blocks:
            handlers = block.get("hooks", [])
            if not isinstance(handlers, list) or not all(
                isinstance(handler, dict) for handler in handlers
            ):
                raise HomeStateUnreadable(
                    f"settings.json: each block of hooks.{event} must hold a list of objects"
                )
            for handler in handlers:
                if not isinstance(handler.get("command", ""), str):
                    raise HomeStateUnreadable(
                        f"settings.json: a command in hooks.{event} must be a string"
                    )
                args = handler.get("args", [])
                if not isinstance(args, list) or not all(
                    isinstance(arg, str) for arg in args
                ):
                    raise HomeStateUnreadable(
                        f"settings.json: args in hooks.{event} must be a list of strings"
                    )
    retired = state.get("retired", [])
    if not isinstance(retired, list) or not all(isinstance(r, str) for r in retired):
        raise HomeStateUnreadable(
            "settings.sync-state.json: retired must be a list of names"
        )


class SyncSession:
    """A prepared release and per-home snapshots, used while switch.lock is held."""

    def __init__(
        self,
        operation: str,
        homes: Sequence[HookHome],
        roots: wiring.Roots,
        source: ReleaseSource,
        offer: ReleaseOffer,
        disk: wiring.Disk,
        steps: wiring.Steps,
        *,
        system: str = "Darwin",
        recovered: bool = False,
    ) -> None:
        self.operation, self.roots, self.source = operation, roots, source
        self.offer, self.disk, self.steps, self.system = offer, disk, steps, system
        self.recovered = recovered
        self.plans = {home.key: self.plan_or_stop(home) for home in homes}

    @property
    def changed(self) -> bool:
        return self.recovered or any(
            home.plan.changed or home.plan.action == "stop"
            for home in self.plans.values()
        )

    def plan_or_stop(self, home: HookHome) -> PlannedHome:
        """The home's plan, or a stop that names what could not be read: one
        unreadable home stops alone, and the others are still planned."""
        try:
            return self.read_plan(home)
        except (OSError, ValueError) as exc:
            return PlannedHome(
                home,
                None,
                HomePlan(
                    "stop",
                    UNCHANGED,
                    UNCHANGED,
                    UNCHANGED,
                    None,
                    None,
                    False,
                    False,
                    f"cannot read the home's state: {exc}",
                ),
            )

    def read_plan(self, home: HookHome) -> PlannedHome:
        rules = home.read_rules()
        settings = _read_optional(self.disk, home.directory / "settings.json")
        state = _read_optional(self.disk, home.directory / "settings.sync-state.json")
        value = settings_value(settings)
        check_shapes(value, settings_value(state))
        evidence, reason = self.offer.release, self.offer.reason
        rendered = None
        if evidence is not None and self.operation != "uninstall":
            rendered_call = self.source.render(
                evidence, self.roots.link(home.key), self.system
            )
            try:
                if not rendered_call.ok:
                    raise ValueError(rendered_call.reason or "render failed")
                rendered = json.loads(rendered_call.stdout)
                if (
                    not isinstance(rendered, dict)
                    or not isinstance(rendered.get("hooks"), dict)
                    or not rendered["hooks"]
                ):
                    raise ValueError("render did not provide hook blocks")
                if rules.managed_from(rendered) != rendered["hooks"]:
                    raise ValueError("render contains handlers not owned by this home")
            except (ValueError, TypeError, KeyError, AttributeError) as exc:
                evidence, rendered, reason = None, None, f"render: {exc}"
        facts = HomeFacts(
            home.key,
            settings,
            state,
            rules.managed_from(value),
            rules.wired_from(value),
            _read_target(self.disk, self.roots.link(home.key)),
            self.disk.exists(self.roots.mark(home.key)),
            evidence,
            rendered,
            rules.scripts,
            rules.hook_merge,
            rules.shared_merge,
            rules.managed_from,
            reason,
            retired=rules.retired_from(value),
        )
        return PlannedHome(home, facts, plan_home(self.operation, facts))

    def _check_facts(self, prepared: PlannedHome) -> None:
        home, facts = prepared.home, prepared.facts
        assert facts is not None
        for component, found, expected in (
            (
                "settings.json",
                _read_optional(self.disk, home.directory / "settings.json"),
                facts.settings,
            ),
            (
                "settings.sync-state.json",
                _read_optional(self.disk, home.directory / "settings.sync-state.json"),
                facts.state,
            ),
            ("link", _read_target(self.disk, self.roots.link(home.key)), facts.target),
            ("mark", self.disk.exists(self.roots.mark(home.key)), facts.marked),
        ):
            if found != expected:
                raise wiring.ChangedSinceRead(
                    f"{component} changed while sync ran; run sync again"
                )

    def apply_home(self, key: str) -> HomeResult:
        prepared = self.plans[key]
        for attempt in range(2):
            home, facts, plan = prepared.home, prepared.facts, prepared.plan
            if facts is None:
                return HomeResult(key, plan.action, "stopped", plan.reason)
            evidence = facts.release
            release_id = "" if evidence is None else evidence.id
            try:
                self._check_facts(prepared)
                if plan.action == "stop" and not plan.changed:
                    return HomeResult(key, plan.action, "stopped", plan.reason)
                if plan.changed:
                    wiring.ensure_directories(
                        self.disk, home.directory, mode=wiring.STATE_MODE
                    )
                if isinstance(plan.state, bytes):
                    wiring.write_if_unchanged(
                        self.disk,
                        home.directory / "settings.sync-state.json",
                        facts.state,
                        plan.state,
                    )
                    prepared = replace(prepared, facts=replace(facts, state=plan.state))
                self._check_facts(prepared)
                if plan.action in {"register", "install", "unregister"}:
                    kind = plan.action
                    new_bytes = (
                        plan.settings
                        if isinstance(plan.settings, bytes)
                        else facts.settings
                    )
                    if new_bytes is None:
                        # No settings.json, and nothing to write into one:
                        # an unregister of such a home is its mark alone.
                        wiring.set_mark(
                            self.disk,
                            wiring.MarkChange(
                                self.roots.mark(key), plan.old_mark, plan.new_mark
                            ),
                            plan.new_mark,
                        )
                        return HomeResult(key, kind, "committed", "", release_id)
                    journal = wiring.Journal(
                        home=key,
                        kind=kind,
                        stage="file" if kind == "unregister" else "link",
                        release=None
                        if kind == "unregister" or evidence is None
                        else wiring.Release(
                            evidence.path, evidence.id, evidence.sha256
                        ),
                        link=None
                        if kind == "unregister"
                        else wiring.LinkChange(
                            self.roots.link(key), plan.old_target, str(plan.new_target)
                        ),
                        file=wiring.FileChange(
                            home.directory / "settings.json", facts.settings, new_bytes
                        ),
                        # named even when it does not change (a register),
                        # so every step checks it
                        mark=wiring.MarkChange(
                            self.roots.mark(key), plan.old_mark, plan.new_mark
                        ),
                    )
                    result = wiring.apply_change(
                        wiring.Change(self.roots, journal),
                        self.disk,
                        self.steps,
                        self.source,
                    )
                    return HomeResult(
                        key, kind, result.status, result.error or "", release_id
                    )
                if plan.action == "link":
                    assert plan.new_target is not None
                    wiring.switch_link(
                        self.disk, self.roots.data, key, Path(plan.new_target)
                    )
                if isinstance(plan.settings, bytes):
                    wiring.write_if_unchanged(
                        self.disk,
                        home.directory / "settings.json",
                        facts.settings,
                        plan.settings,
                    )
                return HomeResult(
                    key,
                    plan.action,
                    "stopped" if plan.action == "stop" else "committed",
                    plan.reason,
                    release_id,
                )
            except wiring.ChangedSinceRead as exc:
                if attempt:
                    return HomeResult(key, plan.action, "stopped", str(exc))
                prepared = self.plan_or_stop(home)
                self.plans[key] = prepared
            except (OSError, ValueError) as exc:
                return HomeResult(key, plan.action, "stopped", str(exc))
        raise AssertionError("two checked attempts exhausted")


@contextmanager
def open_session(
    operation: str,
    homes: Sequence[HookHome],
    roots: wiring.Roots,
    source: ReleaseSource,
    *,
    disk: wiring.Disk | None = None,
    steps: wiring.Steps | None = None,
    validate: Callable[[], None] = lambda: None,
    system: str = "Darwin",
    wait_limit: float = 30,
) -> Generator[SyncSession]:
    disk = PosixDisk() if disk is None else disk
    steps = wiring.NoSteps() if steps is None else steps
    with wiring.switch_lock(roots, wait_limit=wait_limit):
        outcomes = wiring.recover(roots, disk, steps, source)
        for outcome in outcomes:
            print(
                f"agent-hook: {outcome.home} recovered: {outcome.status}"
                + (
                    f" ({outcome.error})"
                    if outcome.error and outcome.status != "committed"
                    else ""
                )
            )
        if any(result.status == "stopped" for result in outcomes):
            stopped = outcomes[-1]
            raise SyncStopped(
                f"recovery stopped in {stopped.home}: {stopped.error}; found {stopped.found!r}; expected {stopped.expected!r}"
            )
        validate()
        offer = (
            source.prepare(roots)
            if operation in {"sync", "install"}
            else ReleaseOffer(None)
        )
        if operation == "install" and offer.release is None:
            raise SyncStopped(f"no release: {offer.reason}")
        yield SyncSession(
            operation,
            homes,
            roots,
            source,
            offer,
            disk,
            steps,
            system=system,
            recovered=bool(outcomes),
        )


def preview_plans(
    homes: Sequence[HookHome],
    roots: wiring.Roots,
    source: ReleaseSource,
    *,
    disk: wiring.Disk | None = None,
    system: str = "Darwin",
) -> SyncSession:
    """Read the available facts without locking, recovering, or publishing a release."""
    return SyncSession(
        "sync",
        homes,
        roots,
        source,
        source.preview(roots),
        PosixDisk() if disk is None else disk,
        wiring.NoSteps(),
        system=system,
    )


def _hook_strings(value: object) -> Generator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for element in value:
            yield from _hook_strings(element)
    elif isinstance(value, dict):
        for key, element in value.items():
            if key in {"command", "args"} or isinstance(element, (dict, list)):
                yield from _hook_strings(element)


def _decoded_json(raw: bytes) -> bytes:
    """raw's JSON as a harness reads it, with every escape decoded (a \\u0061
    is an a), or nothing when raw is no JSON."""
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return b""
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def release_references(
    roots: wiring.Roots, disk: ReleaseDisk, registrations: Sequence[Path]
) -> set[Path]:
    """Every release something may still run, whoever owns the block.

    That is each home's link target, and each release whose ID appears
    anywhere in a registration file or a journal, however a path spells it:
    a shell reaches $HOME/..., ~/..., a relative path after a cd, or a name
    built from a variable. Matching the ID errs on keeping; a release is
    kept by a mention that runs nothing, never deleted under one that does.
    """
    references: set[Path] = set()
    if not disk.exists(roots.data):
        return references
    resolved_root = disk.resolve(roots.data)
    releases = resolved_root / "releases"
    chunks = [
        raw
        for raw in (_read_optional(disk, path) for path in registrations)
        if raw is not None
    ]
    for path in disk.journals(roots.state):
        # The journal names its release and links as text, and holds the
        # file's bytes in base64, so both are read.
        chunks.append(disk.read_bytes(path))
        journal = wiring.read_journal(disk, path)
        chunks.extend(raw for raw in (journal.file.old, journal.file.new) if raw)
    mentions = b"\n".join([*chunks, *map(_decoded_json, chunks)])
    for entry in disk.entries(releases):
        if (
            re.fullmatch(r"[0-9a-f]{16}", entry.name)
            and entry.name.encode("ascii") in mentions
        ):
            references.add(releases / entry.name / "agent-hook")

    def add_path(path: Path) -> None:
        try:
            resolved = disk.resolve(path)
        except FileNotFoundError:
            try:
                resolved = disk.resolve(path.parent) / path.name
            except FileNotFoundError:
                return
        if (
            resolved.name == "agent-hook"
            and re.fullmatch(r"[0-9a-f]{16}", resolved.parent.name)
            and resolved.parent.parent == resolved_root / "releases"
        ):
            references.add(resolved)

    for directory in disk.entries(roots.data / "current"):
        if not disk.is_directory(directory):
            continue
        link = directory / "agent-hook"
        target = _read_target(disk, link)
        if target is not None:
            add_path(link.parent / target)
    return references


def collect_releases(
    config: HookConfiguration, disk: ReleaseDisk, *, delete: bool
) -> None:
    print(
        "agent-hook gc: after removing a direct release block, restart sessions that read it before deleting that release"
    )
    directory = config.roots.data / "releases"
    if delete and config.processes.running():
        raise SyncStopped("Codex is running; gc --delete is refused until PR 3d.2")
    if not disk.exists(directory):
        return
    # Only the layout hookrelease makes: a releases directory that is a link
    # (or lies below one) would make every reference miss, so gc stops.
    if disk.resolve(directory) != disk.resolve(config.roots.data) / "releases":
        raise SyncStopped(
            f"{directory} is a link; gc works only on the releases directory "
            "hookrelease makes"
        )
    with disk.lock_releases(directory):
        references = release_references(config.roots, disk, config.registrations)
        for path in disk.entries(directory):
            if not re.fullmatch(r"[0-9a-f]{16}", path.name) or not disk.is_directory(
                path
            ):
                continue
            try:
                disk.read_link(path)
            except OSError as exc:
                if exc.errno != errno.EINVAL:
                    raise
            else:
                continue  # Never remove a symlink as though it were a release directory.
            binary = disk.resolve(path) / "agent-hook"
            if binary in references:
                continue
            print(f"agent-hook gc: unreferenced {path}")
            if delete:
                if config.processes.running():
                    raise SyncStopped(
                        "Codex started; gc --delete is refused until PR 3d.2"
                    )
                if binary in release_references(
                    config.roots, disk, config.registrations
                ):
                    print(f"agent-hook gc: kept {path.name}; a reference changed")
                    continue
                disk.remove_release(path)
                print(f"agent-hook gc: deleted {path.name}")


def run_command(
    config: HookConfiguration,
    operation: str,
    targets: Sequence[str],
    *,
    delete: bool = False,
    disk: ReleaseDisk | None = None,
    steps: wiring.Steps | None = None,
) -> int:
    disk = PosixDisk() if disk is None else disk
    try:
        if config.system == "Windows":
            raise SyncStopped(
                "native Windows keeps today's scripts; wiring commands require POSIX"
            )
        if operation not in {"install", "uninstall", "gc"}:
            raise ValueError(f"unknown operation: {operation}")
        if operation == "gc":
            if targets:
                raise ValueError("gc accepts --delete only, not home targets")
            selected = []
        else:
            if delete:
                raise ValueError("--delete is for gc only")
            keys = config.resolve(list(targets))
            homes = {home.key: home for home in config.homes}
            for key in keys:
                if key == "codex":
                    raise ValueError("codex is refused until PR 3d.2")
                if key not in homes:
                    raise ValueError(f"{key} is not a Claude home")
            selected = [home for home in config.homes if home.key in keys]
        with open_session(
            operation,
            selected,
            config.roots,
            config.source,
            disk=disk,
            steps=steps,
            system=config.system,
            validate=lambda: config.validate([home.key for home in selected]),
        ) as session:
            if operation == "gc":
                collect_releases(config, disk, delete=delete)
                return 0
            for home in selected:
                result = session.apply_home(home.key)
                print(result.message)
                if result.status != "committed":
                    return 1
        return 0
    except (OSError, ValueError, SyncStopped, wiring.LockBusy) as exc:
        print(f"agent-hook: stopped: {exc}")
        return 1


def main(
    argv: Sequence[str] | None = None,
    *,
    configure: Callable[[Path | None], HookConfiguration],
) -> int:
    parser = argparse.ArgumentParser(
        description="Install/uninstall Claude hook wiring, or collect unreferenced releases"
    )
    parser.add_argument("operation", choices=["install", "uninstall", "gc"])
    parser.add_argument("targets", nargs="*")
    parser.add_argument("--delete", action="store_true")
    parser.add_argument("--dotfiles", type=Path)
    args = parser.parse_args(argv)
    return run_command(
        configure(args.dotfiles), args.operation, args.targets, delete=args.delete
    )


if __name__ == "__main__":
    raise SystemExit(main(configure=cli_sync.hook_configuration))
