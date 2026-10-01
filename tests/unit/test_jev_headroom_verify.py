"""The live check that j-cc's session and its workers go through headroom.

A dedicated proxy logs each request's messages; the main session's first user
message carries MAIN, a worker's carries WORKER (the task the session hands the
worker). The verdict needs both, plus the hook's record of the worker rewrite.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import jev_headroom_verify as verify  # noqa: E402

REWRITE = {"effort": "high", "from": "general-purpose", "to": "worker-high"}


def _request(text: str) -> list[dict]:
    return [{"role": "user", "content": [{"type": "text", "text": text}]}]


MAIN = _request(f"{verify.MAIN} launch one worker")
WORKER = _request(f"{verify.WORKER} reply with OK")


def _agent_call() -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "a", "name": "Agent", "input": {}}
                ]
            },
        }
    )


def test_main_and_worker_through_the_proxy_pass() -> None:
    report = verify.analyze([_agent_call()], [REWRITE], [MAIN, WORKER, MAIN])
    assert report.status == "pass"


def test_a_worker_that_bypassed_the_proxy_fails() -> None:
    report = verify.analyze([_agent_call()], [REWRITE], [MAIN, MAIN])
    assert report.status == "fail"
    assert "worker" in report.reason


def test_no_main_request_at_the_proxy_fails() -> None:
    assert verify.analyze([_agent_call()], [REWRITE], [WORKER]).status == "fail"


def test_a_model_that_launched_no_worker_learned_nothing() -> None:
    assert verify.analyze([], [], [MAIN]).status == "blocked"


def test_a_launch_the_hook_never_rewrote_fails() -> None:
    report = verify.analyze([_agent_call()], [], [MAIN, WORKER])
    assert report.status == "fail"
    assert "hook" in report.reason


def test_a_usage_limit_blocks() -> None:
    limit = json.dumps(
        {"type": "result", "is_error": True, "result": "You've hit your weekly limit"}
    )
    assert verify.analyze([limit], [], []).status == "blocked"


def test_the_main_marker_wins_over_the_worker_marker() -> None:
    # The session's own prompt quotes the worker task; it is still the session
    both = _request(f"{verify.MAIN} hand the worker: {verify.WORKER} reply")
    report = verify.analyze([_agent_call()], [REWRITE], [both])
    assert report.status == "fail"


@pytest.mark.parametrize(
    "content",
    [
        f"{verify.WORKER} plain string content",
        [{"type": "text", "text": f"{verify.WORKER} block content"}],
    ],
)
def test_first_user_text_reads_both_content_shapes(content: object) -> None:
    messages = [{"role": "user", "content": content}]
    assert verify.WORKER in verify.first_user_text(messages)


def test_proxied_requests_are_read_from_the_log(tmp_path: Path) -> None:
    log = tmp_path / "requests.jsonl"
    rows = [
        {"request_messages": MAIN},
        {"no_messages": True},
        {"request_messages": WORKER},
    ]
    log.write_text(
        "".join(json.dumps(r) + "\n" for r in rows) + "not json\n", encoding="utf-8"
    )
    assert verify.proxied_requests(log) == [MAIN, WORKER]
    assert verify.proxied_requests(tmp_path / "missing.jsonl") == []
