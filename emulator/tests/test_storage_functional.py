"""Firebase Storage functional test.

Notes:
- Bucket creation endpoint may return 501 Not Implemented on the emulator.
  We treat 501 as acceptable and proceed to upload/download checks, which is
  the behavior we truly want to validate locally.
"""

import urllib.parse
import pytest
from aiohttp import ClientTimeout


BASE = "http://localhost:9199"


async def _ensure_bucket(http_client, project_id: str, bucket: str) -> None:
    url = f"{BASE}/storage/v1/b?project={project_id}"
    async with http_client.post(
        url, json={"name": bucket}, timeout=ClientTimeout(total=5.0)
    ) as res:
        # 200/201 OK when created, 409 if exists; 501 Not Implemented is acceptable in emulator
        if res.status in (200, 201, 409, 501):
            return
        pytest.fail(await res.text())


@pytest.mark.parametrize(
    "object_name,content",
    [
        ("hello.txt", b"hello world"),
        ("data/sample.json", b'{\n  "ok": true\n}'),
        ("dir/nested/file.bin", b"\x00\x01\x02\x03"),
    ],
)
@pytest.mark.asyncio
async def test_storage_upload_and_download(
    object_name, content, project_id, http_client
):
    # given: bucket exists and an object name/content
    bucket = f"{project_id}.appspot.com"
    await _ensure_bucket(http_client, project_id, bucket)

    upload_url = (
        f"{BASE}/upload/storage/v1/b/{bucket}/o?uploadType=media&name="
        + urllib.parse.quote(object_name, safe="")
    )

    # when: upload object content
    async with http_client.post(
        upload_url, data=content, timeout=ClientTimeout(total=5.0)
    ) as up_res:
        # then: upload succeeds and metadata returns the object name
        assert up_res.status in (200, 201), await up_res.text()
        meta = await up_res.json()
    assert meta.get("name") == object_name

    # when: download raw object content
    download_url = (
        f"{BASE}/storage/v1/b/{bucket}/o/"
        + urllib.parse.quote(object_name, safe="")
        + "?alt=media"
    )
    async with http_client.get(
        download_url, timeout=ClientTimeout(total=5.0)
    ) as down_res:
        # then: content matches
        assert down_res.status == 200
        body = await down_res.read()
        assert body == content
