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
    - given: ROOT_AGENTS_hooks_formatter.md is created (legacy naming)
    - when: Run sync-agents
    - then: File is synced to hooks/formatter.md
    """
    cmd = """
    set -euo pipefail

    # Create a legacy-named file
    echo "# Legacy Hook" > /root/dotfiles/ROOT_AGENTS_hooks_formatter.md

    # Verify source file exists
    [ -f /root/dotfiles/ROOT_AGENTS_hooks_formatter.md ] && echo "source exists"

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify converted path
    [ -f /root/.claude/hooks/formatter.md ] && echo "hooks/formatter.md exists"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Path conversion works
    assert "source exists" in result.stdout
    assert "hooks/formatter.md exists" in result.stdout


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
    assert (
        "Base file not found" in result.stdout
        or "script failed as expected" in result.stdout
    )


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


# =============================================================================
# Per-Item Sync Tests (unmanaged items preserved)
# =============================================================================


def test_sync_agents_preserves_unmanaged_items_in_target(docker_image):
    """Test that sync preserves items in target not managed by dotfiles.

    Scenario:
    - given: Target has an extra skill (e.g. a symlink-installed plugin)
    - when: Run sync-agents
    - then: The extra skill is preserved, dotfiles skills are synced
    """
    cmd = """
    set -euo pipefail

    # Create a dotfiles skill
    mkdir -p /root/dotfiles/skills/my-skill
    echo "# My Skill" > /root/dotfiles/skills/my-skill/README.md

    # First sync - creates target skills
    cd /root/dotfiles && just sync-agents-auto

    # Add an extra item in target (simulating plugin install)
    mkdir -p /root/.claude/skills/external-plugin
    echo "# External Plugin" > /root/.claude/skills/external-plugin/README.md

    # Run sync again
    cd /root/dotfiles && just sync-agents-auto

    # Verify both exist
    [ -f /root/.claude/skills/my-skill/README.md ] && echo "dotfiles skill preserved"
    [ -f /root/.claude/skills/external-plugin/README.md ] && echo "external plugin preserved"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Both items exist
    assert "dotfiles skill preserved" in result.stdout
    assert "external plugin preserved" in result.stdout


# =============================================================================
# Import (symlink resolution) Tests
# =============================================================================


def test_sync_agents_imports_symlinked_skills_from_target(docker_image):
    """Test that symlinks in target are resolved and imported to dotfiles.

    Scenario:
    - given: Target (~/.claude/skills/) has a symlink to an external skill
    - when: Run sync-agents
    - then: Symlink is resolved and real content is copied to dotfiles/skills/
    """
    cmd = """
    set -euo pipefail

    # Create an external skill directory (the symlink target)
    mkdir -p /opt/external-skills/cool-plugin
    echo "# Cool Plugin" > /opt/external-skills/cool-plugin/README.md
    echo "skill content" > /opt/external-skills/cool-plugin/skill.md

    # Set up ~/.claude/skills/ with a symlink to the external skill
    mkdir -p /root/.claude/skills
    ln -s /opt/external-skills/cool-plugin /root/.claude/skills/cool-plugin

    # Verify symlink exists
    [ -L /root/.claude/skills/cool-plugin ] && echo "symlink exists"

    # Run sync-agents (import phase should detect and import the symlink)
    cd /root/dotfiles && just sync-agents-auto

    # Verify the skill was imported to dotfiles
    [ -d /root/dotfiles/skills/cool-plugin ] && echo "imported to dotfiles"
    [ -f /root/dotfiles/skills/cool-plugin/README.md ] && echo "README imported"
    [ -f /root/dotfiles/skills/cool-plugin/skill.md ] && echo "skill.md imported"

    # Verify it's a real directory, not a symlink
    [ ! -L /root/dotfiles/skills/cool-plugin ] && echo "not a symlink in dotfiles"

    # Verify content
    grep -q "Cool Plugin" /root/dotfiles/skills/cool-plugin/README.md && echo "content correct"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Symlink was resolved and imported
    assert "symlink exists" in result.stdout
    assert "imported to dotfiles" in result.stdout
    assert "README imported" in result.stdout
    assert "skill.md imported" in result.stdout
    assert "not a symlink in dotfiles" in result.stdout
    assert "content correct" in result.stdout


