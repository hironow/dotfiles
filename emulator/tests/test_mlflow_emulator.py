import pytest

from tests.utils.helpers import (
    mlflow_endpoint,
    podman_client,
    skip_unless_container_running,
)


@pytest.fixture(autouse=True)
def _require_mlflow():
    skip_unless_container_running("mlflow-server")


@pytest.mark.asyncio
async def test_mlflow_container_starts(http_client):
    """MLflow container should be running and UI reachable."""
    base = mlflow_endpoint() + "/"
    client = podman_client()

    from tests.utils.helpers import get_container, wait_for_http
    from tests.utils.result import Error, Ok

    # Check if mlflow container exists and is running
    match get_container(client, "mlflow-server"):
        case Ok(container):
            assert container.status == "running", (
                f"MLflow container is not running, status: {container.status}"
            )
        case Error(msg):
            pytest.fail(msg)

    # Check if MLflow UI is accessible
    match await wait_for_http(http_client, base):
        case Ok(_):
            pass
        case Error(msg):
            pytest.fail(msg)

    # Final verification
    async with http_client.get(base) as response:
        assert response.status in (200, 302), (
            f"MLflow UI not ready, status: {response.status}"
        )
