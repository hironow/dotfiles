"""`just status` must also report what GITHUB thinks of each runner.

Found live (2026-08-20, twice in one day): the local probes were ALL GREEN
while GitHub showed the runner offline —

- a hung pwsh step ignored a job cancellation, so the broker session died
  with the Listener process still up ("zombie": offline + busy=true), and
- a runner whose server-side registration had been auto-purged started,
  connected, was rejected, and only the GitHub UI knew.

Both times a human noticed via the browser, not via `just status`. The
GitHub-truth section (scripts/gc_github_status.sh, fed by gc_status.sh with
`name|url|local_up|restart_hint` lines) closes that gap. Its contract:

- **Never hard-fails.** status is a read-only report; a missing gh, a 403
  (admin:org scope), or a broken response degrade to WARN, exit 0.
- **Exact-name matching.** Real agent names carry spaces ('trade win');
  substring matching would cross-match siblings.
- **Endpoints without a leading slash.** Git Bash rewrites `/orgs/...` into
  `C:/Program Files/Git/orgs/...` before gh sees it (MSYS path mangling).
- **The zombie runbook must survive its own advice**: `just
  runner-svc-restart` is REFUSED while Runner.Worker lives (the guard that
  protects in-flight jobs), which is exactly the zombie state — so the
  runbook must name the wait-first path and the -Force escape hatch.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "scripts" / "gc_status.sh"
GITHUB = ROOT / "scripts" / "gc_github_status.sh"
JUSTFILE = ROOT / "justfile"

winskip = pytest.mark.skipif(
    sys.platform == "win32",
    reason=(
        "native Windows: bare `bash` resolves to System32 (WSL) bash, which "
        "cannot read the drive-lettered script path; runs on Linux/WSL/CI "
        "(.github/workflows/unit-test.yaml is ubuntu, so this DOES run in CI)"
    ),
)


# --- static wiring ------------------------------------------------------------


def test_status_feeds_the_github_section() -> None:
    text = STATUS.read_text(encoding="utf-8")
    assert "gc_github_status.sh" in text, (
        "gc_status.sh must render the GitHub-truth section after the legs."
    )


def test_github_section_builds_slashless_endpoints_for_both_scopes() -> None:
    text = GITHUB.read_text(encoding="utf-8")
    assert "orgs/" in text and "repos/" in text, (
        "gitHubUrl may be org-level (https://github.com/<org>) or repo-level "
        "(<owner>/<repo>); both endpoint shapes must be constructed."
    )
    assert 'gh api "/' not in text and "gh api '/" not in text, (
        "a leading-slash endpoint gets MSYS-mangled into a Git-install path "
        "on Git Bash; build endpoints without it."
    )
    assert "--paginate" in text, (
        "an org can have more runners than one page; unpaginated listings "
        "silently miss the tail."
    )
    assert "--jq" in text, (
        "use gh's built-in jq (external jq is not guaranteed); --paginate "
        "without --jq concatenates page JSONs into a non-JSON stream."
    )


def test_github_section_degrades_instead_of_failing() -> None:
    text = GITHUB.read_text(encoding="utf-8")
    assert "gh not installed" in text, (
        "a host without gh must get a WARN, not a broken status."
    )
    assert "admin:org" in text, (
        "a 403 must point at `gh auth refresh -h github.com -s admin:org` — "
        "the exact fix used live."
    )


def test_github_section_names_the_registration_purge_mode() -> None:
    """Yesterday's failure mode: the runner is absent from the listing
    because GitHub auto-purged a long-offline registration."""
    text = GITHUB.read_text(encoding="utf-8")
    assert "registration" in text, (
        "an absent name must be reported as a server-side registration "
        "purge with the re-register runbook, not as a generic offline."
    )


def test_zombie_runbook_survives_its_own_advice() -> None:
    github = GITHUB.read_text(encoding="utf-8")
    assert "5 min" in github, (
        "the runbook must say to wait for the ~5-minute job-cancellation "
        "self-heal first — that is how the live incident resolved."
    )
    status = STATUS.read_text(encoding="utf-8")
    assert "runner-svc-restart" in status and "-Force" in status, (
        "the Windows restart hint must name the -Force escape hatch: the "
        "plain restart is REFUSED while Runner.Worker lives, which is "
        "exactly the zombie state."
    )
    assert "systemctl restart" in status and "actions.runner.%s.%s.service" in status, (
        "the WSL restart hint must carry a CONCRETE unit name (built from "
        "the .runner identity) — a bare 'actions.runner.*' glob matches "
        "zero loaded units and silently succeeds (the trap gc_status.sh "
        "itself documents)."
    )


def test_justfile_offers_the_force_restart() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    assert "runner-svc-restart-force" in text, (
        "the -Force path must be a just recipe, not folklore (AGENTS.md: "
        "commands live in the justfile)."
    )


# --- behavioral: run the section against a stub gh ----------------------------

STUB_GH = """#!/usr/bin/env bash
if [ -n "${GH_STUB_EXIT:-}" ]; then exit "$GH_STUB_EXIT"; fi
printf '%s\\n' "$GH_STUB_TSV"
"""


def _run_section(
    tmp_path: Path,
    stdin: str,
    *,
    tsv: str = "",
    gh_exit: str = "",
    with_gh: bool = True,
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if with_gh:
        stub_dir = tmp_path / "bin"
        stub_dir.mkdir(exist_ok=True)
        gh = stub_dir / "gh"
        gh.write_text(STUB_GH, encoding="ascii")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)
        env["PATH"] = f"{stub_dir}{os.pathsep}" + env.get("PATH", "")
    else:
        # PATH games are unreliable (a real gh may live in /usr/bin, which
        # the script's own tools need) — use the explicit seam instead.
        env["GC_GITHUB_GH"] = "gh-definitely-absent"
    env["GH_STUB_TSV"] = tsv
    if gh_exit:
        env["GH_STUB_EXIT"] = gh_exit
    else:
        env.pop("GH_STUB_EXIT", None)
    return subprocess.run(
        ["bash", str(GITHUB)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
    )


LINE = "trade win|https://github.com/m4k3-co|{up}|just runner-svc-restart\n"


@winskip
def test_online_runner_reads_ok(tmp_path: Path) -> None:
    proc = _run_section(tmp_path, LINE.format(up="1"), tsv="trade win\tonline\tfalse")
    assert proc.returncode == 0, proc.stderr
    assert "online" in proc.stdout and "OK" in proc.stdout


@winskip
def test_offline_with_local_up_is_the_zombie_fail(tmp_path: Path) -> None:
    proc = _run_section(tmp_path, LINE.format(up="1"), tsv="trade win\toffline\ttrue")
    assert proc.returncode == 0, proc.stderr
    assert "FAIL" in proc.stdout
    assert "5 min" in proc.stdout, "the wait-first runbook must be printed."
    assert "runner-svc-restart" in proc.stdout, (
        "the caller-supplied restart hint must be printed."
    )


@winskip
def test_offline_with_local_down_stays_informational(tmp_path: Path) -> None:
    """The leg above already carries the FAIL + fix; a second alarm would
    double-count one problem."""
    proc = _run_section(tmp_path, LINE.format(up="0"), tsv="trade win\toffline\tfalse")
    assert proc.returncode == 0, proc.stderr
    assert "FAIL" not in proc.stdout


@winskip
def test_absent_name_is_the_registration_purge_fail(tmp_path: Path) -> None:
    proc = _run_section(tmp_path, LINE.format(up="1"), tsv="gpu-win\tonline\tfalse")
    assert proc.returncode == 0, proc.stderr
    assert "FAIL" in proc.stdout and "registration" in proc.stdout


@winskip
def test_sibling_name_does_not_cross_match(tmp_path: Path) -> None:
    """'trade win' vs 'trade win 2': substring/prefix matching would read
    the sibling's state."""
    proc = _run_section(
        tmp_path,
        LINE.format(up="1"),
        tsv="trade win 2\tonline\tfalse",
    )
    assert proc.returncode == 0, proc.stderr
    assert "registration" in proc.stdout, (
        "only an EXACT name match may count; the sibling must not satisfy it."
    )


@winskip
def test_api_error_degrades_to_warn(tmp_path: Path) -> None:
    proc = _run_section(tmp_path, LINE.format(up="1"), gh_exit="1")
    assert proc.returncode == 0, (
        "an API error must never break `just status`: " + proc.stderr
    )
    assert "WARN" in proc.stdout and "admin:org" in proc.stdout


@winskip
def test_missing_gh_degrades_to_warn(tmp_path: Path) -> None:
    proc = _run_section(tmp_path, LINE.format(up="1"), with_gh=False)
    assert proc.returncode == 0, proc.stderr
    assert "WARN" in proc.stdout and "gh not installed" in proc.stdout
