"""install.sh must self-provision `mise` (and its toolchain) on a bare
Linux/WSL host — not merely assume the devcontainer feature already did.

Why this exists
---------------
install.sh's Linux path historically skipped almost everything with
"covered by apt + dev container feature". That is true inside a Coder /
devcontainer image, but a plain WSL Ubuntu box running `curl … | bash`
gets no mise, hence no uv/node/prek/… and every downstream step self-skips.

Two new steps close that, without disturbing the container flow (both are
`command -v` guarded — a devcontainer with mise already present is a no-op):

- `step_mise_bootstrap`: if mise is missing, download the pinned mise
  release binary to ~/.local/bin, SHA256-verified (same posture as the
  existing `step_just_bootstrap`; no `curl | bash`, per the repo guardrail).
- `step_mise_install`: `mise trust && mise install` to materialize the
  mise.toml toolset. Gated by INSTALL_SKIP_ADD_UPDATE so the Docker
  install-verification (which sets it) stays fast.

These are regex assertions on install.sh source, host-side (tests/unit/,
no Docker), so they run in `just ci` + unit-test.yaml.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL_SH = ROOT / "install.sh"


def _text() -> str:
    return INSTALL_SH.read_text()


def _drive_section(text: str) -> str:
    """install.sh body with the function definitions stripped, so a step
    name that appears there is an actual invocation, not a definition."""
    return re.sub(
        r"^[a-z_]+\s*\(\s*\)\s*\{[\s\S]*?^\}\s*$", "", text, flags=re.MULTILINE
    )


def test_defines_and_calls_mise_bootstrap() -> None:
    text = _text()
    assert re.search(r"^step_mise_bootstrap\s*\(\s*\)\s*\{", text, re.MULTILINE), (
        "install.sh must define step_mise_bootstrap to install mise on a bare host."
    )
    assert re.search(r"\bstep_mise_bootstrap\b", _drive_section(text)), (
        "step_mise_bootstrap is defined but never invoked in the drive section."
    )


def test_defines_and_calls_mise_install() -> None:
    text = _text()
    assert re.search(r"^step_mise_install\s*\(\s*\)\s*\{", text, re.MULTILINE), (
        "install.sh must define step_mise_install to materialize the mise.toml toolset."
    )
    assert re.search(r"\bstep_mise_install\b", _drive_section(text)), (
        "step_mise_install is defined but never invoked in the drive section."
    )


def test_mise_bootstrap_downloads_verified_binary() -> None:
    """Linux mise bootstrap: pinned GitHub release + SHA256 verify, no curl|bash."""
    m = re.search(
        r"^step_mise_bootstrap\s*\(\s*\)\s*\{([\s\S]*?)^\}", _text(), re.MULTILINE
    )
    assert m is not None, "step_mise_bootstrap definition not found"
    body = m.group(1)
    assert "github.com/jdx/mise" in body, "must download mise from its GitHub releases"
    assert "sha256sum -c" in body, "must SHA256-verify the mise download before use"
    assert "curl" in body, "linux path must fetch the release"
    assert "| bash" not in body and "| sh" not in body, (
        "no pipe-to-shell — the repo guardrail forbids `curl | bash`."
    )


def test_mise_install_is_skippable() -> None:
    """mise install (heavy: node + AI CLIs) must honour INSTALL_SKIP_ADD_UPDATE
    so the Docker install-verification stays fast (it sets that var)."""
    m = re.search(
        r"^step_mise_install\s*\(\s*\)\s*\{([\s\S]*?)^\}", _text(), re.MULTILINE
    )
    assert m is not None, "step_mise_install definition not found"
    assert "INSTALL_SKIP_ADD_UPDATE" in m.group(1), (
        "step_mise_install must be gated by INSTALL_SKIP_ADD_UPDATE."
    )
