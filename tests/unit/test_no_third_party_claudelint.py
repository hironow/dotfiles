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


def test_effective_settings_checker_is_stdlib_only() -> None:
    src = (ROOT / "scripts" / "check_effective_settings.py").read_text(encoding="utf-8")
    assert "claude-code-lint" not in src and "bunx" not in src, (
        "check_effective_settings.py must validate composed settings with "
        "in-repo stdlib checks, not by shelling out to the retired "
        "third-party claudelint."
    )
