"""The disk-GC mechanism for both self-hosted runners must not silently
stop collecting within its authorized scope (ADR 0035/0067).
Build/mount-cache reclamation is deliberately omitted by ADR 0067; these tests
do not preserve the old cache-growth guarantee.

Why this exists
---------------
Every failure mode below is *silent* — the scripts still exit 0, they just stop
reclaiming, and the disk resumes its one-way growth until WSL can no longer
start:

- **Job detection.** `pgrep -f Runner.Worker` matches the GC script's own
  command line, so it reports "a job is running" 100% of the time and the GC
  skips forever. Only `pgrep -x` (exact executable name) is correct.
- **MSYS path mangling.** Git Bash rewrites unix-looking arguments
  (`/usr/local/bin/runner-gc`, `/mnt/c/...`, a bare `/`) into Windows paths
  before `wsl.exe` sees them, so every Windows->WSL dispatch must disable the
  conversion.
- **Half a sweep.** The Windows entrypoints must drive the native runner *and*
  the WSL one; an `exec` into WSL would drop the Windows leg silently.
- **Mojibake logs.** `powershell.exe` (5.1) reads a BOM-less UTF-8 script as
  ANSI, so the Windows scripts must stay ASCII-only to remain readable in the
  Scheduled Task's log — the only trace an unattended run leaves.
- **Wrong owner.** The hourly timer runs as root. Rootful and rootless Podman
  have different inventories. A successful query in root's context does not
  prove that the runner owner's inventory was reached.
- **Unbounded `_diag`.** The runner never rotates its own diagnostic logs, so
  they accumulate for the life of the box.
- **Toolcache generations.** `actions/setup-*` stacks a new
  `_tool/<tool>/<version>/` per release and never drops the old one. Reaping it
  by *lexical* order silently deletes the newest (`1.25.8` sorts above
  `1.25.11`), and deleting anything narrower than the whole `<version>/`
  directory leaves the `<version>/<arch>.complete` marker claiming a tool that
  is no longer there.
- **Stale directory timestamps.** Windows does not bump a directory's
  `LastWriteTime` when a nested file changes, so a workspace rebuilt minutes ago
  can still carry a two-month-old stamp. Ageing `_work/<repo>` on the directory
  mtime would therefore delete hot checkouts and spare cold ones — the marker
  file is what makes the 2 h budget mean anything there.

Mostly static checks (part of `tests/unit/`): the scripts drive a live runner,
systemd and the Windows task scheduler, none of which is reproducible
host-side. The workspace sweep is the exception — it deletes multi-GB trees, so
it is additionally exercised end-to-end against a synthetic runner root
whenever `pwsh` is available.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest
from _pwsh import resolve_pwsh

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
GC = SCRIPTS / "runner_gc.sh"
INSTALL = SCRIPTS / "install_runner_gc.sh"
COMPACT = SCRIPTS / "wsl_compact.sh"
GC_WIN = SCRIPTS / "runner_gc_win.ps1"
BASH = shutil.which("bash") or "/bin/bash"
PWSH = resolve_pwsh(os.environ)
# How runner_gc.sh starts runner_gc_win.ps1. Without -ExecutionPolicy Bypass,
# Windows PowerShell 5.1 refuses a script under its default policy.
GC_START = ("-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File")

# Every script that shells out to wsl.exe from a possible Git Bash host.

# Written by the GC into every workspace it sees a job finish in; the only
# reliable "last used" signal (see the module docstring).
MARKER = ".runner-gc-last-used"


def test_windows_scripts_are_ascii_only() -> None:
    """powershell.exe (5.1) reads a BOM-less UTF-8 script as ANSI.

    Any non-ASCII byte then arrives mojibake in the Scheduled Task log, which
    is the only record an unattended run leaves behind.

    Globbed, not listed: a hardcoded tuple silently exempts every .ps1 added
    after it, and this test is the only gate .ps1 files have (`just check`
    lints shell and Python, never PowerShell).
    """
    for script in sorted(SCRIPTS.glob("*.ps1")):
        raw = script.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf"), (
            f"{script.name} must not carry a UTF-8 BOM."
        )
        bad = [
            (n, line)
            for n, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1)
            if any(ord(ch) > 127 for ch in line)
        ]
        assert not bad, f"{script.name} must stay ASCII-only: {bad}"


@pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "native Windows: bare `bash` resolves to System32 (WSL) bash, which "
        "cannot read the drive-lettered script path; runs on Linux/WSL/CI"
    ),
)
def test_scripts_parse() -> None:
    """`bash -n` every script so a syntax error cannot ship."""
    for script in (GC, INSTALL, COMPACT, SCRIPTS / "disk_gc.sh"):
        proc = subprocess.run(
            [BASH, "-n", str(script)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        assert proc.returncode == 0, f"{script.name}: {proc.stderr}"


# ---------------------------------------------------------------------------
# Workspace sweep — the collector for `_work/<repo>`
#
# `_diag` and `_work/_temp` are rounding errors (0.3 GB and 12 KB on the host
# that prompted this); the workspaces are where the growth actually lives, at
# 4.9 GB across three repos. Deleting whole multi-GB trees earns stricter
# tests than the rest of the file: a mistake here is unrecoverable, not just a
# missed collection.
# ---------------------------------------------------------------------------


# --- end-to-end against a synthetic runner root -----------------------------


def _make_runner_root(tmp_path: Path) -> Path:
    """A directory that passes the script's own safety check."""
    root = tmp_path / "actions-runner-win"
    (root / "_work").mkdir(parents=True)
    (root / "_diag").mkdir()
    (root / ".runner").write_text("{}", encoding="utf-8")
    return root


