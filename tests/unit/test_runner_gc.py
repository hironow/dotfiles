"""The disk-GC mechanism for both self-hosted runners must not silently
stop collecting (ADR 0035).

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
- **Wrong daemon.** The hourly timer runs as root. On a host where the runner
  drives *rootless* Docker, root's `docker` resolves to `/var/run/docker.sock`
  — a different, usually empty daemon — so `docker info` succeeds, both
  `system df` lines read ~0B and the sweep exits 0 having reclaimed nothing,
  while the runner's real hoard grows untouched.
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
import re
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
GC = SCRIPTS / "runner_gc.sh"
INSTALL = SCRIPTS / "install_runner_gc.sh"
COMPACT = SCRIPTS / "wsl_compact.sh"
GC_WIN = SCRIPTS / "runner_gc_win.ps1"
INSTALL_WIN = SCRIPTS / "install_runner_gc_win.ps1"
DISK = SCRIPTS / "disk_gc.sh"
BASH = shutil.which("bash") or "/bin/bash"
PWSH = shutil.which("pwsh")

# Every script that shells out to wsl.exe from a possible Git Bash host.
DISPATCHERS = (GC, INSTALL, COMPACT, DISK)

# Written by the GC into every workspace it sees a job finish in; the only
# reliable "last used" signal (see the module docstring).
MARKER = ".runner-gc-last-used"


def test_job_detection_uses_exact_name_match() -> None:
    """`pgrep -f Runner.Worker` self-matches; only `pgrep -x` is correct."""
    text = GC.read_text(encoding="utf-8")
    assert re.search(r"pgrep\s+-x\s+Runner\.Worker", text), (
        "runner_gc.sh must detect a running job with `pgrep -x Runner.Worker`."
    )
    # -f may legitimately appear in a comment explaining the trap, so only
    # reject it as an actual invocation.
    bad = [
        line
        for line in text.splitlines()
        if re.search(r"^\s*[^#]*pgrep\s+(-\w*f\w*\s+)", line)
    ]
    assert not bad, (
        "runner_gc.sh invokes `pgrep -f`, which matches its own command line "
        f"and disables the GC permanently: {bad}"
    )


def test_dispatchers_disable_msys_path_conversion() -> None:
    """Git Bash mangles unix-looking argv before wsl.exe receives it."""
    for script in DISPATCHERS:
        text = script.read_text(encoding="utf-8")
        if "wsl.exe" not in text:
            continue
        assert "MSYS_NO_PATHCONV=1" in text and "MSYS2_ARG_CONV_EXCL" in text, (
            f"{script.name} calls wsl.exe without disabling MSYS path "
            "conversion; unix paths arrive rewritten to Windows paths."
        )


def test_retention_is_time_based_and_overridable() -> None:
    """The 2h budget is the decision in ADR 0035; keep it configurable."""
    text = GC.read_text(encoding="utf-8")
    assert 'RETENTION="${RUNNER_GC_RETENTION:-2h}"' in text, (
        "runner_gc.sh must default to a 2h retention overridable by "
        "RUNNER_GC_RETENTION."
    )
    # All three docker prunes must be age-filtered, never unconditional.
    for cmd in ("container prune", "image prune", "builder prune"):
        pattern = rf"docker {cmd}[^\n]*--filter \"until=\$\{{RETENTION\}}\""
        assert re.search(pattern, text), (
            f"`docker {cmd}` must carry the --filter until=$RETENTION guard."
        )


def test_gc_prunes_docker_container_buildx_builders() -> None:
    """`docker builder prune` does not reach docker-container builders."""
    text = GC.read_text(encoding="utf-8")
    assert "docker buildx prune" in text and "--builder" in text, (
        "runner_gc.sh must also prune non-default buildx builders, whose "
        "cache lives inside their own container."
    )


def test_installer_upserts_hook_without_duplicating() -> None:
    """Re-running the installer must not append the hook key twice."""
    text = INSTALL.read_text(encoding="utf-8")
    assert re.search(r'grep -v "\^\$\{_hook_key\}="', text), (
        "install_runner_gc.sh must strip the prior hook line before appending "
        "so repeated runs stay idempotent."
    )
    # `sed -i` is BSD/GNU-incompatible; reject real invocations but allow the
    # comment that explains why the upsert avoids it.
    bad = [
        line for line in text.splitlines() if re.search(r"^\s*[^#]*\bsed\s+-i\b", line)
    ]
    assert not bad, f"install_runner_gc.sh must stay portable (no `sed -i`): {bad}"


def test_compaction_stays_advisory() -> None:
    """Compaction stops the distro and kills CI; never self-apply it."""
    text = COMPACT.read_text(encoding="utf-8")
    assert "--shutdown" in text, "wsl_compact.sh should document the shutdown."
    assert not re.search(r"^\s*[^#]*wsl\.exe --shutdown", text, re.M), (
        "wsl_compact.sh must not execute `wsl --shutdown` itself — it would "
        "take the self-hosted runner offline without asking."
    )
    assert not re.search(r"^\s*[^#]*--allow-unsafe", text, re.M), (
        "sparse VHD is disabled by Microsoft over data corruption (ADR 0035); "
        "never force it on a CI host."
    )


def test_windows_scripts_are_ascii_only() -> None:
    """powershell.exe (5.1) reads a BOM-less UTF-8 script as ANSI.

    Any non-ASCII byte then arrives mojibake in the Scheduled Task log, which
    is the only record an unattended run leaves behind.
    """
    for script in (GC_WIN, INSTALL_WIN):
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


def test_windows_gc_skips_while_a_job_runs() -> None:
    """Same job-safety contract as the Linux leg."""
    text = GC_WIN.read_text(encoding="utf-8")
    assert "Get-Process -Name 'Runner.Worker'" in text, (
        "runner_gc_win.ps1 must check for an in-flight job before pruning."
    )
    assert "--filter=until=$Retention" in text, (
        "Windows docker prunes must carry the same age filter as the WSL leg."
    )


def test_windows_installer_upserts_hook_without_bom() -> None:
    """The runner's .env parser chokes on a BOM, and re-runs must not stack."""
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert "UTF8Encoding($false)" in text, (
        "install_runner_gc_win.ps1 must write .env as UTF-8 without a BOM."
    )
    assert '-notmatch "^$hookKey="' in text, (
        "install_runner_gc_win.ps1 must drop the prior hook line so repeated "
        "runs stay idempotent."
    )
    assert "Unregister-ScheduledTask" in text, (
        "the installer must clear the old task so triggers do not stack."
    )


