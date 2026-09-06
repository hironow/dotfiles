"""E2E tests for sync-agents just command.

These tests run in Docker containers to avoid polluting the host environment.
The sync-agents command syncs ROOT_AGENTS files to agent instruction directories.

File naming convention:
    ROOT_AGENTS.md                      -> <agent>/AGENT.md (base file)
    ROOT_AGENTS_commands_strict.md      -> <agent>/commands/strict.md
    ROOT_AGENTS_hooks_formatter.py      -> <agent>/hooks/formatter.py
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER_JSON = ROOT / ".devcontainer" / "devcontainer.json"
IMAGE = "dotfiles-just-sandbox:latest"


def _copy_tracked_into(src: str, snapshot: str) -> None:
    """Copy git-tracked files into snapshot.

    Same rationale as test_just_sandbox.py: the container must never see
    the real repo. This suite's containers even run `sync-agents import`
    style commands that WRITE into /root/dotfiles, so a direct bind mount
    mutates the mounted tree (observed: deleted ROOT_AGENTS.md, junk
    commands). Every test gets its own disposable snapshot via the
    autouse fixture below.
    """
    tracked = subprocess.run(
        ["git", "-C", src, "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout.decode()
    for rel in tracked.split("\0"):
        if not rel:
            continue
        source = os.path.join(src, rel)
        if not os.path.isfile(source):  # skip gitlinks / vanished paths
            continue
        dest = os.path.join(snapshot, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(source, dest, follow_symlinks=False)


# Mount source for the current test's containers (set by the autouse
# fixture; None only outside tests).
_SANDBOX_REPO: str | None = None


@pytest.fixture(autouse=True)
def sandbox_repo():
    """Give every test a disposable repo copy to mount instead of the host
    working tree. Bind-mounting the checkout directly (even the ephemeral CI
    one) is not enough: tests mutate /root/dotfiles, so a shared mount
    cross-contaminates the suite (observed as 44 CI failures).

    Under docker-outside-of-docker (CI; LOCAL_WORKSPACE_FOLDER set) mount
    sources must be HOST paths, so the snapshot is created inside the
    workspace itself and its host path derived via LOCAL_WORKSPACE_FOLDER."""
    global _SANDBOX_REPO
    lwf = os.environ.get("LOCAL_WORKSPACE_FOLDER")
    if lwf:
        snapshots_root = ROOT / ".e2e-snapshots"
        snapshots_root.mkdir(exist_ok=True)
        snapshot = tempfile.mkdtemp(prefix="snap-", dir=str(snapshots_root))
        _copy_tracked_into(str(ROOT), snapshot)
        _SANDBOX_REPO = os.path.join(lwf, os.path.relpath(snapshot, str(ROOT)))
        yield
        _SANDBOX_REPO = None
        shutil.rmtree(snapshot, ignore_errors=True)
        return
    snapshot = tempfile.mkdtemp(prefix="dotfiles-syncagents-")
    _copy_tracked_into(str(ROOT), snapshot)
    _SANDBOX_REPO = snapshot
    yield
    _SANDBOX_REPO = None
    shutil.rmtree(snapshot, ignore_errors=True)


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
        capture_output=True,
        check=False,
    )


def _docker_available() -> bool:
    """Check if Docker is available."""
    r = _run(["docker", "info"])
    return r.returncode == 0


def _devcontainer_cli_available() -> bool:
    r = _run(["devcontainer", "--version"])
    return r.returncode == 0


def _image_exists(image: str) -> bool:
    return _run(["docker", "image", "inspect", image]).returncode == 0


@pytest.fixture(scope="module")
def docker_image():
    """Provide the dotfiles dev container image, mirroring
    test_just_sandbox.py: reuse the CI-prebuilt image when present,
    fall back to a local devcontainer build."""
    if not _docker_available():
        pytest.skip("Docker is not available; skipping e2e tests.")

    if not DEVCONTAINER_JSON.exists():
        pytest.skip("devcontainer.json missing; skipping e2e tests.")

    if _image_exists(IMAGE):
        yield IMAGE
        return

    if not _devcontainer_cli_available():
        pytest.skip(
            "Image 'dotfiles-just-sandbox:latest' not present and the "
            "@devcontainers/cli is not installed. Run "
            "`npm i -g @devcontainers/cli` or rely on CI."
        )

    build_cmd = [
        "devcontainer",
        "build",
        "--workspace-folder",
        str(ROOT),
        "--image-name",
        IMAGE,
    ]
    result = _run(build_cmd, cwd=ROOT)
    if result.returncode != 0:
        pytest.fail(f"devcontainer build failed: {result.stderr}")

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
    # /root/dotfiles is a bind mount in devcontainer.json, not a
    # baked-in COPY layer. Re-create the mount for each one-shot
    # container so the workspace is reachable — mounting the per-test
    # snapshot (sandbox_repo fixture), never the host working tree.
    # Forward GITHUB_TOKEN for the same reason as in test_just_sandbox.py.
    assert _SANDBOX_REPO is not None, "sandbox_repo fixture not active"
    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{_SANDBOX_REPO}:/root/dotfiles",
        "-w",
        "/root/dotfiles",
    ]
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if gh_token:
        docker_cmd.extend(["-e", f"GITHUB_TOKEN={gh_token}"])
    docker_cmd.extend([docker_image, "bash", "-c", cmd])
    result = _run(docker_cmd)

    if check and result.returncode != 0:
        pytest.fail(
            f"Command failed with exit code {result.returncode}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )

    return result


# =============================================================================
# Default-Scope Tests (claude only)
# =============================================================================


def test_sync_agents_default_targets_claude_only(docker_image):
    """Default invocation (no targets) must touch only ~/.claude.

    Scenario:
    - given: Fresh container with no agent files
    - when: Run sync-agents WITHOUT any targets (new default)
    - then: ~/.claude/CLAUDE.md is created, but ~/.gemini, ~/.codex,
            ~/.claude-work-a are NOT created
    """
    cmd = """
    set -euo pipefail

    cd /root/dotfiles && just sync-agents

    [ -f /root/.claude/CLAUDE.md ] && echo "CLAUDE.md exists" || echo "CLAUDE.md missing"
    [ ! -d /root/.gemini ] && echo "gemini absent" || echo "gemini PRESENT"
    [ ! -d /root/.codex ] && echo "codex absent" || echo "codex PRESENT"
    [ ! -d /root/.claude-work-a ] && echo "work-a absent" || echo "work-a PRESENT"
    """
    result = _run_in_container(docker_image, cmd)

    assert "CLAUDE.md exists" in result.stdout
    assert "gemini absent" in result.stdout
    assert "codex absent" in result.stdout
    assert "work-a absent" in result.stdout


def test_sync_agents_explicit_target_widens_scope(docker_image):
    """Passing target identifiers extends sync scope beyond claude.

    Scenario:
    - given: Fresh container
    - when: Run sync-agents with explicit targets `p a`
    - then: ~/.claude AND ~/.claude-work-a are populated, others stay empty
    """
    cmd = """
    set -euo pipefail

    cd /root/dotfiles && just sync-agents p a

    [ -f /root/.claude/CLAUDE.md ] && echo "claude ok"
    [ -f /root/.claude-work-a/CLAUDE.md ] && echo "work-a ok"
    [ ! -d /root/.gemini ] && echo "gemini absent" || echo "gemini PRESENT"
    [ ! -d /root/.codex ] && echo "codex absent" || echo "codex PRESENT"
    """
    result = _run_in_container(docker_image, cmd)

    assert "claude ok" in result.stdout
    assert "work-a ok" in result.stdout
    assert "gemini absent" in result.stdout
    assert "codex absent" in result.stdout


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
    cd /root/dotfiles && just sync-agents all

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
    cd /root/dotfiles && just sync-agents all

    # Second run - should report synced
    cd /root/dotfiles && just sync-agents-preview all
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
    cd /root/dotfiles && just sync-agents all

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
    cd /root/dotfiles && just sync-agents all

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
    - given: ROOT_AGENTS_agents_test-skill/ directory exists with multiple files and subdirs
    - when: Run sync-agents
    - then: Directory and ALL contents are synced to agents/test-skill/
    """
    cmd = """
    set -euo pipefail

    # Create a test directory source with multiple files and nested subdirectories
    mkdir -p /root/dotfiles/ROOT_AGENTS_agents_test-skill
    mkdir -p /root/dotfiles/ROOT_AGENTS_agents_test-skill/templates
    mkdir -p /root/dotfiles/ROOT_AGENTS_agents_test-skill/examples/advanced

    # Create files at various levels
    echo "# Test Skill README" > /root/dotfiles/ROOT_AGENTS_agents_test-skill/README.md
    echo "skill_name: test-skill" > /root/dotfiles/ROOT_AGENTS_agents_test-skill/config.yaml
    echo "template content" > /root/dotfiles/ROOT_AGENTS_agents_test-skill/templates/main.txt
    echo "example 1" > /root/dotfiles/ROOT_AGENTS_agents_test-skill/examples/basic.md
    echo "advanced example" > /root/dotfiles/ROOT_AGENTS_agents_test-skill/examples/advanced/complex.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify directory structure
    [ -d /root/.claude/agents/test-skill ] && echo "agents/test-skill/ exists"
    [ -d /root/.claude/agents/test-skill/templates ] && echo "templates/ subdir exists"
    [ -d /root/.claude/agents/test-skill/examples/advanced ] && echo "examples/advanced/ nested subdir exists"

    # Verify all files exist
    [ -f /root/.claude/agents/test-skill/README.md ] && echo "README.md exists"
    [ -f /root/.claude/agents/test-skill/config.yaml ] && echo "config.yaml exists"
    [ -f /root/.claude/agents/test-skill/templates/main.txt ] && echo "templates/main.txt exists"
    [ -f /root/.claude/agents/test-skill/examples/basic.md ] && echo "examples/basic.md exists"
    [ -f /root/.claude/agents/test-skill/examples/advanced/complex.md ] && echo "examples/advanced/complex.md exists"

    # Verify file contents are correct
    grep -q "Test Skill README" /root/.claude/agents/test-skill/README.md && echo "README content correct"
    grep -q "skill_name: test-skill" /root/.claude/agents/test-skill/config.yaml && echo "config content correct"
    grep -q "advanced example" /root/.claude/agents/test-skill/examples/advanced/complex.md && echo "nested content correct"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Directory and all contents are synced
    assert "agents/test-skill/ exists" in result.stdout
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
    cd /root/dotfiles && just sync-agents all

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
    cd /root/dotfiles && just sync-agents-preview all

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

    cd /root/dotfiles && just sync-agents-preview all
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
    cd /root/dotfiles && just sync-agents all

    # Then preview
    cd /root/dotfiles && just sync-agents-preview all
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
    cd /root/dotfiles && just sync-agents all

    # Modify target file
    echo "# Modified" >> /root/.claude/CLAUDE.md

    # Preview to see changes
    cd /root/dotfiles && just sync-agents-preview all
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
    cd /root/dotfiles && just sync-agents all 2>&1 || echo "script failed as expected"
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
    cd /root/dotfiles && just sync-agents all

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


# =============================================================================
# Import (symlink resolution) Tests
# =============================================================================


# =============================================================================
# Bidirectional Sync Full Cycle Tests
# =============================================================================


def test_sync_agents_import_only_from_import_source(docker_image):
    """Test that import only happens from agents with is_import_source=True.

    Scenario:
    - given: A symlink exists in ~/.gemini/agents/ (not an import source)
    - when: Run sync-agents
    - then: Symlink is NOT imported to dotfiles
    """
    cmd = """
    set -euo pipefail

    # Create an external agent symlinked into gemini (NOT an import source)
    mkdir -p /opt/gemini-plugin/special
    echo "# Gemini Plugin" > /opt/gemini-plugin/special/README.md
    mkdir -p /root/.gemini/agents
    ln -s /opt/gemini-plugin/special /root/.gemini/agents/special

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify the symlink was NOT imported to dotfiles
    if [ -d /root/dotfiles/agents/special ]; then
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

    # Hermetic probe command
    mkdir -p /root/dotfiles/commands
    echo "# Probe" > /root/dotfiles/commands/probe-cmd.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify manifest was created
    [ -f /root/dotfiles/.sync-manifest.json ] && echo "manifest created"

    # Verify manifest contains version and commands
    grep -q '"version"' /root/dotfiles/.sync-manifest.json && echo "has version"
    grep -q '"commands"' /root/dotfiles/.sync-manifest.json && echo "has commands key"
    grep -q 'probe-cmd.md' /root/dotfiles/.sync-manifest.json && echo "has probe-cmd"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Manifest was created with items
    assert "manifest created" in result.stdout
    assert "has version" in result.stdout
    assert "has commands key" in result.stdout
    assert "has probe-cmd" in result.stdout