def _age(path: Path, hours: float) -> None:
    stamp = time.time() - hours * 3600
    os.utime(path, (stamp, stamp))


def _age_link(path: Path, hours: float) -> None:
    """Backdate a reparse point itself.

    `os.utime` resolves the link and stamps the target, leaving the link
    reading fresh — which is exactly the state that hides the `bin.*` filter
    bug from a test.
    """
    assert PWSH is not None, "pwsh-only helper"
    subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-Command",
            (
                f"(Get-Item -LiteralPath '{path}' -Force).LastWriteTime = "
                f"(Get-Date).AddHours(-{hours})"
            ),
        ],
        capture_output=True,
        check=True,
    )


def _workspace(root: Path, name: str, age_hours: float, *, marker: bool = True) -> Path:
    """A workspace shaped like the runner builds it: `_work/<repo>/<repo>`."""
    top = root / "_work" / name
    (top / name / "target").mkdir(parents=True)
    (top / name / "target" / "build.bin").write_bytes(b"x" * 512)
    if marker:
        stamp = top / MARKER
        stamp.touch()
        _age(stamp, age_hours)
    _age(top, age_hours)
    return top


def _run_gc(root: Path, *extra: str, env: dict[str, str] | None = None):
    overrides = dict(os.environ)
    # A real job's variables must not leak in from the developer's shell.
    for key in ("RUNNER_WORKSPACE", "GITHUB_WORKSPACE", "GITHUB_REPOSITORY"):
        overrides.pop(key, None)
    profile = root.parent / "disposable-profile"
    profile.mkdir(exist_ok=True)
    overrides.update({"USERPROFILE": str(profile), "HOME": str(profile)})
    overrides.update(env or {})
    assert PWSH is not None, "pwsh-only helper"
    return subprocess.run(
        [
            PWSH,
            *GC_START,
            str(GC_WIN),
            "-RunnerRoot",
            str(root),
            "-SkipPodman",
            "-Force",
            *extra,
        ],
        capture_output=True,
        text=True,
        env=overrides,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


pwshonly = pytest.mark.skipif(PWSH is None, reason="needs pwsh to run the GC")


@pwshonly
def test_cold_workspace_goes_warm_workspace_stays(tmp_path: Path) -> None:
    root = _make_runner_root(tmp_path)
    cold = _workspace(root, "example-repo-a", age_hours=5)
    warm = _workspace(root, "example-repo-b", age_hours=0.5)

    proc = _run_gc(root)

    assert proc.returncode == 0, proc.stderr
    assert not cold.exists(), "a workspace idle for 5 h must be collected"
    assert warm.exists(), "a workspace used 30 min ago must survive"


@pwshonly
def test_marker_outranks_a_stale_directory_timestamp(tmp_path: Path) -> None:
    """The regression the marker exists for: old directory, fresh marker."""
    root = _make_runner_root(tmp_path)
    ws = _workspace(root, "example-repo-a", age_hours=800)
    _age(ws / MARKER, 0.25)

    proc = _run_gc(root)

    assert proc.returncode == 0, proc.stderr
    assert ws.exists(), (
        "the marker says this workspace was used 15 min ago; the two-month-old "
        "directory mtime must not override it."
    )


@pwshonly
def test_live_workspace_survives_even_when_cold(tmp_path: Path) -> None:
    root = _make_runner_root(tmp_path)
    live = _workspace(root, "example-repo-a", age_hours=99)

    proc = _run_gc(root, env={"RUNNER_WORKSPACE": str(live / "example-repo-a")})

    assert proc.returncode == 0, proc.stderr
    assert live.exists(), (
        "RUNNER_WORKSPACE points at the job the runner is finishing; it must "
        "be excluded no matter how the ageing lands."
    )


@pwshonly
def test_hook_stamps_the_marker_for_the_finishing_job(tmp_path: Path) -> None:
    """Without this the workspace of the *last* job ages from its checkout."""
    root = _make_runner_root(tmp_path)
    ws = _workspace(root, "example-repo-a", age_hours=99, marker=False)

    proc = _run_gc(root, env={"GITHUB_REPOSITORY": "example-org/example-repo-a"})

    assert proc.returncode == 0, proc.stderr
    assert ws.exists(), "the workspace of the job we just ran must be kept"
    assert (ws / MARKER).exists(), (
        "the GC must stamp the marker for GITHUB_REPOSITORY so the next sweep "
        "ages this workspace from now, not from its checkout date."
    )


@pwshonly
def test_runner_owned_directories_are_never_swept(tmp_path: Path) -> None:
    root = _make_runner_root(tmp_path)
    managed = []
    for name in ("_actions", "_tool", "_PipelineMapping"):
        directory = root / "_work" / name
        directory.mkdir()
        (directory / "keep.txt").write_text("keep", encoding="utf-8")
        _age(directory, 999)
        managed.append(directory)

    proc = _run_gc(root)

    assert proc.returncode == 0, proc.stderr
    for directory in managed:
        assert directory.exists(), (
            f"{directory.name} is runner-owned state, not a workspace cache; "
            "deleting it forces every action to re-download."
        )


@pwshonly
def test_readonly_files_do_not_stop_the_sweep(tmp_path: Path) -> None:
    """`.git/objects` is read-only; a naive delete aborts the whole tree."""
    root = _make_runner_root(tmp_path)
    ws = _workspace(root, "example-repo-a", age_hours=9)
    locked = ws / "example-repo-a" / ".git" / "objects"
    locked.mkdir(parents=True)
    blob = locked / "cafebabe"
    blob.write_bytes(b"blob")
    blob.chmod(stat.S_IREAD)

    proc = _run_gc(root)

    assert proc.returncode == 0, proc.stderr
    assert not ws.exists(), (
        "read-only git objects must be cleared, not left behind as a partial "
        "delete that keeps the disk full."
    )


@pwshonly
def test_a_single_stale_log_does_not_throw(tmp_path: Path) -> None:
    """One match makes Get-ChildItem return a bare FileInfo, not an array.

    Under `Set-StrictMode -Version Latest` that object has no `.Count`, so the
    trim throws PropertyNotFoundStrict mid-sweep. `$ErrorActionPreference =
    'Continue'` keeps the exit code at 0, so this only ever shows up as a
    stack trace in the Scheduled Task log nobody reads.
    """
    root = _make_runner_root(tmp_path)
    log = root / "_diag" / "Runner_only_one.log"
    log.write_text("x", encoding="utf-8")
    _age(log, 24 * 30)

    proc = _run_gc(root)

    assert proc.returncode == 0, proc.stderr
    assert "PropertyNotFoundStrict" not in proc.stderr, (
        f"the _diag trim threw on a single match: {proc.stderr}"
    )
    assert not log.exists(), "the stale log should still have been collected"


@pwshonly
def test_dry_run_reports_without_deleting(tmp_path: Path) -> None:
    """Rehearsal before pointing this at a real 5 GB runner root."""
    root = _make_runner_root(tmp_path)
    cold = _workspace(root, "example-repo-a", age_hours=5)

    proc = _run_gc(root, "-DryRun")

    assert proc.returncode == 0, proc.stderr
    assert cold.exists(), "-DryRun must not delete anything"
    assert "example-repo-a" in proc.stdout, (
        "-DryRun has to name what it would collect, or it cannot be reviewed."
    )


@pwshonly
def test_dry_run_spares_the_log_trim_too(tmp_path: Path) -> None:
    """A rehearsal that deletes 800 log files is not a rehearsal.

    The workspace sweep gained -DryRun; the _diag/_temp trims predate it and
    silently ignored the flag, so the first real dry-run against the live
    runner reclaimed 282 MB it had just promised not to touch.
    """
    root = _make_runner_root(tmp_path)
    log = root / "_diag" / "Runner_ancient.log"
    log.write_text("old", encoding="utf-8")
    _age(log, 24 * 30)
    scratch = root / "_work" / "_temp" / "leftover"
    scratch.mkdir(parents=True)
    _age(scratch, 24 * 30)

    proc = _run_gc(root, "-DryRun")

    assert proc.returncode == 0, proc.stderr
    assert log.exists(), "-DryRun deleted a _diag log"
    assert scratch.exists(), "-DryRun deleted _work/_temp scratch"


@pwshonly
@pytest.mark.skipif(sys.platform != "win32", reason="needs a real NTFS link")
def test_the_live_bin_link_is_never_pruned(tmp_path: Path) -> None:
    """`-Filter bin.*` matches `bin` itself.

    Windows treats a trailing `.*` as "extension optional", so the filter that
    finds `bin.2.335.1` also returns the live `bin` link - and its name never
    equals the resolved target, so the "is this the current one?" guard waves
    it through. Deleting that link leaves a runner that cannot start.
    """
    root = _make_runner_root(tmp_path)
    live = root / "bin.2.336.0"
    live.mkdir()
    (live / "Runner.Listener.exe").write_text("x", encoding="utf-8")
    stale = root / "bin.2.335.1"
    stale.mkdir()
    (stale / "Runner.Listener.exe").write_text("x", encoding="utf-8")
    _age(stale, 24 * 30)
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "bin"), str(live)],
        capture_output=True,
        check=True,
    )
    _age_link(root / "bin", 24 * 30)

    proc = _run_gc(root)

    assert proc.returncode == 0, proc.stderr
    assert (root / "bin").exists(), "the live bin link must survive the sweep"
    assert (live / "Runner.Listener.exe").exists(), (
        "the version bin points at must survive with its contents"
    )
    assert not stale.exists(), "the superseded version should still be collected"