def test_windows_entrypoint_drives_both_runners() -> None:
    """`just runner-gc` must sweep the WSL *and* the native Windows runner."""
    for script, ps1 in (
        (GC, "runner_gc_win.ps1"),
        (INSTALL, "install_runner_gc_win.ps1"),
    ):
        text = script.read_text(encoding="utf-8")
        assert "wsl.exe" in text and ps1 in text, (
            f"{script.name}'s Windows branch must drive both legs, not just WSL."
        )
        assert "exec wsl.exe" not in text, (
            f"{script.name} must not `exec` into WSL — that would skip the "
            "Windows leg entirely."
        )


def test_docker_leg_also_runs_as_each_runner_owner() -> None:
    """Root's own docker context cannot reach a rootless daemon.

    The timer runs as root. Where the runner drives rootless Docker, root's
    `docker` talks to `/var/run/docker.sock` — a *different* daemon that is
    typically empty — so every prune succeeds against nothing and the sweep
    reports success. Root must therefore also re-enter the docker leg as each
    runner's owning user, whose context points at the daemon the jobs actually
    dirty. Keeping root's own leg as well means a rootful-only host is
    unaffected, so the fix cannot regress either topology.
    """
    text = GC.read_text(encoding="utf-8")
    assert re.search(r"runuser\s+-u", text), (
        "runner_gc.sh must drop to the runner's owning user for the docker "
        "leg; as root it would prune the wrong (often empty) daemon."
    )
    assert "XDG_RUNTIME_DIR" in text, (
        "the re-entry must set XDG_RUNTIME_DIR so the rootless context "
        "resolves to /run/user/<uid>/docker.sock."
    )
    assert "RUNNER_GC_DOCKER_ONLY" in text, (
        "the re-entry needs a docker-only mode so it neither recurses nor "
        "repeats the root-only apt/journal work."
    )


