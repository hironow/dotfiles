import pytest
import docker

from tests.utils.helpers import skip_unless_container_running


@pytest.fixture(autouse=True)
def _require_bigtable():
    skip_unless_container_running("bigtable-emulator")


def test_bigtable_container_starts():
    """Test that the Bigtable emulator container starts and is healthy."""
    client = docker.from_env()

    from tests.utils.helpers import get_container, wait_for_tcp
    from tests.utils.result import Error, Ok

    # Check if bigtable container exists and is running
    match get_container(client, "bigtable-emulator"):
        case Ok(container):
            assert container.status == "running", (
                f"Bigtable container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if Bigtable gRPC endpoint is accessible
    match wait_for_tcp("localhost", 8086):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)