def test_sync_agents_deletes_removed_items_from_targets(docker_image):
    """Test that items removed from dotfiles are deleted from all targets.

    Scenario:
    - given: A command exists in dotfiles and is synced to targets
    - when: The command is removed from dotfiles and sync runs again
    - then: The command is deleted from all targets
    """
    cmd = """
    set -euo pipefail

    # Create a command in dotfiles
    mkdir -p /root/dotfiles/commands
    echo "# Temp Command" > /root/dotfiles/commands/temp-command.md

    # First sync: distributes temp-command to all targets
    cd /root/dotfiles && just sync-agents all

    # Verify it was synced
    [ -f /root/.claude/commands/temp-command.md ] && echo "synced to claude"
    [ -f /root/.gemini/commands/temp-command.md ] && echo "synced to gemini"

    # Now delete from dotfiles
    rm -f /root/dotfiles/commands/temp-command.md

    # Second sync: should delete from all targets
    cd /root/dotfiles && just sync-agents all

    # Verify deletion
    if [ -f /root/.claude/commands/temp-command.md ]; then
        echo "ERROR: not deleted from claude"
    else
        echo "deleted from claude"
    fi
    if [ -f /root/.gemini/commands/temp-command.md ]; then
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
    mkdir -p /root/.claude/agents/ephemeral-skill
    echo "# Ephemeral" > /root/.claude/agents/ephemeral-skill/README.md

    # First sync: imports to dotfiles, syncs to targets
    cd /root/dotfiles && just sync-agents all
    [ -d /root/dotfiles/agents/ephemeral-skill ] && echo "initially imported"

    # Delete from dotfiles (simulating intentional removal)
    rm -rf /root/dotfiles/agents/ephemeral-skill

    # Second sync: should NOT re-import, should delete from targets
    cd /root/dotfiles && just sync-agents all

    # Verify NOT re-imported to dotfiles
    if [ -d /root/dotfiles/agents/ephemeral-skill ]; then
        echo "ERROR: re-imported to dotfiles"
    else
        echo "correctly not re-imported"
    fi

    # Verify deleted from claude (import source)
    if [ -d /root/.claude/agents/ephemeral-skill ]; then
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


def test_sync_agents_does_not_import_from_codex(docker_image):
    """Codex-home skills never enter dotfiles (skills are not synced at all).

    Scenario:
    - given: A skill exists in ~/.codex/skills/
    - when: Run sync-agents
    - then: It stays codex-only: not imported, not propagated
    """
    cmd = """
    set -euo pipefail

    # Create a codex-native skill
    mkdir -p /root/.codex/skills/codex-native
    echo "# Codex Native" > /root/.codex/skills/codex-native/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify NOT imported to dotfiles and NOT propagated
    [ ! -e /root/dotfiles/skills/codex-native ] && echo "not imported"
    [ ! -e /root/.claude/skills/codex-native ] && echo "not propagated"
    [ -f /root/.codex/skills/codex-native/SKILL.md ] && echo "preserved in codex"
    """
    result = _run_in_container(docker_image, cmd)

    # then: codex-only skill is left alone
    assert "not imported" in result.stdout
    assert "not propagated" in result.stdout
    assert "preserved in codex" in result.stdout


def test_sync_agents_skips_hidden_directories(docker_image):
    """Test that hidden directories (starting with .) are skipped.

    Scenario:
    - given: A hidden directory exists in ~/.codex/agents/.system/
    - when: Run sync-agents
    - then: Hidden directory is NOT imported
    """
    cmd = """
    set -euo pipefail

    # Create a hidden directory in codex agents
    mkdir -p /root/.codex/agents/.system/internal
    echo "# Internal" > /root/.codex/agents/.system/internal/README.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify hidden dir was NOT imported
    if [ -d /root/dotfiles/agents/.system ]; then
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
    mkdir -p /root/dotfiles/agents/real-skill
    echo "# Real Skill" > /root/dotfiles/agents/real-skill/README.md

    # Create a symlink in gemini pointing elsewhere
    mkdir -p /opt/other/real-skill
    echo "# Other" > /opt/other/real-skill/README.md
    mkdir -p /root/.gemini/agents
    ln -s /opt/other/real-skill /root/.gemini/agents/real-skill

    # Verify it's a symlink before sync
    [ -L /root/.gemini/agents/real-skill ] && echo "is symlink before"

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify symlink was replaced with real dir
    if [ -L /root/.gemini/agents/real-skill ]; then
        echo "ERROR: still a symlink"
    else
        echo "replaced with real dir"
    fi
    grep -q "Real Skill" /root/.gemini/agents/real-skill/README.md && echo "correct content"
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
    mkdir -p /root/dotfiles/agents/evolving-skill
    echo "# Version 1" > /root/dotfiles/agents/evolving-skill/README.md

    # First sync to distribute
    cd /root/dotfiles && just sync-agents all

    # Wait to ensure mtime difference
    sleep 2

    # Edit the skill in import source (newer version)
    echo "# Version 2 - Updated" > /root/.claude/agents/evolving-skill/README.md

    # Run sync again
    cd /root/dotfiles && just sync-agents all

    # Verify dotfiles was updated with newer version
    grep -q "Version 2" /root/dotfiles/agents/evolving-skill/README.md && echo "dotfiles updated"

    # Verify all targets got the newer version
    grep -q "Version 2" /root/.gemini/agents/evolving-skill/README.md && echo "gemini updated"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Newer version won
    assert "dotfiles updated" in result.stdout
    assert "gemini updated" in result.stdout


