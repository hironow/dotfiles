"""The root JS workspace gate delegates the Pi extension to a real Bun gate."""

import re
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = (ROOT / "justfile").read_text(encoding="utf-8")
WORKFLOW = (ROOT / ".github/workflows/unit-test.yaml").read_text(encoding="utf-8")


def _recipe_body(text: str, name: str) -> str:
    bodies = re.findall(
        rf"^{re.escape(name)}:\n((?:[ \t]+[^\n]*(?:\n|$)|\n)*)", text, re.MULTILINE
    )
    assert len(bodies) == 1, f"missing or ambiguous recipe: {name}"
    return bodies[0]


def test_pi_extension_is_excluded_from_inapplicable_vp_and_built_with_bun() -> None:
    # vp runs only in site/, the Pages site's package (test_justfile_js_files.py),
    # so it never reaches the Pi extension or its bun test; bun gates those.
    assert "just pi-jev-test" in _recipe_body(JUSTFILE, "check")
    assert "vp -C site fmt" in _recipe_body(JUSTFILE, "fmt")
    lint = _recipe_body(JUSTFILE, "lint")
    assert "vp -C site lint" in lint
    assert "just pi-jev-test" in lint
    assert "bun build config/pi/extensions/jev-sonnet-fallback.ts" in JUSTFILE
    assert "bun test tests/unit/jev_sonnet_fallback.test.ts" in JUSTFILE
    assert WORKFLOW.count("bun test tests/unit/jev_sonnet_fallback.test.ts") == 2


@pytest.mark.parametrize(
    ("name", "earlier"),
    [("check", "spec-check"), ("fmt", "pre-fmt"), ("lint", "pre-lint")],
)
def test_recipe_selection_uses_full_header(name: str, earlier: str) -> None:
    text = f"{earlier}:\n    wrong\n\n{name}:\n    expected\n"
    assert _recipe_body(text, name) == "    expected\n"


@pytest.mark.parametrize(
    "text", ["", "spec-check:\n    wrong\n", "check:\n    one\ncheck:\n    two\n"]
)
def test_recipe_selection_rejects_missing_or_duplicate_headers(text: str) -> None:
    with pytest.raises(AssertionError, match="missing or ambiguous recipe"):
        _recipe_body(text, "check")


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
