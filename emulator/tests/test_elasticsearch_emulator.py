import pytest
import docker


@pytest.mark.asyncio
async def test_elasticsearch_container_starts(http_client):
    """Test that the Elasticsearch container starts and is healthy."""
    client = docker.from_env()

    from tests.utils.helpers import get_container, wait_for_http
    from tests.utils.result import Error, Ok

    # Check if elasticsearch container exists and is running
    match get_container(client, "elasticsearch-emulator"):
        case Ok(container):
            assert container.status == "running", (
                f"Elasticsearch container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if Elasticsearch REST API is accessible
    match await wait_for_http(http_client, "http://localhost:9200/_cluster/health"):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)

    # Verify Elasticsearch is ready
    async with http_client.get("http://localhost:9200/_cluster/health") as response:
        assert response.status == 200, (
            f"Elasticsearch is not ready, status: {response.status}"
        )
        # Check cluster health
        health_data = await response.json()
    assert health_data["status"] in ["green", "yellow"], (
        f"Elasticsearch cluster is not healthy: {health_data['status']}"
    )
