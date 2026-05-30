import pytest
import docker


def test_spanner_container_starts():
    """Test that the Spanner container starts and is healthy."""
    client = docker.from_env()

    from tests.utils.helpers import get_container, wait_for_tcp
    from tests.utils.result import Error, Ok

    # Check if spanner container exists and is running
    match get_container(client, "spanner-emulator"):
        case Ok(container):
            assert container.status == "running", (
                f"Spanner container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if Spanner gRPC endpoint is accessible
    match wait_for_tcp("localhost", 9010):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)
