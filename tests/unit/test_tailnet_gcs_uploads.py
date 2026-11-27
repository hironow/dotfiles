"""Run the sandbox GCS fake with fixed-length and streamed state uploads."""

import importlib.util
import io
import json
from email.message import Message
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("chunked", [False, True], ids=["content-length", "chunked"])
def test_tailnet_gcs_accepts_multipart_state_uploads(chunked, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "tailnet_sandbox_under_test", ROOT / "tests/test_just_sandbox.py"
    )
    assert spec and spec.loader
    sandbox = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sandbox)
    key = ("gen-ai-hironow-tofu-state", "tailnet/default.tfstate")
    objects = {}
    program = tmp_path / "tailnet_http.py"
    program.write_text(sandbox._TAILNET_HTTP, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("tailnet_http_under_test", program)
    assert spec and spec.loader
    fake = importlib.util.module_from_spec(spec)
    vars(fake).update(state_key=key, objects=objects, requests=[], violations=[])
    spec.loader.exec_module(fake)
    state = b'{"encrypted_data":"synthetic ciphertext"}\n'
    body = (
        b"--state-boundary\r\nContent-Type: application/json\r\n\r\n"
        + json.dumps({"name": key[1]}).encode()
        + b"\r\n--state-boundary\r\nContent-Type: application/octet-stream\r\n\r\n"
        + state
        + b"\r\n--state-boundary--\r\n"
    )
    headers = Message()
    headers["Content-Type"] = "multipart/related; boundary=state-boundary"
    if chunked:
        headers["Transfer-Encoding"] = "chunked"
        chunks = [body[:17], body[17:89], body[89:]]
        wire = (
            b"".join(
                f"{len(chunk):x};fixture=yes\r\n".encode() + chunk + b"\r\n"
                for chunk in chunks
            )
            + b"0\r\nX-Fixture-Trailer: done\r\n\r\n"
        )
    else:
        headers["Content-Length"] = str(len(body))
        wire = body
    handler = object.__new__(fake.Services)
    handler.headers = headers
    handler.rfile = io.BytesIO(wire)
    handler.wfile = io.BytesIO()
    handler.command = "POST"
    handler.path = f"/upload/storage/v1/b/{key[0]}/o?uploadType=multipart"
    handler.request_version = "HTTP/1.1"
    handler.requestline = f"POST {handler.path} HTTP/1.1"

    handler.handle_request()

    assert handler.wfile.getvalue().split(b"\r\n", 1)[0] == b"HTTP/1.0 200 OK"
    assert objects == {key: state}
    assert fake.violations == []
    assert handler.rfile.read() == b""
