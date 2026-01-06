"""E2E tests for sync-agents just command.

These tests run in Docker containers to avoid polluting the host environment.
The sync-agents command syncs ROOT_AGENTS files to agent instruction directories.

File naming convention:
    ROOT_AGENTS.md                      -> <agent>/AGENT.md (base file)
    ROOT_AGENTS_commands_strict.md      -> <agent>/commands/strict.md
    ROOT_AGENTS_skills_my-skill/        -> <agent>/skills/my-skill/
    ROOT_AGENTS_hooks_formatter.py      -> <agent>/hooks/formatter.py
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
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


# =============================================================================
# Basic Functionality Tests
# =============================================================================


def test_sync_agents_creates_files_on_first_run(docker_image):
    """Test that sync-agents creates agent files on first run.

    Scenario:
    - given: Fresh container with no agent files
    - when: Run sync-agents command with --yes flag
    - then: Agent files are created
    """
    cmd = """
    set -euo pipefail

    # Run sync-agents with auto-yes (no prompts)
    cd /root/dotfiles && just sync-agents-auto

    # Verify files exist
    [ -f /root/.claude/CLAUDE.md ] && echo "CLAUDE.md exists" || echo "CLAUDE.md missing"
    [ -f /root/.gemini/GEMINI.md ] && echo "GEMINI.md exists" || echo "GEMINI.md missing"
    [ -f /root/.codex/AGENTS.md ] && echo "AGENTS.md exists" || echo "AGENTS.md missing"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Files were created
    assert "CLAUDE.md exists" in result.stdout
    assert "GEMINI.md exists" in result.stdout
    assert "AGENTS.md exists" in result.stdout


def test_sync_agents_is_idempotent(docker_image):
    """Test that sync-agents is idempotent.

    Scenario:
    - given: Agent files already in sync
    - when: Run sync-agents again
    - then: No changes made, reports "SYNCED"
    """
    cmd = """
    set -euo pipefail

    # First run - create files
    cd /root/dotfiles && just sync-agents-auto

    # Second run - should report synced
    cd /root/dotfiles && just sync-agents-preview
    """
    result = _run_in_container(docker_image, cmd)

    # then: Reports synced
    assert result.returncode == 0
    assert "SYNCED" in result.stdout


def test_sync_agents_creates_missing_directories(docker_image):
    """Test that sync-agents creates directories if they don't exist.

    Scenario:
    - given: Agent directories don't exist
    - when: Run sync-agents
    - then: Directories are created
    """
    cmd = """
    set -euo pipefail

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

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


# =============================================================================
# Path Conversion Tests
# =============================================================================


def test_sync_agents_converts_underscore_to_path(docker_image):
    """Test that ROOT_AGENTS_xxx_yyy.md becomes xxx/yyy.md.

    Scenario:
    - given: ROOT_AGENTS_commands_strict.md exists
    - when: Run sync-agents
    - then: File is synced to commands/strict.md
    """
    cmd = """
    set -euo pipefail

    # Verify source file exists
    [ -f /root/dotfiles/ROOT_AGENTS_commands_strict.md ] && echo "source exists"

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify converted path
    [ -f /root/.claude/commands/strict.md ] && echo "commands/strict.md exists"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Path conversion works
    assert "source exists" in result.stdout
    assert "commands/strict.md exists" in result.stdout


