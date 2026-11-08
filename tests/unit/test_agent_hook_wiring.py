"""Crash recovery for one home's hook registration, in isolated directories."""

import json
import os
import select
import signal
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

if os.name == "nt":
    pytest.skip("hook wiring uses POSIX flock", allow_module_level=True)

import agent_hook_wiring as wiring

# The real flush, for the tests of the flush itself.
REAL_FLUSH = wiring.flush


@pytest.fixture(autouse=True)
def plain_fsync(monkeypatch: pytest.MonkeyPatch) -> None:
    """A full flush (F_FULLFSYNC) takes milliseconds on macOS, and these tests
    flush thousands of times. What they pin is the order of the Disk port's
    calls and faults injected at them, which a plain fsync keeps; the flush's
    own tests put REAL_FLUSH back."""
    monkeypatch.setattr(wiring, "flush", os.fsync)


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for variable, directory in (
        ("HOME", "home"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_STATE_HOME", "state"),
    ):
        monkeypatch.setenv(variable, str(tmp_path / directory))


def test_roots_use_only_the_supplied_environment(tmp_path: Path) -> None:
    roots = wiring.Roots.from_env({"HOME": str(tmp_path)})
    assert roots.data == tmp_path / ".local/share/dotfiles/agent-hooks"
    assert roots.state == tmp_path / ".local/state/dotfiles/agent-hooks"
    assert roots.link("work-a") == roots.data / "current/work-a/agent-hook"
    assert roots.mark("work-a") == roots.state / "uninstalled/work-a"
    assert roots.journal("work-a") == roots.state / "switch-work-a.json"
    assert roots.lock == roots.state / "switch.lock"


@pytest.mark.parametrize("variable", ["XDG_DATA_HOME", "XDG_STATE_HOME"])
def test_relative_xdg_falls_back_to_home(tmp_path: Path, variable: str) -> None:
    roots = wiring.Roots.from_env({"HOME": str(tmp_path), variable: "relative"})
    assert roots == wiring.Roots.from_env({"HOME": str(tmp_path)})


def test_absolute_xdg_needs_no_home(tmp_path: Path) -> None:
    roots = wiring.Roots.from_env(
        {"XDG_DATA_HOME": str(tmp_path / "d"), "XDG_STATE_HOME": str(tmp_path / "s")}
    )
    assert roots.data == tmp_path / "d/dotfiles/agent-hooks"
    assert roots.state == tmp_path / "s/dotfiles/agent-hooks"


@pytest.mark.parametrize("env", [{}, {"HOME": ""}, {"HOME": "relative"}])
def test_unusable_roots_explain_the_error(env: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="absolute"):
        wiring.Roots.from_env(env)


@pytest.mark.parametrize(
    "key", ["", "../claude", "Work-a", "work_a", "a/b", "é", "a\n"]
)
def test_bad_home_keys_are_refused(tmp_path: Path, key: str) -> None:
    roots = wiring.Roots.from_env({"HOME": str(tmp_path)})
    for path_for in (roots.link, roots.mark, roots.journal):
        with pytest.raises(ValueError, match="key"):
            path_for(key)


class FaultDisk(wiring.RealDisk):
    """A real scratch disk with an ordered log and one-shot I/O faults."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fail_operation: str | None = None
        self.remaining: int | None = None
        self.after: Callable[[str, tuple[Any, ...]], None] = lambda *_: None

    def arm(self, operation: str | None, occurrence: int) -> None:
        self.fail_operation = operation
        self.remaining = occurrence

    def __getattribute__(self, name: str) -> Any:
        method = super().__getattribute__(name)
        if name.startswith("_") or name not in wiring.Disk.__dict__:
            return method

        def call(*args: Any) -> Any:
            self.calls.append((name, args))
            if self.remaining is not None and self.fail_operation in (None, name):
                self.remaining -= 1
                if self.remaining == 0:
                    self.remaining = None
                    raise OSError(f"injected {name}")
            value = method(*args)
            self.after(name, args)
            return value

        return call


def test_write_whole_orders_durable_replace_and_preserves_mode(tmp_path: Path) -> None:
    disk = FaultDisk()
    path = tmp_path / "settings.json"
    path.write_bytes(b"old")
    path.chmod(0o640)
    wiring.write_whole(disk, path, b"new")
    writes = [(op, args) for op, args in disk.calls if op != "mode"]
    assert [op for op, _ in writes] == [
        "create",
        "write",
        "fsync_file",
        "rename",
        "fsync_directory",
    ]
    temporary = writes[0][1][0]
    assert temporary.parent == path.parent
    assert writes[3][1] == (temporary, path)
    assert writes[4][1] == (path.parent,)
    assert path.read_bytes() == b"new"
    assert path.stat().st_mode & 0o777 == 0o640
    assert list(tmp_path.iterdir()) == [path]


@pytest.mark.parametrize(
    "operation", ["mode", "create", "write", "fsync_file", "rename", "fsync_directory"]
)
def test_each_write_fault_leaves_whole_old_or_new_bytes(
    tmp_path: Path, operation: str
) -> None:
    path = tmp_path / "settings.json"
    path.write_bytes(b"old" * 1000)
    disk = FaultDisk()
    disk.arm(operation, 1)
    with pytest.raises(OSError, match="injected"):
        wiring.write_whole(disk, path, b"new" * 1000)
    assert path.read_bytes() in (b"old" * 1000, b"new" * 1000)
    assert list(tmp_path.iterdir()) == [path]


def test_new_file_is_private(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    wiring.write_whole(FaultDisk(), path, b"{}")
    assert path.stat().st_mode & 0o777 == 0o600


def test_new_directories_fsync_each_parent(tmp_path: Path) -> None:
    disk = FaultDisk()
    wiring.ensure_directories(disk, tmp_path / "a/b/c", mode=0o700)
    mutations = [
        (op, args) for op, args in disk.calls if op in ("mkdir", "fsync_directory")
    ]
    assert mutations == [
        ("mkdir", (tmp_path / "a", 0o700)),
        ("fsync_directory", (tmp_path,)),
        ("mkdir", (tmp_path / "a/b", 0o700)),
        ("fsync_directory", (tmp_path / "a",)),
        ("mkdir", (tmp_path / "a/b/c", 0o700)),
        ("fsync_directory", (tmp_path / "a/b",)),
    ]


LINK_CASES = json.loads(
    (
        Path(__file__).resolve().parents[2]
        / "tools/agent-hooks/cmd/hookrelease/testdata/link-cases.json"
    ).read_text(encoding="utf-8")
)["cases"]


@pytest.mark.parametrize("case", LINK_CASES, ids=lambda case: case["name"])
@pytest.mark.parametrize("aliased_root", [False, True])
def test_release_targets_match_the_shared_go_table(
    tmp_path: Path, case: dict[str, Any], aliased_root: bool
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    for entry in case["make"]:
        name = entry.get("file", entry.get("dir", entry.get("symlink")))
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if "file" in entry:
            path.write_bytes(b"release")
        elif "dir" in entry:
            path.mkdir()
        else:
            path.symlink_to(entry["to"])
    supplied_root = root
    if aliased_root:
        supplied_root = tmp_path / "alias"
        supplied_root.symlink_to(root, target_is_directory=True)
    target = supplied_root / case["target"]
    if case["want"] is None:
        with pytest.raises((ValueError, OSError)):
            wiring.release_target(supplied_root, target)
    else:
        assert (
            wiring.release_target(supplied_root, target)
            == root.resolve() / case["want"]
        )


def test_switch_link_is_atomic_and_returns_the_previous_target(tmp_path: Path) -> None:
    root = tmp_path / "data"
    release = root / "releases/0123456789abcdef/agent-hook"
    release.parent.mkdir(parents=True)
    release.write_bytes(b"release")
    link = root / "current/claude/agent-hook"
    link.parent.mkdir(parents=True)
    link.symlink_to("../../releases/1111111111111111/agent-hook")
    disk = FaultDisk()
    assert (
        wiring.switch_link(disk, root, "claude", release)
        == "../../releases/1111111111111111/agent-hook"
    )
    writes = [
        (op, args)
        for op, args in disk.calls
        if op in ("symlink", "rename", "fsync_directory", "unlink")
    ]
    assert [op for op, _ in writes] == ["symlink", "rename", "fsync_directory"]
    temporary = writes[0][1][1]
    assert writes[0][1][0] == str(release.resolve())
    assert writes[1][1] == (temporary, link)
    assert writes[2][1] == (link.parent,)
    assert list(link.parent.iterdir()) == [link]
    assert wiring.switch_link(disk, root, "work-a", release) is None


def test_switch_link_fault_removes_its_temporary_entry(tmp_path: Path) -> None:
    root = tmp_path / "data"
    release = root / "releases/0123456789abcdef/agent-hook"
    release.parent.mkdir(parents=True)
    release.write_bytes(b"release")
    disk = FaultDisk()
    disk.arm("rename", 1)
    with pytest.raises(OSError):
        wiring.switch_link(disk, root, "claude", release)
    assert list((root / "current/claude").iterdir()) == []


def test_lock_wait_names_holder_and_sigkill_releases_it(tmp_path: Path) -> None:
    roots = wiring.Roots.from_env(os.environ)
    read_fd, write_fd = os.pipe()
    child = os.fork()
    if child == 0:
        os.close(read_fd)
        try:
            with wiring.switch_lock(roots, argv=["first-holder", "claude"]):
                os.write(write_fd, b"ready")
                time.sleep(10)
        finally:
            os._exit(0)
    os.close(write_fd)
    try:
        assert select.select([read_fd], [], [], 3)[0]
        assert os.read(read_fd, 5) == b"ready"
        started = time.monotonic()
        with (
            pytest.raises(wiring.LockBusy) as busy,
            wiring.switch_lock(roots, wait_limit=0.08),
        ):
            pytest.fail("second holder entered")
        assert time.monotonic() - started >= 0.08
        assert isinstance(busy.value.holder, dict)
        assert busy.value.holder["pid"] == child
        assert busy.value.holder["argv"] == ["first-holder", "claude"]
        assert str(child) in str(busy.value)
        assert "first-holder" in str(busy.value)
        holder = json.loads(roots.lock.read_bytes())
        assert set(holder) == {"pid", "argv", "started"}
        assert holder["started"].endswith("+00:00")
    finally:
        os.close(read_fd)
        os.kill(child, signal.SIGKILL)
        os.waitpid(child, 0)
    with wiring.switch_lock(roots, wait_limit=0):
        assert json.loads(roots.lock.read_bytes())["pid"] == os.getpid()


def prepared_change(
    tmp_path: Path,
    kind: str = "register",
    *,
    old_link: bool = True,
    old_file: bool = True,
) -> wiring.Change:
    roots = wiring.Roots.from_env({"HOME": str(tmp_path)})
    disk = FaultDisk()
    old_release = roots.data / "releases/1111111111111111/agent-hook"
    new_release = roots.data / "releases/2222222222222222/agent-hook"
    for release in (old_release, new_release):
        release.parent.mkdir(parents=True, exist_ok=True)
        release.write_bytes(release.parent.name.encode())
    if old_link:
        wiring.switch_link(disk, roots.data, "claude", old_release)
    path = tmp_path / "claude/settings.json"
    path.parent.mkdir(exist_ok=True)
    before = b'{"hooks":{"pre":["old"]},"keep":1}' if old_file else None
    after = b'{"hooks":{"pre":["new"]},"keep":1}'
    if before is not None:
        path.write_bytes(before)
    mark = wiring.MarkChange(
        roots.mark("claude"), kind == "install", kind == "unregister"
    )
    if mark.old:
        mark.path.parent.mkdir(parents=True)
        mark.path.write_bytes(b"")
    journal = wiring.Journal(
        home="claude",
        kind=kind,
        stage="file" if kind == "unregister" else "link",
        release=None
        if kind == "unregister"
        else wiring.Release(
            new_release,
            new_release.parent.name,
            sha256(new_release.read_bytes()).hexdigest(),
        ),
        link=None
        if kind == "unregister"
        else wiring.LinkChange(
            roots.link("claude"),
            str(old_release.resolve()) if old_link else None,
            str(new_release.resolve()),
        ),
        file=wiring.FileChange(path, before, after),
        # Every kind names the mark's state, so every step checks it: a
        # register's mark is absent before and after.
        mark=mark,
    )
    return wiring.Change(roots, journal)


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
def test_journal_round_trip_and_only_stage_can_change(
    tmp_path: Path, kind: str
) -> None:
    change = prepared_change(tmp_path, kind)
    disk = FaultDisk()
    path = change.roots.journal("claude")
    wiring.write_journal(disk, path, change.journal)
    assert wiring.read_journal(disk, path) == change.journal
    document = json.loads(path.read_bytes())
    assert set(document) == {
        "version",
        "home",
        "kind",
        "stage",
        "release",
        "link",
        "file",
        "mark",
        "trust",
    }
    assert document["version"] == 1 and document["trust"] is None
    assert document["file"]["old"] != change.journal.file.old
    next_stage = replace(change.journal, stage="verify")
    wiring.write_journal(disk, path, next_stage)
    assert wiring.read_journal(disk, path) == next_stage
    with pytest.raises(wiring.JournalUnreadable, match="immutable"):
        wiring.write_journal(
            disk, path, replace(next_stage, file=replace(next_stage.file, new=b"{}"))
        )
    assert wiring.read_journal(disk, path) == next_stage


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 2),
        ("version", True),
        ("home", "unknown"),
        ("home", "codex"),
        ("kind", "sync"),
        ("stage", "trust"),
        ("stage", "restore-mark"),
        ("file", None),
        ("release", None),
        ("link", []),
        ("mark", False),
        ("trust", {}),
        ("extra", 1),
        ("release.id", "0123456789ABCDEF"),
        ("release.sha256", "00"),
        ("release.path", "relative"),
        ("release.extra", 0),
        ("link.old", False),
        ("link.new", None),
        ("file.path", []),
        ("file.old", "%%%"),
        ("file.new", None),
        ("file.new", "bm90LWpzb24="),
        ("mark", {"path": "/mark", "old": 1, "new": False}),
    ],
)
def test_unreadable_journal_is_rejected_and_kept(
    tmp_path: Path, field: str, value: Any
) -> None:
    change = prepared_change(tmp_path)
    disk = FaultDisk()
    path = change.roots.journal("claude")
    wiring.write_journal(disk, path, change.journal)
    document = json.loads(path.read_bytes())
    parts = field.split(".")
    if len(parts) == 2:
        document[parts[0]][parts[1]] = value
    else:
        document[field] = value
    raw = json.dumps(document).encode()
    path.write_bytes(raw)
    with pytest.raises(wiring.JournalUnreadable):
        wiring.read_journal(disk, path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "raw", [b"{", b"[]", b"null", b"\xff", b'{"version":1,"version":1}']
)
def test_bad_json_journal_is_kept(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "switch-claude.json"
    path.write_bytes(raw)
    with pytest.raises(wiring.JournalUnreadable):
        wiring.read_journal(FaultDisk(), path)
    assert path.read_bytes() == raw


def test_missing_field_is_refused(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)
    path = change.roots.journal("claude")
    wiring.write_journal(FaultDisk(), path, change.journal)
    document = json.loads(path.read_bytes())
    del document["trust"]
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(wiring.JournalUnreadable, match="fields"):
        wiring.read_journal(FaultDisk(), path)


class StageVisits:
    def __init__(self, action: Callable[[str], None] = lambda _: None) -> None:
        self.visits: list[str] = []
        self.action = action

    def before(self, key: str, stage: str) -> None:
        assert key == "claude"
        self.visits.append(stage)
        self.action(stage)


class FakeVerifier:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.links: list[Path] = []

    def selftest(self, link: Path) -> wiring.Outcome:
        self.links.append(link)
        return (
            wiring.Outcome() if self.ok else wiring.Outcome(1, reason="selftest failed")
        )


@pytest.mark.parametrize(
    "kind,order",
    [
        ("register", ["link", "file", "verify"]),
        ("install", ["link", "file", "mark", "verify"]),
        ("unregister", ["file", "mark", "verify"]),
    ],
)
def test_each_kind_commits_in_the_designed_order(
    tmp_path: Path, kind: str, order: list[str]
) -> None:
    change = prepared_change(tmp_path, kind)
    steps = StageVisits()
    verifier = FakeVerifier()
    outcome = wiring.apply_change(change, FaultDisk(), steps, verifier)
    assert outcome.status == "committed"
    assert steps.visits == order
    assert change.journal.file.path.read_bytes() == change.journal.file.new
    assert change.roots.mark("claude").exists() == (kind == "unregister")
    assert not change.roots.journal("claude").exists()
    assert verifier.links == (
        [] if kind == "unregister" else [change.roots.link("claude")]
    )


@pytest.mark.parametrize("kind", ["register", "install"])
def test_selftest_failure_restores_the_registration_and_components(
    tmp_path: Path, kind: str
) -> None:
    change = prepared_change(tmp_path, kind)
    steps = StageVisits()
    outcome = wiring.apply_change(change, FaultDisk(), steps, FakeVerifier(False))
    assert outcome.status == "restored" and outcome.error is not None
    assert "selftest failed" in outcome.error
    assert json.loads(change.journal.file.path.read_bytes())["hooks"] == {
        "pre": ["old"]
    }
    assert str(change.roots.link("claude").readlink()).endswith(
        "1111111111111111/agent-hook"
    )
    assert change.roots.mark("claude").exists() == (kind == "install")
    assert not change.roots.journal("claude").exists()
    assert steps.visits[-2:] == ["restore-file", "restore-link"]


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
@pytest.mark.parametrize("fails", [False, True])
def test_other_settings_edits_survive_verification_and_restore(
    tmp_path: Path, kind: str, fails: bool
) -> None:
    change = prepared_change(tmp_path, kind)

    def edit(stage: str) -> None:
        if stage == "verify":
            current = json.loads(change.journal.file.path.read_bytes())
            current["editor"] = "kept"
            change.journal.file.path.write_text(json.dumps(current), encoding="utf-8")
            if fails and kind == "unregister":
                raise OSError("verify failed")

    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(edit), FakeVerifier(not fails)
    )
    assert outcome.status == ("restored" if fails else "committed")
    current = json.loads(change.journal.file.path.read_bytes())
    assert current["editor"] == "kept"
    assert current["hooks"] == {"pre": ["old" if fails else "new"]}


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
def test_hooks_edits_stop_without_undoing_anything_else(
    tmp_path: Path, kind: str
) -> None:
    change = prepared_change(tmp_path, kind)
    foreign = b'{"hooks":{"third-party":[]}}'

    def edit(stage: str) -> None:
        if stage == "verify":
            change.journal.file.path.write_bytes(foreign)

    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(edit), FakeVerifier()
    )
    assert outcome.status == "stopped" and outcome.component == "file.hooks"
    assert outcome.found == {"third-party": []}
    assert change.journal.file.path.read_bytes() == foreign
    assert change.roots.journal("claude").exists()


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
@pytest.mark.parametrize("old_link", [False, True])
def test_change_before_file_step_abandons_and_leaves_the_other_programs_file(
    tmp_path: Path, kind: str, old_link: bool
) -> None:
    change = prepared_change(tmp_path, kind, old_link=old_link)
    foreign = b'{"hooks":{"editor":[]}}'

    def edit(stage: str) -> None:
        if stage == "file":
            change.journal.file.path.write_bytes(foreign)

    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(edit), FakeVerifier()
    )
    assert outcome.status == "abandoned"
    assert change.journal.file.path.read_bytes() == foreign
    assert not change.roots.journal("claude").exists()
    if kind != "unregister":
        expected_id = "1111111111111111" if old_link else "2222222222222222"
        assert change.roots.link("claude").resolve().parent.name == expected_id


FORWARD_CASES = [
    ("register", "link"),
    ("register", "file"),
    ("register", "verify"),
    ("install", "link"),
    ("install", "file"),
    ("install", "mark"),
    ("install", "verify"),
    ("unregister", "file"),
    ("unregister", "mark"),
    ("unregister", "verify"),
]
RESTORE_CASES = [
    ("register", "restore-file"),
    ("register", "restore-link"),
    ("install", "restore-mark"),
    ("install", "restore-file"),
    ("install", "restore-link"),
    ("unregister", "restore-mark"),
    ("unregister", "restore-file"),
]


def assert_registration(
    change: wiring.Change, committed: bool, *, old_link: bool = True
) -> None:
    current = change.journal.file.path
    before = change.journal.file.old
    if not committed and before is None:
        # A change's scope is the hooks value: the file stays, with every
        # other key the new bytes held (the shared settings sync wrote).
        restored = json.loads(current.read_bytes())
        written = json.loads(change.journal.file.new)
        assert "hooks" not in restored
        assert restored == {k: v for k, v in written.items() if k != "hooks"}
    else:
        expected_bytes = change.journal.file.new if committed else before
        assert expected_bytes is not None
        expected = json.loads(expected_bytes)["hooks"]
        assert json.loads(current.read_bytes())["hooks"] == expected
    mark = change.journal.mark
    assert change.roots.mark("claude").exists() == (
        False if mark is None else mark.new if committed else mark.old
    )
    if change.journal.link:
        link = change.journal.link.path
        if committed:
            assert change.journal.release is not None
            assert link.resolve() == change.journal.release.path
        elif old_link:
            assert str(link.readlink()) == change.journal.link.old
        elif link.is_symlink():
            assert str(link.readlink()) == change.journal.link.new
    assert not change.roots.journal("claude").exists()


def fork_apply(
    change: wiring.Change,
    steps: StageVisits,
    disk: FaultDisk | None = None,
    *,
    selftest_ok: bool = True,
) -> None:
    child = os.fork()
    if child == 0:
        try:
            wiring.apply_change(
                change, disk or FaultDisk(), steps, FakeVerifier(selftest_ok)
            )
        finally:
            os._exit(90)  # A crash point that was not reached fails the test.
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0


@pytest.mark.parametrize("kind,stage", FORWARD_CASES)
@pytest.mark.parametrize("old_link", [False, True])
def test_child_crash_before_each_forward_stage_recovers_from_journal(
    tmp_path: Path, kind: str, stage: str, old_link: bool
) -> None:
    change = prepared_change(tmp_path, kind, old_link=old_link)

    def crash(visited: str) -> None:
        if visited == stage:
            os._exit(0)

    fork_apply(change, StageVisits(crash))
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    committed = stage == "verify"
    assert [outcome.status for outcome in outcomes] == [
        "committed" if committed else "restored"
    ]
    assert_registration(change, committed, old_link=old_link)


@pytest.mark.parametrize("kind,stage", RESTORE_CASES)
def test_child_crash_in_each_restore_resumes_it(
    tmp_path: Path, kind: str, stage: str
) -> None:
    change = prepared_change(tmp_path, kind)

    def crash(visited: str) -> None:
        if visited == "verify":
            raise OSError("force restore")
        if visited == stage:
            os._exit(0)

    fork_apply(change, StageVisits(crash))
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    assert [outcome.status for outcome in outcomes] == ["restored"]
    assert_registration(change, False)


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
def test_recovery_at_verify_restores_if_verification_fails(
    tmp_path: Path, kind: str
) -> None:
    change = prepared_change(tmp_path, kind)

    def crash(stage: str) -> None:
        if stage == "verify":
            os._exit(0)

    fork_apply(change, StageVisits(crash))
    if kind == "unregister":
        change.roots.mark("claude").unlink()
    outcomes = wiring.recover(
        change.roots, FaultDisk(), StageVisits(), FakeVerifier(False)
    )
    assert [outcome.status for outcome in outcomes] == ["restored"]
    assert_registration(change, False)


@pytest.mark.parametrize("old_link", [False, True])
@pytest.mark.parametrize(
    "point", ["before-abandon", "abandon", "restored-link", "before-delete"]
)
@pytest.mark.parametrize("foreign_hooks", [False, True])
def test_crashes_around_abandon_keep_the_foreign_file(
    tmp_path: Path, old_link: bool, point: str, foreign_hooks: bool
) -> None:
    change = prepared_change(tmp_path, old_link=old_link)
    foreign = (
        b'{"hooks":{"editor":[]}}'
        if foreign_hooks
        else b'{"hooks":{"pre":["old"]},"editor":1}'
    )
    disk = FaultDisk()
    switched = False

    def after(operation: str, args: tuple[Any, ...]) -> None:
        nonlocal switched
        if (
            operation == "read_bytes"
            and args[0] == change.journal.file.path
            and point == "before-abandon"
        ):
            os._exit(0)
        if operation == "rename" and args[1] == change.roots.link("claude"):
            switched = True
        if (
            operation == "fsync_directory"
            and args[0] == change.roots.link("claude").parent
            and switched
        ):
            switched = False
            if point == "restored-link" and change.roots.journal("claude").exists():
                document = json.loads(change.roots.journal("claude").read_bytes())
                if document["stage"] == "abandon":
                    os._exit(0)
        if (
            operation == "read_link"
            and point == "before-delete"
            and change.journal.file.path.read_bytes() == foreign
            and change.roots.journal("claude").exists()
            and json.loads(change.roots.journal("claude").read_bytes())["stage"]
            == "abandon"
        ):
            assert change.journal.link is not None
            restored = change.journal.link.old or change.journal.link.new
            if str(change.roots.link("claude").readlink()) == restored:
                os._exit(0)

    disk.after = after

    def crash(stage: str) -> None:
        if stage == "file":
            change.journal.file.path.write_bytes(foreign)
        if stage == "abandon" and (
            point == "abandon" or (point == "restored-link" and not old_link)
        ):
            os._exit(0)

    fork_apply(change, StageVisits(crash), disk)
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    expected = (
        "stopped"
        if point == "before-abandon" and foreign_hooks
        else "restored"
        if point == "before-abandon"
        else "abandoned"
    )
    assert [outcome.status for outcome in outcomes] == [expected]
    assert change.journal.file.path.read_bytes() == foreign
    assert change.roots.journal("claude").exists() == (expected == "stopped")


def test_recovery_stops_at_unreadable_journal_in_name_order(tmp_path: Path) -> None:
    roots = wiring.Roots.from_env(os.environ)
    roots.state.mkdir(parents=True)
    broken = roots.journal("claude")
    broken.write_bytes(b"{")
    later = roots.journal("work-a")
    later.write_bytes(b"also invalid")
    disk = FaultDisk()
    outcomes = wiring.recover(roots, disk, StageVisits(), FakeVerifier())
    assert len(outcomes) == 1 and outcomes[0].status == "stopped"
    assert outcomes[0].component == "journal"
    assert [args[0] for op, args in disk.calls if op == "read_bytes"] == [broken]
    assert broken.read_bytes() == b"{"
    assert later.read_bytes() == b"also invalid"


@pytest.mark.parametrize(
    "expected,current",
    [(None, None), (b"old", b"old"), (None, b"appeared"), (b"old", b"edited")],
)
def test_checked_write_refuses_a_changed_or_appeared_file(
    tmp_path: Path, expected: bytes | None, current: bytes | None
) -> None:
    disk = FaultDisk()
    path = tmp_path / "settings.json"
    if current is not None:
        path.write_bytes(current)
    if current == expected:
        wiring.write_if_unchanged(disk, path, expected, b"new")
        assert path.read_bytes() == b"new"
    else:
        with pytest.raises(wiring.ChangedSinceRead):
            wiring.write_if_unchanged(disk, path, expected, b"new")
        assert path.read_bytes() == current
        assert [op for op, _ in disk.calls] == ["read_bytes"]


@pytest.mark.parametrize("kind,stage", FORWARD_CASES)
def test_write_error_at_each_stage_restores(
    tmp_path: Path, kind: str, stage: str
) -> None:
    change = prepared_change(tmp_path, kind)

    def fail(visited: str) -> None:
        if visited == stage:
            raise OSError(f"write error at {stage}")

    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(fail), FakeVerifier()
    )
    assert outcome.status == "restored" and outcome.error == f"write error at {stage}"
    assert_registration(change, False)


@pytest.mark.parametrize("kind", ["register", "unregister"])
def test_whole_change_has_the_designed_power_loss_order(
    tmp_path: Path, kind: str
) -> None:
    change = prepared_change(tmp_path, kind)
    change.roots.state.mkdir(parents=True, exist_ok=True)
    change.roots.mark("claude").parent.mkdir(parents=True, exist_ok=True)
    disk = FaultDisk()
    outcome = wiring.apply_change(change, disk, StageVisits(), FakeVerifier())
    assert outcome.status == "committed"
    mutations = []
    for operation, args in disk.calls:
        if operation not in {
            "create",
            "write",
            "fsync_file",
            "rename",
            "fsync_directory",
            "symlink",
            "unlink",
            "mkdir",
        }:
            continue
        path = args[1] if operation in {"rename", "symlink"} else args[0]
        if path == change.roots.state or "switch-claude.json" in path.name:
            component = "journal"
        elif path == change.journal.file.path.parent or "settings.json" in path.name:
            component = "file"
        elif (
            path == change.roots.mark("claude").parent
            or path.name.startswith(".claude-")
            or path == change.roots.mark("claude")
        ):
            component = "mark"
        else:
            component = "link"
        mutations.append(f"{operation}:{component}")
    journal_write = [
        "create:journal",
        "write:journal",
        "fsync_file:journal",
        "rename:journal",
        "fsync_directory:journal",
    ]
    file_write = [
        "create:file",
        "write:file",
        "fsync_file:file",
        "rename:file",
        "fsync_directory:file",
    ]
    mark_write = [
        "create:mark",
        "write:mark",
        "fsync_file:mark",
        "rename:mark",
        "fsync_directory:mark",
    ]
    expected = (
        journal_write
        + ["symlink:link", "rename:link", "fsync_directory:link"]
        + journal_write
        + file_write
        + journal_write
        if kind == "register"
        else journal_write + file_write + journal_write + mark_write + journal_write
    )
    assert mutations == expected + ["unlink:journal", "fsync_directory:journal"]


def apply_with_read_fault(change: wiring.Change, disk: FaultDisk) -> None:
    # A read can fail before there is a journal. Recovery still must be safe.
    try:
        wiring.apply_change(change, disk, StageVisits(), FakeVerifier())
    except OSError:
        pass


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
def test_fault_at_every_disk_call_then_recovery_never_leaves_a_mix(
    tmp_path: Path, kind: str
) -> None:
    reference = prepared_change(tmp_path / "reference", kind)
    reference_disk = FaultDisk()
    assert (
        wiring.apply_change(
            reference, reference_disk, StageVisits(), FakeVerifier()
        ).status
        == "committed"
    )
    for occurrence in range(1, len(reference_disk.calls) + 1):
        change = prepared_change(tmp_path / f"fault-{occurrence}", kind)
        disk = FaultDisk()
        disk.arm(None, occurrence)
        apply_with_read_fault(change, disk)
        recovered = wiring.recover(
            change.roots, FaultDisk(), StageVisits(), FakeVerifier()
        )
        assert all(outcome.status != "stopped" for outcome in recovered), (
            occurrence,
            reference_disk.calls[occurrence - 1],
            recovered,
        )
        current_hooks = json.loads(change.journal.file.path.read_bytes())["hooks"]
        assert current_hooks in ({"pre": ["old"]}, {"pre": ["new"]})
        assert_registration(change, current_hooks == {"pre": ["new"]})


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
def test_restore_of_initially_missing_file_keeps_its_other_keys(
    tmp_path: Path, kind: str
) -> None:
    change = prepared_change(tmp_path, kind, old_file=False)

    def fail(stage: str) -> None:
        if stage == "verify":
            raise OSError("restore")

    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(fail), FakeVerifier()
    )
    assert outcome.status == "restored"
    assert_registration(change, False)


def test_absent_hooks_and_null_hooks_are_different(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)
    old = b'{"keep":1}'
    new = b'{"hooks":null,"keep":1}'
    change.journal.file.path.write_bytes(old)
    change = replace(
        change,
        journal=replace(
            change.journal, file=replace(change.journal.file, old=old, new=new)
        ),
    )
    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(), FakeVerifier(False)
    )
    assert outcome.status == "restored"
    assert json.loads(change.journal.file.path.read_bytes()) == {"keep": 1}


@pytest.mark.parametrize("component", ["link", "mark"])
def test_unexpected_components_stop_before_any_more_writes(
    tmp_path: Path, component: str
) -> None:
    change = prepared_change(tmp_path, "register")
    if component == "mark":
        change = replace(
            change,
            journal=replace(
                change.journal,
                mark=wiring.MarkChange(change.roots.mark("claude"), False, False),
            ),
        )

    def edit(stage: str) -> None:
        if stage == "file":
            if component == "link":
                change.roots.link("claude").unlink()
                change.roots.link("claude").symlink_to("/unexpected")
            else:
                change.roots.mark("claude").parent.mkdir(parents=True)
                change.roots.mark("claude").write_bytes(b"")

    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(edit), FakeVerifier()
    )
    assert outcome.status == "stopped" and outcome.component == component
    assert change.journal.file.path.read_bytes() == change.journal.file.old
    assert change.roots.journal("claude").exists()


def test_real_verifier_uses_bounded_runner_on_scratch_executable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    link = tmp_path / "agent-hook"
    link.write_text('#!/bin/sh\n[ "$1" = selftest ]\n', encoding="utf-8")
    link.chmod(0o700)
    assert wiring.ReleaseVerifier().selftest(link).ok
    timeouts = []
    real_run = wiring.run

    def bounded(args: list[str], *, timeout: float) -> wiring.Outcome:
        timeouts.append(timeout)
        return real_run(args, timeout=timeout)

    monkeypatch.setattr(wiring, "run", bounded)
    assert wiring.ReleaseVerifier().selftest(link).ok
    assert timeouts == [30]


def test_recovery_checks_already_restored_components_before_deleting_journal(
    tmp_path: Path,
) -> None:
    change = prepared_change(tmp_path)

    def crash(stage: str) -> None:
        if stage == "verify":
            raise OSError("restore")
        if stage == "restore-link":
            os._exit(0)

    fork_apply(change, StageVisits(crash))
    # Another writer repeats the new hooks while restoration is interrupted.
    change.journal.file.path.write_bytes(change.journal.file.new)
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    assert outcomes[0].status == "stopped"
    assert outcomes[0].component == "file.hooks"
    assert change.roots.journal("claude").exists()


def test_missing_release_during_link_step_restores_cleanly(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)
    assert change.journal.release is not None

    def remove_release(stage: str) -> None:
        if stage == "link":
            assert change.journal.release is not None
            change.journal.release.path.unlink()

    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(remove_release), FakeVerifier()
    )
    assert outcome.status == "restored"
    assert_registration(change, False)


@pytest.mark.parametrize("kind", ["register", "install"])
def test_release_evidence_is_verified_again_during_recovery(
    tmp_path: Path, kind: str
) -> None:
    change = prepared_change(tmp_path, kind)

    def crash(stage: str) -> None:
        if stage == "verify":
            os._exit(0)

    fork_apply(change, StageVisits(crash))
    assert change.journal.release is not None
    change.journal.release.path.write_bytes(b"tampered")
    verifier = FakeVerifier()
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), verifier)
    assert outcomes[0].status == "restored" and "SHA-256" in (outcomes[0].error or "")
    assert verifier.links == []
    assert_registration(change, False)


@pytest.mark.parametrize("kind,stage", RESTORE_CASES)
@pytest.mark.parametrize("point", ["write", "rename", "fsync"])
def test_crash_during_restore_io_is_recoverable(
    tmp_path: Path, kind: str, stage: str, point: str
) -> None:
    change = prepared_change(tmp_path, kind)
    disk = FaultDisk()
    current_stage = ""
    component_path = {
        "restore-file": change.journal.file.path,
        "restore-link": change.roots.link("claude"),
        "restore-mark": change.roots.mark("claude"),
    }[stage]

    def before(visited: str) -> None:
        nonlocal current_stage
        current_stage = visited
        if visited == "verify":
            raise OSError("restore")

    def after(operation: str, args: tuple[Any, ...]) -> None:
        if current_stage != stage:
            return
        # Removal of an uninstall mark is a single unlink and directory fsync.
        wanted_operation = (
            "unlink"
            if stage == "restore-mark" and kind == "unregister"
            else "symlink"
            if stage == "restore-link" and point == "write"
            else "fsync_directory"
            if point == "fsync"
            else point
        )
        if stage == "restore-mark" and kind == "unregister" and point == "fsync":
            wanted_operation = "fsync_directory"
        if operation != wanted_operation:
            return
        path = args[1] if operation in {"rename", "symlink"} else args[0]
        if (
            path == component_path
            or path == component_path.parent
            or (
                path.parent == component_path.parent
                and path.name.startswith(f".{component_path.name}-")
            )
        ):
            os._exit(0)

    disk.after = after
    fork_apply(change, StageVisits(before), disk)
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    assert [outcome.status for outcome in outcomes] == ["restored"]
    assert_registration(change, False)


@pytest.mark.parametrize(
    "component,field",
    [
        (None, "version"),
        (None, "home"),
        (None, "kind"),
        (None, "stage"),
        (None, "release"),
        (None, "link"),
        (None, "file"),
        (None, "mark"),
        (None, "trust"),
        ("release", "path"),
        ("release", "id"),
        ("release", "sha256"),
        ("link", "path"),
        ("link", "old"),
        ("link", "new"),
        ("file", "path"),
        ("file", "old"),
        ("file", "new"),
        ("mark", "path"),
        ("mark", "old"),
        ("mark", "new"),
    ],
)
def test_every_missing_journal_field_is_rejected(
    tmp_path: Path, component: str | None, field: str
) -> None:
    change = prepared_change(tmp_path, "install")
    path = change.roots.journal("claude")
    wiring.write_journal(FaultDisk(), path, change.journal)
    document = json.loads(path.read_bytes())
    del (document if component is None else document[component])[field]
    raw = json.dumps(document).encode()
    path.write_bytes(raw)
    with pytest.raises(wiring.JournalUnreadable):
        wiring.read_journal(FaultDisk(), path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("component", ["release", "link", "file", "mark"])
def test_extra_nested_journal_fields_are_rejected(
    tmp_path: Path, component: str
) -> None:
    change = prepared_change(tmp_path, "install")
    path = change.roots.journal("claude")
    wiring.write_journal(FaultDisk(), path, change.journal)
    document = json.loads(path.read_bytes())
    document[component]["unexpected"] = False
    raw = json.dumps(document).encode()
    path.write_bytes(raw)
    with pytest.raises(wiring.JournalUnreadable):
        wiring.read_journal(FaultDisk(), path)
    assert path.read_bytes() == raw


def test_recovery_rejects_paths_for_a_different_home(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)
    path = change.roots.journal("claude")
    wiring.write_journal(FaultDisk(), path, change.journal)
    document = json.loads(path.read_bytes())
    document["link"]["path"] = str(change.roots.link("work-a"))
    raw = json.dumps(document).encode()
    path.write_bytes(raw)
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    assert outcomes[0].status == "stopped" and outcomes[0].component == "journal"
    assert path.read_bytes() == raw


def test_an_edit_during_selftest_cannot_commit(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)

    class EditingVerifier:
        def selftest(self, link: Path) -> wiring.Outcome:
            change.journal.file.path.write_bytes(b'{"hooks":{"editor":[]}}')
            return wiring.Outcome()

    outcome = wiring.apply_change(change, FaultDisk(), StageVisits(), EditingVerifier())
    assert outcome.status == "stopped" and outcome.component == "file.hooks"
    assert change.roots.journal("claude").exists()


def test_journal_text_is_strictly_utf8(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)
    path = change.roots.journal("claude")
    wiring.write_journal(FaultDisk(), path, change.journal)
    document = path.read_text(encoding="utf-8")
    raw = document.encode("utf-16")
    path.write_bytes(raw)
    with pytest.raises(wiring.JournalUnreadable):
        wiring.read_journal(FaultDisk(), path)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
def test_steps_always_observe_their_own_durable_stage_even_when_abandoning(
    tmp_path: Path, kind: str
) -> None:
    change = prepared_change(tmp_path, kind)
    path = change.roots.journal("claude")

    def edit(stage: str) -> None:
        assert wiring.read_journal(FaultDisk(), path).stage == stage
        if stage == "file":
            change.journal.file.path.write_bytes(b'{"hooks":{"editor":[]}}')

    outcome = wiring.apply_change(
        change, FaultDisk(), StageVisits(edit), FakeVerifier()
    )
    assert outcome.status == "abandoned"


def test_journal_is_kept_if_its_deletion_cannot_be_fsynced_after_restore(
    tmp_path: Path,
) -> None:
    change = prepared_change(tmp_path)
    disk = FaultDisk()
    path = change.roots.journal("claude")

    def fail_verify(stage: str) -> None:
        if stage == "verify":
            raise OSError("force restore")

    def fail_deletion_sync(operation: str, args: tuple[Any, ...]) -> None:
        if operation == "unlink" and args[0] == path:
            disk.arm("fsync_directory", 1)

    disk.after = fail_deletion_sync
    outcome = wiring.apply_change(
        change, disk, StageVisits(fail_verify), FakeVerifier()
    )
    assert outcome.status == "stopped"
    assert path.exists()
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    assert outcomes[0].status == "restored"
    assert_registration(change, False)


@pytest.mark.parametrize("kind", ["register", "install", "unregister"])
def test_state_directories_are_private_and_link_directories_are_not(
    tmp_path: Path, kind: str
) -> None:
    # given a change on a machine with no state directory yet (the old link
    # is made first, so current/ exists before the state root does)
    change = prepared_change(tmp_path, kind, old_link=False)
    # (an install's mark is there already, made by the helper: model its
    # directories as private, as the module makes them)
    for existing in [
        tmp_path / ".local/state",
        *(tmp_path / ".local/state").rglob("*"),
    ]:
        if existing.is_dir():
            existing.chmod(0o700)
    # when it commits
    assert (
        wiring.apply_change(change, FaultDisk(), StageVisits(), FakeVerifier()).status
        == "committed"
    )
    # then what it made below the state root is the owner's only, as the file
    # log's directories are, and a link's directory is readable, as Go's
    # switch makes it
    state = change.roots.state
    made = [state, *(path for path in state.rglob("*") if path.is_dir())]
    assert all(path.stat().st_mode & 0o777 == 0o700 for path in made), [
        (str(path), oct(path.stat().st_mode & 0o777)) for path in made
    ]
    if change.journal.link:
        link_dir = change.roots.link("claude").parent
        assert link_dir.stat().st_mode & 0o777 == 0o755


def test_the_lock_makes_a_private_state_root(tmp_path: Path) -> None:
    roots = wiring.Roots.from_env({"HOME": str(tmp_path)})
    with wiring.switch_lock(roots, wait_limit=0):
        pass
    assert roots.state.stat().st_mode & 0o777 == 0o700


def test_journal_homes_are_the_claude_homes_sync_wires() -> None:
    import sync_agents

    assert wiring.HOMES == {
        agent.key for agent in sync_agents.AGENTS if agent.receives_hooks
    }


# ---- review round 1 (PR 3d.1): the independent review's findings ----


def test_recovery_stops_at_the_first_journal_it_cannot_resolve(tmp_path: Path) -> None:
    # given claude's change crashed at its file step, then its link moved by
    # another program, and work-a's change pending after it in name order
    change = prepared_change(tmp_path)

    def crash(stage: str) -> None:
        if stage == "file":
            os._exit(0)

    fork_apply(change, StageVisits(crash))
    elsewhere = change.roots.data / "releases/3333333333333333/agent-hook"
    elsewhere.parent.mkdir(parents=True)
    elsewhere.write_bytes(b"3")
    wiring.switch_link(FaultDisk(), change.roots.data, "claude", elsewhere)
    mark = change.roots.mark("work-a")
    work_a = wiring.Journal(
        home="work-a",
        kind="unregister",
        stage="mark",
        release=None,
        link=None,
        file=wiring.FileChange(
            tmp_path / "work-a/settings.json", b'{"hooks":{}}', b'{"hooks":{}}'
        ),
        mark=wiring.MarkChange(mark, False, True),
    )
    wiring.write_journal(FaultDisk(), change.roots.journal("work-a"), work_a)
    # when recovery runs, then it stops at claude, and leaves work-a's journal
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    assert [(outcome.home, outcome.status) for outcome in outcomes] == [
        ("claude", "stopped")
    ]
    assert change.roots.journal("work-a").is_file()


def test_a_restore_stops_when_a_restored_file_changes_again(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)
    path = change.journal.file.path

    def act(stage: str) -> None:
        if stage == "verify":
            raise OSError("force restore")
        if stage == "restore-link":
            # another program writes the new hooks back after restore-file
            path.write_bytes(change.journal.file.new)

    outcome = wiring.apply_change(change, FaultDisk(), StageVisits(act), FakeVerifier())
    assert outcome.status == "stopped" and outcome.component == "file.hooks"
    assert change.roots.journal("claude").is_file()
    # and nothing more changed: the link was not restored after the file moved
    assert change.journal.link is not None
    assert str(change.journal.link.path.readlink()) == change.journal.link.new


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_a_flush_on_macos_reaches_the_disk_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setattr(wiring, "flush", REAL_FLUSH)
    import fcntl

    # given macOS, where fsync stops at the drive's cache
    calls: list[tuple[str, int]] = []
    monkeypatch.setattr(wiring.sys, "platform", "darwin")
    monkeypatch.setattr(
        fcntl, "fcntl", lambda fd, op, *a: calls.append(("fcntl", op)) or 0
    )
    monkeypatch.setattr(wiring.os, "fsync", lambda fd: calls.append(("fsync", 0)))
    target = tmp_path / "f"
    target.write_bytes(b"x")
    # when a file or a directory is flushed
    disk = wiring.RealDisk()
    if kind == "file":
        disk.fsync_file(target)
    else:
        disk.fsync_directory(tmp_path)
    # then it asks for a full flush (F_FULLFSYNC, 51 on macOS), not fsync
    assert calls == [("fcntl", 51)]


def test_a_flush_falls_back_to_fsync_where_a_full_flush_is_not_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wiring, "flush", REAL_FLUSH)
    import errno
    import fcntl

    calls: list[str] = []

    def unsupported(fd: int, op: int, *args: object) -> int:
        calls.append("fcntl")
        raise OSError(errno.ENOTSUP, "not supported")

    monkeypatch.setattr(wiring.sys, "platform", "darwin")
    monkeypatch.setattr(fcntl, "fcntl", unsupported)
    monkeypatch.setattr(wiring.os, "fsync", lambda fd: calls.append("fsync"))
    target = tmp_path / "f"
    target.write_bytes(b"x")
    wiring.RealDisk().fsync_file(target)
    assert calls == ["fcntl", "fsync"]


def test_a_flush_elsewhere_is_fsync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wiring, "flush", REAL_FLUSH)
    calls: list[str] = []
    monkeypatch.setattr(wiring.sys, "platform", "linux")
    monkeypatch.setattr(wiring.os, "fsync", lambda fd: calls.append("fsync"))
    target = tmp_path / "f"
    target.write_bytes(b"x")
    wiring.RealDisk().fsync_file(target)
    assert calls == ["fsync"]


@pytest.mark.skipif(sys.platform != "darwin", reason="F_FULLFSYNC is macOS's")
def test_a_full_flush_works_on_this_machine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a read-only file and a directory, as RealDisk opens them
    monkeypatch.setattr(wiring, "flush", REAL_FLUSH)
    target = tmp_path / "f"
    target.write_bytes(b"x")
    wiring.RealDisk().fsync_file(target)
    wiring.RealDisk().fsync_directory(tmp_path)


# ---- review round 2 (PR 3d.1) ----


def test_a_journal_must_name_the_marks_state(tmp_path: Path) -> None:
    # given a journal written with no mark, as no sync writes one
    change = prepared_change(tmp_path)
    document = wiring._journal_document(change.journal)
    document["mark"] = None
    path = change.roots.journal("claude")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    # when it is read, then it is refused, and kept
    with pytest.raises(wiring.JournalUnreadable, match="mark"):
        wiring.read_journal(FaultDisk(), path)
    assert path.is_file()


def test_a_mark_made_during_a_register_stops_it(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)
    mark = change.roots.mark("claude")

    def act(stage: str) -> None:
        if stage == "verify":
            # someone marks the home uninstalled while it is being wired
            mark.parent.mkdir(parents=True, exist_ok=True)
            mark.write_bytes(b"")

    outcome = wiring.apply_change(change, FaultDisk(), StageVisits(act), FakeVerifier())
    assert outcome.status == "stopped" and outcome.component == "mark"
    assert change.roots.journal("claude").is_file()


def test_a_mark_made_before_recovery_of_a_register_stops_it(tmp_path: Path) -> None:
    change = prepared_change(tmp_path)

    def crash(stage: str) -> None:
        if stage == "verify":
            os._exit(0)

    fork_apply(change, StageVisits(crash))
    # given the home marked uninstalled after the crash, yet wired
    mark = change.roots.mark("claude")
    mark.parent.mkdir(parents=True, exist_ok=True)
    mark.write_bytes(b"")
    # when recovery runs, then it does not commit that state: it stops
    outcomes = wiring.recover(change.roots, FaultDisk(), StageVisits(), FakeVerifier())
    assert [(outcome.status, outcome.component) for outcome in outcomes] == [
        ("stopped", "mark")
    ]
    assert change.roots.journal("claude").is_file()


@pytest.mark.parametrize("kind", ["file", "directory"])
def test_a_failed_full_flush_is_an_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    import errno
    import fcntl

    monkeypatch.setattr(wiring, "flush", REAL_FLUSH)
    monkeypatch.setattr(wiring.sys, "platform", "darwin")

    def io_error(fd: int, op: int, *args: object) -> int:
        raise OSError(errno.EIO, "I/O error")

    calls: list[str] = []
    monkeypatch.setattr(fcntl, "fcntl", io_error)
    monkeypatch.setattr(wiring.os, "fsync", lambda fd: calls.append("fsync"))
    target = tmp_path / "f"
    target.write_bytes(b"x")
    # when the full flush fails for a reason other than no support, then the
    # error goes up, and no weaker flush stands in for it
    with pytest.raises(OSError) as raised:
        if kind == "file":
            wiring.RealDisk().fsync_file(target)
        else:
            wiring.RealDisk().fsync_directory(tmp_path)
    assert raised.value.errno == errno.EIO
    assert calls == []
