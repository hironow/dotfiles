"""E2E tests for sync-agents just command.

These tests run in Docker containers to avoid polluting the host environment.
The sync-agents command syncs ROOT_AGENTS files to agent instruction directories.

File naming convention:
    ROOT_AGENTS.md                      -> <agent>/AGENT.md (base file)
    ROOT_AGENTS_commands_strict.md      -> <agent>/commands/strict.md
    ROOT_AGENTS_skills_my-skill/        -> <agent>/skills/my-skill/
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
    """Copy git-tracked files (superproject + skills submodule) into snapshot.

    Same rationale as test_just_sandbox.py: the container must never see
    the real repo. This suite's containers even run `sync-agents import`
    style commands that WRITE into /root/dotfiles, so a direct bind mount
    mutates the mounted tree (observed: deleted ROOT_AGENTS.md, junk
    skills/commands). Every test gets its own disposable snapshot via the
    autouse fixture below.
    """
    # Superproject tracked files, plus the skills submodule's tracked files
    # (`git ls-files` skips gitlinks, but this suite's tests rely on the
    # self-authored skills shipping in /root/dotfiles/skills).
    for prefix in ("", "skills"):
        tree = os.path.join(src, prefix) if prefix else src
        # the skills submodule may be un-inited on a fresh clone
        if prefix and not os.path.exists(os.path.join(tree, ".git")):
            continue
        tracked = subprocess.run(
            ["git", "-C", tree, "ls-files", "-z"],
            check=True,
            stdout=subprocess.PIPE,
        ).stdout.decode()
        for rel in tracked.split("\0"):
            if not rel:
                continue
            source = os.path.join(tree, rel)
            if not os.path.isfile(source):  # skip gitlinks / vanished paths
                continue
            dest = (
                os.path.join(snapshot, prefix, rel)
                if prefix
                else os.path.join(snapshot, rel)
            )
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


def test_sync_agents_preserves_unmanaged_items_in_target(docker_image):
    """Test that sync preserves items in target not managed by dotfiles.

    Scenario:
    - given: Target has an extra skill (e.g. a symlink-installed plugin)
    - when: Run sync-agents
    - then: The extra skill is preserved, dotfiles skills are synced
    """
    cmd = """
    set -euo pipefail

    # Create a dotfiles skill (SKILL.md required by the quality gate)
    mkdir -p /root/dotfiles/skills/my-skill
    echo "# My Skill" > /root/dotfiles/skills/my-skill/SKILL.md

    # First sync - creates target skills
    cd /root/dotfiles && just sync-agents all

    # Add an extra item in target (simulating plugin install)
    mkdir -p /root/.claude/skills/external-plugin
    echo "# External Plugin" > /root/.claude/skills/external-plugin/README.md

    # Run sync again
    cd /root/dotfiles && just sync-agents all

    # Verify both exist
    [ -f /root/.claude/skills/my-skill/SKILL.md ] && echo "dotfiles skill preserved"
    [ -f /root/.claude/skills/external-plugin/README.md ] && echo "external plugin preserved"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Both items exist
    assert "dotfiles skill preserved" in result.stdout
    assert "external plugin preserved" in result.stdout


# =============================================================================
# Import (symlink resolution) Tests
# =============================================================================


