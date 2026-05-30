import pytest
import docker


@pytest.mark.asyncio
async def test_firebase_container_starts(http_client):
    """Test that the Firebase container starts and is healthy."""
    client = docker.from_env()

    from tests.utils.helpers import get_container, wait_for_http
    from tests.utils.result import Error, Ok

    # Check if firebase container exists and is running
    match get_container(client, "firebase-emulator"):
        case Ok(container):
            assert container.status == "running", (
                f"Firebase container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if Firebase UI is accessible
    match await wait_for_http(http_client, "http://localhost:4000"):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)
