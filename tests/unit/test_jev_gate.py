"""The root JS workspace gate delegates the Pi extension to a real Bun gate."""

import re
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/unit-test.yaml").read_text(encoding="utf-8")


def test_pi_extension_is_excluded_from_inapplicable_vp_and_built_with_bun() -> None:
    assert "':!config/pi/extensions/**'" in JUSTFILE
    assert "':!tests/unit/jev_sonnet_fallback.test.ts'" in JUSTFILE
    assert (
        "just pi-jev-test" in JUSTFILE.split("check:\n", 1)[1].split("\n[group(", 1)[0]
    )
    fmt = JUSTFILE.split("fmt:\n", 1)[1].split("\n[group(", 1)[0]
    assert "':!config/pi/extensions/**'" in fmt
    assert "':!tests/unit/jev_sonnet_fallback.test.ts'" in fmt
    lint = JUSTFILE.split("lint:\n", 1)[1].split("\n[group(", 1)[0]
    assert "':!config/pi/extensions/**'" in lint
    assert "':!tests/unit/jev_sonnet_fallback.test.ts'" in lint
    assert "just pi-jev-test" in lint
    assert "bun build config/pi/extensions/jev-sonnet-fallback.ts" in JUSTFILE
    assert "bun test tests/unit/jev_sonnet_fallback.test.ts" in JUSTFILE
    assert WORKFLOW.count("bun test tests/unit/jev_sonnet_fallback.test.ts") == 2


def test_the_claude_live_verification_is_one_command() -> None:
    assert (
        "\njev-claude-verify:\n    {{UV_RUN}} scripts/jev_claude_verify.py" in JUSTFILE
    )
    runbook = (ROOT / "docs/runbook/jev-launchers.md").read_text(encoding="utf-8")
    assert "just jev-claude-verify" in runbook


def test_windows_ci_runs_the_codex_runner_tests() -> None:
    assert "tests/unit/test_jev_codex_exec.py" in WORKFLOW


def _windows_step(name: str) -> str:
    windows = WORKFLOW.split("\n  windows-jev:\n", 1)[1].split("\n  # The Ollama", 1)[0]
    matches = re.findall(
        rf"^      - name: {re.escape(name)}\n"
        r"(?:        shell: pwsh\n)?        run: \|\n"
        r"((?:          [^\n]*\n)+)",
        windows,
        re.MULTILINE,
    )
    assert len(matches) == 1, f"missing or ambiguous Windows step: {name}"
    return textwrap.dedent(matches[0])


@pytest.mark.parametrize(
    ("step", "native_commands"),
    [
        ("Install just", ["uv tool install", "(uv tool dir"]),
        (
            "Check PowerShell launchers and HOME-less justfile",
            ["just --summary", "uvx pytest", "bun test"],
        ),
    ],
)
def test_windows_ci_rejects_native_failures_before_later_success(
    step: str, native_commands: list[str]
) -> None:
    body = _windows_step(step)
    guard = "$PSNativeCommandUseErrorActionPreference = $true"
    assert guard in body
    for command in native_commands:
        assert body.index(guard) < body.index(command)
    assert "_EXE_SRC_DIR" not in body