# =============================================================================
# Workspace Exclusion Tests (skill-creator workspace preservation)
# =============================================================================


# =============================================================================
# Agents Global Directory (~/.agents/) Sync Tests
# =============================================================================


# =============================================================================
# Override mode tests
# =============================================================================


# =============================================================================
# Orphan Detection and Override Tests
# =============================================================================


def test_sync_agents_orphans_shows_target_only_items(docker_image):
    """Test that --orphans lists items existing only in the target.

    Scenario:
    - given: Non-import target has a skill not present in dotfiles
    - when: Run sync-agents --orphans
    - then: Orphan skill is listed in the output

    Note: Orphans must be added to a non-import-source target (Work-A),
    since import sources (Claude, Codex) would import new items into dotfiles.
    """
    cmd = """
    set -euo pipefail

    # First sync to establish baseline
    cd /root/dotfiles && just sync-agents all

    # Add an orphan skill to a non-import target
    mkdir -p /root/.claude-work-a/agents/orphan-test-skill
    echo "# Orphan" > /root/.claude-work-a/agents/orphan-test-skill/SKILL.md

    # Run orphans detection
    cd /root/dotfiles && uv run scripts/sync_agents.py --orphans all
    """
    result = _run_in_container(docker_image, cmd)

    # then: Orphan skill is detected
    assert "orphan-test-skill" in result.stdout
    assert "Target-Only Items" in result.stdout


