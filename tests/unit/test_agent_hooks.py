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
    shutil.which("bash") is None or shutil.which("python3") is None,
    reason="hook needs bash + python3 on PATH",
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


def test_pnpm_with_lockfile_in_ancestor_is_allowed(locked_repo: Path) -> None:
    """Monorepo subdirectory: the lockfile lives at the repo root above cwd."""
    sub = locked_repo / "packages" / "app"
    sub.mkdir(parents=True)
    assert _run_hook("pnpm install", sub) == EXIT_ALLOW


def test_pnpm_cd_into_locked_repo_is_allowed(
    locked_repo: Path, unlocked_repo: Path
) -> None:
    """Cross-repo: cwd has no lockfile, but the cd target does."""
    cmd = f"cd {locked_repo} && pnpm install"
    assert _run_hook(cmd, unlocked_repo) == EXIT_ALLOW


def test_pnpm_dash_c_locked_repo_is_allowed(
    locked_repo: Path, unlocked_repo: Path
) -> None:
    cmd = f"pnpm -C {locked_repo} install"
    assert _run_hook(cmd, unlocked_repo) == EXIT_ALLOW


def test_pnpm_mixed_cd_segments_blocked(
    locked_repo: Path, unlocked_repo: Path, tmp_path: Path
) -> None:
    """Per-invocation gate: one governed pnpm call must not bless the others."""
    cmd = f"cd {locked_repo} && pnpm install; cd {unlocked_repo} && pnpm install"
    assert _run_hook(cmd, tmp_path) == EXIT_BLOCK


def test_pnpm_dash_c_mixed_blocked(
    locked_repo: Path, unlocked_repo: Path, tmp_path: Path
) -> None:
    cmd = f"pnpm -C {locked_repo} install && pnpm -C {unlocked_repo} install"
    assert _run_hook(cmd, tmp_path) == EXIT_BLOCK


def test_pnpm_variable_dir_is_blocked(unlocked_repo: Path) -> None:
    """Unresolvable target (variable) fails safe: block."""
    assert _run_hook('cd "$PROJECT_DIR" && pnpm install', unlocked_repo) == EXIT_BLOCK


def test_pnpm_mention_in_commit_message_is_allowed(unlocked_repo: Path) -> None:
    """Prose mentions inside quotes are not invocations (observed false block)."""
    cmd = 'git commit -m "docs: explain why pnpm is gated on lockfiles"'
    assert _run_hook(cmd, unlocked_repo) == EXIT_ALLOW


def test_npm_mention_in_commit_message_is_allowed(unlocked_repo: Path) -> None:
    cmd = 'git commit -m "build: switch from npm to bun"'
    assert _run_hook(cmd, unlocked_repo) == EXIT_ALLOW


def test_make_mention_in_commit_message_is_allowed(unlocked_repo: Path) -> None:
    """The English verb 'make' in a quoted message must not trip the task-runner
    guard (observed false block)."""
    cmd = 'git commit -m "ci: have the gate make builds reproducible"'
    assert _run_hook(cmd, unlocked_repo) == EXIT_ALLOW


# --- Heredocs: data bodies are opaque, interpreter bodies are code -----------


def test_heredoc_prose_to_data_sink_is_allowed(tmp_path: Path) -> None:
    """PR-body style heredoc fed to a data sink is prose, not invocations
    (observed false block on a multi-line gh pr create body)."""
    cmd = (
        "cat <<'EOF' > /tmp/pr-body.md\n"
        "this prose mentions npm and pnpm and make and even gcloud run deploy\n"
        "EOF"
    )
    assert _run_hook(cmd, tmp_path) == EXIT_ALLOW


def test_heredoc_prose_with_unbalanced_quote_is_allowed(tmp_path: Path) -> None:
    """Prose apostrophes inside a data heredoc must not break parsing."""
    cmd = "cat <<'EOF'\ndon't use npm here — prose only, isn't it\nEOF"
    assert _run_hook(cmd, tmp_path) == EXIT_ALLOW


def test_heredoc_to_shell_interpreter_is_blocked(tmp_path: Path) -> None:
    """A heredoc piped into a shell executes — its body is scanned as code."""
    cmd = "bash <<'EOF'\nnpm install\nEOF"
    assert _run_hook(cmd, tmp_path) == EXIT_BLOCK


# --- .yml creation via Bash ---------------------------------------------------


def test_redirect_to_yml_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("echo hi > notes.yml", tmp_path) == EXIT_BLOCK


def test_append_redirect_to_yml_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("echo hi >> notes.yml", tmp_path) == EXIT_BLOCK


def test_touch_yml_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("touch a.yml", tmp_path) == EXIT_BLOCK


def test_tee_yml_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("printf hi | tee a.yml", tmp_path) == EXIT_BLOCK


def test_cp_to_yml_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("cp a.yaml b.yml", tmp_path) == EXIT_BLOCK


def test_mv_to_yml_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("mv a.yaml c.yml", tmp_path) == EXIT_BLOCK