def test_sync_agents_does_not_import_symlinked_skills_from_target(docker_image):
    """Symlink-installed skills (bunx skills CLI) are never imported.

    Scenario:
    - given: Target (~/.claude/skills/) has a symlink to an external skill
    - when: Run sync-agents
    - then: The symlink stays in the target and nothing lands in dotfiles
      (declarative model: third-party skills are lock-managed, ADR 0038)
    """
    cmd = """
    set -euo pipefail

    # Create an external skill directory (the symlink target)
    mkdir -p /opt/external-skills/cool-plugin
    echo "# Cool Plugin" > /opt/external-skills/cool-plugin/SKILL.md

    # Set up ~/.claude/skills/ with a symlink to the external skill
    mkdir -p /root/.claude/skills
    ln -s /opt/external-skills/cool-plugin /root/.claude/skills/cool-plugin

    # Verify symlink exists
    [ -L /root/.claude/skills/cool-plugin ] && echo "symlink exists"

    # Run sync-agents (import of skills is abolished)
    cd /root/dotfiles && just sync-agents all

    # Verify the skill was NOT imported to dotfiles
    [ ! -e /root/dotfiles/skills/cool-plugin ] && echo "not imported to dotfiles"

    # Verify the target symlink survived untouched
    [ -L /root/.claude/skills/cool-plugin ] && echo "symlink preserved"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Symlink stays put, nothing imported
    assert "symlink exists" in result.stdout
    assert "not imported to dotfiles" in result.stdout
    assert "symlink preserved" in result.stdout


def test_sync_agents_does_not_import_regular_skill_directories(docker_image):
    """Target-only real skill dirs stay in the target, never enter dotfiles.

    Scenario:
    - given: Target has a regular (non-symlink) skill directory
    - when: Run sync-agents
    - then: It is neither imported to dotfiles nor propagated to other
      targets, but it is preserved in place (additive)
    """
    cmd = """
    set -euo pipefail

    # Set up target with a regular (non-symlink) skill directory
    mkdir -p /root/.claude/skills/manual-skill
    echo "# Manual Skill" > /root/.claude/skills/manual-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify the regular dir was NOT imported to dotfiles
    [ ! -e /root/dotfiles/skills/manual-skill ] && echo "not imported"

    # Verify it did NOT propagate to other targets
    [ ! -e /root/.gemini/skills/manual-skill ] && echo "not propagated"

    # Verify it survived in place
    grep -q "Manual Skill" /root/.claude/skills/manual-skill/SKILL.md && echo "preserved in target"
    """
    result = _run_in_container(docker_image, cmd)

    # then: target-only skill is left alone
    assert "not imported" in result.stdout
    assert "not propagated" in result.stdout
    assert "preserved in target" in result.stdout


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
    cd /root/dotfiles && just sync-agents all

    # Verify dotfiles version was preserved (it's newer) — import-conflict
    # resolution is unchanged by additive skills.
    grep -q "Dotfiles version (newer)" /root/dotfiles/skills/shared-skill/README.md && echo "dotfiles version preserved"

    # skills is additive: the EXISTING target symlink is preserved (not
    # overwritten with the dotfiles copy).
    [ -L /root/.claude/skills/shared-skill ] && echo "claude symlink preserved"
    grep -q "External version (older)" /root/.claude/skills/shared-skill/README.md && echo "claude kept existing"
    """
    result = _run_in_container(docker_image, cmd)

    # then: dotfiles keeps the newer copy; the target's existing skill is kept
    assert "dotfiles version preserved" in result.stdout
    assert "claude symlink preserved" in result.stdout
    assert "claude kept existing" in result.stdout


# =============================================================================
# Bidirectional Sync Full Cycle Tests
# =============================================================================


def test_sync_agents_one_way_cycle_ignores_cli_symlinks(docker_image):
    """Skills flow one way (dotfiles -> targets); CLI symlinks never re-enter.

    Scenario:
    - given: An external skill is symlinked into ~/.claude/skills/ and a
      self-authored skill exists in dotfiles
    - when: Run sync-agents
    - then: The dotfiles skill reaches every target; the symlinked skill is
      neither imported nor propagated (declarative model, ADR 0038)
    """
    cmd = """
    set -euo pipefail

    # Create an external (CLI-style) skill and symlink it into ~/.claude
    mkdir -p /opt/plugins/awesome-plugin
    echo "# Awesome Plugin" > /opt/plugins/awesome-plugin/SKILL.md
    mkdir -p /root/.claude/skills
    ln -s /opt/plugins/awesome-plugin /root/.claude/skills/awesome-plugin

    # Create a self-authored skill in dotfiles
    mkdir -p /root/dotfiles/skills/own-skill
    echo "# Own Skill" > /root/dotfiles/skills/own-skill/SKILL.md

    # Run sync-agents (forward only for skills)
    cd /root/dotfiles && just sync-agents all

    # CLI symlink is NOT imported
    [ ! -e /root/dotfiles/skills/awesome-plugin ] && echo "symlink not imported"
    [ ! -e /root/.gemini/skills/awesome-plugin ] && echo "symlink not propagated"

    # Self-authored skill IS distributed everywhere
    [ -f /root/.gemini/skills/own-skill/SKILL.md ] && echo "synced to gemini"
    [ -f /root/.codex/skills/own-skill/SKILL.md ] && echo "synced to codex"
    [ -f /root/.claude-work-a/skills/own-skill/SKILL.md ] && echo "synced to claude-work-a"
    """
    result = _run_in_container(docker_image, cmd)

    # then: One-way flow holds in both directions of the assertion
    assert "symlink not imported" in result.stdout
    assert "symlink not propagated" in result.stdout
    assert "synced to gemini" in result.stdout
    assert "synced to codex" in result.stdout
    assert "synced to claude-work-a" in result.stdout
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
    cd /root/dotfiles && just sync-agents all

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

    # Hermetic probe skill (the skills submodule may be absent in CI —
    # it is a private repo the workflow token cannot clone)
    mkdir -p /root/dotfiles/skills/probe-skill
    echo "# Probe" > /root/dotfiles/skills/probe-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify manifest was created
    [ -f /root/dotfiles/.sync-manifest.json ] && echo "manifest created"

    # Verify manifest contains version and skills
    grep -q '"version"' /root/dotfiles/.sync-manifest.json && echo "has version"
    grep -q '"skills"' /root/dotfiles/.sync-manifest.json && echo "has skills key"
    grep -q 'probe-skill' /root/dotfiles/.sync-manifest.json && echo "has probe-skill"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Manifest was created with items
    assert "manifest created" in result.stdout
    assert "has version" in result.stdout
    assert "has skills key" in result.stdout
    assert "has probe-skill" in result.stdout