def test_sync_agents_orphans_clean_when_no_orphans(docker_image):
    """Test that --orphans shows clean message when all in sync.

    Scenario:
    - given: All targets match dotfiles
    - when: Run sync-agents --orphans
    - then: Clean status message is shown
    """
    cmd = """
    set -euo pipefail

    # Sync to establish baseline
    cd /root/dotfiles && just sync-agents all

    # Run orphans detection (should be clean)
    cd /root/dotfiles && uv run scripts/sync_agents.py --orphans all
    """
    result = _run_in_container(docker_image, cmd)

    # then: No orphans found
    assert "No target-only items found" in result.stdout


def test_sync_agents_override_removes_orphans(docker_image):
    """Test that --override removes target-only items without prompts.

    Scenario:
    - given: Non-import target has orphan agents
    - when: Run sync-agents --override
    - then: Orphans are deleted, target matches dotfiles

    Note: Uses Work-A (non-import-source) to avoid import phase interference.
    """
    cmd = """
    set -euo pipefail

    # First sync to establish baseline
    cd /root/dotfiles && just sync-agents all

    # Add orphan agents to non-import target
    mkdir -p /root/.claude-work-a/agents/orphan-alpha
    echo "# Alpha" > /root/.claude-work-a/agents/orphan-alpha/SKILL.md
    mkdir -p /root/.claude-work-a/agents/orphan-beta
    echo "# Beta" > /root/.claude-work-a/agents/orphan-beta/SKILL.md

    # Verify orphans exist
    [ -d /root/.claude-work-a/agents/orphan-alpha ] && echo "orphan-alpha exists before"
    [ -d /root/.claude-work-a/agents/orphan-beta ] && echo "orphan-beta exists before"

    # Run override
    cd /root/dotfiles && uv run scripts/sync_agents.py --override all

    # Verify orphans are gone
    if [ -d /root/.claude-work-a/agents/orphan-alpha ]; then
        echo "ERROR: orphan-alpha still exists"
    else
        echo "orphan-alpha removed"
    fi
    if [ -d /root/.claude-work-a/agents/orphan-beta ]; then
        echo "ERROR: orphan-beta still exists"
    else
        echo "orphan-beta removed"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: Orphans existed before and were removed
    assert "orphan-alpha exists before" in result.stdout
    assert "orphan-beta exists before" in result.stdout
    assert "orphan-alpha removed" in result.stdout
    assert "orphan-beta removed" in result.stdout


def test_sync_agents_override_preserves_source_items(docker_image):
    """Test that --override keeps items that exist in dotfiles.

    Scenario:
    - given: Non-import target has both dotfiles agents and orphans
    - when: Run sync-agents --override
    - then: Dotfiles agents remain, orphans are removed

    Note: Uses Work-A (non-import-source) to avoid import phase interference.
    """
    cmd = """
    set -euo pipefail

    # Create a skill in dotfiles
    mkdir -p /root/dotfiles/agents/my-real-skill
    echo "# Real" > /root/dotfiles/agents/my-real-skill/SKILL.md

    # First sync
    cd /root/dotfiles && just sync-agents all

    # Add an orphan to the non-import target
    mkdir -p /root/.claude-work-a/agents/orphan-only
    echo "# Orphan" > /root/.claude-work-a/agents/orphan-only/SKILL.md

    # Run override
    cd /root/dotfiles && uv run scripts/sync_agents.py --override all

    # Verify: real skill preserved, orphan removed
    [ -d /root/.claude-work-a/agents/my-real-skill ] && echo "real skill preserved"
    if [ -d /root/.claude-work-a/agents/orphan-only ]; then
        echo "ERROR: orphan still exists"
    else
        echo "orphan removed"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then
    assert "real skill preserved" in result.stdout
    assert "orphan removed" in result.stdout


