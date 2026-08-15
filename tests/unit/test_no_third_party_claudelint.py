"""The third-party claudelint (npm `claude-code-lint`) is retired (ADR 0041).

The operator withdrew trust in it: a single-maintainer, non-Anthropic tool
that parses every distributed Claude artifact, running both locally and in
CI. Validation now rests on the OFFICIAL `claude plugin validate --strict`
(claude CLI) plus in-repo stdlib checks. These tests keep the retired tool
from creeping back into any gate.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_justfile_has_no_claudelint() -> None:
    text = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "claude-code-lint" not in text, (
        "justfile invokes the retired third-party claude-code-lint; "
        "only the official `claude plugin validate` gate remains (ADR 0041)."
    )


def test_workflow_runs_official_validate_not_claudelint() -> None:
    wf = (ROOT / ".github" / "workflows" / "claude-lint.yaml").read_text(
        encoding="utf-8"
    )
    assert "claude-code-lint" not in wf, (
        "CI workflow still runs the retired third-party claudelint."
    )
    assert "plugin validate" in wf, (
        "CI must run the OFFICIAL `claude plugin validate --strict` — "
        "before ADR 0041 the official half never ran in CI at all."
    )
    assert "@anthropic-ai/claude-code@" in wf, (
        "the official CLI must be invoked via a version-pinned bunx run "
        "(reproducible; nothing global on the runner)."
    )


def test_effective_settings_checker_is_stdlib_only() -> None:
    src = (ROOT / "scripts" / "check_effective_settings.py").read_text(encoding="utf-8")
    assert "claude-code-lint" not in src and "bunx" not in src, (
        "check_effective_settings.py must validate composed settings with "
        "in-repo stdlib checks, not by shelling out to the retired "
        "third-party claudelint."
    )
