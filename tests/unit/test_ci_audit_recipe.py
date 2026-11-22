"""`just ci-audit` reads every workflow that checks code, and nothing else.

Its default list named `small-checks.yaml` before that file existed, and missed
`check.yaml` when it was added (ADR-0089): the audit then failed, or measured
less than CI runs. This keeps the list and the workflow folder equal.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")
WORKFLOWS = ROOT / ".github/workflows"
# pages.yaml publishes the site from main; it checks nothing.
NOT_AUDITED = {"pages.yaml"}


def _recipe(name: str) -> str:
    match = re.search(rf"(?ms)^{name} [^\n]*:\n(.*?)(?=^\S|\Z)", JUSTFILE)
    assert match, f"no recipe {name}"
    return match.group(1)


def _default_workflows() -> set[str]:
    # the one args+=(...) line that lists workflow files
    (listed,) = [
        group
        for group in re.findall(r"args\+=\(([^)]*)\)", _recipe("ci-audit"))
        if ".yaml" in group
    ]
    return set(listed.split())


def test_every_listed_workflow_exists() -> None:
    missing = {name for name in _default_workflows() if not (WORKFLOWS / name).exists()}
    assert not missing


def test_every_checking_workflow_is_listed() -> None:
    present = {path.name for path in WORKFLOWS.glob("*.yaml")} - NOT_AUDITED
    assert present == _default_workflows()


def test_every_named_recipe_step_is_a_step_of_that_job() -> None:
    # A renamed step would show up only as "named step missing" in a report;
    # this turns it red at once.
    named = re.findall(r'--recipe-step "([^"=]+)=([^"]+)"', _recipe("ci-audit"))
    assert named, "the recipe names no recipe step"
    workflows = [p.read_text(encoding="utf-8") for p in WORKFLOWS.glob("*.yaml")]
    for job, step in named:
        holder = [w for w in workflows if f"\n    name: {job}\n" in w]
        assert len(holder) == 1, f"no single workflow has the job {job!r}"
        body = holder[0].split(f"\n    name: {job}\n", 1)[1]
        body = re.split(r"\n  [a-z0-9-]+:\n", body, maxsplit=1)[0]
        assert f"\n      - name: {step}\n" in body, f"{job!r} has no step {step!r}"


def _run_recipe(tmp_path: Path, *args: str) -> list[str]:
    """The argv the recipe hands to `go run . jobs`, with stub gh and mise."""
    just, bash = shutil.which("just"), shutil.which("bash")
    if just is None or bash is None or sys.platform == "win32":
        pytest.skip("needs just and a Unix bash")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stubs = {
        "gh": "echo o/r\n",
        # one argument per line, so the test sees the argv as given
        "mise": 'printf "%s\\n" "$@"\n',
    }
    for name, body in stubs.items():
        stub = bin_dir / name
        stub.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8", newline="\n")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    result = subprocess.run(
        [just, "--justfile", str(ROOT / "justfile"), "ci-audit", *args],
        cwd=ROOT,
        env={**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    lines = result.stdout.splitlines()
    return lines[lines.index("jobs") + 1 :]


@pytest.mark.parametrize(
    "args",
    [(), ("shellcheck.yaml",), ("--runs", "5", "unit-test.yaml")],
)
def test_every_flag_comes_before_the_first_workflow(tmp_path: Path, args) -> None:
    # Go's flag package stops at the first argument that is not a flag: a
    # default flag after a workflow name was read as a workflow (HTTP 404).
    argv = _run_recipe(tmp_path, *args)
    first_workflow = next(i for i, a in enumerate(argv) if a.endswith(".yaml"))
    assert all(not a.startswith("--") for a in argv[first_workflow:]), argv
    assert "--recipe-step" in argv[:first_workflow]


def test_arguments_keep_their_quoting() -> None:
    # --recipe-step "just check (no container)=Run just check" holds spaces;
    # just's {{ args }} would split it, positional arguments keep it whole.
    start = JUSTFILE.index("\nci-audit *args:\n")
    head = JUSTFILE[JUSTFILE.rindex("\n\n", 0, start) : start]
    assert "[positional-arguments]" in head
    assert 'args=("$@")' in _recipe("ci-audit")