def test_redirect_to_deprecated_compose_name_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("echo x > docker-compose.yaml", tmp_path) == EXIT_BLOCK


def test_touch_compose_yaml_is_allowed(tmp_path: Path) -> None:
    assert _run_hook("touch compose.yaml", tmp_path) == EXIT_ALLOW


def test_reading_yml_is_allowed(tmp_path: Path) -> None:
    assert _run_hook("cat config.yml", tmp_path) == EXIT_ALLOW


def test_cp_yml_to_directory_is_allowed(tmp_path: Path) -> None:
    """Copying an existing .yml elsewhere (dest is a dir) is not creation."""
    assert _run_hook("cp foo.yml backup/", tmp_path) == EXIT_ALLOW


# --- Minimal shell grammar: prefixes, wrappers, boundaries --------------------


def test_assignment_prefix_does_not_hide_command(tmp_path: Path) -> None:
    assert _run_hook("VAR=x touch a.yml", tmp_path) == EXIT_BLOCK


def test_env_wrapper_does_not_hide_command(tmp_path: Path) -> None:
    assert _run_hook("env FOO=1 touch a.yml", tmp_path) == EXIT_BLOCK


def test_command_after_cd_is_scanned(tmp_path: Path) -> None:
    assert _run_hook("cd sub && touch a.yml", tmp_path) == EXIT_BLOCK


def test_xargs_wrapper_does_not_hide_command(tmp_path: Path) -> None:
    assert _run_hook("echo x | xargs npm install", tmp_path) == EXIT_BLOCK


# --- Wrapper contract: deployed layout and fail-closed ------------------------


def test_wrapper_resolves_deployed_layout(tmp_path: Path) -> None:
    """In agent homes the pair is hooks/block-prohibited-commands.{sh,py}."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    shutil.copy(HOOK, hooks_dir / "block-prohibited-commands.sh")
    shutil.copy(
        HOOK.with_name("ROOT_AGENTS_hooks_block-prohibited-commands.py"),
        hooks_dir / "block-prohibited-commands.py",
    )
    payload = json.dumps({"tool_input": {"command": "npm install"}})
    result = subprocess.run(
        ["bash", str(hooks_dir / "block-prohibited-commands.sh")],
        input=payload,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == EXIT_BLOCK


def test_wrapper_fails_closed_without_companion(tmp_path: Path) -> None:
    """A wrapper that cannot find its Python companion must block, loudly."""
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    shutil.copy(HOOK, hooks_dir / "block-prohibited-commands.sh")
    payload = json.dumps({"tool_input": {"command": "ls"}})
    result = subprocess.run(
        ["bash", str(hooks_dir / "block-prohibited-commands.sh")],
        input=payload,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == EXIT_BLOCK
    assert "failing closed" in result.stderr


# --- Destructive / IaC drift ------------------------------------------------


def test_rm_rf_root_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("rm -rf /", tmp_path) == EXIT_BLOCK


def test_force_push_to_main_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("git push --force origin main", tmp_path) == EXIT_BLOCK


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("git push --force origin main", id="long-flag-before-ref"),
        pytest.param("git push -f origin main", id="short-flag"),
        pytest.param("git push origin main --force", id="flag-after-ref"),
        pytest.param("git push --force-with-lease origin main", id="force-with-lease"),
        pytest.param(
            "git push --force-if-includes origin main", id="force-if-includes"
        ),
        pytest.param("git push --force origin master", id="master-branch"),
        pytest.param("git push -f origin HEAD:main", id="refspec-dest-main"),
        pytest.param("git -C /repo push -f origin main", id="git-global-opt"),
    ],
)
def test_force_push_to_protected_branch_is_blocked(
    command: str, tmp_path: Path
) -> None:
    assert _run_hook(command, tmp_path) == EXIT_BLOCK


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("git push -f origin feature", id="force-feature-branch"),
        pytest.param("git push origin main", id="non-force-to-main"),
        pytest.param(
            'git commit -m "git push --force origin main"', id="prose-mention"
        ),
    ],
)
def test_non_protected_force_push_is_allowed(command: str, tmp_path: Path) -> None:
    assert _run_hook(command, tmp_path) == EXIT_ALLOW


def test_readonly_gcloud_is_allowed(tmp_path: Path) -> None:
    assert _run_hook("gcloud compute instances list", tmp_path) == EXIT_ALLOW


def test_gcloud_iam_binding_is_blocked(tmp_path: Path) -> None:
    cmd = "gcloud projects add-iam-policy-binding my-proj --member=x --role=y"
    assert _run_hook(cmd, tmp_path) == EXIT_BLOCK


def test_gcloud_run_deploy_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("gcloud run deploy api --image x", tmp_path) == EXIT_BLOCK


def test_cdr_workspace_update_is_blocked(tmp_path: Path) -> None:
    assert _run_hook("cdr workspaces update my-ws", tmp_path) == EXIT_BLOCK
