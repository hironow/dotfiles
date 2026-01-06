# E2E Tests

End-to-end tests for dotfiles justfile commands.

## Overview

E2E tests run in isolated Docker containers to avoid polluting the host environment. All dependencies (files, directories, commands) are real - no mocks are used.

## Requirements

- Docker daemon running
- `pytest` (installed via `uvx`)
- `uv` (for running Python scripts)
- `just` (latest version with `[group()]` syntax support)

## Running Tests

```bash
# Run all e2e tests
uvx pytest tests/e2e/ -v

# Run specific test file
uvx pytest tests/e2e/test_sync_agents.py -v

# Run specific test
uvx pytest tests/e2e/test_sync_agents.py::test_sync_agents_is_idempotent -v

# Run tests by keyword
uvx pytest tests/e2e/ -v -k "directory"
```

## Test Structure

### Test Environment

- **Docker Image**: `dotfiles-just-sandbox:latest` (built from `tests/docker/JustSandbox.Dockerfile`)
- **Base Image**: Alpine Linux 3.19
- **Tools**: bash, just (latest), python3, uv
- **Working Directory**: `/root/dotfiles` (repository contents copied)
- **Container Lifecycle**: Each test runs in a fresh container (`--rm` flag)

### Test Isolation

- Each test uses a fresh Docker container
- No state persists between tests
- Commands and verification run in the same container instance (single bash script)
- Host environment is never modified

## Available Tests

### `test_sync_agents.py`

Tests for the `just sync-agents` commands that sync ROOT_AGENTS files to agent instruction directories.

#### File Naming Convention

```
dotfiles/ (flat)                     -> ~/.claude/ (structured)
---------------------------------------------------------
ROOT_AGENTS.md                       -> CLAUDE.md
ROOT_AGENTS_commands_strict.md       -> commands/strict.md
ROOT_AGENTS_skills_my-skill/         -> skills/my-skill/
ROOT_AGENTS_hooks_formatter.py       -> hooks/formatter.py
ROOT_AGENTS_agents_subagent/         -> agents/subagent/
```

The `_` in filenames (after `ROOT_AGENTS_`) are converted to `/` for target path.

#### Just Commands

| Command | Description |
|---------|-------------|
| `just sync-agents` | Interactive sync (prompts on changes) |
| `just sync-agents-preview` | Dry-run mode (show plan without changes) |
| `just sync-agents-auto` | Auto-sync all without prompts |

#### Test Cases (12 tests)

**Basic Functionality**

1. `test_sync_agents_creates_files_on_first_run` - Verifies files are created on first run
2. `test_sync_agents_is_idempotent` - Second run reports "SYNCED" status
3. `test_sync_agents_creates_missing_directories` - Creates agent directories if missing

**Path Conversion**

4. `test_sync_agents_converts_underscore_to_path` - `ROOT_AGENTS_commands_strict.md` -> `commands/strict.md`
5. `test_sync_agents_handles_directory_sources` - Syncs directories with nested contents
6. `test_sync_agents_handles_python_file_extension` - `ROOT_AGENTS_hooks_formatter.py` -> `hooks/formatter.py`

**Preview Mode**

7. `test_sync_agents_preview_shows_plan` - Shows plan without making changes
8. `test_sync_agents_preview_shows_new_files` - Shows `[NEW]` status for missing files
9. `test_sync_agents_preview_shows_synced_files` - Shows `[SYNCED]` status for up-to-date files

**Change Detection**

10. `test_sync_agents_detects_changed_files` - Shows `[CHANGED]` status for modified files

**Error Handling**

11. `test_sync_agents_fails_without_base_file` - Fails gracefully when `ROOT_AGENTS.md` is missing

**Multi-Agent**

12. `test_sync_agents_syncs_to_all_agents` - Syncs to all configured agents (Claude, Gemini, Codex)

## Writing New E2E Tests

### Principles

1. **No Mocks**: Use real files, commands, and file systems
2. **Isolation**: Run in Docker to avoid host pollution
3. **Single Container Instance**: Run commands and verification in the same container
4. **Clear Scenarios**: Use Given-When-Then structure

### Example Pattern

```python
def test_my_just_command(docker_image):
    """Test description with clear scenario.

    Scenario:
    - given: Initial state
    - when: Action performed
    - then: Expected outcome
    """
    cmd = """
    set -euo pipefail

    # Setup if needed
    mkdir -p /some/dir
    echo "content" > /some/file

    # Execute command
    cd /root/dotfiles && just my-command

    # Verify results in same container
    [ -f /expected/file ] && echo "file exists"
    grep -q "expected content" /expected/file && echo "content correct"
    """
    result = _run_in_container(docker_image, cmd)

    # Assertions
    assert "file exists" in result.stdout
    assert "content correct" in result.stdout
```

### Helper Functions

- `_run_in_container(docker_image, cmd, check=True)`: Run bash command in container
- `_run(cmd, cwd=None, env=None)`: Run command on host (for docker commands)
- `_docker_available()`: Check if Docker is available

## Debugging Failed Tests

1. **Check Docker**: Ensure Docker daemon is running

   ```bash
   docker info
   ```

2. **Rebuild Image**: Force rebuild if Dockerfile changed

   ```bash
   docker build -t dotfiles-just-sandbox:latest -f tests/docker/JustSandbox.Dockerfile .
   ```

3. **Manual Container Run**: Test commands manually

   ```bash
   docker run --rm -it -w /root/dotfiles dotfiles-just-sandbox:latest bash
   ```

4. **View Test Output**: Use `-v -s` flags for verbose output

   ```bash
   uvx pytest tests/e2e/test_sync_agents.py -v -s
   ```

## CI Integration

Tests are designed to run in CI environments:

- Skip if Docker is unavailable (`pytest.skip`)
- Build image once per test session (module-scoped fixture)
- Clean up containers automatically (`--rm` flag)
- Fast execution (~25s for all 12 tests)

## Related Files

| File | Description |
|------|-------------|
| `tests/docker/JustSandbox.Dockerfile` | Docker image definition |
| `scripts/sync_agents.py` | Python script for sync-agents (PEP 723) |
| `justfile` | Commands being tested |
| `ROOT_AGENTS.md` | Base agent instruction file |
| `ROOT_AGENTS_*.md` | Additional agent files (path-converted) |
