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
    (listed,) = re.findall(r"args\+=\(([^)]*)\)", _recipe("ci-audit"))
    return set(listed.split())


def test_every_listed_workflow_exists() -> None:
    missing = {name for name in _default_workflows() if not (WORKFLOWS / name).exists()}
    assert not missing


def test_every_checking_workflow_is_listed() -> None:
    present = {path.name for path in WORKFLOWS.glob("*.yaml")} - NOT_AUDITED
    assert present == _default_workflows()


def test_arguments_keep_their_quoting() -> None:
    # --recipe-step "just check (no container)=Run just check" holds spaces;
    # just's {{ args }} would split it, positional arguments keep it whole.
    start = JUSTFILE.index("\nci-audit *args:\n")
    head = JUSTFILE[JUSTFILE.rindex("\n\n", 0, start) : start]
    assert "[positional-arguments]" in head
    assert 'args=("$@")' in _recipe("ci-audit")