def test_sync_agents_preview_shows_orphans(docker_image):
    """Test that --preview shows target-only items with TARGET-ONLY label.

    Scenario:
    - given: Non-import target has an orphan skill
    - when: Run sync-agents --preview
    - then: Orphan is shown with TARGET-ONLY label

    Note: Uses Work-A (non-import-source) to avoid import phase interference.
    """
    cmd = """
    set -euo pipefail

    # First sync
    cd /root/dotfiles && just sync-agents all

    # Add an orphan to non-import target
    mkdir -p /root/.claude-work-a/agents/preview-orphan
    echo "# Preview" > /root/.claude-work-a/agents/preview-orphan/SKILL.md

    # Run preview
    cd /root/dotfiles && uv run scripts/sync_agents.py --preview all
    """
    result = _run_in_container(docker_image, cmd)

    # then: Orphan shown with TARGET-ONLY label
    assert "preview-orphan" in result.stdout
    assert "TARGET-ONLY" in result.stdout


# =============================================================================
# Import-Only Mode Tests (just import-agents)
# =============================================================================


def test_import_agents_does_not_forward_sync_to_targets(docker_image):
    """import-agents must NOT push dotfiles content into targets (Phase 2-3 skipped).

    Scenario:
    - given: A command exists in dotfiles but not in any target
    - when: Run `just import-agents all`
    - then: The command stays only in dotfiles; targets are NOT created/updated
    """
    cmd = """
    set -euo pipefail

    mkdir -p /root/dotfiles/commands
    echo "# dotfiles only" > /root/dotfiles/commands/dotfiles-only.md

    cd /root/dotfiles && just import-agents all

    [ -f /root/dotfiles/commands/dotfiles-only.md ] && echo "stayed in dotfiles"
    [ ! -e /root/.claude/commands/dotfiles-only.md ] && echo "not pushed to claude"
    [ ! -e /root/.claude-work-a/commands/dotfiles-only.md ] && echo "not pushed to work-a"
    [ ! -e /root/.gemini/commands/dotfiles-only.md ] && echo "not pushed to gemini"
    """
    result = _run_in_container(docker_image, cmd)

    assert "stayed in dotfiles" in result.stdout
    assert "not pushed to claude" in result.stdout
    assert "not pushed to work-a" in result.stdout
    assert "not pushed to gemini" in result.stdout