def test_diag_logs_are_rotated_on_the_linux_leg() -> None:
    """The runner never rotates `_diag`; nothing else will.

    The Windows leg already trims `_diag`; without the same on the Linux leg
    the WSL runner keeps every diagnostic log it has ever written.
    """
    text = GC.read_text(encoding="utf-8")
    assert "_diag" in text, (
        "runner_gc.sh must rotate the runner's _diag logs — they are never "
        "rotated by the runner itself."
    )
    assert re.search(r"-mtime\s+\+", text), (
        "_diag rotation must be age-based (`find -mtime +N`), so the current "
        "job's logs survive."
    )


def test_toolcache_keeps_the_newest_patch_of_each_series() -> None:
    """Counting generations deletes versions the matrices still pin.

    Workflows pin a *series* (`go-version: 1.25.x`, `node-version: 22.x`,
    `python-version: 3.13`) and `setup-*` resolves it to the newest patch in
    that series. So "keep the newest N versions" is the wrong axis: on this
    runner three repos pin Python 3.10, 3.13 and 3.14, and keeping only the
    newest would evict two of them on every sweep and re-download them on the
    next job.

    Keeping the newest patch *per series* protects exactly what a series pin
    resolves to, while still reaping superseded patches (go had 1.25.0 and
    1.25.8 sitting behind 1.25.11). `RUNNER_GC_TOOLCACHE_KEEP` then bounds how
    many series survive, so the cache cannot grow without limit either.
    """
    text = GC.read_text(encoding="utf-8")
    assert "RUNNER_GC_TOOLCACHE_KEEP" in text, (
        "the number of retained series must stay configurable."
    )
    assert re.search(r"series", text, re.I), (
        "toolcache reaping must group versions by major.minor series; a flat "
        "newest-N count evicts versions the matrices still pin."
    )


def test_toolcache_reaping_is_semver_ordered_and_atomic() -> None:
    """Lexical order deletes the newest tool; partial deletes corrupt the cache.

    `sort -V` is mandatory: this box holds `go/1.25.8` and `go/1.25.11`, and
    lexically `1.25.8` sorts *above* `1.25.11`, so a plain `sort` would keep
    the older one and delete the newest. The unit of deletion must be the whole
    `<version>/` directory, because `<version>/<arch>.complete` — the marker
    the runner trusts to decide a tool is cached — lives inside it.
    """
    text = GC.read_text(encoding="utf-8")
    assert "_tool" in text, (
        "runner_gc.sh must reap stale toolcache generations; setup-* actions "
        "stack one directory per release and never remove the old ones."
    )
    assert re.search(r"\bsort\s+-V\b", text), (
        "toolcache generations must be ordered with `sort -V`; lexical order "
        "keeps 1.25.8 over 1.25.11 and deletes the newest tool."
    )
    bad = [
        line
        for line in text.splitlines()
        if re.search(r"^\s*[^#]*\bsort\s+-r?\s*$", line)
        or re.search(r"^\s*[^#]*\bsort\s+-r\b", line)
    ]
    assert not bad, f"toolcache ordering must not fall back to lexical sort: {bad}"


