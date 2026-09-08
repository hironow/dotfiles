"""The root ruff/ty pins must agree across their declarations (ADR 0044).

`just fmt` / `just lint` / `just check` run `uvx ruff@<ver>` (pinned because a
newer ruff widens the default rule set); the same version is a root dev
dependency (`ruff==<ver>` in pyproject.toml) so `uv run ruff` -- the
format-after-edit hook -- and mise's global copy (`config/mise/config.toml`)
report exactly what the gate reports. ty is pre-1.0 and therefore pinned `==`
in every declaration that carries it. A drift between any two of these is a
silent difference between "what I see" and "what CI sees".
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _dev_pin(name: str) -> str:
    dev = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))[
        "dependency-groups"
    ]["dev"]
    spec = next(s for s in dev if isinstance(s, str) and re.match(rf"^{name}\b", s))
    m = re.fullmatch(rf"{name}==([0-9][0-9A-Za-z.]*)", spec)
    assert m, f"{name} must be pinned with == in [dependency-groups].dev, got {spec!r}"
    return m.group(1)


def _mise_pin(name: str) -> str:
    tools = tomllib.loads(
        (REPO / "config" / "mise" / "config.toml").read_text(encoding="utf-8")
    )["tools"]
    value = tools[name]
    assert isinstance(value, str) and re.fullmatch(r"[0-9][0-9A-Za-z.]*", value), (
        f"{name} must be an exact version in config/mise/config.toml, got {value!r}"
    )
    return value


def test_justfile_uvx_ruff_pins_are_one_version_and_match_the_dev_dependency() -> None:
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    uvx_pins = set(re.findall(r"uvx ruff@([0-9][0-9A-Za-z.]*)", justfile))
    assert len(uvx_pins) == 1, (
        f"justfile pins ruff at more than one version: {sorted(uvx_pins)}"
    )
    assert uvx_pins == {_dev_pin("ruff")}


def test_mise_ruff_matches_the_gate_pin() -> None:
    assert _mise_pin("ruff") == _dev_pin("ruff")


def _emulator_dev_pin(name: str) -> str:
    dev = tomllib.loads(
        (REPO / "emulator" / "pyproject.toml").read_text(encoding="utf-8")
    )["dependency-groups"]["dev"]
    spec = next(s for s in dev if isinstance(s, str) and re.match(rf"^{name}\b", s))
    m = re.fullmatch(rf"{name}==([0-9][0-9A-Za-z.]*)", spec)
    assert m, (
        f"emulator: {name} must be pinned with == in [dependency-groups].dev, got {spec!r}"
    )
    return m.group(1)


def test_ty_is_pinned_exactly_and_to_one_version_everywhere() -> None:
    """mise (interactive copy), the root dev group and the emulator dev group must
    name the same ty; a newer release reaches the uv locks only after the 7-day
    quarantine, so the mise pin is bumped together with them, not ahead."""
    assert _mise_pin("ty") == _dev_pin("ty") == _emulator_dev_pin("ty")