def test_sync_agents_handles_directory_sources(docker_image):
    """Test that ROOT_AGENTS_xxx_yyy/ becomes xxx/yyy/ with all contents.

    Scenario:
    - given: ROOT_AGENTS_skills_test-skill/ directory exists with multiple files and subdirs
    - when: Run sync-agents
    - then: Directory and ALL contents are synced to skills/test-skill/
    """
    cmd = """
    set -euo pipefail

    # Create a test directory source with multiple files and nested subdirectories
    mkdir -p /root/dotfiles/ROOT_AGENTS_skills_test-skill
    mkdir -p /root/dotfiles/ROOT_AGENTS_skills_test-skill/templates
    mkdir -p /root/dotfiles/ROOT_AGENTS_skills_test-skill/examples/advanced

    # Create files at various levels
    echo "# Test Skill README" > /root/dotfiles/ROOT_AGENTS_skills_test-skill/README.md
    echo "skill_name: test-skill" > /root/dotfiles/ROOT_AGENTS_skills_test-skill/config.yaml
    echo "template content" > /root/dotfiles/ROOT_AGENTS_skills_test-skill/templates/main.txt
    echo "example 1" > /root/dotfiles/ROOT_AGENTS_skills_test-skill/examples/basic.md
    echo "advanced example" > /root/dotfiles/ROOT_AGENTS_skills_test-skill/examples/advanced/complex.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify directory structure
    [ -d /root/.claude/skills/test-skill ] && echo "skills/test-skill/ exists"
    [ -d /root/.claude/skills/test-skill/templates ] && echo "templates/ subdir exists"
    [ -d /root/.claude/skills/test-skill/examples/advanced ] && echo "examples/advanced/ nested subdir exists"

    # Verify all files exist
    [ -f /root/.claude/skills/test-skill/README.md ] && echo "README.md exists"
    [ -f /root/.claude/skills/test-skill/config.yaml ] && echo "config.yaml exists"
    [ -f /root/.claude/skills/test-skill/templates/main.txt ] && echo "templates/main.txt exists"
    [ -f /root/.claude/skills/test-skill/examples/basic.md ] && echo "examples/basic.md exists"
    [ -f /root/.claude/skills/test-skill/examples/advanced/complex.md ] && echo "examples/advanced/complex.md exists"

    # Verify file contents are correct
    grep -q "Test Skill README" /root/.claude/skills/test-skill/README.md && echo "README content correct"
    grep -q "skill_name: test-skill" /root/.claude/skills/test-skill/config.yaml && echo "config content correct"
    grep -q "advanced example" /root/.claude/skills/test-skill/examples/advanced/complex.md && echo "nested content correct"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Directory and all contents are synced
    assert "skills/test-skill/ exists" in result.stdout
    assert "templates/ subdir exists" in result.stdout
    assert "examples/advanced/ nested subdir exists" in result.stdout
    assert "README.md exists" in result.stdout
    assert "config.yaml exists" in result.stdout
    assert "templates/main.txt exists" in result.stdout
    assert "examples/basic.md exists" in result.stdout
    assert "examples/advanced/complex.md exists" in result.stdout
    assert "README content correct" in result.stdout
    assert "config content correct" in result.stdout
    assert "nested content correct" in result.stdout


def test_sync_agents_handles_python_file_extension(docker_image):
    """Test that ROOT_AGENTS_hooks_formatter.py becomes hooks/formatter.py.

    Scenario:
    - given: ROOT_AGENTS_hooks_formatter.py exists
    - when: Run sync-agents
    - then: File is synced to hooks/formatter.py
    """
    cmd = """
    set -euo pipefail

    # Create a test Python file
    echo '#!/usr/bin/env python3' > /root/dotfiles/ROOT_AGENTS_hooks_formatter.py
    echo 'print("Hello")' >> /root/dotfiles/ROOT_AGENTS_hooks_formatter.py

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify converted path
    [ -f /root/.claude/hooks/formatter.py ] && echo "hooks/formatter.py exists"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Python file is synced
    assert "hooks/formatter.py exists" in result.stdout


# =============================================================================
# Preview Mode Tests
# =============================================================================


