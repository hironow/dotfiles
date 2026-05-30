"""Common e2e test fixtures for Docker-based scenarios.

- Provides a shared `docker_client` with ping/skip handling.
- Ensures emulator Docker network and required services are present.
- Helpers to build images and run CLI commands inside containers.
"""

import os
import textwrap
from typing import Callable

import pytest


# Automatically mark tests under tests/e2e/ as e2e (and only those)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    from pathlib import Path

    e2e_root = Path(__file__).parent.resolve()
    for item in items:
        path = Path(str(getattr(item, "path", ""))).resolve()
        try:
            # Python 3.9+: precise subtree check
            if path.is_relative_to(e2e_root):
                item.add_marker(pytest.mark.e2e)
        except AttributeError:  # pragma: no cover
            # Fallback for very old Python (not expected here)
            if str(path).startswith(str(e2e_root)):
                item.add_marker(pytest.mark.e2e)


@pytest.fixture(scope="session")
def e2e_network_name() -> str:
    """Docker network name used by emulators.

    Override with env var `EMULATOR_NETWORK` if needed.
    """
    return os.environ.get("EMULATOR_NETWORK", "emulator-network")


@pytest.fixture(scope="session")
def docker_client():
    """Shared Docker client or skip if unavailable."""
    try:
        import docker  # type: ignore

        client = docker.from_env()
        client.ping()
        return client
    except Exception as e:  # pragma: no cover - env dependent
        pytest.skip(f"docker not available: {e}")


@pytest.fixture
def ensure_network(docker_client, e2e_network_name: str) -> Callable[[], None]:
    """Return a callable that skips if the emulator network is missing."""

    def _ensure() -> None:
        nets = docker_client.networks.list(names=[e2e_network_name])
        if not nets:
            pytest.skip(
                f"network '{e2e_network_name}' not found. Start emulators first (docker compose up -d)"
            )

    return _ensure


@pytest.fixture
def require_services(docker_client) -> Callable[[list[str]], None]:
    """Return a callable that ensures given containers are running, else skip."""

    def _req(names: list[str]) -> None:
        running = {c.name for c in docker_client.containers.list()}
        missing = [n for n in names if n not in running]
        if missing:
            pytest.skip(
                f"required emulator containers not running: {', '.join(missing)}"
            )

    return _req


@pytest.fixture
def build_image(docker_client) -> Callable[[str, str], None]:
    """Return a callable to build a local image from a directory path."""

    def _build(path: str, tag: str) -> None:
        try:
            docker_client.images.build(path=path, tag=tag, rm=True)
        except Exception as e:  # pragma: no cover - env dependent
            pytest.skip(f"failed to build image {tag} from {path}: {e}")

    return _build


@pytest.fixture
def run_cli(
    docker_client, e2e_network_name: str
) -> Callable[[str, str, str, dict[str, str]], str]:
    """Return a callable to run a CLI binary in a container via here-doc.

    Usage: run_cli(image, binary, script, env) -> stdout/stderr text
    """

    def _run(image: str, binary: str, script: str, env: dict[str, str]) -> str:
        script = textwrap.dedent(script).lstrip("\n")
        heredoc = f"cat <<'EOF' | ./{binary}\n{script}\nEOF"
        container = None
        try:
            # Run container in detached mode to enable timeout handling
            container = docker_client.containers.run(
                image=image,
                command=["sh", "-lc", heredoc],
                environment=env,
                network=e2e_network_name,
                detach=True,
                stdout=True,
                stderr=True,
            )

            # Wait for container to finish with 5-minute timeout
            exit_code = container.wait(timeout=300)

            # Get logs after completion
            logs = container.logs(stdout=True, stderr=True)

            # Clean up container
            container.remove()

            # Check exit code
            if isinstance(exit_code, dict):
                status_code = exit_code.get("StatusCode", 0)
            else:
                status_code = exit_code

            if status_code != 0:
                pytest.fail(
                    f"Container exited with code {status_code}. Output:\n{logs.decode(errors='ignore')}"
                )

            return logs.decode(errors="ignore")
        except Exception as e:  # pragma: no cover - env dependent
            # Clean up container on error
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            pytest.skip(f"run {image} failed: {e}")

    return _run


@pytest.fixture
def run_shell(
    docker_client, e2e_network_name: str
) -> Callable[[str, str, dict[str, str]], str]:
    """Return a callable to run an arbitrary shell command in a container.

    Usage: run_shell(image, command, env) -> stdout/stderr text
    """

    def _run(image: str, command: str, env: dict[str, str]) -> str:
        container = None
        try:
            # Run container in detached mode to enable timeout handling
            container = docker_client.containers.run(
                image=image,
                command=["sh", "-lc", command],
                environment=env,
                network=e2e_network_name,
                detach=True,
                stdout=True,
                stderr=True,
            )

            # Wait for container to finish with 5-minute timeout
            exit_code = container.wait(timeout=300)

            # Get logs after completion
            logs = container.logs(stdout=True, stderr=True)

            # Clean up container
            container.remove()

            # Check exit code
            if isinstance(exit_code, dict):
                status_code = exit_code.get("StatusCode", 0)
            else:
                status_code = exit_code

            if status_code != 0:
                pytest.fail(
                    f"Container exited with code {status_code}. Output:\n{logs.decode(errors='ignore')}"
                )

            return logs.decode(errors="ignore")
        except Exception as e:  # pragma: no cover - env dependent
            # Clean up container on error
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            pytest.skip(f"run {image} failed: {e}")

    return _run
