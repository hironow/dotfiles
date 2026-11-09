import pytest

from tests.utils.helpers import (
    host_endpoint,
    podman_client,
    skip_unless_container_running,
)


@pytest.fixture(autouse=True)
def _require_qdrant():
    skip_unless_container_running("qdrant-emulator")


@pytest.mark.asyncio
async def test_qdrant_container_starts(http_client):
    """Test that the Qdrant container starts and is healthy."""
    client = podman_client()

    from tests.utils.helpers import get_container, wait_for_http
    from tests.utils.result import Error, Ok

    # Check if qdrant container exists and is running
    match get_container(client, "qdrant-emulator"):
        case Ok(container):
            assert container.status == "running", (
                f"Qdrant container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if Qdrant REST API is accessible
    match await wait_for_http(
        http_client, host_endpoint("http://localhost:6333/healthz")
    ):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)

    # Verify Qdrant is ready
    async with http_client.get(
        host_endpoint("http://localhost:6333/readyz")
    ) as response:
        assert response.status == 200, f"Qdrant is not ready, status: {response.status}"
