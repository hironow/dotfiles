import os

import docker
import pytest


def test_postgres18_container_starts() -> None:
    client = docker.from_env()

    from tests.utils.helpers import get_container, wait_for_tcp
    from tests.utils.result import Error, Ok

    # Check if postgres container exists and is running
    match get_container(client, "postgres-18"):
        case Ok(container):
            assert container.status == "running", (
                f"PostgreSQL container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if PostgreSQL port is accessible
    port = int(os.getenv("POSTGRES_PORT", "5433"))
    match wait_for_tcp("localhost", port):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)
