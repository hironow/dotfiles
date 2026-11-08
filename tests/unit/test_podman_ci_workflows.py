"""Static workflow/bootstrap safety contracts; no host operations."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from _bash_hook import run_bash

ROOT = Path(__file__).resolve().parents[2]


def test_both_engine_jobs_use_one_rootless_native_bootstrap():
    for name in ("test-just.yaml", "test-emulators.yaml"):
        body = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")
        assert "runs-on: ubuntu-26.04" in body
        assert "bash .devcontainer/ci-bootstrap.sh" in body
        assert "devcontainers/ci@" not in body
        assert "github.event.pull_request.draft == false" in body
        assert "ready_for_review" in body
        for action in re.findall(r"uses:\s+(\S+)", body):
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", action), action
    sandbox = (ROOT / ".github/workflows/test-just.yaml").read_text(encoding="utf-8")
    assert "vars.RUN_SANDBOX_TESTS == 'true'" in sandbox
    assert "${GITHUB_WORKSPACE}/pytest-report.xml" in sandbox
    assert "path: ${{ github.workspace }}/pytest-report.xml" in sandbox


def test_emulator_ci_never_kills_by_port_or_shared_compose_project():
    body = (ROOT / ".github/workflows/test-emulators.yaml").read_text(encoding="utf-8")
    for unsafe in (
        "publish=$port",
        "docker stop",
        "docker rm",
        "docker compose down",
        "sudo lsof",
    ):
        assert unsafe not in body
    assert "if: always()" in body
    assert "DOTFILES_E2E_REQUIRED: '1'" in body
    assert "DOTFILES_PODMAN_RUN_MANIFEST:" in body
    for operation in ("prepare", "start", "wait", "cleanup"):
        assert f"python -m tests.utils.isolation {operation}" in body
    assert (
        "--services firebase-emulator,spanner-emulator,pgadapter,postgres --telemetry"
        in body
    )
    assert "pytest tests/e2e -v -m e2e -ra" in body
    assert "tests/test_postgres18_features.py tests/test_postgres18_emulator.py" in body
    assert "Docker executable unexpectedly present" in body


def test_ci_bootstrap_refuses_operator_hosts_before_installation(tmp_path):
    result = run_bash(
        ROOT / ".devcontainer/ci-bootstrap.sh",
        cwd=tmp_path,
        env=dict(
            os.environ, GITHUB_ACTIONS="false", RUNNER_ENVIRONMENT="github-hosted"
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 1
    assert "ephemeral non-root GitHub Actions Linux runner" in result.stderr


def test_bootstrap_is_ci_only_and_uses_canonical_pins_and_order():
    body = (ROOT / ".devcontainer/ci-bootstrap.sh").read_text(encoding="utf-8")
    assert '"${GITHUB_ACTIONS:-}" != true' in body
    assert '"${RUNNER_ENVIRONMENT:-}" != github-hosted' in body
    assert 'bash "$repo/install.sh" --podman-only' in body
    assert "source['bootstrap']['mise']" in body
    assert "generated mise tools missing" in body
    assert "MISE_GLOBAL_CONFIG_FILE" in body
    assert body.index("mise install bun uv node just") < body.index(
        "mise install npm:@devcontainers/cli pypi:podman-compose"
    )
    assert "systemctl --user start podman.socket" in body
    assert '"host"]["remoteSocket"]["path"]' in body
    assert "PODMAN_COMPOSE_PROVIDER=podman-compose" in body
    assert "sudo podman" not in body
    assert "Docker remains on PATH" in body
    assert not re.search(r"podman-compose[=@][0-9]|devcontainers/cli[=@][0-9]", body)


@pytest.mark.parametrize(
    "label, valid", [("ubuntu-26.04", True), ("ubuntu-unknown-podman", False)]
)
def test_actionlint_exact_runner_extension_retains_unknown_label_rejection(
    tmp_path, label, valid
):
    executable = shutil.which("actionlint")
    if executable is None:
        pytest.skip("actionlint not installed; workflow schema control unverified")
    workflow = tmp_path / "runner.yaml"
    workflow.write_text(
        f"name: Runner control\non: push\njobs:\n  control:\n    runs-on: {label}\n    steps:\n      - run: echo control\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            executable,
            "-config-file",
            str(ROOT / ".github/actionlint.yaml"),
            str(workflow),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert (result.returncode == 0) is valid, result.stdout + result.stderr
    if not valid:
        assert "runner-label" in result.stdout + result.stderr
