"""Unit tests for the agent PreToolUse hook ROOT_AGENTS_hooks_block-prohibited-commands.sh.

The hook receives Claude Code tool input as JSON on stdin and answers with its
exit code: 0 allows the command, 2 blocks it (exit 1 would NOT block — see the
exit-code contract in ROOT_AGENTS_docs_agents_enforcement.md).

These tests run the real script through bash with a controlled cwd, so they
pin both the block list and the pnpm lockfile-resolution behavior.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = (
    Path(__file__).resolve().parents[2]
    / "ROOT_AGENTS_hooks_block-prohibited-commands.sh"
)

EXIT_ALLOW = 0
EXIT_BLOCK = 2

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="hook needs bash + jq on PATH",
)


def _run_hook(command: str, cwd: Path) -> int:
    """Feed a Bash tool_input payload to the hook and return its exit code."""
    payload = json.dumps({"tool_input": {"command": command}})
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )
    return result.returncode


@pytest.fixture()
def locked_repo(tmp_path: Path) -> Path:
    """A project directory governed by pnpm-lock.yaml."""
    repo = tmp_path / "locked"
    repo.mkdir()
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    return repo


@pytest.fixture()
def unlocked_repo(tmp_path: Path) -> Path:
    """A project directory without a pnpm lockfile."""
    repo = tmp_path / "unlocked"
    repo.mkdir()
    return repo


# --- Package managers -----------------------------------------------------


def test_pip_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("pip install requests", tmp_path) == EXIT_BLOCK


def test_npm_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("npm install", tmp_path) == EXIT_BLOCK


def test_uv_is_allowed(tmp_path: Path) -> None:
    assert _run_hook("uv add httpx", tmp_path) == EXIT_ALLOW


def test_make_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("make build", tmp_path) == EXIT_BLOCK


# --- pnpm lockfile gate ----------------------------------------------------


def test_pnpm_with_lockfile_in_cwd_is_allowed(locked_repo: Path) -> None:
    assert _run_hook("pnpm install", locked_repo) == EXIT_ALLOW


def test_pnpm_without_lockfile_is_blocked(unlocked_repo: Path) -> None:
    assert _run_hook("pnpm install", unlocked_repo) == EXIT_BLOCK


# --- Destructive / IaC drift ------------------------------------------------


def test_rm_rf_root_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("rm -rf /", tmp_path) == EXIT_BLOCK


def test_force_push_to_main_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("git push --force origin main", tmp_path) == EXIT_BLOCK


def test_readonly_gcloud_is_allowed(tmp_path: Path) -> None:
    assert _run_hook("gcloud compute instances list", tmp_path) == EXIT_ALLOW


def test_gcloud_iam_binding_is_blocked(tmp_path: Path) -> None:
    cmd = "gcloud projects add-iam-policy-binding my-proj --member=x --role=y"
    assert _run_hook(cmd, tmp_path) == EXIT_BLOCK


def test_gcloud_run_deploy_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("gcloud run deploy api --image x", tmp_path) == EXIT_BLOCK


def test_cdr_workspace_update_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("cdr workspaces update my-ws", tmp_path) == EXIT_BLOCK