def test_sync_agents_deletes_removed_items_from_targets(docker_image):
    """Test that items removed from dotfiles are deleted from all targets.

    Scenario:
    - given: A command exists in dotfiles and is synced to targets
      (skills/ is additive and exempt from deletion, so the deletion
      machinery is exercised with commands/)
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
    """Codex-home skills never enter dotfiles (declarative model).

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
    cd /root/dotfiles && just sync-agents all

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


def test_sync_agents_target_copy_never_overwrites_dotfiles(docker_image):
    """A target-side copy of a dotfiles skill can never overwrite dotfiles.

    With skills import abolished there is no conflict machinery left to
    race: dotfiles is simply authoritative for its own skills.

    Scenario:
    - given: A skill exists in both dotfiles and ~/.claude with different content
    - when: Run sync-agents
    - then: Dotfiles keeps its version; a missing target gets the dotfiles
      version; an existing target copy is preserved (additive)
    """
    cmd = """
    set -euo pipefail

    # Create a diverged copy in the target
    mkdir -p /root/.claude/skills/stable-skill
    echo "# Old Version" > /root/.claude/skills/stable-skill/SKILL.md

    # Create the authoritative version in dotfiles
    mkdir -p /root/dotfiles/skills/stable-skill
    echo "# New Version in Dotfiles" > /root/dotfiles/skills/stable-skill/SKILL.md

    # Run sync
    cd /root/dotfiles && just sync-agents all

    # Verify dotfiles version was untouched (no import can occur)
    grep -q "New Version in Dotfiles" /root/dotfiles/skills/stable-skill/SKILL.md && echo "dotfiles preserved"

    # gemini was MISSING the skill -> additive adds the dotfiles version.
    grep -q "New Version in Dotfiles" /root/.gemini/skills/stable-skill/SKILL.md && echo "gemini got dotfiles version"
    # claude already HAD the skill -> additive preserves it (no overwrite).
    grep -q "Old Version" /root/.claude/skills/stable-skill/SKILL.md && echo "claude kept existing"
    """
    result = _run_in_container(docker_image, cmd)

    # then: dotfiles authoritative; missing target added; existing target kept
    assert "dotfiles preserved" in result.stdout
    assert "gemini got dotfiles version" in result.stdout
    assert "claude kept existing" in result.stdout


# =============================================================================
# Workspace Exclusion Tests (skill-creator workspace preservation)
# =============================================================================


def test_sync_agents_preserves_workspace_dirs_in_learned(docker_image):
    """Test that -workspace dirs inside learned/ are preserved during sync.

    Scenario:
    - given: Target has learned/ with both real skills and -workspace dirs
    - when: A managed skill inside learned/ changes and sync runs
    - then: -workspace dirs are preserved, managed skills are updated
    """
    cmd = """
    set -euo pipefail

    # Create a real skill in dotfiles learned/
    mkdir -p /root/dotfiles/skills/learned/my-real-skill
    echo "# My Real Skill v1" > /root/dotfiles/skills/learned/my-real-skill/SKILL.md

    # First sync: distribute learned/ to targets
    cd /root/dotfiles && just sync-agents all

    # Verify learned was synced
    [ -f /root/.claude/skills/learned/my-real-skill/SKILL.md ] && echo "initial sync ok"

    # Create workspace dirs in targets (simulating skill-creator)
    mkdir -p /root/.claude/skills/learned/my-real-skill-workspace/iteration-1
    echo "workspace data" > /root/.claude/skills/learned/my-real-skill-workspace/iteration-1/results.md
    mkdir -p /root/.gemini/skills/learned/test-workspace/iteration-1
    echo "gemini workspace" > /root/.gemini/skills/learned/test-workspace/iteration-1/data.md

    # Update the real skill in dotfiles
    echo "# My Real Skill v2" > /root/dotfiles/skills/learned/my-real-skill/SKILL.md

    # Run sync again - should update skill but preserve workspace
    cd /root/dotfiles && just sync-agents all

    # Verify managed skill was updated
    grep -q "v2" /root/.claude/skills/learned/my-real-skill/SKILL.md && echo "skill updated"

    # Verify workspace dirs were preserved
    [ -d /root/.claude/skills/learned/my-real-skill-workspace ] && echo "claude workspace preserved"
    [ -f /root/.claude/skills/learned/my-real-skill-workspace/iteration-1/results.md ] && echo "workspace contents intact"
    [ -d /root/.gemini/skills/learned/test-workspace ] && echo "gemini workspace preserved"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Workspace dirs preserved, skills updated
    assert "initial sync ok" in result.stdout
    assert "skill updated" in result.stdout
    assert "claude workspace preserved" in result.stdout
    assert "workspace contents intact" in result.stdout
    assert "gemini workspace preserved" in result.stdout


def test_sync_agents_does_not_import_workspace_dirs(docker_image):
    """Test that -workspace dirs are not imported from import sources.

    Scenario:
    - given: Import source has learned/ with -workspace dirs
    - when: Run sync-agents
    - then: -workspace dirs are NOT imported to dotfiles
    """
    cmd = """
    set -euo pipefail

    # Create learned dir with real skill in import source
    mkdir -p /root/.claude/skills/learned/imported-skill
    echo "# Imported Skill" > /root/.claude/skills/learned/imported-skill/SKILL.md

    # Create workspace dir in import source (should NOT be imported)
    mkdir -p /root/.claude/skills/learned/imported-skill-workspace/iteration-1
    echo "workspace data" > /root/.claude/skills/learned/imported-skill-workspace/iteration-1/data.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify real skill WAS imported
    [ -d /root/dotfiles/skills/learned/imported-skill ] && echo "real skill imported"

    # Verify workspace dir was NOT imported to dotfiles
    if [ -d /root/dotfiles/skills/learned/imported-skill-workspace ]; then
        echo "ERROR: workspace was imported"
    else
        echo "workspace correctly excluded"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: Real skill imported, workspace excluded
    assert "real skill imported" in result.stdout
    assert "workspace correctly excluded" in result.stdout


