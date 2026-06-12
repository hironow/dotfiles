"""Unit tests for the shared plugin scope hook (plugins/_shared/check-scope.sh).

The canonical script lives in plugins/_shared/ and is copied into each
auto-loop plugin (autoresearch / autodesign / autoreview) by
`just sync-plugin-scope-hook` — installed plugins only ship their own
directory, so the per-plugin copies are distribution artifacts that cannot
reference a shared file at runtime. These tests gate drift between the
copies and the canonical, verify the sync recipe actually propagates, and
pin the hook's scope decision: exit 0 with empty stdout allows the edit;
a hookSpecificOutput JSON with permissionDecision=ask escalates it.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CANONICAL = REPO / "plugins" / "_shared" / "check-scope.sh"
LOOP_PLUGINS = ["autoresearch", "autodesign", "autoreview"]

# Args mirroring the autoresearch hooks.json wiring.
ARGS = [
    "experiment-config.yaml",
    "target_files",
    "results.tsv run.log",
    "outside experiment scope (test reason)",
]

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="hook needs bash on PATH",
)


def _plugin_copy(plugin: str) -> Path:
    return REPO / "plugins" / plugin / "hooks" / "scripts" / "check-scope.sh"


def _run_hook(
    cwd: Path,
    file_path: str,
    config: str | None = None,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the canonical hook in cwd with a PreToolUse payload."""
    if config is not None:
        (cwd / ARGS[0]).write_text(config)
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    return subprocess.run(
        ["bash", str(CANONICAL), *(args or ARGS)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


CONFIG_BASIC = 'target_files:\n  - "src/algo.py"\neval_command: "just test"\n'


# --- drift gate -------------------------------------------------------------


def test_canonical_exists() -> None:
    assert CANONICAL.is_file(), "canonical plugins/_shared/check-scope.sh is missing"


@pytest.mark.parametrize("plugin", LOOP_PLUGINS)
def test_plugin_copy_matches_canonical(plugin: str) -> None:
    copy = _plugin_copy(plugin)
    assert copy.is_file(), f"{plugin} is missing its check-scope.sh copy"
    assert copy.read_bytes() == CANONICAL.read_bytes(), (
        f"plugins/{plugin}/hooks/scripts/check-scope.sh has drifted from the "
        "canonical plugins/_shared/check-scope.sh — edit the canonical and run "
        "`just sync-plugin-scope-hook`"
    )


@pytest.mark.skipif(shutil.which("just") is None, reason="recipe test needs just")
def test_sync_recipe_propagates_canonical(tmp_path: Path) -> None:
    """`just sync-plugin-scope-hook` must copy the canonical into all plugins."""
    # given: a minimal repo copy (justfile + canonical + per-plugin copies)
    shutil.copy(REPO / "justfile", tmp_path / "justfile")
    shared = tmp_path / "plugins" / "_shared"
    shared.mkdir(parents=True)
    marker = "# sync-recipe-test-marker\n"
    shutil.copy(CANONICAL, shared / "check-scope.sh")
    (shared / "check-scope.sh").write_text(CANONICAL.read_text() + marker)
    for plugin in LOOP_PLUGINS:
        dest = tmp_path / "plugins" / plugin / "hooks" / "scripts"
        dest.mkdir(parents=True)
        shutil.copy(CANONICAL, dest / "check-scope.sh")

    # when
    result = subprocess.run(
        ["just", "sync-plugin-scope-hook"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )

    # then
    assert result.returncode == 0, result.stderr
    for plugin in LOOP_PLUGINS:
        copied = tmp_path / "plugins" / plugin / "hooks" / "scripts" / "check-scope.sh"
        assert copied.read_text().endswith(marker), (
            f"recipe did not propagate the canonical to {plugin}"
        )


# --- scope decision behavior -------------------------------------------------


def test_no_config_allows_silently(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, "anything/at/all.py")
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_in_scope_target_allows_silently(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, "/repo/src/algo.py", config=CONFIG_BASIC)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_out_of_scope_target_asks_with_reason(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, "/repo/README.md", config=CONFIG_BASIC)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    hook_output = output["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "ask"
    assert hook_output["permissionDecisionReason"] == ARGS[3]


@pytest.mark.parametrize("artifact", ["results.tsv", "run.log"])
def test_whitelisted_artifacts_allow_silently(tmp_path: Path, artifact: str) -> None:
    result = _run_hook(tmp_path, f"/repo/{artifact}", config=CONFIG_BASIC)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_empty_file_path_allows_silently(tmp_path: Path) -> None:
    (tmp_path / ARGS[0]).write_text(CONFIG_BASIC)
    payload = json.dumps({"tool_input": {"command": "echo no file_path here"}})
    result = subprocess.run(
        ["bash", str(CANONICAL), *ARGS],
        input=payload,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""