def test_sync_agents_imports_regular_directories(docker_image):
    """Test that regular directories (not just symlinks) are imported.

    Scenario:
    - given: Target has a regular directory (not a symlink)
    - when: Run sync-agents
    - then: Regular directory IS imported to dotfiles
    """
    cmd = """
    set -euo pipefail

    # Set up target with a regular (non-symlink) skill directory
    mkdir -p /root/.claude/skills/manual-skill
    echo "# Manual Skill" > /root/.claude/skills/manual-skill/README.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify the regular dir WAS imported to dotfiles
    if [ -d /root/dotfiles/skills/manual-skill ]; then
        echo "regular dir imported"
        grep -q "Manual Skill" /root/dotfiles/skills/manual-skill/README.md && echo "content correct"
    else
        echo "ERROR: regular dir was not imported"
    fi

    # Verify it was also synced to other targets
    [ -f /root/.gemini/skills/manual-skill/README.md ] && echo "synced to gemini"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Regular directory was imported and synced
    assert "regular dir imported" in result.stdout
    assert "content correct" in result.stdout
    assert "synced to gemini" in result.stdout


def test_sync_agents_keeps_newer_dotfiles_over_older_symlink(docker_image):
    """Test that newer dotfiles version wins over older symlink target.

    Scenario:
    - given: Target has a symlink to external content, dotfiles has newer version
    - when: Run sync-agents
    - then: Dotfiles version is preserved (newer wins)
    """
    cmd = """
    set -euo pipefail

    # Create external version first (older)
    mkdir -p /opt/external/shared-skill
    echo "# External version (older)" > /opt/external/shared-skill/README.md

    # Symlink in target to the external version
    mkdir -p /root/.claude/skills
    ln -s /opt/external/shared-skill /root/.claude/skills/shared-skill

    # Wait to ensure mtime difference
    sleep 2

    # Create newer version in dotfiles
    mkdir -p /root/dotfiles/skills/shared-skill
    echo "# Dotfiles version (newer)" > /root/dotfiles/skills/shared-skill/README.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify dotfiles version was preserved (it's newer)
    grep -q "Dotfiles version (newer)" /root/dotfiles/skills/shared-skill/README.md && echo "dotfiles version preserved"

    # Verify targets got the dotfiles version
    grep -q "Dotfiles version (newer)" /root/.claude/skills/shared-skill/README.md && echo "claude got dotfiles version"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Dotfiles version was preserved
    assert "dotfiles version preserved" in result.stdout
    assert "claude got dotfiles version" in result.stdout


# =============================================================================
# Bidirectional Sync Full Cycle Tests
# =============================================================================


def test_sync_agents_full_bidirectional_cycle(docker_image):
    """Test full bidirectional sync: import symlink -> forward sync to all targets.

    Scenario:
    - given: An external skill is symlinked into ~/.claude/skills/
    - when: Run sync-agents
    - then: Skill is imported to dotfiles AND synced to all other targets
    """
    cmd = """
    set -euo pipefail

    # Create an external skill
    mkdir -p /opt/plugins/awesome-plugin
    echo "# Awesome Plugin" > /opt/plugins/awesome-plugin/README.md

    # Symlink it into ~/.claude/skills/
    mkdir -p /root/.claude/skills
    ln -s /opt/plugins/awesome-plugin /root/.claude/skills/awesome-plugin

    # Run sync-agents (should import + forward sync)
    cd /root/dotfiles && just sync-agents-auto

    # Verify Phase 1: imported to dotfiles
    [ -d /root/dotfiles/skills/awesome-plugin ] && echo "imported to dotfiles"
    [ ! -L /root/dotfiles/skills/awesome-plugin ] && echo "real dir in dotfiles"

    # Verify Phase 3: synced to other targets
    [ -f /root/.gemini/skills/awesome-plugin/README.md ] && echo "synced to gemini"
    [ -f /root/.codex/skills/awesome-plugin/README.md ] && echo "synced to codex"
    [ -f /root/.claude-work-a/skills/awesome-plugin/README.md ] && echo "synced to claude-work-a"

    # Run preview to confirm everything is in sync
    cd /root/dotfiles && just sync-agents-preview 2>&1 | tail -3
    """
    result = _run_in_container(docker_image, cmd)

    # then: Full bidirectional cycle works
    assert "imported to dotfiles" in result.stdout
    assert "real dir in dotfiles" in result.stdout
    assert "synced to gemini" in result.stdout
    assert "synced to codex" in result.stdout
    assert "synced to claude-work-a" in result.stdout


def test_sync_agents_import_only_from_import_source(docker_image):
    """Test that import only happens from agents with is_import_source=True.

    Scenario:
    - given: A symlink exists in ~/.gemini/skills/ (not an import source)
    - when: Run sync-agents
    - then: Symlink is NOT imported to dotfiles
    """
    cmd = """
    set -euo pipefail

    # Create an external skill symlinked into gemini (NOT an import source)
    mkdir -p /opt/gemini-plugin/special
    echo "# Gemini Plugin" > /opt/gemini-plugin/special/README.md
    mkdir -p /root/.gemini/skills
    ln -s /opt/gemini-plugin/special /root/.gemini/skills/special

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify the symlink was NOT imported to dotfiles
    if [ -d /root/dotfiles/skills/special ]; then
        echo "ERROR: imported from non-import-source"
    else
        echo "correctly skipped non-import-source"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: No import from non-import-source
    assert "correctly skipped non-import-source" in result.stdout


# =============================================================================
# Manifest and Deletion Sync Tests
# =============================================================================


def test_sync_agents_creates_manifest_on_first_run(docker_image):
    """Test that .sync-manifest.json is auto-created on first run.

    Scenario:
    - given: No manifest file exists
    - when: Run sync-agents
    - then: Manifest is created with current dotfiles items
    """
    cmd = """
    set -euo pipefail

    # Ensure no manifest exists
    rm -f /root/dotfiles/.sync-manifest.json

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify manifest was created
    [ -f /root/dotfiles/.sync-manifest.json ] && echo "manifest created"

    # Verify manifest contains version and skills
    grep -q '"version"' /root/dotfiles/.sync-manifest.json && echo "has version"
    grep -q '"skills"' /root/dotfiles/.sync-manifest.json && echo "has skills key"
    grep -q 'brand-legal-review' /root/dotfiles/.sync-manifest.json && echo "has brand-legal-review"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Manifest was created with items
    assert "manifest created" in result.stdout
    assert "has version" in result.stdout
    assert "has skills key" in result.stdout
    assert "has brand-legal-review" in result.stdout


def test_sync_agents_deletes_removed_items_from_targets(docker_image):
    """Test that items removed from dotfiles are deleted from all targets.

    Scenario:
    - given: A skill exists in dotfiles and is synced to targets
    - when: Skill is removed from dotfiles and sync runs again
    - then: Skill is deleted from all targets
    """
    cmd = """
    set -euo pipefail

    # Create a skill in dotfiles
    mkdir -p /root/dotfiles/skills/temp-skill
    echo "# Temp Skill" > /root/dotfiles/skills/temp-skill/README.md

    # First sync: distributes temp-skill to all targets
    cd /root/dotfiles && just sync-agents-auto

    # Verify it was synced
    [ -f /root/.claude/skills/temp-skill/README.md ] && echo "synced to claude"
    [ -f /root/.gemini/skills/temp-skill/README.md ] && echo "synced to gemini"

    # Now delete from dotfiles
    rm -rf /root/dotfiles/skills/temp-skill

    # Second sync: should delete from all targets
    cd /root/dotfiles && just sync-agents-auto

    # Verify deletion
    if [ -d /root/.claude/skills/temp-skill ]; then
        echo "ERROR: not deleted from claude"
    else
        echo "deleted from claude"
    fi
    if [ -d /root/.gemini/skills/temp-skill ]; then
        echo "ERROR: not deleted from gemini"
    else
        echo "deleted from gemini"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: Skill was synced then deleted
    assert "synced to claude" in result.stdout
    assert "synced to gemini" in result.stdout
    assert "deleted from claude" in result.stdout
    assert "deleted from gemini" in result.stdout


def test_sync_agents_does_not_reimport_deleted_items(docker_image):
    """Test that items deleted from dotfiles are NOT re-imported from targets.

    Scenario:
    - given: A skill was imported, synced, then deleted from dotfiles
    - when: Run sync-agents again
    - then: The skill is NOT re-imported (manifest prevents it)
    """
    cmd = """
    set -euo pipefail

    # Create and import a skill via import source
    mkdir -p /root/.claude/skills/ephemeral-skill
    echo "# Ephemeral" > /root/.claude/skills/ephemeral-skill/README.md

    # First sync: imports to dotfiles, syncs to targets
    cd /root/dotfiles && just sync-agents-auto
    [ -d /root/dotfiles/skills/ephemeral-skill ] && echo "initially imported"

    # Delete from dotfiles (simulating intentional removal)
    rm -rf /root/dotfiles/skills/ephemeral-skill

    # Second sync: should NOT re-import, should delete from targets
    cd /root/dotfiles && just sync-agents-auto

    # Verify NOT re-imported to dotfiles
    if [ -d /root/dotfiles/skills/ephemeral-skill ]; then
        echo "ERROR: re-imported to dotfiles"
    else
        echo "correctly not re-imported"
    fi

    # Verify deleted from claude (import source)
    if [ -d /root/.claude/skills/ephemeral-skill ]; then
        echo "ERROR: still in claude"
    else
        echo "deleted from claude"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: Not re-imported and deleted from targets
    assert "initially imported" in result.stdout
    assert "correctly not re-imported" in result.stdout
    assert "deleted from claude" in result.stdout


def test_sync_agents_imports_from_codex(docker_image):
    """Test that skills from ~/.codex/ (import source) are imported.

    Scenario:
    - given: A skill exists in ~/.codex/skills/ (an import source)
    - when: Run sync-agents
    - then: Skill is imported to dotfiles and synced to other targets
    """
    cmd = """
    set -euo pipefail

    # Create a codex-native skill
    mkdir -p /root/.codex/skills/codex-native
    echo "# Codex Native" > /root/.codex/skills/codex-native/README.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify imported to dotfiles
    [ -d /root/dotfiles/skills/codex-native ] && echo "imported to dotfiles"

    # Verify synced to other targets
    [ -f /root/.claude/skills/codex-native/README.md ] && echo "synced to claude"
    [ -f /root/.gemini/skills/codex-native/README.md ] && echo "synced to gemini"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Codex skill was imported and synced
    assert "imported to dotfiles" in result.stdout
    assert "synced to claude" in result.stdout
    assert "synced to gemini" in result.stdout


def test_sync_agents_skips_hidden_directories(docker_image):
    """Test that hidden directories (starting with .) are skipped.

    Scenario:
    - given: A hidden directory exists in ~/.codex/skills/.system/
    - when: Run sync-agents
    - then: Hidden directory is NOT imported
    """
    cmd = """
    set -euo pipefail

    # Create a hidden directory in codex skills
    mkdir -p /root/.codex/skills/.system/internal
    echo "# Internal" > /root/.codex/skills/.system/internal/README.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify hidden dir was NOT imported
    if [ -d /root/dotfiles/skills/.system ]; then
        echo "ERROR: hidden dir was imported"
    else
        echo "hidden dir correctly skipped"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: Hidden directory was skipped
    assert "hidden dir correctly skipped" in result.stdout


def test_sync_agents_replaces_symlinks_in_targets(docker_image):
    """Test that symlinks in targets are replaced with real directories.

    Scenario:
    - given: A skill exists in dotfiles AND target has a symlink with same name
    - when: Run sync-agents
    - then: Symlink is replaced with a real directory copy
    """
    cmd = """
    set -euo pipefail

    # Create a skill in dotfiles
    mkdir -p /root/dotfiles/skills/real-skill
    echo "# Real Skill" > /root/dotfiles/skills/real-skill/README.md

    # Create a symlink in gemini pointing elsewhere
    mkdir -p /opt/other/real-skill
    echo "# Other" > /opt/other/real-skill/README.md
    mkdir -p /root/.gemini/skills
    ln -s /opt/other/real-skill /root/.gemini/skills/real-skill

    # Verify it's a symlink before sync
    [ -L /root/.gemini/skills/real-skill ] && echo "is symlink before"

    # Run sync-agents
    cd /root/dotfiles && just sync-agents-auto

    # Verify symlink was replaced with real dir
    if [ -L /root/.gemini/skills/real-skill ]; then
        echo "ERROR: still a symlink"
    else
        echo "replaced with real dir"
    fi
    grep -q "Real Skill" /root/.gemini/skills/real-skill/README.md && echo "correct content"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Symlink was replaced
    assert "is symlink before" in result.stdout
    assert "replaced with real dir" in result.stdout
    assert "correct content" in result.stdout


def test_sync_agents_newer_import_source_wins_conflict(docker_image):
    """Test that newer files in import source overwrite older dotfiles version.

    Scenario:
    - given: A skill exists in both dotfiles and import source with different content
    - when: The import source version is newer (by mtime)
    - then: The newer import source version overwrites dotfiles
    """
    cmd = """
    set -euo pipefail

    # Create a skill in dotfiles (older version)
    mkdir -p /root/dotfiles/skills/evolving-skill
    echo "# Version 1" > /root/dotfiles/skills/evolving-skill/README.md

    # First sync to distribute
    cd /root/dotfiles && just sync-agents-auto

    # Wait to ensure mtime difference
    sleep 2

    # Edit the skill in import source (newer version)
    echo "# Version 2 - Updated" > /root/.claude/skills/evolving-skill/README.md

    # Run sync again
    cd /root/dotfiles && just sync-agents-auto

    # Verify dotfiles was updated with newer version
    grep -q "Version 2" /root/dotfiles/skills/evolving-skill/README.md && echo "dotfiles updated"

    # Verify all targets got the newer version
    grep -q "Version 2" /root/.gemini/skills/evolving-skill/README.md && echo "gemini updated"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Newer version won
    assert "dotfiles updated" in result.stdout
    assert "gemini updated" in result.stdout


def test_sync_agents_older_import_source_loses_conflict(docker_image):
    """Test that older files in import source do NOT overwrite newer dotfiles.

    Scenario:
    - given: A skill exists in both dotfiles and import source with different content
    - when: The dotfiles version is newer (by mtime)
    - then: Dotfiles version is preserved and pushed to targets
    """
    cmd = """
    set -euo pipefail

    # Create a skill in import source first (older)
    mkdir -p /root/.claude/skills/stable-skill
    echo "# Old Version" > /root/.claude/skills/stable-skill/README.md

    # Wait to ensure mtime difference
    sleep 2

    # Create newer version in dotfiles
    mkdir -p /root/dotfiles/skills/stable-skill
    echo "# New Version in Dotfiles" > /root/dotfiles/skills/stable-skill/README.md

    # Run sync
    cd /root/dotfiles && just sync-agents-auto

    # Verify dotfiles version was preserved
    grep -q "New Version in Dotfiles" /root/dotfiles/skills/stable-skill/README.md && echo "dotfiles preserved"

    # Verify targets got the dotfiles version (not the older import source version)
    grep -q "New Version in Dotfiles" /root/.gemini/skills/stable-skill/README.md && echo "gemini got dotfiles version"
    grep -q "New Version in Dotfiles" /root/.claude/skills/stable-skill/README.md && echo "claude got dotfiles version"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Dotfiles version was preserved
    assert "dotfiles preserved" in result.stdout
    assert "gemini got dotfiles version" in result.stdout
    assert "claude got dotfiles version" in result.stdout
