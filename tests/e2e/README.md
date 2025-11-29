# E2E Tests

End-to-end tests for dotfiles justfile commands.

## Overview

E2E tests run in isolated Docker containers to avoid polluting the host environment. All dependencies (files, directories, commands) are real - no mocks are used.

## Requirements

- Docker daemon running
- `pytest` (installed via `uvx`)
- `just` (available in Docker image)

## Running Tests

```bash
# Run all e2e tests
uvx pytest tests/e2e/ -v

# Run specific test file
uvx pytest tests/e2e/test_sync_agents.py -v

# Run specific test
uvx pytest tests/e2e/test_sync_agents.py::test_sync_agents_is_idempotent -v

# Run with verbose output
uvx pytest tests/e2e/ -v -ra
```

## Test Structure

### Test Environment

- **Docker Image**: `dotfiles-just-sandbox:latest` (built from `tests/docker/JustSandbox.Dockerfile`)
- **Base Image**: Alpine Linux 3.19
- **Working Directory**: `/root/dotfiles` (repository contents copied)
- **Container Lifecycle**: Each test runs in a fresh container (--rm flag)

### Test Isolation

- Each test uses a fresh Docker container
- No state persists between tests
- Commands and verification run in the same container instance (single bash script)
- Host environment is never modified

## Available Tests

### `test_sync_agents.py`

Tests for the `just sync-agents` command that syncs ROOT_AGENTS.md to agent instruction files.

#### Test Cases

1. **test_sync_agents_creates_files_on_first_run**

   - Verifies files are created on first run
   - Checks content matches source file
   - Validates all three agent files (Claude, Gemini, Codex)

2. **test_sync_agents_is_idempotent**

   - Runs sync-agents twice
   - Verifies second run reports "Already in sync"
   - Ensures no unnecessary operations

3. **test_sync_agents_detects_differences**

   - Modifies an agent file
   - Verifies differences are detected
   - Tests interactive prompt behavior

4. **test_sync_agents_creates_missing_directories**
   - Verifies directories are created if they don't exist
   - Checks all three agent directories

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
    # given: Setup and action in single container
    cmd = """
    set -euo pipefail

    # Setup if needed
    ...

    # Execute command
    cd /root/dotfiles && just my-command

    # Verify results in same container
    [ -f /some/file ] && echo "success"
    """
    result = _run_in_container(docker_image, cmd)

    # then: Assertions
    assert "success" in result.stdout
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

2. **Manual Container Run**: Test commands manually

   ```bash
   docker run --rm -it -w /root/dotfiles dotfiles-just-sandbox:latest bash
   ```

3. **View Test Output**: Use `-v` flag for verbose output

   ```bash
   uvx pytest tests/e2e/test_sync_agents.py -v -s
   ```

4. **Check Container State**: Remove `--rm` temporarily to inspect
   ```bash
   # In test code, temporarily change:
   "docker", "run", "-it", ...  # instead of "--rm"
   ```

## CI Integration

Tests are designed to run in CI environments:

- Skip if Docker is unavailable (pytest.skip)
- Build image once per test session (module-scoped fixture)
- Clean up containers automatically (--rm flag)
- Fast execution (parallel container runs)

## Related Files

- `tests/docker/JustSandbox.Dockerfile` - Docker image definition
- `tests/test_just_sandbox.py` - Legacy sandbox tests (to be migrated)
- `justfile` - Commands being tested
