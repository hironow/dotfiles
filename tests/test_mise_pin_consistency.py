"""Build-time consistency check between mise.toml and the dev
container feature's hardcoded version constants (ADR 0006).

What this guards
----------------
ADR 0006 (Accepted 2026-05-02) makes `mise.toml` the single SoT
for tool versions. The dev container feature at
`.devcontainer/features/dotfiles-tools/install.sh` keeps its
SHA-256 + SLSA-attestation verified install path for `uv`, `just`,
and `sheldon` — preserving the build-time integrity guarantee
that mise alone does not provide. ADR 0006 decision detail 3
mandates: **versions in mise.toml and the feature-install
hardcoded constants MUST agree**, and the implementation PR adds
a build-time check that fails the image build on mismatch.

This is that check. Run as part of CI and as a pre-build sanity
test.

Why this exists
---------------
Without enforcement, the two SoTs drift:
- Mac operator runs `mise upgrade` and bumps mise.toml.
- Feature install.sh keeps its hardcoded UV_VERSION="0.11.8".
- Mac and workspace now have different versions. Reproducibility
  breaks silently.

The check below catches drift at PR review and at workspace
image build time.

Scope
-----
- `uv` ↔ `UV_VERSION` (feature install.sh hardcoded)
- `just` ↔ `JUST_VERSION` (feature install.sh hardcoded)

Out of scope (handled separately):
- `sheldon` (`SHELDON_VERSION`): not in mise.toml because sheldon
  is installed via brew on Mac and via the feature on Linux; mise
  does not manage it. The feature install.sh hardcoded value is
  the SoT for sheldon.
- `prek`, `vp`, `markdownlint-cli2`: npm-backed, installed via
  mise's npm backend at build time. No feature-install hardcoded
  constant exists for them; mise.toml is the SoT.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MISE_TOML = ROOT / "mise.toml"
FEATURE_INSTALL_SH = (
    ROOT / ".devcontainer" / "features" / "dotfiles-tools" / "install.sh"
)


@pytest.fixture(scope="module")
def mise_pins() -> dict[str, str]:
    """Parse the [tools] section of mise.toml into a dict."""
    text = MISE_TOML.read_text(encoding="utf-8")
    match = re.search(r"^\[tools\]\s*$(.*?)^\[", text, re.DOTALL | re.MULTILINE)
    if match is None:
        # No following section: read to EOF.
        match = re.search(r"^\[tools\]\s*$(.*)\Z", text, re.DOTALL | re.MULTILINE)
    assert match is not None, "could not find [tools] section in mise.toml"
    pins: dict[str, str] = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'([a-zA-Z0-9_-]+)\s*=\s*"([^"]+)"', line)
        if m:
            pins[m.group(1)] = m.group(2)
    return pins


@pytest.fixture(scope="module")
def feature_constants() -> dict[str, str]:
    """Parse the FOO_VERSION="..." constants out of feature
    install.sh."""
    text = FEATURE_INSTALL_SH.read_text(encoding="utf-8")
    return {
        m.group(1): m.group(2)
        for m in re.finditer(r'^([A-Z_]+)_VERSION="([^"]+)"', text, re.MULTILINE)
    }


# ---------- mise.toml is fully pinned (no "latest") ----------------


def test_mise_toml_has_no_latest_pins(mise_pins: dict[str, str]) -> None:
    """ADR 0006 forbids `latest`; every tool gets a concrete pin so
    Mac, Linux, and Windows resolve to the same version."""
    latest_tools = [tool for tool, version in mise_pins.items() if version == "latest"]
    assert not latest_tools, (
        f'mise.toml uses `= "latest"` for {latest_tools}; ADR 0006 '
        f"requires concrete version pins. Bump these explicitly so "
        f"all OSes resolve identically."
    )


def test_mise_toml_pins_look_like_versions(mise_pins: dict[str, str]) -> None:
    """Sanity: every pin should look like a version string. Catches
    typos like `uv = "0,11,8"` (commas) or `uv = "v0.11.8"` (leading v
    that mise's aqua backend doesn't always accept)."""
    bad = {
        tool: ver
        for tool, ver in mise_pins.items()
        if not re.match(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?(?:[-+][\w.-]+)?$", ver)
    }
    assert not bad, (
        f"mise.toml pins do not look like SemVer-without-leading-v: {bad}. "
        f"Use the bare version string (e.g. `0.11.8`, not `v0.11.8`)."
    )


# ---------- mise.toml ↔ feature install.sh consistency -------------


# Tools managed both via mise.toml and via the verified-fetch
# install path in the dev container feature. Add a row here when
# a new tool gets a feature-install hardcoded constant.
SHARED_PINS: dict[str, str] = {
    # mise.toml key  ↔  feature-install constant prefix
    "uv": "UV",
    "just": "JUST",
}


@pytest.mark.parametrize("mise_key,feature_prefix", list(SHARED_PINS.items()))
def test_mise_toml_matches_feature_install_constant(
    mise_pins: dict[str, str],
    feature_constants: dict[str, str],
    mise_key: str,
    feature_prefix: str,
) -> None:
    """For every tool installed BOTH through mise (Mac path) and
    through the verified-fetch feature install (Linux build-time),
    the two SoTs must agree byte-for-byte."""
    mise_version = mise_pins.get(mise_key)
    feature_version = feature_constants.get(feature_prefix)
    assert mise_version is not None, (
        f"mise.toml [tools] is missing the {mise_key!r} pin."
    )
    assert feature_version is not None, (
        f"feature install.sh is missing {feature_prefix}_VERSION."
    )
    assert mise_version == feature_version, (
        f"version drift detected for {mise_key}: "
        f"mise.toml says {mise_version!r}, "
        f"feature install.sh says {feature_prefix}_VERSION={feature_version!r}. "
        f"ADR 0006 mandates these agree. Bump both in the same PR or "
        f"choose a different SoT for this tool."
    )


def test_required_tools_are_present(mise_pins: dict[str, str]) -> None:
    """Sanity: the minimum set of tools the operator's flow depends
    on must be in mise.toml."""
    required = {
        "uv",
        "just",
        "prek",
        "vp",
        "markdownlint-cli2",
        # AI agent CLIs (npm-backend; the keys mise actually stores
        # are the full `npm:<package>` strings).
        "npm:@openai/codex",
        "npm:@google/gemini-cli",
        "npm:@anthropic-ai/claude-code",
        "npm:@github/copilot",
        "npm:@mariozechner/pi-coding-agent",
    }
    missing = required - set(mise_pins)
    assert not missing, (
        f"mise.toml [tools] is missing required pins: {missing}. "
        f"Add them with concrete versions per ADR 0006."
    )


def test_prebuild_mise_toml_matches_workspace_mise_toml(
    mise_pins: dict[str, str],
) -> None:
    """The dev container feature embeds a `/tmp/mise-prebuild/mise.toml`
    via heredoc in `.devcontainer/features/dotfiles-tools/install.sh`.
    That copy is the SoT mise actually consumes at image-build time; if
    it drifts from the workspace `mise.toml` (the SoT operators see),
    the image installs different versions than the repo claims.

    This test parses the heredoc body out of the feature install.sh and
    asserts every (key, version) pair matches the workspace mise.toml.
    """
    feature_text = FEATURE_INSTALL_SH.read_text(encoding="utf-8")
    match = re.search(
        r"cat > /tmp/mise-prebuild/mise\.toml <<'EOF'\n"
        r"\[tools\]\n"
        r"(?P<body>(?:.*\n)*?)"
        r"EOF",
        feature_text,
    )
    assert match is not None, (
        "could not locate the /tmp/mise-prebuild/mise.toml heredoc in "
        "feature install.sh"
    )
    prebuild_pins: dict[str, str] = {}
    for line in match.group("body").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'"?([^"=\s]+)"?\s*=\s*"([^"]+)"', line)
        if m:
            prebuild_pins[m.group(1)] = m.group(2)

    diffs = {
        k: (prebuild_pins.get(k), mise_pins.get(k))
        for k in set(prebuild_pins) | set(mise_pins)
        if prebuild_pins.get(k) != mise_pins.get(k)
    }
    assert not diffs, (
        f"prebuild mise.toml ↔ workspace mise.toml drift detected: "
        f"{diffs}. ADR 0006 mandates these agree byte-for-byte. Bump "
        f"both in the same PR."
    )