@pwshonly
@pytest.mark.skipif(sys.platform != "win32", reason="junctions are Windows-only")
def test_sweep_does_not_follow_a_junction_out_of_the_workspace(
    tmp_path: Path,
) -> None:
    """A junction in a checkout must cost the link, never the target."""
    root = _make_runner_root(tmp_path)
    ws = _workspace(root, "example-repo-a", age_hours=9)
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    subprocess.run(
        [
            "cmd",
            "/c",
            "mklink",
            "/J",
            str(ws / "example-repo-a" / "linked"),
            str(outside),
        ],
        capture_output=True,
        check=True,
    )

    proc = _run_gc(root)

    assert proc.returncode == 0, proc.stderr
    assert not ws.exists(), "the workspace itself must still be collected"
    assert (outside / "keep.txt").exists(), (
        "the GC followed a junction and deleted data outside the runner root."
    )


# --- Returning the space, and reaching the caches that actually grow ---------


# How the sparse flag is read is pinned by behaviour in test_wsl_compact.py;
# a string check here let a localised-grep verdict through.


# --- The hook that never ran ------------------------------------------------


# --- WSL workspaces: the mirror of the Windows leg ---------------------------


@pytest.mark.skipif(
    PWSH is None or sys.platform != "win32",
    reason="requires native Windows pwsh and batch fake",
)
def test_windows_gc_survives_a_hanging_podman(tmp_path: Path) -> None:
    """Behavioral: a podman that never returns must not hang the sweep."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    # Found via Get-Command 'podman' on PATH; sleeps far longer than the
    # watchdog budget on every invocation (info and prunes alike).
    (stub_dir / "podman.bat").write_text(
        "@echo off\nping -n 121 127.0.0.1 >nul\n", encoding="ascii"
    )
    root = _make_runner_root(tmp_path)
    start = time.monotonic()
    assert PWSH is not None, "pwsh-only test"
    proc = subprocess.run(
        [
            PWSH,
            *GC_START,
            str(GC_WIN),
            "-RunnerRoot",
            str(root),
            "-Force",
            "-PodmanTimeoutSec",
            "3",
            "-PodmanOnly",
        ],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{stub_dir}{os.pathsep}" + os.environ.get("PATH", ""),
        },
        timeout=90,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed = time.monotonic() - start
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert elapsed < 60, (
        f"a hanging podman held the sweep for {elapsed:.0f}s; the watchdog "
        "must kill it within its budget."
    )
    assert "timed out" in proc.stdout, (
        "the watchdog kill must be logged: " + proc.stdout
    )