def test_toolcache_reaping_never_races_a_running_job() -> None:
    """Deleting an in-use `<version>/` breaks the job outright.

    Losing build cache to a prune only costs time, so `RUNNER_GC_FORCE=1`
    may bypass the job guard for Docker. Removing a toolcache directory that a
    running job resolved earlier makes its next step fail with ENOENT, so this
    leg must re-check for a live job regardless of FORCE.
    """
    text = GC.read_text(encoding="utf-8")
    # The guard is ancestry-aware (`_foreign_worker`) rather than a bare pgrep,
    # so the job-completed hook is not blocked by the very worker that invoked
    # it — but a *concurrent* job still stops this leg, FORCE or not.
    # Top-level guard: FORCE may bypass it (losing build cache only costs time).
    assert re.search(r'if \[ "\$FORCE" != "1" \] && _foreign_worker', text), (
        "the top-level guard must be _foreign_worker, bypassable by FORCE."
    )
    # Toolcache guard: separate, and FORCE must not reach it.
    assert re.search(r"^if _foreign_worker; then$", text, re.M), (
        "the toolcache leg needs its own `_foreign_worker` guard with no FORCE "
        "escape, separate from the top-level docker guard."
    )


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
        proc = subprocess.run([BASH, "-n", str(script)], capture_output=True, text=True)
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


def test_workspace_ageing_never_trusts_the_directory_mtime() -> None:
    """A directory mtime does not track work done inside it on Windows.

    Ageing a workspace on `LastWriteTime` inverts the policy — hot checkouts
    look old and get deleted, cold ones look fresh and survive.
    """
    text = GC_WIN.read_text(encoding="utf-8")
    assert ".runner-gc-last-used" in text, (
        "runner_gc_win.ps1 must age workspaces on a marker file it stamps "
        "itself, not on the directory timestamp."
    )


def test_workspace_sweep_protects_the_live_checkout() -> None:
    """The runner hands us the in-flight workspace; never age it out."""
    text = GC_WIN.read_text(encoding="utf-8")
    for var in ("RUNNER_WORKSPACE", "GITHUB_WORKSPACE"):
        assert var in text, (
            f"runner_gc_win.ps1 must read {var} and exclude that path "
            "unconditionally, so a hook firing mid-checkout cannot delete it."
        )


def test_workspace_sweep_uses_an_explicit_runner_dir_allowlist() -> None:
    """`_`-prefix matching would permanently exclude a repo literally named
    `_foo`; the runner's own directories are a known, closed set."""
    text = GC_WIN.read_text(encoding="utf-8")
    for managed in ("_actions", "_tool", "_temp", "_update", "_PipelineMapping"):
        assert managed in text, (
            f"runner_gc_win.ps1 must name {managed} in its protect list "
            "instead of inferring runner-owned directories from a prefix."
        )


def test_counted_collections_are_wrapped_for_powershell_51() -> None:
    """`runner_gc.sh` drives the Windows leg through `powershell.exe` (5.1).

    There, `Get-ChildItem | Where-Object` yielding exactly one item returns a
    bare FileInfo, which has no `.Count` under `Set-StrictMode -Version
    Latest` - so the sweep throws. pwsh 7 supplies `.Count` on any object, so
    the end-to-end tests below run green while the real hook crashes. Only a
    static check covers this.
    """
    text = GC_WIN.read_text(encoding="utf-8")
    bad = [
        (n, line.strip())
        for n, line in enumerate(text.splitlines(), 1)
        if re.search(r"^\s*\$(\w+)\s*=\s*Get-ChildItem", line)
        and re.search(rf"\${re.match(r'^\s*\$(\w+)', line).group(1)}\.Count", text)
    ]
    assert not bad, (
        "these collections are counted but not wrapped in @(), so a single "
        f"match throws under powershell.exe 5.1: {bad}"
    )


