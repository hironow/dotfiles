"""The exe stacks' tofu suites run in `just ci` and in the PR CI (inbox M57).

tofu/exe-platform and tofu/exe-cluster carry offline `tofu test` suites (mock
providers, and override_data for exe-platform's state), but only standalone
recipes ran them: `just ci` ran the Coder template's suite alone, and no
workflow ran either, so a change could break them with every gate green.
These tests pin both gates, and that the CI job needs nothing private: no
secret, no cloud login, no tfvars.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
JUSTFILE = REPO / "justfile"
WORKFLOW = REPO / ".github" / "workflows" / "iac-test.yaml"
STACKS = ("tofu/exe-platform", "tofu/exe-cluster")


def recipe_body(name: str) -> str:
    lines = JUSTFILE.read_text(encoding="utf-8").splitlines()
    header = re.compile(rf"^{re.escape(name)}(?:\s+[^:]*)?:(?!=)")
    start = next(i for i, line in enumerate(lines) if header.match(line))
    body = []
    for line in lines[start + 1 :]:
        if line and not line[0].isspace():
            break
        body.append(line)
    return "\n".join(body)


def workflow_job(name: str) -> str:
    m = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)",
        WORKFLOW.read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    assert m, f"{WORKFLOW.name} has no {name} job"
    return m.group(1)


def test_just_ci_runs_both_exe_suites() -> None:
    m = re.search(r"^ci:(.*)$", JUSTFILE.read_text(encoding="utf-8"), re.MULTILINE)
    assert m, "the justfile has no ci recipe"
    assert "test-iac-exe" in m.group(1).split()
    body = recipe_body("test-iac-exe")
    for stack in STACKS:
        assert stack in body
    assert "tofu init -backend=false" in body
    assert "tofu test" in body
    assert "TF_DATA_DIR" in body, (
        "local .terraform may retain an encrypted live backend"
    )
    assert "mktemp -d" in body and "trap" in body


def test_the_pr_ci_runs_both_exe_suites_offline() -> None:
    job = workflow_job("test-iac-exe")
    for stack in STACKS:
        assert stack in job
    assert "tofu init -backend=false" in job
    assert "tofu test" in job
    # Draft pull requests run no Actions (docs/agents/draft-ci.md).
    assert "github.event.pull_request.draft == false" in job
    # The suites need nothing private, and CI must never reach the project.
    assert "secrets." not in job
    assert "google-github-actions/auth" not in job
    assert ".tfvars" not in job
