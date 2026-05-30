import pytest
import docker


@pytest.mark.asyncio
async def test_neo4j_container_starts(http_client):
    """Test that the Neo4j container starts and is healthy."""
    client = docker.from_env()

    from tests.utils.helpers import get_container, wait_for_http
    from tests.utils.result import Error, Ok

    # Check if neo4j container exists and is running
    match get_container(client, "neo4j-emulator"):
        case Ok(container):
            assert container.status == "running", (
                f"Neo4j container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if Neo4j HTTP endpoint is accessible
    match await wait_for_http(http_client, "http://localhost:7474"):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)