# =============================================================================
# Agents Global Directory (~/.agents/) Sync Tests
# =============================================================================


def test_sync_agents_does_not_import_from_agents_global(docker_image):
    """The bunx skills CLI store (~/.agents/skills) never enters dotfiles.

    This is the structural gate against re-vendoring (ADR 0038): even a
    perfectly valid SKILL.md in the CLI store must not be imported.

    Scenario:
    - given: A valid skill exists in ~/.agents/skills/ but not in dotfiles
    - when: Run sync-agents
    - then: It is not imported and not propagated to other targets
    """
    cmd = """
    set -euo pipefail

    # Create a skill only in ~/.agents/skills/
    mkdir -p /root/.agents/skills/global-only-skill
    echo "# Global Only Skill" > /root/.agents/skills/global-only-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify NOT imported to dotfiles, NOT propagated, preserved in store
    [ ! -e /root/dotfiles/skills/global-only-skill ] && echo "not imported"
    [ ! -e /root/.claude/skills/global-only-skill ] && echo "not propagated"
    grep -q "Global Only Skill" /root/.agents/skills/global-only-skill/SKILL.md && echo "preserved in store"
    """
    result = _run_in_container(docker_image, cmd)

    # then: the CLI store is left alone
    assert "not imported" in result.stdout
    assert "not propagated" in result.stdout
    assert "preserved in store" in result.stdout


def test_sync_agents_syncs_dotfiles_skills_to_agents_global(docker_image):
    """Test that dotfiles skills are synced TO ~/.agents/skills/.

    Scenario:
    - given: A skill exists in dotfiles but not in ~/.agents/skills/
    - when: Run sync-agents
    - then: Skill is synced to ~/.agents/skills/
    """
    cmd = """
    set -euo pipefail

    # Create a skill in dotfiles
    mkdir -p /root/dotfiles/skills/dotfiles-only-skill
    echo "# Dotfiles Only" > /root/dotfiles/skills/dotfiles-only-skill/SKILL.md

    # Ensure ~/.agents/skills/ exists but empty
    mkdir -p /root/.agents/skills

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify synced to ~/.agents/skills/
    [ -f /root/.agents/skills/dotfiles-only-skill/SKILL.md ] && echo "synced to agents global"
    grep -q "Dotfiles Only" /root/.agents/skills/dotfiles-only-skill/SKILL.md && echo "content correct"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Skill was synced to ~/.agents/
    assert "synced to agents global" in result.stdout
    assert "content correct" in result.stdout


def test_sync_agents_agents_global_only_syncs_skills(docker_image):
    """Test that ~/.agents/ only receives skills/, not commands/ or agents/.

    Scenario:
    - given: dotfiles has commands/ and agents/ directories
    - when: Run sync-agents
    - then: Only skills/ is synced to ~/.agents/, not commands/ or agents/
    """
    cmd = """
    set -euo pipefail

    # Create commands and agents in dotfiles
    mkdir -p /root/dotfiles/commands
    echo "# Strict" > /root/dotfiles/commands/strict.md
    mkdir -p /root/dotfiles/agents
    echo "# Test Agent" > /root/dotfiles/agents/test-agent.md
    # hermetic probe so skills/ distribution is observable even when the
    # (private) skills submodule is absent in CI
    mkdir -p /root/dotfiles/skills/probe-skill
    echo "# Probe" > /root/dotfiles/skills/probe-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify commands/ was NOT synced to ~/.agents/
    if [ -d /root/.agents/commands ]; then
        echo "ERROR: commands synced to agents global"
    else
        echo "commands correctly excluded"
    fi

    # Verify agents/ was NOT synced to ~/.agents/
    if [ -d /root/.agents/agents ]; then
        echo "ERROR: agents synced to agents global"
    else
        echo "agents correctly excluded"
    fi

    # Verify skills/ WAS synced (if any exist)
    [ -d /root/.agents/skills ] && echo "skills dir exists"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Only skills/ synced
    assert "commands correctly excluded" in result.stdout
    assert "agents correctly excluded" in result.stdout
    assert "skills dir exists" in result.stdout