def test_dry_run_covers_the_docker_prunes() -> None:
    """A rehearsal must not prune the daemon either.

    Not reachable from the end-to-end tests: they all pass -SkipDocker, since
    a test that really pruned the developer's Docker Desktop would be worse
    than the bug.
    """
    text = GC_WIN.read_text(encoding="utf-8")
    assert "DRY-RUN: would prune docker" in text, (
        "-DryRun must report the docker prunes rather than executing them."
    )


def test_stale_version_pruning_requires_a_resolvable_symlink() -> None:
    """`bin.*`/`externals.*` are only leftovers when `bin` is a symlink to one
    of them. On a plain install they *are* the runner - deleting them bricks
    it."""
    text = GC_WIN.read_text(encoding="utf-8")
    assert "LinkType" in text or "ResolvedTarget" in text, (
        "runner_gc_win.ps1 must resolve the bin/externals symlink before "
        "pruning versioned directories, and skip the prune when it cannot."
    )


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
    subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-Command",
            f"(Get-Item -LiteralPath '{path}' -Force).LastWriteTime = "
            f"(Get-Date).AddHours(-{hours})",
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
    overrides.update(env or {})
    return subprocess.run(
        [
            PWSH,
            "-NoProfile",
            "-File",
            str(GC_WIN),
            "-RunnerRoot",
            str(root),
            "-SkipDocker",
            "-Force",
            *extra,
        ],
        capture_output=True,
        text=True,
        env=overrides,
    )


pwshonly = pytest.mark.skipif(PWSH is None, reason="needs pwsh to run the GC")


@pwshonly
def test_cold_workspace_goes_warm_workspace_stays(tmp_path: Path) -> None:
    root = _make_runner_root(tmp_path)
    cold = _workspace(root, "manga-uri", age_hours=5)
    warm = _workspace(root, "auto-amv", age_hours=0.5)

    proc = _run_gc(root)

    assert proc.returncode == 0, proc.stderr
    assert not cold.exists(), "a workspace idle for 5 h must be collected"
    assert warm.exists(), "a workspace used 30 min ago must survive"


@pwshonly
def test_marker_outranks_a_stale_directory_timestamp(tmp_path: Path) -> None:
    """The regression the marker exists for: old directory, fresh marker."""
    root = _make_runner_root(tmp_path)
    ws = _workspace(root, "manga-uri", age_hours=800)
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
    live = _workspace(root, "manga-uri", age_hours=99)

    proc = _run_gc(root, env={"RUNNER_WORKSPACE": str(live / "manga-uri")})

    assert proc.returncode == 0, proc.stderr
    assert live.exists(), (
        "RUNNER_WORKSPACE points at the job the runner is finishing; it must "
        "be excluded no matter how the ageing lands."
    )


@pwshonly
def test_hook_stamps_the_marker_for_the_finishing_job(tmp_path: Path) -> None:
    """Without this the workspace of the *last* job ages from its checkout."""
    root = _make_runner_root(tmp_path)
    ws = _workspace(root, "manga-uri", age_hours=99, marker=False)

    proc = _run_gc(root, env={"GITHUB_REPOSITORY": "m4k3-co/manga-uri"})

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
    ws = _workspace(root, "manga-uri", age_hours=9)
    locked = ws / "manga-uri" / ".git" / "objects"
    locked.mkdir(parents=True)
    blob = locked / "cafebabe"
    blob.write_bytes(b"blob")
    os.chmod(blob, stat.S_IREAD)

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
    cold = _workspace(root, "manga-uri", age_hours=5)

    proc = _run_gc(root, "-DryRun")

    assert proc.returncode == 0, proc.stderr
    assert cold.exists(), "-DryRun must not delete anything"
    assert "manga-uri" in proc.stdout, (
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
    ws = _workspace(root, "manga-uri", age_hours=9)
    outside = tmp_path / "precious"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(ws / "manga-uri" / "linked"), str(outside)],
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