def test_import_agents_imports_from_non_import_source_target(docker_image):
    """import-agents drops the is_import_source filter:
    a skill in work-a or gemini is still pulled into dotfiles.

    Scenario:
    - given: A command exists only in ~/.claude-work-a/commands/ (not an import source by flag)
    - when: Run `just import-agents a` (explicitly select work-a)
    - then: The command is imported into dotfiles
    """
    cmd = """
    set -euo pipefail

    mkdir -p /root/.claude-work-a/commands
    echo "# from work-a" > /root/.claude-work-a/commands/from-work-a.md

    cd /root/dotfiles && just import-agents a

    [ -f /root/dotfiles/commands/from-work-a.md ] && echo "imported from work-a"
    """
    result = _run_in_container(docker_image, cmd)

    assert "imported from work-a" in result.stdout


def test_import_agents_preview_makes_no_changes(docker_image):
    """import-agents-preview must not write anything (preview = dry run).

    Scenario:
    - given: A command exists in target but not in dotfiles
    - when: Run `just import-agents-preview`
    - then: Plan is printed but dotfiles is unchanged
    """
    cmd = """
    set -euo pipefail

    mkdir -p /root/.claude/commands
    echo "# preview" > /root/.claude/commands/preview-only-command.md

    cd /root/dotfiles && just import-agents-preview

    if [ -f /root/dotfiles/commands/preview-only-command.md ]; then
        echo "ERROR: preview wrote to dotfiles"
    else
        echo "preview did not write"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    assert "preview did not write" in result.stdout
    # the plan output should mention the command as importable
    assert "preview-only-command" in result.stdout


# =============================================================================
# Override Recipe Tests (just sync-agents-override)
# =============================================================================


def test_just_sync_agents_override_removes_orphans_via_recipe(docker_image):
    """`just sync-agents-override all` removes orphans without prompts.

    Exercises the just recipe end-to-end (not the python script directly),
    so a regression in the recipe wiring would be caught here.
    """
    cmd = """
    set -euo pipefail

    cd /root/dotfiles && just sync-agents all

    mkdir -p /root/.claude-work-a/agents/recipe-orphan
    echo "# orphan" > /root/.claude-work-a/agents/recipe-orphan/SKILL.md

    [ -d /root/.claude-work-a/agents/recipe-orphan ] && echo "orphan before"

    cd /root/dotfiles && just sync-agents-override all

    if [ -d /root/.claude-work-a/agents/recipe-orphan ]; then
        echo "ERROR: orphan still exists"
    else
        echo "orphan removed by recipe"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    assert "orphan before" in result.stdout
    assert "orphan removed by recipe" in result.stdout


