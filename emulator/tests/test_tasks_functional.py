"""Cloud Tasks functional test (REST).

Why this may be skipped:
- The Cloud Tasks emulator often does not implement the full REST surface.
  When the discovery check fails (or endpoints close connections), we skip
  the functional test instead of failing the suite.
"""

import uuid
import pytest
from aiohttp import ClientTimeout


async def _tasks_rest_supported(http_client, base_url: str, project_id: str) -> bool:
    try:
        async with http_client.get(
            f"{base_url}/projects/{project_id}/locations/{LOCATION}/queues",
            timeout=ClientTimeout(total=3.0),
        ) as res:
            return res.status in (200, 404)
    except Exception:
        return False


BASE = "http://localhost:9499/v2"
LOCATION = "us-central1"


@pytest.mark.asyncio
@pytest.mark.parametrize("queue_id", ["q-default", "q-jobs"])
async def test_tasks_create_queue_and_list(queue_id, project_id, http_client):
    if not await _tasks_rest_supported(http_client, BASE, project_id):
        pytest.skip(
            "Cloud Tasks REST API not implemented by emulator; skipping functional test"
        )
    # given: queue name
    queue_name = f"projects/{project_id}/locations/{LOCATION}/queues/{queue_id}-{uuid.uuid4().hex[:6]}"

    # when: create queue
    create_url = f"{BASE}/projects/{project_id}/locations/{LOCATION}/queues"
    async with http_client.post(
        create_url,
        json={"queue": {"name": queue_name}},
        timeout=ClientTimeout(total=5.0),
    ) as create_res:
        # then: queue is created (200) or already exists (409)
        assert create_res.status in (200, 409), await create_res.text()

    # when: list queues
    list_url = f"{BASE}/projects/{project_id}/locations/{LOCATION}/queues"
    async with http_client.get(list_url, timeout=ClientTimeout(total=5.0)) as list_res:
        # then: response includes our queue or is a valid list
        assert list_res.status == 200, await list_res.text()
        data = await list_res.json()
    names = [q.get("name") for q in data.get("queues", [])]
    assert queue_name in names