def test_sync_agents_agents_global_no_base_file(docker_image):
    """Test that ~/.agents/ does NOT receive a base file (CLAUDE.md etc).

    Scenario:
    - given: dotfiles has ROOT_AGENTS.md
    - when: Run sync-agents
    - then: No CLAUDE.md/AGENTS.md/GEMINI.md appears in ~/.agents/
    """
    cmd = """
    set -euo pipefail

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify no base file in ~/.agents/
    if [ -f /root/.agents/CLAUDE.md ] || [ -f /root/.agents/AGENTS.md ] || [ -f /root/.agents/GEMINI.md ]; then
        echo "ERROR: base file synced to agents global"
    else
        echo "no base file in agents global"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: No base file in ~/.agents/
    assert "no base file in agents global" in result.stdout


# =============================================================================
# Learned Skills Symlink Tests (link-learned-skills integration)
# =============================================================================


def test_sync_agents_creates_symlinks_for_learned_skills(docker_image):
    """Test that learned skills get symlinked to top-level skills/.

    Scenario:
    - given: dotfiles has skills/learned/my-skill/SKILL.md
    - when: Run sync-agents
    - then: skills/my-skill -> learned/my-skill symlink created in all targets
    """
    cmd = """
    set -euo pipefail

    # Create a learned skill in dotfiles
    mkdir -p /root/dotfiles/skills/learned/my-learned-skill
    echo "---" > /root/dotfiles/skills/learned/my-learned-skill/SKILL.md
    echo "name: my-learned-skill" >> /root/dotfiles/skills/learned/my-learned-skill/SKILL.md
    echo "---" >> /root/dotfiles/skills/learned/my-learned-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify symlinks created in dotfiles
    [ -L /root/dotfiles/skills/my-learned-skill ] && echo "dotfiles symlink created"
    readlink /root/dotfiles/skills/my-learned-skill | grep -q "learned/my-learned-skill" && echo "dotfiles symlink target correct"

    # Verify symlinks created in targets
    [ -L /root/.claude/skills/my-learned-skill ] && echo "claude symlink created"
    [ -L /root/.gemini/skills/my-learned-skill ] && echo "gemini symlink created"
    [ -L /root/.codex/skills/my-learned-skill ] && echo "codex symlink created"

    # Verify symlink is functional (can read through it)
    [ -f /root/.claude/skills/my-learned-skill/SKILL.md ] && echo "claude symlink functional"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Symlinks created in dotfiles and all targets
    assert "dotfiles symlink created" in result.stdout
    assert "dotfiles symlink target correct" in result.stdout
    assert "claude symlink created" in result.stdout
    assert "gemini symlink created" in result.stdout
    assert "codex symlink created" in result.stdout
    assert "claude symlink functional" in result.stdout


