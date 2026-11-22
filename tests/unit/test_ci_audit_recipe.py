"""`just ci-audit` reads every workflow that checks code, and nothing else.

Its default list named `small-checks.yaml` before that file existed, and missed
`check.yaml` when it was added (ADR-0089): the audit then failed, or measured
less than CI runs. This keeps the list and the workflow folder equal.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def test_arguments_keep_their_quoting() -> None:
    # --recipe-step "just check (no container)=Run just check" holds spaces;
    # just's {{ args }} would split it, positional arguments keep it whole.
    start = JUSTFILE.index("\nci-audit *args:\n")
    head = JUSTFILE[JUSTFILE.rindex("\n\n", 0, start) : start]
    assert "[positional-arguments]" in head
    assert 'args=("$@")' in _recipe("ci-audit")