def test_sync_agents_preview_shows_plan(docker_image):
    """Test that preview mode shows sync plan without making changes.

    Scenario:
    - given: Fresh container
    - when: Run sync-agents-preview
    - then: Shows plan but doesn't create files
    """
    cmd = """
    set -euo pipefail

    # Run preview
    cd /root/dotfiles && just sync-agents-preview

    # Verify files were NOT created
    if [ -f /root/.claude/CLAUDE.md ]; then
        echo "ERROR: file was created in preview mode"
        exit 1
    else
        echo "no files created (expected)"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: Preview shown, no files created
    assert "Preview" in result.stdout or "Dry Run" in result.stdout
    assert "no files created (expected)" in result.stdout


def test_sync_agents_preview_shows_new_files(docker_image):
    """Test that preview mode shows NEW status for missing files.

    Scenario:
    - given: Agent files don't exist
    - when: Run sync-agents-preview
    - then: Shows NEW status
    """
    cmd = """
    set -euo pipefail

    cd /root/dotfiles && just sync-agents-preview
    """
    result = _run_in_container(docker_image, cmd)

    # then: Shows NEW status
    assert "[NEW]" in result.stdout


def test_sync_agents_preview_shows_synced_files(docker_image):
    """Test that preview mode shows SYNCED status for up-to-date files.

    Scenario:
    - given: Agent files are already synced
    - when: Run sync-agents-preview
    - then: Shows SYNCED status
    """
    cmd = """
    set -euo pipefail

    # First, sync files
    cd /root/dotfiles && just sync-agents-auto

    # Then preview
    cd /root/dotfiles && just sync-agents-preview
    """
    result = _run_in_container(docker_image, cmd)

    # then: Shows SYNCED status
    assert "[SYNCED]" in result.stdout


# =============================================================================
# Change Detection Tests
# =============================================================================


def test_sync_agents_detects_changed_files(docker_image):
    """Test that sync-agents detects when target files have changed.

    Scenario:
    - given: Agent file has been modified
    - when: Run sync-agents-preview
    - then: Shows CHANGED status
    """
    cmd = """
    set -euo pipefail

    # First, sync files
    cd /root/dotfiles && just sync-agents-auto

    # Modify target file
    echo "# Modified" >> /root/.claude/CLAUDE.md

    # Preview to see changes
    cd /root/dotfiles && just sync-agents-preview
    """
    result = _run_in_container(docker_image, cmd)

    # then: Shows CHANGED status
    assert "[CHANGED]" in result.stdout


# =============================================================================
# Error Handling Tests
# =============================================================================


def test_sync_agents_fails_without_base_file(docker_image):
    """Test that sync-agents fails gracefully when base file is missing.

    Scenario:
    - given: ROOT_AGENTS.md doesn't exist
    - when: Run sync-agents
    - then: Script exits with error
    """
    cmd = """
    set -uo pipefail

    # Remove base file
    rm -f /root/dotfiles/ROOT_AGENTS.md

    # Run sync-agents (should fail)
    cd /root/dotfiles && just sync-agents-auto 2>&1 || echo "script failed as expected"
    """
    result = _run_in_container(docker_image, cmd, check=False)

    # then: Script fails with appropriate error
    assert "Base file not found" in result.stdout or "script failed as expected" in result.stdout


# =============================================================================
# Multi-Agent Sync Tests
# =============================================================================


def test_sync_agents_syncs_to_all_agents(docker_image):
    """Test that sync-agents syncs to all configured agents.

    Scenario:
    - given: Multiple agents configured
    - when: Run sync-agents
    - then: All agents receive the files
    """
    cmd = """
    set -euo pipefail

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify all agents have files
    [ -f /root/.claude/CLAUDE.md ] && echo "claude ok"
    [ -f /root/.claude-work-a/CLAUDE.md ] && echo "claude-work-a ok"
    [ -f /root/.gemini/GEMINI.md ] && echo "gemini ok"
    [ -f /root/.codex/AGENTS.md ] && echo "codex ok"
    """
    result = _run_in_container(docker_image, cmd)

    # then: All agents synced
    assert "claude ok" in result.stdout
    assert "claude-work-a ok" in result.stdout
    assert "gemini ok" in result.stdout
    assert "codex ok" in result.stdout