def test_just_sync_agents_override_default_scope_does_not_touch_work_a(docker_image):
    """`just sync-agents-override` (no targets) honors the default scope:
    out-of-scope agents (work-a) MUST NOT be touched, even by orphan removal.
    """
    cmd = """
    set -euo pipefail

    cd /root/dotfiles && just sync-agents all

    # Plant an orphan in work-a (out of default scope)
    mkdir -p /root/.claude-work-a/agents/scope-orphan-work-a
    echo "# w" > /root/.claude-work-a/agents/scope-orphan-work-a/SKILL.md

    cd /root/dotfiles && just sync-agents-override

    # work-a orphan must still be there (out of scope by default)
    if [ -d /root/.claude-work-a/agents/scope-orphan-work-a ]; then
        echo "work-a orphan preserved"
    else
        echo "ERROR: work-a touched outside default scope"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    assert "work-a orphan preserved" in result.stdout


# =============================================================================
# Hub-and-spoke layout: ROOT_AGENTS.md (base) + ROOT_CLAUDE.md (overlay) +
# ROOT_AGENTS_docs_agents_* (spokes) + ROOT_AGENTS_hooks_* + settings merge.
# =============================================================================


def test_hub_and_spoke_claude_gets_overlay_base_spokes_hooks(docker_image):
    """claude-family: CLAUDE.md=overlay(@AGENTS.md), AGENTS.md=base, docs/agents/
    spokes with absolute refs, executable hooks, merged settings.json."""
    cmd = r"""
    set -euo pipefail
    cd /root/dotfiles && just sync-agents p

    grep -q '^@AGENTS.md' /root/.claude/CLAUDE.md && echo "overlay-imports-base"
    grep -q 'Non-negotiables' /root/.claude/AGENTS.md && echo "base-is-agents-md"
    [ -f /root/.claude/docs/agents/python-tooling.md ] && echo "spoke-present"
    [ -x /root/.claude/hooks/block-prohibited-commands.sh ] && echo "hook-executable"
    grep -q '/root/.claude/docs/agents/python-tooling.md' /root/.claude/AGENTS.md && echo "spoke-ref-absolute"
    grep -q '/root/.claude/hooks/block-prohibited-commands.sh' /root/.claude/settings.json && echo "settings-merged-absolute"
    """
    result = _run_in_container(docker_image, cmd)
    for marker in (
        "overlay-imports-base",
        "base-is-agents-md",
        "spoke-present",
        "hook-executable",
        "spoke-ref-absolute",
        "settings-merged-absolute",
    ):
        assert marker in result.stdout, f"missing {marker}\n{result.stdout}"


def test_hub_and_spoke_codex_gemini_base_only_no_hooks(docker_image):
    """codex/gemini get the base directly (no overlay, no hooks); spokes present
    with refs rewritten to each agent's own absolute path."""
    cmd = r"""
    set -euo pipefail
    cd /root/dotfiles && just sync-agents x g

    grep -q 'Non-negotiables' /root/.codex/AGENTS.md && echo "codex-base"
    grep -q 'Non-negotiables' /root/.gemini/GEMINI.md && echo "gemini-base"
    [ -f /root/.codex/docs/agents/testing.md ] && echo "codex-spoke"
    grep -q '/root/.codex/docs/agents/testing.md' /root/.codex/AGENTS.md && echo "codex-spoke-ref-absolute"
    [ -d /root/.codex/hooks ] && echo "ERR-codex-hooks" || echo "codex-no-hooks"
    [ -d /root/.gemini/hooks ] && echo "ERR-gemini-hooks" || echo "gemini-no-hooks"
    [ -f /root/.codex/CLAUDE.md ] && echo "ERR-codex-overlay" || echo "codex-no-overlay"
    """
    result = _run_in_container(docker_image, cmd)
    for marker in (
        "codex-base",
        "gemini-base",
        "codex-spoke",
        "codex-spoke-ref-absolute",
        "codex-no-hooks",
        "gemini-no-hooks",
        "codex-no-overlay",
    ):
        assert marker in result.stdout, f"missing {marker}\n{result.stdout}"
    assert "ERR-" not in result.stdout, result.stdout


def test_hub_and_spoke_settings_merge_idempotent_preserves_user_keys(docker_image):
    """settings.json merge preserves user keys + user hooks, adds managed hooks
    with absolute paths, and is idempotent across repeated syncs."""
    cmd = r"""
    set -euo pipefail
    mkdir -p /root/.claude
    cat > /root/.claude/settings.json <<'JSON'
{
  "editorMode": "vim",
  "hooks": {
    "PreToolUse": [
      { "matcher": "Read", "hooks": [ { "type": "command", "command": "echo user-hook" } ] }
    ]
  }
}
JSON
    cd /root/dotfiles
    just sync-agents p
    just sync-agents p

    python3 - <<'PY'
import json
s = json.load(open("/root/.claude/settings.json"))
# probe with a key the settings fragments do NOT declare: fragment-owned
# top-level keys (e.g. theme) are upserted by design (ADR 0037).
assert s.get("editorMode") == "vim", "user key lost"
pre = s["hooks"]["PreToolUse"]
cmds = [h["command"] for b in pre for h in b["hooks"]]
assert "echo user-hook" in cmds, "user hook lost"
managed = [c for c in cmds if c.endswith('block-prohibited-files.sh"')]
assert len(managed) == 1, f"managed hook not idempotent: {managed}"
assert all("/root/.claude/hooks/" in c for c in cmds if "block-" in c), "hook path not absolute"
print("settings-merge-ok")
PY
    """
    result = _run_in_container(docker_image, cmd)
    assert "settings-merge-ok" in result.stdout, result.stdout


