import socket
import time

import docker.errors
import pytest

from tests.utils.helpers import owned_container, podman_client, service_address


def test_pgadapter_container_starts():
    """Test that the pgAdapter container starts and is healthy."""
    host, port = service_address("pgadapter-emulator", 55432, "PGADAPTER_PORT")
    client = podman_client()

    # Check if pgadapter container exists and is running
    try:
        container = owned_container(client, "pgadapter-emulator")
        assert container.status == "running", (
            f"pgAdapter container is not running, status: {container.status}"
        )
    except docker.errors.NotFound:
        pytest.fail(
            "pgAdapter container 'pgadapter-emulator' not found. Run 'PODMAN_COMPOSE_PROVIDER=podman-compose podman compose --in-pod=false up pgadapter' first."
        )

    # Check if PostgreSQL port is accessible
    max_retries = 30
    for i in range(max_retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                break
        except Exception:
            pass

        if i == max_retries - 1:
            pytest.fail(
                f"pgAdapter PostgreSQL endpoint is not accessible at localhost:{port}"
            )
        time.sleep(1)
