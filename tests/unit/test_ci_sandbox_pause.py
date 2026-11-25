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

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# The directories a pull request may change without running the sandbox.


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
