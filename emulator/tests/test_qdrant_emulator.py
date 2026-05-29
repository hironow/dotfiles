import pytest
import docker


@pytest.mark.asyncio
async def test_qdrant_container_starts(http_client):
    """Test that the Qdrant container starts and is healthy."""
    client = docker.from_env()

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
    match await wait_for_http(http_client, "http://localhost:6333/healthz"):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)

    # Verify Qdrant is ready
    async with http_client.get("http://localhost:6333/readyz") as response:
        assert response.status == 200, f"Qdrant is not ready, status: {response.status}"
