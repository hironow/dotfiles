"""The dev container job runs like every other job; the Go tests keep a job
of their own.

The sandbox job ("Required disposable Podman devcontainer build/up/exec")
runs on main pushes, on demand, and on the ready pull requests that change
anything outside `paths-ignore` (ADR-0089): the directories whose every reader
is a leg of `just check`, which check.yaml runs on every pull request with the
image's pinned tools. The Go tests also
run in a job of their own, for fast, independent feedback, through the same
recipe as a local run.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SANDBOX = (ROOT / ".github/workflows/test-just.yaml").read_text(encoding="utf-8")
UNIT = (ROOT / ".github/workflows/unit-test.yaml").read_text(encoding="utf-8")
DRAFT_GUARD = (
    "github.event_name != 'pull_request' || github.event.pull_request.draft == false"
)


def _job(workflow: str, name: str) -> str:
    """A job's block: from its key to the next job's key, or the end."""
    start = workflow.index(f"\n  {name}:\n") + 1
    following = re.search(r"\n  [a-z][a-z0-9-]*:\n", workflow[start:])
    return (
        workflow[start : start + following.start()] if following else workflow[start:]
    )


def _condition(job: str) -> str:
    (condition,) = re.findall(r"\n    if: (.*)\n", job)
    return condition


# The directories a pull request may change without running the sandbox.
IGNORED = [
    "docs/**/*.md",
    "emulator/**",
    "telemetry/**",
    "site/**",
    "tofu/**",
    "tests/unit/**",
    "tests/durations/**",
]


def _paths_ignore() -> list[str]:
    on = SANDBOX.split("\njobs:\n", 1)[0]
    m = re.search(
        r"\n  pull_request:\n    branches: \[main\]\n"
        r"    types: \[opened, synchronize, reopened, ready_for_review\]\n"
        r"    paths-ignore:\n((?:      - '[^']+'(?:  *#[^\n]*)?\n)+)",
        on,
    )
    assert m, on
    return re.findall(r"- '([^']+)'", m.group(1))


def _glob(pattern: str) -> re.Pattern[str]:
    # GitHub's filter patterns: `**/` is any number of directories (none too),
    # `**` anything, `*` anything but `/`.
    regex = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            regex, i = regex + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            regex, i = regex + ".*", i + 2
        elif pattern[i] == "*":
            regex, i = regex + "[^/]*", i + 1
        else:
            regex, i = regex + re.escape(pattern[i]), i + 1
    return re.compile(regex + r"\Z")


def test_the_sandbox_job_runs_on_the_pull_requests_that_can_break_it() -> None:
    assert _paths_ignore() == IGNORED
    assert "\n  push:\n    branches: [main]\n" in SANDBOX
    assert "\n  workflow_dispatch:\n" in SANDBOX
    assert _condition(_job(SANDBOX, "test")) == DRAFT_GUARD
    # no repository variable switches it, anywhere in the workflow
    assert "RUN_SANDBOX_TESTS" not in SANDBOX


@pytest.mark.parametrize(
    ("path", "skipped"),
    [
        ("docs/runbook/windows-host.md", True),
        ("docs/README.md", True),
        # a config file under docs/ changes what markdownlint and git do there
        ("docs/.markdownlint.json", False),
        ("docs/.gitignore", False),
        ("docs/notes.txt", False),
        ("site/index.html", True),
        ("tests/unit/test_just_groups.py", True),
        ("tests/test_just_sandbox.py", False),
        ("justfile", False),
        ("README.md", False),
        (".github/workflows/test-just.yaml", False),
        ("tools/agent-hooks/go.mod", False),
    ],
)
def test_a_change_runs_the_sandbox_unless_every_file_is_ignored(
    path: str, skipped: bool
) -> None:
    assert any(_glob(p).match(path) for p in _paths_ignore()) is skipped


def test_every_ignored_directory_exists() -> None:
    # a renamed directory would quietly stop being ignored, or worse, a new
    # one with the old name would be ignored without review
    for pattern in _paths_ignore():
        assert (ROOT / pattern.split("/**", 1)[0]).is_dir(), pattern


CHECK_PARTS = {
    "check-except-go": "just check-except-go",
    "go-lint": "just go-lint",
    "go-test": "just go-test",
}


def test_just_check_runs_on_ready_pull_requests_without_a_container() -> None:
    check = (ROOT / ".github/workflows/check.yaml").read_text(encoding="utf-8")
    # `just check` is check-except-go, go-lint and go-test; CI runs the three
    # as parallel jobs, so the slowest sets the time, not their sum.
    for job_id, command in CHECK_PARTS.items():
        job = _job(check, job_id)
        assert _condition(job) == DRAFT_GUARD, job_id
        assert f"run: {command}\n" in job, job_id
        assert "ci-bootstrap.sh --tools-only" in job, job_id
        assert re.search(r"\n    timeout-minutes: \d+\n", job), job_id
    assert "podman" not in check.lower()
    # no repository variable switches it, anywhere in the workflow
    assert "RUN_SANDBOX_TESTS" not in SANDBOX


def test_the_check_gate_keeps_its_name_and_needs_every_part() -> None:
    check = (ROOT / ".github/workflows/check.yaml").read_text(encoding="utf-8")
    gate = _job(check, "check")
    assert "    name: just check (no container)\n" in gate
    assert f"    needs: [{', '.join(CHECK_PARTS)}]\n" in gate
    # a skipped or failed part must fail the gate, not skip it
    assert "always()" in _condition(gate)
    assert DRAFT_GUARD in _condition(gate)
    assert '"success success success"' in gate


def test_the_go_tests_run_in_a_job_of_their_own() -> None:
    job = _job(UNIT, "go")
    assert _condition(job) == DRAFT_GUARD
    assert re.search(r"uses: actions/setup-go@[0-9a-f]{40} # v\d+\.\d+\.\d+\n", job)
    assert "go-version-file: tools/agent-hooks/go.mod" in job
    # the jobs share nothing, and the runner image has no just
    assert "tool install rust-just" in job
    run = re.search(r"^ +run: just go-test go$", job, re.MULTILINE)
    assert run
    assert job.index("actions/setup-go@") < run.start()
    # setup-go writes GOTOOLCHAIN=local for the steps after it; a module that
    # asks for a newer Go gets it only with auto
    step = job[job.rindex("- name: Go tests") :]
    assert re.search(r"\n        env:\n          GOTOOLCHAIN: auto\n", step), step
    # a positional argument: "go=go" would run the shell's test, not Go
    assert "go=go" not in job


@pytest.mark.skipif(shutil.which("just") is None, reason="needs just")
def test_go_test_runs_the_go_it_is_given() -> None:
    def dry_run(*args: str) -> str:
        done = subprocess.run(
            ["just", "--dry-run", "go-test", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=True,
        )
        return done.stdout + done.stderr

    # CI: Go from setup-go, on PATH
    assert '(cd "$dir" && go test -short ./...)' in dry_run("go")
    # local, and `just check`: Go from mise, as before
    assert '(cd "$dir" && mise x -- go test -short ./...)' in dry_run()


def test_the_file_logs_macos_code_runs_on_macos() -> None:
    # The agent-hook file log removes macOS ACLs through raw system calls
    # (internal/logsink/acl_darwin.go), which build and run only on macOS;
    # the go job runs on Linux.
    job = _job(UNIT, "go-macos")
    assert _condition(job) == DRAFT_GUARD
    assert re.search(r"\n    runs-on: macos-latest\n", job)
    assert re.search(r"uses: actions/checkout@[0-9a-f]{40} # v\d+\.\d+\.\d+\n", job)
    assert re.search(r"uses: actions/setup-go@[0-9a-f]{40} # v\d+\.\d+\.\d+\n", job)
    assert "go-version-file: tools/agent-hooks/go.mod" in job
    assert "working-directory: tools/agent-hooks" in job
    vet = re.search(r"^ +go vet \./\.\.\.$", job, re.MULTILINE)
    test = re.search(r"^ +go test -count=1 \./internal/logsink/$", job, re.MULTILINE)
    assert vet
    assert test
    assert job.index("actions/setup-go@") < vet.start() < test.start()


CACHE_SHA = "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"  # actions/cache v6.1.0


@pytest.mark.parametrize(
    ("job_id", "inputs"),
    [
        ("go-lint", "'config/mise/image-tools.toml', '.golangci.yaml', '**/go.sum'"),
        ("go-test", "'config/mise/image-tools.toml', '**/go.sum'"),
    ],
)
def test_the_go_jobs_restore_mains_cache_and_only_main_saves_it(
    job_id: str, inputs: str
) -> None:
    # docs/agents/ci-speed.md: seed caches from the default branch; a pull
    # request restores them and writes none. Both caches are content-addressed,
    # so an older entry found by the restore key is safe.
    job = _job(
        (ROOT / ".github/workflows/check.yaml").read_text(encoding="utf-8"), job_id
    )
    restore = job.index(f"uses: actions/cache/restore@{CACHE_SHA} # v6.1.0")
    recipe = job.index(f"run: just {job_id}\n")
    save = job.index(f"uses: actions/cache/save@{CACHE_SHA} # v6.1.0")
    assert restore < recipe < save
    key = f"key: {job_id}-${{{{ runner.os }}}}-${{{{ runner.arch }}}}-${{{{ hashFiles({inputs}) }}}}"
    assert job.count(key) == 2, "restore and save use the same key"
    assert (
        f"restore-keys: {job_id}-${{{{ runner.os }}}}-${{{{ runner.arch }}}}-\n" in job
    )
    save_step = job[job.rindex("\n      - ", 0, save) :]
    assert "if: github.event_name == 'push'\n" in save_step
    assert 'echo "GOCACHE=$RUNNER_TEMP/go-build"' in job
    assert 'echo "GOMODCACHE=$RUNNER_TEMP/go-mod"' in job


def test_go_test_never_takes_a_test_result_from_the_cache() -> None:
    # Some tests read files outside their module, which Go's test cache does
    # not track: only compiled packages may come from the cache.
    job = _job(
        (ROOT / ".github/workflows/check.yaml").read_text(encoding="utf-8"), "go-test"
    )
    assert 'echo "GOFLAGS=-count=1"' in job


def test_the_real_go_tests_run_one_worker_per_core() -> None:
    # The doctor's real-hookrelease test and the installed-release tests build
    # agent-hook from scratch (each uses its own GOCACHE). Serially they were
    # most of the unit extras job; the installed-release tests share one
    # xdist_group, so loadgroup keeps them on one worker and the doctor test
    # runs beside them.
    job = _job(UNIT, "unit-extras")
    step = job[job.index("- name: Agent-hook's real Go tests") :]
    step = step[: step.index("\n      - ", 1)] if "\n      - " in step[1:] else step
    assert 'AGENT_HOOKS_STRICT_GO: "1"' in step
    assert (
        "uvx --with pytest-xdist==3.8.0 pytest -q -ra -n auto --dist loadgroup" in step
    )