def test_hub_and_spoke_settings_merge_updates_managed_in_place(docker_image):
    """When a managed hook command changes in the fragment, the old managed
    block is REPLACED in settings.json (not left as a stale duplicate)."""
    cmd = r"""
    set -euo pipefail
    cd /root/dotfiles
    just sync-agents p
    grep -q 'hooks/block-secrets.sh' /root/.claude/settings.json && echo "v1-present"

    # change a managed hook command in the fragment, then re-sync
    sed -i 's#/.claude/hooks/block-secrets.sh#/.claude/hooks/block-secrets-v2.sh#' \
        .claude/settings.hooks.json
    just sync-agents p

    grep -q 'hooks/block-secrets-v2.sh' /root/.claude/settings.json && echo "v2-present"
    if grep -q 'hooks/block-secrets\.sh"' /root/.claude/settings.json; then
        echo "ERR-v1-stale"
    else
        echo "v1-removed"
    fi
    """
    result = _run_in_container(docker_image, cmd)
    for marker in ("v1-present", "v2-present", "v1-removed"):
        assert marker in result.stdout, f"missing {marker}\n{result.stdout}"
    assert "ERR-v1-stale" not in result.stdout, result.stdout


def test_spoke_and_hook_orphans_are_cleaned(docker_image):
    """A distributed spoke/hook whose ROOT_AGENTS_* source is gone is removed as
    an orphan on the next sync; current spokes/hooks are preserved."""
    cmd = r"""
    set -euo pipefail
    cd /root/dotfiles
    just sync-agents p
    [ -f /root/.claude/docs/agents/testing.md ] && echo "current-spoke-present"

    # plant stale files with no backing ROOT_AGENTS_* source
    echo "# stale" > /root/.claude/docs/agents/removed-spoke.md
    echo "#!/bin/sh" > /root/.claude/hooks/removed-hook.sh

    just sync-agents p

    [ -f /root/.claude/docs/agents/removed-spoke.md ] && echo "ERR-spoke-stale" || echo "spoke-orphan-removed"
    [ -f /root/.claude/hooks/removed-hook.sh ] && echo "ERR-hook-stale" || echo "hook-orphan-removed"
    [ -f /root/.claude/docs/agents/testing.md ] && echo "current-spoke-kept"
    [ -x /root/.claude/hooks/block-secrets.sh ] && echo "current-hook-kept"
    """
    result = _run_in_container(docker_image, cmd)
    for marker in (
        "current-spoke-present",
        "spoke-orphan-removed",
        "hook-orphan-removed",
        "current-spoke-kept",
        "current-hook-kept",
    ):
        assert marker in result.stdout, f"missing {marker}\n{result.stdout}"
    assert "ERR-spoke-stale" not in result.stdout, result.stdout
    assert "ERR-hook-stale" not in result.stdout, result.stdout


# =============================================================================
# Skills are out of the sync's business (ADR 0043)
# =============================================================================


def test_sync_never_touches_skills_dirs(docker_image):
    """Skills reach the homes through the bunx skills CLI and skills_lock.py;
    the sync must neither copy a skills/ dir from dotfiles nor delete, import,
    or rewrite anything under a home's skills/ — in --yes and --override mode,
    and even when a stale manifest still lists skills items."""
    cmd = r"""
    set -euo pipefail
    # a stale manifest from before the retirement
    cat > /root/dotfiles/.sync-manifest.json <<'EOF'
{"version": 1, "items": {"skills": ["cli-managed", "gone-skill"], "commands": [], "agents": []}}
EOF
    # a stray skills dir in dotfiles must NOT be distributed
    mkdir -p /root/dotfiles/skills/probe-skill
    echo "# Probe" > /root/dotfiles/skills/probe-skill/SKILL.md
    # what a home holds: a CLI-managed real dir and a symlink into the store
    mkdir -p /root/.agents/skills/linked
    echo "# linked" > /root/.agents/skills/linked/SKILL.md
    mkdir -p /root/.claude/skills/cli-managed
    echo "SENTINEL" > /root/.claude/skills/cli-managed/SKILL.md
    ln -s ../../.agents/skills/linked /root/.claude/skills/linked

    cd /root/dotfiles && just sync-agents all
    cd /root/dotfiles && uv run scripts/sync_agents.py --override all

    grep -q SENTINEL /root/.claude/skills/cli-managed/SKILL.md && echo "real-dir-untouched"
    [ -L /root/.claude/skills/linked ] && echo "symlink-untouched"
    [ ! -e /root/.claude/skills/probe-skill ] && echo "dotfiles-skills-not-copied"
    [ ! -e /root/.gemini/skills/probe-skill ] && echo "not-copied-to-gemini"
    grep -q '"skills"' /root/dotfiles/.sync-manifest.json && echo "ERR-manifest-still-lists-skills" || echo "manifest-pruned"
    """
    result = _run_in_container(docker_image, cmd)
    for marker in (
        "real-dir-untouched",
        "symlink-untouched",
        "dotfiles-skills-not-copied",
        "not-copied-to-gemini",
        "manifest-pruned",
    ):
        assert marker in result.stdout, f"missing {marker}\n{result.stdout}"
    assert "ERR-manifest-still-lists-skills" not in result.stdout, result.stdout
