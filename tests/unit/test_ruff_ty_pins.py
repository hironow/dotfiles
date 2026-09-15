"""The root ruff/ty pins must agree across their declarations (ADR 0044).

`just fmt` / `just lint` / `just check` run
`uv run --frozen --only-group lint ruff` so the lock pins the version (a newer
ruff widens the default rule set). The same version is a root lint-group
dependency (`ruff==<ver>` in pyproject.toml) so the format-after-edit hook --
and mise's global copy (`config/mise/config.toml`) -- report exactly what the
gate reports. ty is pre-1.0 and therefore pinned `==` in every declaration that
carries it, and is invoked with `--group lint` (not `--only-group`) so it can
resolve project imports. A drift between any two of these is a silent
difference between "what I see" and "what CI sees".
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _lint_pin(name: str, pyproject: Path, *, label: str) -> str:
    groups = tomllib.loads(pyproject.read_text(encoding="utf-8"))["dependency-groups"]
    lint = groups["lint"]
    spec = next(s for s in lint if isinstance(s, str) and re.match(rf"^{name}\b", s))
    m = re.fullmatch(rf"{name}==([0-9][0-9A-Za-z.]*)", spec)
    assert m, (
        f"{label}: {name} must be pinned with == in [dependency-groups].lint, "
        f"got {spec!r}"
    )
    return m.group(1)


def _root_lint_pin(name: str) -> str:
    return _lint_pin(name, REPO / "pyproject.toml", label="root")


def _emulator_lint_pin(name: str) -> str:
    return _lint_pin(name, REPO / "emulator" / "pyproject.toml", label="emulator")


def _mise_pin(name: str) -> str:
    tools = tomllib.loads(
        (REPO / "config" / "mise" / "config.toml").read_text(encoding="utf-8")
    )["tools"]
    value = tools[name]
    assert isinstance(value, str) and re.fullmatch(r"[0-9][0-9A-Za-z.]*", value), (
        f"{name} must be an exact version in config/mise/config.toml, got {value!r}"
    )
    return value


def _group_specs(pyproject: Path, group: str) -> list[str]:
    groups = tomllib.loads(pyproject.read_text(encoding="utf-8"))["dependency-groups"]
    return [s for s in groups[group] if isinstance(s, str)]


def test_ruff_and_ty_live_in_the_lint_group_not_dev() -> None:
    for pyproject, label in (
        (REPO / "pyproject.toml", "root"),
        (REPO / "emulator" / "pyproject.toml", "emulator"),
    ):
        dev = _group_specs(pyproject, "dev")
        lint = _group_specs(pyproject, "lint")
        for name in ("ruff", "ty"):
            assert any(re.match(rf"^{name}\b", s) for s in lint), (
                f"{label}: {name} must be in [dependency-groups].lint"
            )
            assert not any(re.match(rf"^{name}\b", s) for s in dev), (
                f"{label}: {name} must not remain in [dependency-groups].dev"
            )


def test_justfile_has_no_uvx_ruff_pin() -> None:
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    uvx_pins = set(re.findall(r"uvx ruff@([0-9][0-9A-Za-z.]*)", justfile))
    assert not uvx_pins, (
        "justfile must not pin ruff via uvx; the lint group + lock are the pin, "
        f"found {sorted(uvx_pins)}"
    )


def _code_lines_with(justfile: str, pattern: str) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for n, line in enumerate(justfile.splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.search(pattern, stripped):
            hits.append((n, stripped))
    return hits


def test_justfile_ruff_uses_frozen_only_group_lint() -> None:
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    invocations = _code_lines_with(justfile, r"\bruff\b")
    uv_ruff = [
        (n, line)
        for n, line in invocations
        if "uv run" in line or "{{UV_RUN}}" in line or line.startswith("uvx ")
    ]
    assert uv_ruff, "expected uv-run ruff invocations in the justfile"
    for n, line in uv_ruff:
        assert "--only-group lint" in line, (
            f"justfile:{n}: ruff must use --only-group lint: {line}"
        )
        assert "uvx " not in line, f"justfile:{n}: ruff must not use uvx: {line}"


def test_justfile_ty_uses_group_lint_not_only_group() -> None:
    justfile = (REPO / "justfile").read_text(encoding="utf-8")
    invocations = [
        (n, line)
        for n, line in _code_lines_with(justfile, r"\bty check\b")
        if not re.match(r"^@?echo\b", line)
    ]
    assert invocations, "expected ty check invocations in the justfile"
    for n, line in invocations:
        assert "--group lint" in line, (
            f"justfile:{n}: ty must use --group lint so imports resolve: {line}"
        )
        assert "--only-group" not in line, (
            f"justfile:{n}: ty must not use --only-group (it hides project deps): {line}"
        )


def test_emulator_ruff_matches_the_gate_pin() -> None:
    """just emu-lint runs the emulator's own ruff; at 0.16 it reported 52 findings
    the 0.15.22 gate never sees (2026-09-08)."""
    assert _emulator_lint_pin("ruff") == _root_lint_pin("ruff")


def test_ty_is_pinned_exactly_and_to_one_version_everywhere() -> None:
    """mise (interactive copy), the root lint group and the emulator lint group must
    name the same ty; a newer release reaches the uv locks only after the 7-day
    quarantine, so the mise pin is bumped together with them, not ahead."""
    assert _mise_pin("ty") == _root_lint_pin("ty") == _emulator_lint_pin("ty")


def test_mise_ruff_matches_the_gate_pin() -> None:
    assert _mise_pin("ruff") == _root_lint_pin("ruff")
