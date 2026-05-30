import os
import pytest
import docker
import time
import socket


def test_pgadapter_container_starts():
    """Test that the pgAdapter container starts and is healthy."""
    client = docker.from_env()

    # Check if pgadapter container exists and is running
    try:
        container = client.containers.get("pgadapter-emulator")
        assert container.status == "running", (
            f"pgAdapter container is not running, status: {container.status}"
        )
    except docker.errors.NotFound:
        pytest.fail(
            "pgAdapter container 'pgadapter-emulator' not found. Run 'docker compose up pgadapter' first."
        )

    # Check if PostgreSQL port is accessible
    max_retries = 30
    port = int(os.getenv("PGADAPTER_PORT", "55432"))
    for i in range(max_retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex(("localhost", port))
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
