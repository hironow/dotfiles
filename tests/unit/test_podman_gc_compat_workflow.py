"""Static contract of the Podman GC PowerShell compatibility workflow.

The 5.1 job runs the GC's JSON reader on Windows PowerShell 5.1, which runs
the GC in production. The 7.4 job only observes: it runs the PowerShell GC
replays on one pinned, hash-checked PowerShell 7.4 build.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/test-podman-gc-compat.yaml"
POWERSHELL_51 = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
TARBALL_URL = (
    "https://github.com/PowerShell/PowerShell/releases/download/v7.4.22/"
    "powershell-7.4.22-linux-x64.tar.gz"
)
# the official release's hashes.sha256 and its API asset digest agree on it
TARBALL_SHA256 = "9de443bef974f219c98a33b0f4096aace7f30b42188f37a1b14c5da7e82c8a6a"
JOBS = ("windows-powershell-51", "linux-powershell-74-observation")


def _jobs(body):
    """Each job's text, keyed by its id (two-space indent under `jobs:`)."""
    section = body.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  ([a-z0-9-]+):\n", section, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


def test_workflow_runs_like_the_others_and_pins_every_action():
    body = WORKFLOW.read_text(encoding="utf-8")
    for event in ("push:", "pull_request:"):
        assert f"  {event}\n    branches: [main]\n" in body
    assert "types: [opened, synchronize, reopened, ready_for_review]" in body
    for path in (
        "scripts/runner_gc_win.ps1",
        "tests/powershell/get_podman_json_51.ps1",
        "tests/unit/test_podman_gc_simulation.py",
        "tests/unit/_pwsh.py",
        ".github/workflows/test-podman-gc-compat.yaml",
    ):
        assert body.count(f"      - '{path}'\n") == 2, path
    assert "permissions:\n  contents: read\n" in body
    assert (
        "concurrency:\n  group: ${{ github.workflow }}-${{ github.ref }}\n"
        "  cancel-in-progress: true\n" in body
    )
    assert "continue-on-error" not in body
    actions = re.findall(r"uses:\s+(\S+)", body)
    assert actions
    for action in actions:
        assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action
    jobs = _jobs(body)
    assert tuple(jobs) == JOBS
    for job in jobs.values():
        assert (
            "    if: github.event_name != 'pull_request' || "
            "github.event.pull_request.draft == false\n" in job
        )
        assert "    timeout-minutes: 15\n" in job


def test_windows_powershell_51_runs_the_json_reader_test():
    job = _jobs(WORKFLOW.read_text(encoding="utf-8"))["windows-powershell-51"]
    assert "    runs-on: windows-latest\n" in job
    assert "shell: cmd" in job
    assert (
        f"run: {POWERSHELL_51} -NoProfile -NonInteractive -ExecutionPolicy Bypass"
        r" -File tests\powershell\get_podman_json_51.ps1" in job
    )
    assert (ROOT / "tests/powershell/get_podman_json_51.ps1").is_file()


def test_powershell_74_is_checked_before_it_runs_and_only_observed():
    job = _jobs(WORKFLOW.read_text(encoding="utf-8"))["linux-powershell-74-observation"]
    assert "    runs-on: ubuntu-24.04\n" in job
    assert f"PWSH_TARBALL_URL: {TARBALL_URL}\n" in job
    assert f"PWSH_TARBALL_SHA256: {TARBALL_SHA256}\n" in job
    # one download, the official asset only, into its own new directory
    assert job.count("curl ") == 1
    assert 'mkdir "$RUNNER_TEMP/powershell-download"' in job
    assert 'mkdir "$RUNNER_TEMP/powershell-7.4.22"' in job
    check = job.index("sha256sum --check --strict")
    extract = job.index("tar -xzf")
    assert check < extract
    assert '"7.4.22 Core"' in job
    assert job.index('"7.4.22 Core"') < job.index("uvx pytest")
    assert "PODMAN_GC_TEST_PWSH=$RUNNER_TEMP/powershell-7.4.22/pwsh" in job
    assert "PODMAN_GC_REQUIRE_PWSH: '1'" in job
    assert (
        "uvx pytest -q -rA --tb=line tests/unit/test_podman_gc_simulation.py"
        " -k powershell" in job
    )
    # each case's outcome reaches the job summary, also when the run fails
    summary = job.split("- name: Record each case's outcome", 1)[1]
    assert "if: always()" in summary
    assert "GITHUB_STEP_SUMMARY" in summary
    assert "shell: bash" in job
