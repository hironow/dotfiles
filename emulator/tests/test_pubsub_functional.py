"""Pub/Sub functional test via REST.

The firebase Pub/Sub emulator downloads its jar on first start, so the REST
endpoint can briefly refuse or 5xx before it is ready. We retry topic/subscription
creation while it boots, then assert the publish -> pull -> ack round-trip. A
genuine failure now fails the test instead of silently skipping it.
"""

import asyncio
import base64
import uuid

import pytest

BASE = "http://localhost:9399/v1"


async def _put_until_ready(client, url, *, json=None, retries: int = 30) -> None:
    """PUT until the Pub/Sub emulator answers (200/409), tolerating startup.

    Always sends a JSON body (empty `{}` when none is given) so aiohttp sets
    `Content-Type: application/json`; the emulator's REST router 404s a bodyless
    PUT, which is what made the original test silently skip.
    """
    body = json if json is not None else {}
    last = ""
    for _ in range(retries):
        try:
            async with client.put(url, json=body) as res:
                if res.status in (200, 409):
                    return
                last = f"{res.status} {await res.text()}"
        except Exception as e:  # connection refused while the jar boots
            last = str(e)
        await asyncio.sleep(1)
    raise AssertionError(f"Pub/Sub REST not ready after {retries}s: {last}")


@pytest.mark.asyncio
@pytest.mark.parametrize("topic_base", ["test-topic", "events"])
async def test_pubsub_end_to_end_publish_and_pull(topic_base, project_id, http_client):
    suffix = uuid.uuid4().hex[:8]
    topic = f"projects/{project_id}/topics/{topic_base}-{suffix}"
    sub = f"projects/{project_id}/subscriptions/{topic_base}-sub-{suffix}"
    client = http_client

    # given: a topic and a subscription (retry create while the emulator boots)
    await _put_until_ready(client, f"{BASE}/{topic}")
    await _put_until_ready(client, f"{BASE}/{sub}", json={"topic": topic})

    # when: publish a message
    payload = base64.b64encode(b"hello-pubsub").decode()
    async with client.post(
        f"{BASE}/{topic}:publish", json={"messages": [{"data": payload}]}
    ) as pub_res:
        assert pub_res.status == 200, await pub_res.text()

    # then: the message is pullable and the payload round-trips
    pulled: list = []
    for _ in range(10):
        async with client.post(
            f"{BASE}/{sub}:pull", json={"maxMessages": 1}
        ) as pull_res:
            assert pull_res.status == 200, await pull_res.text()
            pulled = (await pull_res.json(content_type=None)).get(
                "receivedMessages", []
            )
        if pulled:
            break
        await asyncio.sleep(1)
    assert pulled, "no message pulled from Pub/Sub"
    msg = pulled[0]["message"]
    assert base64.b64decode(msg["data"]).decode() == "hello-pubsub"

    # and: it can be acknowledged
    async with client.post(
        f"{BASE}/{sub}:acknowledge", json={"ackIds": [pulled[0]["ackId"]]}
    ) as ack_res:
        assert ack_res.status == 200, await ack_res.text()