def test_sync_agents_skips_workspace_dirs_in_learned(docker_image):
    """Test that -workspace directories in learned/ are not symlinked.

    Scenario:
    - given: learned/ contains both a skill and a -workspace directory
    - when: Run sync-agents
    - then: Skill is symlinked, workspace is NOT symlinked
    """
    cmd = """
    set -euo pipefail

    # Create a learned skill and a workspace
    mkdir -p /root/dotfiles/skills/learned/real-skill
    echo "---" > /root/dotfiles/skills/learned/real-skill/SKILL.md
    mkdir -p /root/dotfiles/skills/learned/real-skill-workspace/iteration-1
    echo "workspace data" > /root/dotfiles/skills/learned/real-skill-workspace/iteration-1/data.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify skill IS symlinked
    [ -L /root/.claude/skills/real-skill ] && echo "skill symlinked"

    # Verify workspace is NOT symlinked at top level
    if [ -L /root/.claude/skills/real-skill-workspace ]; then
        echo "ERROR: workspace was symlinked"
    else
        echo "workspace not symlinked"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: Skill symlinked, workspace not
    assert "skill symlinked" in result.stdout
    assert "workspace not symlinked" in result.stdout


def test_sync_agents_skips_learned_dirs_without_skill_md(docker_image):
    """Test that directories in learned/ without SKILL.md are not symlinked.

    Scenario:
    - given: learned/ contains a directory without SKILL.md
    - when: Run sync-agents
    - then: No symlink is created for it
    """
    cmd = """
    set -euo pipefail

    # Create a directory in learned/ without SKILL.md
    mkdir -p /root/dotfiles/skills/learned/no-skill-md
    echo "# README" > /root/dotfiles/skills/learned/no-skill-md/README.md

    # Create a valid one too for comparison
    mkdir -p /root/dotfiles/skills/learned/valid-skill
    echo "---" > /root/dotfiles/skills/learned/valid-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify valid skill IS symlinked
    [ -L /root/.claude/skills/valid-skill ] && echo "valid skill symlinked"

    # Verify no-skill-md is NOT symlinked
    if [ -L /root/.claude/skills/no-skill-md ]; then
        echo "ERROR: dir without SKILL.md was symlinked"
    else
        echo "no-skill-md correctly skipped"
    fi
    """
    result = _run_in_container(docker_image, cmd)

    # then: Only valid skill symlinked
    assert "valid skill symlinked" in result.stdout
    assert "no-skill-md correctly skipped" in result.stdout


def test_sync_agents_preserves_existing_learned_symlinks(docker_image):
    """Test that existing symlinks are preserved (idempotent).

    Scenario:
    - given: Learned skill symlinks already exist
    - when: Run sync-agents again
    - then: Symlinks are preserved, no errors
    """
    cmd = """
    set -euo pipefail

    # Create a learned skill
    mkdir -p /root/dotfiles/skills/learned/stable-skill
    echo "---" > /root/dotfiles/skills/learned/stable-skill/SKILL.md

    # First sync
    cd /root/dotfiles && just sync-agents all

    # Verify symlink created
    [ -L /root/.claude/skills/stable-skill ] && echo "first run: symlink exists"

    # Second sync (should be idempotent)
    cd /root/dotfiles && just sync-agents all

    # Verify symlink still exists and is correct
    [ -L /root/.claude/skills/stable-skill ] && echo "second run: symlink preserved"
    readlink /root/.claude/skills/stable-skill | grep -q "learned/stable-skill" && echo "symlink target still correct"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Symlinks preserved across runs
    assert "first run: symlink exists" in result.stdout
    assert "second run: symlink preserved" in result.stdout
    assert "symlink target still correct" in result.stdout


def test_sync_agents_no_symlink_when_real_dir_exists(docker_image):
    """Test that symlink is NOT created if a real (non-symlink) dir exists.

    Scenario:
    - given: skills/foo/ is a real directory AND learned/foo/ also exists
    - when: Run sync-agents
    - then: The real directory is preserved, no symlink replaces it
    """
    cmd = """
    set -euo pipefail

    # Create a learned skill
    mkdir -p /root/dotfiles/skills/learned/conflicting-skill
    echo "---" > /root/dotfiles/skills/learned/conflicting-skill/SKILL.md
    echo "learned version" >> /root/dotfiles/skills/learned/conflicting-skill/SKILL.md

    # Also create a real (non-learned) skill with the same name
    mkdir -p /root/dotfiles/skills/conflicting-skill
    echo "# Real skill" > /root/dotfiles/skills/conflicting-skill/SKILL.md
    echo "real version" >> /root/dotfiles/skills/conflicting-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify in target: should be a real directory, NOT a symlink
    if [ -L /root/.claude/skills/conflicting-skill ]; then
        echo "ERROR: symlink replaced real dir"
    else
        echo "real dir preserved"
    fi

    # Verify it has the real version content (from dotfiles/skills/, not learned/)
    grep -q "real version" /root/.claude/skills/conflicting-skill/SKILL.md && echo "real content preserved"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Real directory preserved, no symlink
    assert "real dir preserved" in result.stdout
    assert "real content preserved" in result.stdout


def test_sync_agents_no_learned_dir_no_error(docker_image):
    """Test that sync works fine when learned/ directory doesn't exist.

    Scenario:
    - given: No skills/learned/ directory
    - when: Run sync-agents
    - then: No errors, sync completes normally
    """
    cmd = """
    set -euo pipefail

    # Ensure no learned dir exists
    rm -rf /root/dotfiles/skills/learned

    # Create a regular skill
    mkdir -p /root/dotfiles/skills/regular-skill
    echo "# Regular" > /root/dotfiles/skills/regular-skill/SKILL.md

    # Run sync-agents (should not error)
    cd /root/dotfiles && just sync-agents all

    # Verify regular skill was synced
    [ -f /root/.claude/skills/regular-skill/SKILL.md ] && echo "regular skill synced"
    echo "no errors"
    """
    result = _run_in_container(docker_image, cmd)

    # then: No errors
    assert "regular skill synced" in result.stdout
    assert "no errors" in result.stdout


def test_sync_agents_learned_symlinks_survive_resync(docker_image):
    """Test that learned symlinks survive when learned/ content changes.

    Scenario:
    - given: A learned skill with symlink exists
    - when: The learned skill content changes and sync runs again
    - then: Symlink still works and points to updated content
    """
    cmd = """
    set -euo pipefail

    # Create initial learned skill
    mkdir -p /root/dotfiles/skills/learned/evolving-skill
    echo "# Version 1" > /root/dotfiles/skills/learned/evolving-skill/SKILL.md

    # First sync
    cd /root/dotfiles && just sync-agents all
    [ -L /root/.claude/skills/evolving-skill ] && echo "symlink created"

    # Update the learned skill content
    echo "# Version 2" > /root/dotfiles/skills/learned/evolving-skill/SKILL.md

    # Second sync
    cd /root/dotfiles && just sync-agents all

    # Verify symlink still works and reflects new content
    [ -L /root/.claude/skills/evolving-skill ] && echo "symlink preserved"
    grep -q "Version 2" /root/.claude/skills/evolving-skill/SKILL.md && echo "content updated through symlink"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Symlink preserved and content accessible
    assert "symlink created" in result.stdout
    assert "symlink preserved" in result.stdout
    assert "content updated through symlink" in result.stdout


