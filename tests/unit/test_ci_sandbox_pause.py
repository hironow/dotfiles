"""Sandbox CI runs on ready PRs and main; standalone Go checks remain.

Sandbox uses the same draft guard as the other CI jobs, without an
additional repository-variable pause. Standalone Go jobs retain fast,
independent feedback through the same recipe as a local run.
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


def test_the_sandbox_job_uses_only_the_draft_guard() -> None:
    assert _condition(_job(SANDBOX, "test")) == DRAFT_GUARD
    assert "RUN_SANDBOX_TESTS" not in SANDBOX


def test_the_sandbox_workflow_keeps_main_and_ready_pr_triggers() -> None:
    assert re.search(r"\n  push:\n    branches: \[main\]\n", SANDBOX)
    assert re.search(r"\n  pull_request:\n    branches: \[main\]\n", SANDBOX)
    assert "types: [opened, synchronize, reopened, ready_for_review]" in SANDBOX


def test_the_sandbox_job_runs_the_disposable_container_suite() -> None:
    job = _job(SANDBOX, "test")
    assert re.search(r"\n    runs-on: ubuntu-latest\n", job)
    assert re.search(r"uses: devcontainers/ci@[0-9a-f]{40}", job)
    assert re.search(r"\n          runCmd: just test\n", job)
    assert "DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT=1" in job


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
