import pytest
import docker


@pytest.mark.asyncio
async def test_a2a_inspector_container_starts(http_client):
    """Test that the A2A Inspector container starts and is healthy."""
    client = docker.from_env()

    # Check if a2a-inspector container exists and is running
    from tests.utils.helpers import get_container, wait_for_http
    from tests.utils.result import Error, Ok

    match get_container(client, "a2a-inspector"):
        case Ok(container):
            assert container.status == "running", (
                f"A2A Inspector container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if A2A Inspector HTTP endpoint is accessible
    match await wait_for_http(http_client, "http://localhost:8081"):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)