def test_sync_agents_learned_symlinks_in_dotfiles_itself(docker_image):
    """Test that symlinks are also created in dotfiles/skills/ itself.

    Scenario:
    - given: dotfiles has skills/learned/my-skill/SKILL.md
    - when: Run sync-agents
    - then: dotfiles/skills/my-skill -> learned/my-skill symlink exists
    """
    cmd = """
    set -euo pipefail

    # Create a learned skill
    mkdir -p /root/dotfiles/skills/learned/dotfiles-linked-skill
    echo "---" > /root/dotfiles/skills/learned/dotfiles-linked-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify symlink in dotfiles itself
    [ -L /root/dotfiles/skills/dotfiles-linked-skill ] && echo "dotfiles symlink exists"
    readlink /root/dotfiles/skills/dotfiles-linked-skill | grep -q "learned/dotfiles-linked-skill" && echo "relative symlink correct"

    # Verify the symlink is functional
    [ -f /root/dotfiles/skills/dotfiles-linked-skill/SKILL.md ] && echo "symlink functional"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Symlink exists in dotfiles
    assert "dotfiles symlink exists" in result.stdout
    assert "relative symlink correct" in result.stdout
    assert "symlink functional" in result.stdout


def test_sync_agents_agents_global_gets_learned_symlinks(docker_image):
    """Test that ~/.agents/skills/ also gets learned skill symlinks.

    Scenario:
    - given: dotfiles has skills/learned/my-skill/SKILL.md
    - when: Run sync-agents
    - then: ~/.agents/skills/my-skill -> learned/my-skill symlink exists
    """
    cmd = """
    set -euo pipefail

    # Create a learned skill
    mkdir -p /root/dotfiles/skills/learned/agents-linked-skill
    echo "---" > /root/dotfiles/skills/learned/agents-linked-skill/SKILL.md

    # Run sync-agents
    cd /root/dotfiles && just sync-agents all

    # Verify learned/ was synced to ~/.agents/skills/
    [ -d /root/.agents/skills/learned/agents-linked-skill ] && echo "learned synced"

    # Verify symlink created in ~/.agents/skills/
    [ -L /root/.agents/skills/agents-linked-skill ] && echo "agents symlink exists"
    readlink /root/.agents/skills/agents-linked-skill | grep -q "learned/agents-linked-skill" && echo "agents symlink target correct"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Symlinks in ~/.agents/
    assert "learned synced" in result.stdout
    assert "agents symlink exists" in result.stdout
    assert "agents symlink target correct" in result.stdout


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
    - given: Non-import target has orphan skills
    - when: Run sync-agents --override
    - then: Orphans are deleted, target matches dotfiles

    Note: Uses Work-A (non-import-source) to avoid import phase interference.
    """
    cmd = """
    set -euo pipefail

    # First sync to establish baseline
    cd /root/dotfiles && just sync-agents all

    # Add orphan skills to non-import target
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
    - given: Non-import target has both dotfiles skills and orphans
    - when: Run sync-agents --override
    - then: Dotfiles skills remain, orphans are removed

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


def test_import_agents_never_pulls_skills_into_dotfiles(docker_image):
    """Even explicit import-agents does not pull skills (declarative model).

    Scenario:
    - given: A valid skill exists in ~/.claude/skills/ but not in dotfiles
    - when: Run `just import-agents` (default scope = claude only)
    - then: The skill is NOT imported into dotfiles/skills/
    """
    cmd = """
    set -euo pipefail

    mkdir -p /root/.claude/skills/imported-from-claude
    echo "# imported" > /root/.claude/skills/imported-from-claude/SKILL.md

    cd /root/dotfiles && just import-agents

    [ ! -e /root/dotfiles/skills/imported-from-claude ] && echo "skill not imported"
    """
    result = _run_in_container(docker_image, cmd)

    assert "skill not imported" in result.stdout