def test_gc_discards_freed_blocks_back_to_the_host() -> None:
    """Pruning inside the distro is invisible to C: until something discards.

    The vhdx keeps freed ext4 blocks claimed from Windows, which is why a large
    prune can leave C: unchanged and make the whole GC look like a no-op. On a
    sparse vhdx `fstrim` punches the holes straight back out with no downtime:
    43.5 GB returned to C: in a single call on the runner host.
    """
    text = GC.read_text(encoding="utf-8")
    assert re.search(r"^\s*[^#]*\bfstrim\b", text, re.M), (
        "runner_gc.sh must fstrim after pruning, or the space it frees never "
        "reaches the Windows host."
    )
    # The script runs under `set -e`, so an unguarded fstrim would abort the
    # sweep on any guest whose filesystem cannot discard.
    assert re.search(r"if\s+fstrim\b|fstrim[^\n]*\|\|", text), (
        "the fstrim call must be guarded so a guest without discard support "
        "degrades quietly instead of aborting the sweep."
    )


def test_windows_dispatch_falls_back_to_the_checkout() -> None:
    """A first `just runner-gc` must collect, not exit 127.

    Hard-coding the installed payload made the WSL leg die with `No such file
    or directory` whenever runner-gc-install had not run yet, which reads as a
    broken GC rather than an uninstalled one.
    """
    text = GC.read_text(encoding="utf-8")
    assert re.search(r"if \[ -x /usr/local/bin/runner-gc\.sh \]", text), (
        "runner_gc.sh must test for the installed payload and fall back to "
        "this checkout instead of exec'ing a path that may not exist."
    )


def test_disk_gc_reaches_the_wsl_runner_user() -> None:
    """The biggest caches on the box live in the WSL user's HOME, not Windows.

    `~/.cache/uv` alone measured 44 GB there against ~2.5 GB for the entire
    Windows profile, and `just disk-gc` previously had no route into the distro.
    """
    text = DISK.read_text(encoding="utf-8")
    assert "wsl.exe" in text, "disk_gc.sh must collect the WSL leg too."
    # `-u root` would collect root's empty HOME and silently reclaim nothing.
    assert not re.search(r"wsl\.exe[^\n]*-u root", text), (
        "the disk-gc WSL leg must run as the distro user; the caches live in "
        "that user's HOME."
    )
    assert "DISK_GC_NO_WSL" in text, "the WSL leg must be opt-out-able."


def test_disk_gc_uses_go_clean_for_the_module_cache() -> None:
    """Go's module cache is deliberately read-only, so a plain delete fails."""
    text = DISK.read_text(encoding="utf-8")
    assert "go clean -modcache" in text, (
        "disk_gc.sh must use `go clean -modcache`; a recursive delete leaves "
        "the 11 GB module cache behind because its files are read-only."
    )


def test_disk_gc_finds_mise_managed_tools() -> None:
    """Non-interactive shells have no mise shims on PATH.

    The WSL leg is invoked non-interactively, where `uv` and `go` resolve to
    "command not found" and the two largest caches survive untouched.
    """
    text = DISK.read_text(encoding="utf-8")
    assert "mise/shims" in text, (
        "disk_gc.sh must put the mise shims on PATH before invoking uv/go."
    )


def test_disk_gc_keeps_huggingface_opt_in() -> None:
    """Models are not wheels: one directory measured 77 GB to re-download."""
    text = DISK.read_text(encoding="utf-8")
    assert "DISK_GC_HUGGINGFACE" in text, (
        "the huggingface cache must be opt-in, never swept by default."
    )
    unconditional = [
        line
        for line in text.splitlines()
        if "huggingface" in line
        and "DISK_GC_HUGGINGFACE" not in line
        and not line.strip().startswith("#")
    ]
    assert not unconditional, (
        f"huggingface must not be collected unconditionally: {unconditional}"
    )


