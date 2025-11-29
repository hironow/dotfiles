"""E2E tests for sync-agents just command.

These tests run in Docker containers to avoid polluting the host environment.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "tests" / "docker" / "JustSandbox.Dockerfile"
IMAGE = "dotfiles-just-sandbox:latest"


def _run(
    cmd: list[str] | str, cwd: Path | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    """Run a command and return the completed process."""
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        shell=isinstance(cmd, str),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _docker_available() -> bool:
    """Check if Docker is available."""
    r = _run(["docker", "info"])
    return r.returncode == 0


@pytest.fixture(scope="module")
def docker_image():
    """Build Docker image for testing."""
    # given: docker daemon availability
    if not _docker_available():
        pytest.skip("Docker is not available; skipping e2e tests.")

    if not DOCKERFILE.exists():
        pytest.skip("Dockerfile missing; skipping e2e tests.")

    # when: build test image
    build_cmd = [
        "docker",
        "build",
        "-t",
        IMAGE,
        "-f",
        str(DOCKERFILE),
        "--build-arg",
        "BASE_IMAGE=alpine:3.19",
        str(ROOT),
    ]
    result = _run(build_cmd, cwd=ROOT)

    # then: build succeeds
    if result.returncode != 0:
        pytest.fail(f"Docker build failed: {result.stderr}")

    yield IMAGE

    # cleanup: image remains for session reuse


def _run_in_container(
    docker_image: str, cmd: str, check: bool = True
) -> subprocess.CompletedProcess:
    """Run a command inside a Docker container.

    Args:
        docker_image: Docker image name
        cmd: Command to run inside container
        check: If True, raise error on non-zero exit code

    Returns:
        CompletedProcess with stdout/stderr
    """
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-w",
        "/root/dotfiles",
        docker_image,
        "bash",
        "-c",
        cmd,
    ]
    result = _run(docker_cmd)

    if check and result.returncode != 0:
        pytest.fail(
            f"Command failed with exit code {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    return result


def test_sync_agents_creates_files_on_first_run(docker_image):
    """Test that sync-agents creates agent files on first run.

    Scenario:
    - given: Fresh container with no agent files
    - when: Run sync-agents command
    - then: Agent files are created with correct content
    """
    # given: Container with dotfiles but no agent files
    # when: Run sync-agents and verify in single container instance
    cmd = """
    set -euo pipefail

    # Run sync-agents (files don't exist, so no prompt)
    cd /root/dotfiles && just sync-agents

    # Verify files exist
    [ -f /root/.claude/CLAUDE.md ] && echo "CLAUDE.md exists" || echo "CLAUDE.md missing"
    [ -f /root/.gemini/GEMINI.md ] && echo "GEMINI.md exists" || echo "GEMINI.md missing"
    [ -f /root/.codex/AGENTS.md ] && echo "AGENTS.md exists" || echo "AGENTS.md missing"

    # Check content matches source
    diff -q /root/dotfiles/ROOT_AGENTS.md /root/.claude/CLAUDE.md && echo "CLAUDE.md matches"
    diff -q /root/dotfiles/ROOT_AGENTS.md /root/.gemini/GEMINI.md && echo "GEMINI.md matches"
    diff -q /root/dotfiles/ROOT_AGENTS.md /root/.codex/AGENTS.md && echo "AGENTS.md matches"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Files were created and match source
    assert "CLAUDE.md exists" in result.stdout
    assert "GEMINI.md exists" in result.stdout
    assert "AGENTS.md exists" in result.stdout
    assert "CLAUDE.md matches" in result.stdout
    assert "GEMINI.md matches" in result.stdout
    assert "AGENTS.md matches" in result.stdout
    assert "Synced successfully" in result.stdout


def test_sync_agents_is_idempotent(docker_image):
    """Test that sync-agents is idempotent.

    Scenario:
    - given: Agent files already in sync
    - when: Run sync-agents again
    - then: No changes made, reports "already in sync"
    """
    # given: First run to create files, then run again
    cmd = """
    set -euo pipefail

    # First run - create files
    cd /root/dotfiles && just sync-agents

    # Second run - should report already in sync
    cd /root/dotfiles && just sync-agents
    """
    result = _run_in_container(docker_image, cmd)

    # then: Reports already in sync
    assert result.returncode == 0
    assert "Already in sync" in result.stdout
    assert result.stdout.count("Already in sync") >= 3  # All three files


def test_sync_agents_detects_differences(docker_image):
    """Test that sync-agents detects file differences.

    Scenario:
    - given: Agent file exists but has been modified
    - when: Run sync-agents
    - then: Differences are detected
    """
    # given: Create initial files then modify one, then run sync-agents again
    cmd = """
    set -euo pipefail

    # First run - create files
    cd /root/dotfiles && just sync-agents

    # Modify one file
    echo "# Modified content" >> /root/.claude/CLAUDE.md

    # Second run - should detect differences and answer 'n' to skip
    cd /root/dotfiles && just sync-agents << 'EOF' || true
n
EOF
    """
    result = _run_in_container(docker_image, cmd, check=False)

    # then: Detects differences
    assert "Differences detected" in result.stdout or "⚠️" in result.stdout


def test_sync_agents_creates_missing_directories(docker_image):
    """Test that sync-agents creates directories if they don't exist.

    Scenario:
    - given: Agent directories don't exist
    - when: Run sync-agents
    - then: Directories are created
    """
    # given: Fresh container (directories don't exist)
    # when: Run sync-agents and verify directories
    cmd = """
    set -euo pipefail

    # Run sync-agents
    cd /root/dotfiles && just sync-agents

    # Verify directories were created
    [ -d /root/.claude ] && echo ".claude directory exists"
    [ -d /root/.gemini ] && echo ".gemini directory exists"
    [ -d /root/.codex ] && echo ".codex directory exists"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Directories were created
    assert ".claude directory exists" in result.stdout
    assert ".gemini directory exists" in result.stdout
    assert ".codex directory exists" in result.stdout
