"""Frozen installations must not regress below the reviewed incident floors."""

import json
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = {"bun", "go", "node", "uv", "mise", "rustup"}


def check_fixed_pins(
    pins: dict[str, str], floors: dict[str, list[dict[str, str]]]
) -> None:
    for tool in REQUIRED:
        if not floors.get(tool) or tool not in pins:
            raise ValueError(f"missing required declaration or incident floor: {tool}")
    for tool, version in pins.items():
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValueError(f"non-stable fixed pin: {tool} {version}")
        candidates = [f for f in floors[tool] if version.startswith(f["branch"] + ".")]
        if len(candidates) != 1:
            raise ValueError(f"unreviewed branch: {tool} {version}")
        minimum = candidates[0]["minimum"]
        if tuple(map(int, version.split("."))) < tuple(map(int, minimum.split("."))):
            raise ValueError(f"below incident floor: {tool} {version} < {minimum}")


def incident() -> dict:
    return json.loads(
        (ROOT / "tools/ca-doctor/incidents/emudhra-2026.json").read_text(
            encoding="utf-8"
        )
    )


def source_pins() -> dict[str, str]:
    image = tomllib.loads(
        (ROOT / "config/mise/image-tools.toml").read_text(encoding="utf-8")
    )
    feature = (ROOT / ".devcontainer/features/dotfiles-tools/install.sh").read_text(
        encoding="utf-8"
    )
    match = re.search(r'^RUSTUP_VERSION="([^"]+)"$', feature, re.MULTILINE)
    assert match, "the feature must declare its pinned rustup"
    return {
        **{tool: image["tools"][tool] for tool in REQUIRED - {"mise", "rustup"}},
        "mise": image["bootstrap"]["mise"],
        "rustup": match[1],
    }


def test_frozen_and_host_exact_pins_meet_reviewed_floors() -> None:
    policy = incident()
    pins = source_pins()
    check_fixed_pins(pins, policy["floors"])
    assert "bun" not in policy["pending"], "patched Bun must not remain pending"
    host = tomllib.loads((ROOT / "config/mise/config.toml").read_text(encoding="utf-8"))
    for tool in REQUIRED & host["tools"].keys():
        spec = host["tools"][tool]
        version = spec["version"] if isinstance(spec, dict) else spec
        if version in {"latest", "lts"}:
            # Moving selectors are not minima; doctor checks installed versions.
            continue
        check_fixed_pins({**pins, tool: version}, policy["floors"])
    feature = (ROOT / ".devcontainer/features/dotfiles-tools/install.sh").read_text(
        encoding="utf-8"
    )
    rust = re.search(r'^RUST_TOOLCHAIN="([^"]+)"$', feature, re.MULTILINE)
    assert rust and rust[1] == host["tools"]["rust"]["version"]


@pytest.mark.parametrize("tool", sorted(REQUIRED))
def test_guard_rejects_stale_pins_and_missing_registration(tool: str) -> None:
    floors = incident()["floors"]
    # This fixture is derived from the policy, never from the deployed pins.
    assert all(floors.get(name) for name in REQUIRED), "required policy missing"
    pins = {name: floors[name][0]["minimum"] for name in REQUIRED}
    check_fixed_pins(pins, floors)
    major, minor, patch = map(int, pins[tool].split("."))
    assert patch > 0, "choose a stale same-branch fixture if the floor becomes x.y.0"
    with pytest.raises(ValueError, match="below incident floor"):
        check_fixed_pins({**pins, tool: f"{major}.{minor}.{patch - 1}"}, floors)
    for invalid in ("0.0.0", pins[tool] + "-rc.1", "latest", "lts"):
        with pytest.raises(ValueError):
            check_fixed_pins({**pins, tool: invalid}, floors)
    with pytest.raises(ValueError, match="missing required"):
        check_fixed_pins({name: v for name, v in pins.items() if name != tool}, floors)
    with pytest.raises(ValueError, match="missing required"):
        check_fixed_pins(pins, {name: v for name, v in floors.items() if name != tool})