def test_compaction_measures_allocated_not_logical_size() -> None:
    """Logical size is a high-water mark and overstates the slack.

    A sparse vhdx read 227 GB logical against 174 GB actually on disk, so
    `logical - used` reported 130 GB of "reclaimable" space where only 33 GB
    was real — the rest had already been returned to Windows on its own.
    """
    text = COMPACT.read_text(encoding="utf-8")
    assert "du -B1" in text, (
        "wsl_compact.sh must measure the allocated size (du -B1); stat -c %s "
        "reports the logical high-water mark."
    )
    assert "fsutil sparse queryflag" in text, (
        "wsl_compact.sh must report whether the vhdx is sparse: it decides "
        "whether compaction is needed at all."
    )


# --- The hook that never ran ------------------------------------------------


def test_hook_payload_carries_a_script_extension() -> None:
    """The runner validates the hook path and rejects a bare name.

    An extensionless `/usr/local/bin/runner-gc` sat in `.env` looking correct
    while the runner threw `ArgumentException: ... is not a valid path to a
    script` on all 877 jobs. The extension is load-bearing.
    """
    text = INSTALL.read_text(encoding="utf-8")
    assert re.search(r'_dest="/usr/local/bin/runner-gc\.sh"', text), (
        "the payload must be installed under a .sh name or the runner refuses "
        "to execute the job-completed hook."
    )


def test_windows_hook_is_a_path_not_a_command_line() -> None:
    """Same validation on Windows: arguments make it not a path."""
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert re.search(r"^\s*\$hookCmd\s*=\s*\$payload\s*$", text, re.M), (
        "the Windows hook must be the bare .ps1 path; a `powershell.exe "
        "-File <script>` wrapper fails the runner's path validation."
    )


def test_job_safety_ignores_our_own_worker() -> None:
    """The hook runs *inside* Runner.Worker, so it is always its own ancestor.

    Counting that worker made the hook — the brake that fires at the ideal
    moment — skip unconditionally. Only a worker outside our ancestry belongs
    to a concurrent job.
    """
    sh = GC.read_text(encoding="utf-8")
    assert "_ancestor_pids" in sh and "_foreign_worker" in sh, (
        "runner_gc.sh must compare live workers against its own ancestry."
    )
    # A bare pgrep as the decision would reintroduce the always-skip bug.
    bad = [
        line
        for line in sh.splitlines()
        if re.search(r"^\s*if\s+.*pgrep -x Runner\.Worker", line)
    ]
    assert not bad, f"job-safety must go through _foreign_worker: {bad}"

    ps = GC_WIN.read_text(encoding="utf-8")
    assert "Get-AncestorProcessId" in ps and "-notcontains" in ps, (
        "runner_gc_win.ps1 must exclude its own ancestry the same way."
    )


def test_status_validates_the_hook_rather_than_its_presence() -> None:
    """`just status` exists because 'installed' and 'working' differed.

    The wiring looked perfect in `.env` for 877 jobs; only the job's own log
    showed the rejection. Status has to check the extension and surface those
    rejections, or it would have reported green throughout.
    """
    status = SCRIPTS / "gc_status.sh"
    assert status.is_file(), "scripts/gc_status.sh must exist"
    text = status.read_text(encoding="utf-8")
    assert "is not a valid path to a script" in text, (
        "status must surface the runner's own rejection message from the job "
        "logs; it is the only place the failure is recorded."
    )
    assert ".ps1" in text and ".sh" in text, (
        "status must validate the hook extension the runner requires."
    )
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    assert re.search(r"^status:\n\s+bash scripts/gc_status\.sh", justfile, re.M), (
        "`just status` must be wired to scripts/gc_status.sh."
    )


def test_windows_installer_survives_without_elevation() -> None:
    """S4U is better but needs admin; staying installable matters more."""
    text = INSTALL_WIN.read_text(encoding="utf-8")
    assert "S4U" in text, "prefer a principal that fires while logged off"
    assert re.search(r"catch\s*\{", text), (
        "registering an S4U principal needs elevation, so the installer must "
        "fall back instead of failing for an unelevated user."
    )
