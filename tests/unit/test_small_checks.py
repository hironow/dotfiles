"""The small checks run in one job and report every failure (ADR-0089).

docs/agents/ci-speed.md ("Shape") folds the small checks into one job whose
recipe runs every checker to the end and lists every failure, instead of
stopping at the first. `just small-checks` runs shellcheck, actionlint, and the
semgrep rules' own tests (which ran on pull requests only inside the dev
container job before ADR-0089).
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import _workflow
import pytest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github/workflows"
SMALL = WORKFLOWS / "small-checks.yaml"
CHECKERS = ("shellcheck", "actionlint", "semgrep-test")


def _stub(bin_dir: Path, name: str, exit_code: int) -> None:
    path = bin_dir / name
    path.write_text(
        f"#!/usr/bin/env bash\necho 'stub {name}' \"$@\"\nexit {exit_code}\n",
        encoding="utf-8",
        newline="\n",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_small_checks(tmp_path: Path, failing: set[str]) -> subprocess.CompletedProcess:
    just = shutil.which("just")
    bash = shutil.which("bash")
    if just is None or bash is None or sys.platform == "win32":
        pytest.skip("needs just and a Unix bash")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # The recipe calls `just semgrep-test`; a stub `just` on PATH stands in for
    # that inner call, while the outer run uses the real just.
    _stub(bin_dir, "shellcheck", 1 if "shellcheck" in failing else 0)
    _stub(bin_dir, "actionlint", 1 if "actionlint" in failing else 0)
    _stub(bin_dir, "just", 1 if "semgrep-test" in failing else 0)
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    return subprocess.run(
        [just, "--justfile", str(ROOT / "justfile"), "small-checks"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def test_every_checker_runs_and_every_failure_is_listed(tmp_path: Path) -> None:
    result = _run_small_checks(tmp_path, set(CHECKERS))
    assert result.returncode == 1, result.stdout + result.stderr
    for name in CHECKERS:
        # each checker ran, though the ones before it failed
        assert f"stub {'just' if name == 'semgrep-test' else name}" in result.stdout
    assert "small checks failed: shellcheck actionlint semgrep-test" in result.stderr


def test_one_failure_fails_the_recipe(tmp_path: Path) -> None:
    result = _run_small_checks(tmp_path, {"actionlint"})
    assert result.returncode == 1
    assert "small checks failed: actionlint" in result.stderr


def test_the_recipe_passes_when_every_checker_passes(tmp_path: Path) -> None:
    result = _run_small_checks(tmp_path, set())
    assert result.returncode == 0, result.stdout + result.stderr
    assert "stub just semgrep-test" in result.stdout


def test_the_workflow_runs_the_recipe_with_a_checked_actionlint() -> None:
    body = SMALL.read_text(encoding="utf-8")
    (job,) = _workflow.jobs(body).values()
    assert (
        "    if: github.event_name != 'pull_request' || "
        "github.event.pull_request.draft == false\n"
    ) in job
    assert "ready_for_review" in body
    assert re.search(r"\n    timeout-minutes: \d+\n", job)
    for action in re.findall(r"uses:\s+(\S+)", job):
        assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action
    version = re.search(r"ACTIONLINT_VERSION: (\d+\.\d+\.\d+)\n", job)
    digest = re.search(r"ACTIONLINT_SHA256: ([0-9a-f]{64})\n", job)
    assert version and digest
    assert "sha256sum -c -" in job
    runs = [c for step in _workflow.steps(job) for c in _workflow.run_commands(step)]
    assert runs[-1] == "just small-checks"


def test_the_old_shellcheck_workflow_is_gone() -> None:
    # Its one job is part of small-checks now; two jobs would run shellcheck
    # twice on every pull request.
    assert not (WORKFLOWS / "shellcheck.yaml").exists()
