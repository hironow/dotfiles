import pytest

from tests.utils.helpers import podman_client, service_address


def test_postgres18_container_starts() -> None:
    host, port = service_address("postgres-18", 5433, "POSTGRES_PORT")
    client = podman_client()

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
    match wait_for_tcp(host, port):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)