def test_import_agents_does_not_forward_sync_to_targets(docker_image):
    """import-agents must NOT push dotfiles content into targets (Phase 2-3 skipped).

    Scenario:
    - given: A skill exists in dotfiles but not in any target
    - when: Run `just import-agents all`
    - then: The skill stays only in dotfiles; targets are NOT created/updated
    """
    cmd = """
    set -euo pipefail

    mkdir -p /root/dotfiles/skills/dotfiles-only
    echo "# dotfiles only" > /root/dotfiles/skills/dotfiles-only/README.md

    cd /root/dotfiles && just import-agents all

    [ -f /root/dotfiles/skills/dotfiles-only/README.md ] && echo "stayed in dotfiles"
    [ ! -e /root/.claude/skills/dotfiles-only ] && echo "not pushed to claude"
    [ ! -e /root/.claude-work-a/skills/dotfiles-only ] && echo "not pushed to work-a"
    [ ! -e /root/.gemini/skills/dotfiles-only ] && echo "not pushed to gemini"
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


def test_skills_are_additive_add_missing_no_overwrite_no_delete(docker_image):
    """skills/ is additive: even `--yes` sync ADDS a missing dotfiles skill, but
    never overwrites an existing target skill (a bunx-skills CLI symlink/copy)
    and never deletes a target-only skill."""
    cmd = r"""
    set -euo pipefail
    mkdir -p /root/.claude/skills/cli-only-skill
    echo "# CLI Only" > /root/.claude/skills/cli-only-skill/SKILL.md
    mkdir -p /root/.claude/skills/tdd-workflow
    echo "SENTINEL-KEEP" > /root/.claude/skills/tdd-workflow/SKILL.md
    # hermetic probes: one skill missing from the target, one already present
    mkdir -p /root/dotfiles/skills/probe-add-skill
    echo "# Probe Add" > /root/dotfiles/skills/probe-add-skill/SKILL.md
    mkdir -p /root/dotfiles/skills/tdd-workflow
    echo "# dotfiles version" > /root/dotfiles/skills/tdd-workflow/SKILL.md

    cd /root/dotfiles && just sync-agents p

    [ -f /root/.claude/skills/cli-only-skill/SKILL.md ] && echo "orphan-preserved"
    grep -q "CLI Only" /root/.claude/skills/cli-only-skill/SKILL.md && echo "orphan-content-intact"
    grep -q "SENTINEL-KEEP" /root/.claude/skills/tdd-workflow/SKILL.md && echo "existing-not-overwritten"
    # a skill in dotfiles but missing in the target IS added (add-only)
    [ -e /root/.claude/skills/probe-add-skill ] && echo "missing-skill-added" || echo "ERR-missing-not-added"
    """
    result = _run_in_container(docker_image, cmd)
    for marker in (
        "orphan-preserved",
        "orphan-content-intact",
        "existing-not-overwritten",
        "missing-skill-added",
    ):
        assert marker in result.stdout, f"missing {marker}\n{result.stdout}"
    assert "ERR-missing-not-added" not in result.stdout, result.stdout


def test_no_skills_flag_deploys_instructions_and_skips_skills(docker_image):
    """--no-skills deploys instructions (base/spokes) but skips skills entirely:
    no dotfiles skill is copied in, and a target-only skill is left untouched."""
    cmd = r"""
    set -euo pipefail
    # a target-only skill that a full sync would otherwise see
    mkdir -p /root/.gemini/skills/cli-only-skill
    echo "# CLI Only" > /root/.gemini/skills/cli-only-skill/SKILL.md
    # hermetic probe: a dotfiles skill that --no-skills must NOT copy
    mkdir -p /root/dotfiles/skills/probe-add-skill
    echo "# Probe Add" > /root/dotfiles/skills/probe-add-skill/SKILL.md

    cd /root/dotfiles && just sync-agents --no-skills g

    # instructions ARE deployed
    grep -q 'Non-negotiables' /root/.gemini/GEMINI.md && echo "base-deployed"
    [ -f /root/.gemini/docs/agents/testing.md ] && echo "spoke-deployed"
    # skills are NOT touched: target-only skill preserved, dotfiles skill NOT copied
    [ -f /root/.gemini/skills/cli-only-skill/SKILL.md ] && echo "orphan-preserved"
    [ -e /root/.gemini/skills/probe-add-skill ] && echo "ERR-skill-copied" || echo "dotfiles-skill-not-copied"
    """
    result = _run_in_container(docker_image, cmd)
    for marker in (
        "base-deployed",
        "spoke-deployed",
        "orphan-preserved",
        "dotfiles-skill-not-copied",
    ):
        assert marker in result.stdout, f"missing {marker}\n{result.stdout}"
    assert "ERR-skill-copied" not in result.stdout, result.stdout


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
