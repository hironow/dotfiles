"""`just exe-snapshot-gc`, the operator's way to run the orphan-snapshot GC (plan D11).

The recipe makes a one-off Job from the suspended exe-snapshot-gc CronJob
(tofu/exe-cluster/snapshot_gc.tf), prints the GC's report, and deletes the Job.
These tests read the recipe: what it may pass to the GC, and that nothing
holding the GC's identity outlives it (inbox M35).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JUSTFILE = REPO / "justfile"


def recipe(name: str) -> tuple[list[str], str]:
    """A recipe's attribute lines and its body, from the root justfile."""
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
    start = next(
        i for i, line in enumerate(lines) if re.match(rf"^{re.escape(name)}\b.*:", line)
    )
    attributes = []
    i = start - 1
    while i >= 0 and lines[i].startswith("["):
        attributes.append(lines[i])
        i -= 1
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return attributes, "\n".join(body)


def test_the_recipe_passes_each_word_to_the_gc_as_its_own_argument() -> None:
    # `-allow <prefix>` must reach the GC as two arguments, and a prefix is
    # never re-split: only "$@" keeps the words apart.
    attributes, body = recipe("exe-snapshot-gc")
    assert "[positional-arguments]" in attributes
    assert "{{" not in body
    # and jq takes -apply and -allow as arguments, not as its own options
    assert re.search(r"\$ARGS\.positional.*--args -- \"\$@\"", body, re.S)


def test_the_job_comes_from_the_suspended_template() -> None:
    _, body = recipe("exe-snapshot-gc")
    assert "--from=cronjob/exe-snapshot-gc" in body


def test_the_job_is_ours_not_the_cronjobs() -> None:
    # `create job --from` makes the CronJob the Job's owner, and with a
    # history limit of 0 its controller deleted the finished Job, and the
    # GC's report with it, before the recipe could read it (W2, 18:56 JST).
    _, body = recipe("exe-snapshot-gc")
    assert "del(.metadata.ownerReferences)" in body


def test_a_job_that_vanishes_ends_the_wait() -> None:
    # A Job that is gone will not finish: the wait fails at once rather than
    # polling NotFound for 15 minutes.
    _, body = recipe("exe-snapshot-gc")
    assert re.search(r"get job \"\$job\"[^\n]*\|\| \{", body)


def test_the_job_is_deleted_whatever_happens() -> None:
    _, body = recipe("exe-snapshot-gc")
    trap = re.search(r"^\s*trap '([^']*)' EXIT", body, re.M)
    assert trap, "no EXIT trap"
    assert "delete job" in trap.group(1)


def test_it_refuses_to_start_a_job_with_no_node_up() -> None:
    # A Job with no node waits Pending until its deadline, holding the GC's
    # identity for nothing; the recipe says to wake instead.
    _, body = recipe("exe-snapshot-gc")
    nodes = body.index("get nodes")
    create = body.index("create job")
    assert nodes < create
    assert "just exe-wake" in body


def test_the_recipe_never_removes_trees() -> None:
    _, body = recipe("exe-snapshot-gc")
    assert "rm -rf" not in body
