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


# headroom logs a Codex (Responses API) request without its messages, but tags
# the client; the dedicated proxy serves only the runner under test
CODEX_ROW = {"provider": "openai", "tags": {"client": "codex"}}
CLAUDE_ROW = {
    "provider": "anthropic",
    "tags": {"client": "claude-code"},
    "request_messages": MAIN,
}


def test_a_codex_worker_through_the_proxy_passes() -> None:
    report = verify.analyze_codex(
        0, "OK", "Headroom: http://127.0.0.1:4321", 4321, [CODEX_ROW]
    )
    assert report.status == "pass"


def test_a_codex_worker_that_bypassed_the_proxy_fails() -> None:
    report = verify.analyze_codex(
        0, "OK", "Headroom: http://127.0.0.1:4321", 4321, [CLAUDE_ROW]
    )
    assert report.status == "fail"


def test_a_runner_that_did_not_reuse_the_dedicated_proxy_fails() -> None:
    # It started or reused another proxy: the check would not see its requests
    report = verify.analyze_codex(
        0, "OK", "Headroom: http://127.0.0.1:9999", 4321, [CODEX_ROW]
    )
    assert report.status == "fail"


def test_a_codex_run_without_a_final_message_fails() -> None:
    report = verify.analyze_codex(1, "", "", 4321, [])
    assert report.status == "fail"


def test_a_codex_usage_limit_blocks() -> None:
    report = verify.analyze_codex(
        1, "", "You've hit your usage limit. Try again later.", 4321, []
    )
    assert report.status == "blocked"


def test_a_codex_http_429_blocks() -> None:
    report = verify.analyze_codex(
        1, "", "stream error: unexpected status 429 Too Many Requests", 4321, []
    )
    assert report.status == "blocked"


def test_a_429_inside_a_longer_number_is_not_a_limit() -> None:
    report = verify.analyze_codex(1, "", "request id 14290 failed", 4321, [])
    assert report.status == "fail"


@pytest.mark.parametrize(
    ("argv", "targets"),
    [
        ([], ["claude", "codex", "rtk"]),
        (["codex"], ["codex"]),
        (["claude"], ["claude"]),
        (["rtk"], ["rtk"]),
    ],
)
def test_targets_default_to_all(argv: list[str], targets: list[str]) -> None:
    assert verify.targets(argv) == targets


def test_an_unknown_target_is_refused() -> None:
    with pytest.raises(SystemExit):
        verify.targets(["pi"])


def test_log_rows_are_read_whole(tmp_path: Path) -> None:
    log = tmp_path / "requests.jsonl"
    lines = [json.dumps(CODEX_ROW), "[1, 2]", "not json"]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert verify.proxied_rows(log) == [CODEX_ROW]


# --- rtk: one j-cc session through headroom, its Bash through rtk ----------

RTK_SESSION = _request(f"{verify.RTK} run ls once")


def _bash_call() -> str:
    return json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "b", "name": "Bash", "input": {}}
                ]
            },
        }
    )


def test_a_session_through_headroom_with_bash_through_rtk_passes() -> None:
    report = verify.analyze_rtk([_bash_call()], [RTK_SESSION], rtk_commands=1)
    assert report.status == "pass"


def test_a_bash_call_rtk_never_saw_fails() -> None:
    report = verify.analyze_rtk([_bash_call()], [RTK_SESSION], rtk_commands=0)
    assert report.status == "fail"
    assert "rtk" in report.reason


def test_a_session_that_bypassed_the_proxy_fails() -> None:
    report = verify.analyze_rtk([_bash_call()], [], rtk_commands=1)
    assert report.status == "fail"
    assert "proxy" in report.reason


def test_no_bash_call_learned_nothing() -> None:
    assert verify.analyze_rtk([], [RTK_SESSION], rtk_commands=0).status == "blocked"


def test_an_unreadable_rtk_count_blocks() -> None:
    # rtk missing or its tracking unreadable: nothing about the hook was learned
    assert (
        verify.analyze_rtk([_bash_call()], [RTK_SESSION], rtk_commands=None).status
        == "blocked"
    )


@pytest.mark.parametrize(
    ("out", "count"),
    [
        ('{"summary": {"total_commands": 2}}', 2),
        ('{"summary": {}}', None),
        ("not json", None),
        (None, None),
    ],
)
def test_rtk_counts_come_from_its_per_project_summary(
    out: str | None, count: int | None
) -> None:
    assert verify.rtk_commands(out) == count
