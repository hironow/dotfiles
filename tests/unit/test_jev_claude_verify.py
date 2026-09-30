"""The live verification for the Claude worker hook: analysis of a recorded run.

What a run leaves behind is objective: the hook's own log, each subagent's sidecar
(the agentType it really ran as, and its name if any) and the effort Claude Code
recorded on each of its requests.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "jev_claude_verify", SCRIPTS / "jev_claude_verify.py"
)
assert spec is not None and spec.loader is not None
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

RECORD = {"effort": "high", "from": "general-purpose", "to": "worker-high"}
OK = {"agentType": "worker-high", "name": None, "efforts": ["high", "high"]}


def limit_stream() -> list[str]:
    return [
        json.dumps(
            {
                "type": "result",
                "is_error": True,
                "result": "You've hit your weekly limit · resets Oct 4",
            }
        )
    ]


def test_pass_needs_the_rewritten_type_and_the_chosen_effort_recorded() -> None:
    report = verify.analyze([], [RECORD], [OK], "")
    assert report.status == "pass"


def test_the_weekly_limit_is_blocked_not_failed() -> None:
    assert verify.analyze(limit_stream(), [], [], "").status == "blocked"


@pytest.mark.parametrize(
    "event",
    [
        {"type": "assistant", "error": "rate_limit", "isApiErrorMessage": True},
        {"type": "assistant", "error": "rate_limit"},
        {"type": "result", "is_error": True, "result": "You've hit your weekly limit"},
    ],
)
def test_only_structured_provider_limit_events_block_the_verification(
    event: dict,
) -> None:
    assert verify.analyze([json.dumps(event)], [], [], "").status == "blocked"


@pytest.mark.parametrize(
    "event",
    [
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "You've hit your weekly limit"}]
            },
        },
        {"type": "user", "content": "You've hit your weekly limit"},
        {"type": "tool_result", "content": "You've hit your weekly limit"},
        {"type": "result", "is_error": False, "result": "You've hit your weekly limit"},
        {
            "type": "result",
            "is_error": "true",
            "result": "You've hit your weekly limit",
        },
        {
            "type": "result",
            "is_error": True,
            "result": 'Fixture says "You\'ve hit your weekly limit"',
        },
        {
            "type": "assistant",
            "error": "authentication_failed",
            "isApiErrorMessage": True,
            "text": "You've hit your weekly limit",
        },
        {"type": "assistant", "error": "rate_limit", "isApiErrorMessage": False},
        {"type": "assistant", "error": "rate_limit", "isApiErrorMessage": "true"},
        ["You've hit your weekly limit"],
        "You've hit your weekly limit",
        None,
    ],
)
def test_quoted_or_malformed_limit_text_cannot_hide_real_worker_results(
    event: object,
) -> None:
    lines = [json.dumps(event), "not JSON: You've hit your weekly limit"]
    assert verify.analyze(lines, [RECORD], [OK], "").status == "pass"
    assert (
        verify.analyze(lines, [RECORD], [{**OK, "efforts": ["medium"]}], "").status
        == "fail"
    )


@pytest.mark.parametrize("defect", ["schema", "type", "effort"])
def test_a_proven_defect_is_not_hidden_by_a_real_usage_limit(defect: str) -> None:
    sub = {**OK, "agentType": "general-purpose"} if defect == "type" else OK
    if defect == "effort":
        sub = {**OK, "efforts": ["medium"]}
    debug = (
        "[DEBUG] Hook JSON output had unrecognized keys (ignored): updatedInput."
        if defect == "schema"
        else ""
    )
    assert verify.analyze(limit_stream(), [RECORD], [sub], debug).status == "fail"


def test_a_real_limit_before_worker_execution_is_blocked_not_an_ignored_rewrite() -> (
    None
):
    assert verify.analyze(limit_stream(), [RECORD], [], "").status == "blocked"


def test_a_limit_does_not_discard_already_proven_worker_evidence() -> None:
    report = verify.analyze(limit_stream(), [RECORD], [OK], "")
    assert report.status == "blocked"
    assert report.evidence


def test_every_matched_plain_worker_needs_effort_evidence() -> None:
    report = verify.analyze([], [RECORD, RECORD], [OK, {**OK, "efforts": []}], "")
    assert report.status == "partial"


def test_no_hook_record_means_the_hook_never_ran() -> None:
    report = verify.analyze([], [], [OK], "")
    assert report.status == "fail" and "hook" in report.reason


def test_a_rejected_updated_input_schema_is_reported_from_the_debug_log() -> None:
    debug = "[DEBUG] Hook output ... unrecognized key(s) in object: updatedInput"
    report = verify.analyze([], [RECORD], [OK], debug)
    assert report.status == "fail" and "schema" in report.reason


def test_unrelated_metrics_warning_does_not_reject_a_valid_rewrite() -> None:
    # These are the two diagnostic formats captured from Claude 2.1.284.
    debug = (
        '[DEBUG] Hooks: Parsed initial response: {"hookSpecificOutput":'
        '{"hookEventName":"PreToolUse","updatedInput":{"subagent_type":"worker-high"}}}\n'
        "[DEBUG] Successfully parsed and validated hook JSON output\n"
        "[DEBUG] Hook JSON output had unrecognized keys (ignored): metrics."
    )
    assert verify.analyze([], [RECORD], [OK], debug).status == "pass"
    kept = {**OK, "agentType": "general-purpose"}
    assert verify.analyze([], [RECORD], [kept], debug).status == "fail"
    assert (
        verify.analyze([], [RECORD], [{**OK, "efforts": []}], debug).status == "partial"
    )
    assert (
        verify.analyze([], [RECORD], [{**OK, "efforts": ["medium"]}], debug).status
        == "fail"
    )


def test_words_in_a_valid_hook_payload_are_not_schema_diagnostics() -> None:
    debug = (
        '[DEBUG] Hooks: Parsed initial response: {"updatedInput":'
        '{"prompt":"Fix an unrecognized key(s) in object: updatedInput error"}}'
    )
    assert verify.analyze([], [RECORD], [OK], debug).status == "pass"


def test_rejected_updated_input_in_the_captured_diagnostic_format_still_fails() -> None:
    debug = "[DEBUG] Hook JSON output had unrecognized keys (ignored): updatedInput."
    report = verify.analyze([], [RECORD], [OK], debug)
    assert report.status == "fail" and "schema" in report.reason


def test_default_type_kept_means_updated_input_was_ignored_for_agent() -> None:
    kept = {"agentType": "general-purpose", "name": None, "efforts": ["medium"]}
    report = verify.analyze([], [RECORD], [kept], "")
    assert report.status == "fail" and "updatedInput" in report.reason


def test_the_session_effort_recorded_means_the_frontmatter_effort_was_dropped() -> None:
    inherited = {"agentType": "worker-high", "name": None, "efforts": ["medium"]}
    report = verify.analyze([], [RECORD], [inherited], "")
    assert report.status == "fail" and "effort" in report.reason


def test_no_transcript_effort_is_unknown_not_a_pass() -> None:
    report = verify.analyze([], [RECORD], [{**OK, "efforts": []}], "")
    assert report.status == "partial"


def test_a_medium_choice_cannot_show_the_effort_and_is_partial() -> None:
    record = {"effort": "medium", "from": "general-purpose", "to": "worker-medium"}
    sub = {"agentType": "worker-medium", "name": None, "efforts": ["medium"]}
    assert verify.analyze([], [record], [sub], "").status == "partial"


def test_a_named_teammate_dropping_effort_is_a_warning_when_the_plain_worker_is_fine() -> (
    None
):
    teammate = {"agentType": "worker-high", "name": "probe", "efforts": ["medium"]}
    report = verify.analyze([], [RECORD], [OK, teammate], "")
    assert report.status == "pass"
    assert any("teammate" in line for line in report.evidence)


def test_no_subagent_at_all_is_a_failure() -> None:
    assert verify.analyze([], [RECORD], [], "").status == "fail"


def test_the_claude_stream_is_decoded_as_utf8_on_every_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Claude Code writes UTF-8; decoding with the Windows locale default (cp932)
    # crashed the reader thread and left stdout as None.
    seen: dict[str, object] = {}

    class Stop(Exception):
        pass

    def run(_command: list[str], **kwargs: object) -> None:
        seen.update(kwargs)
        raise Stop

    monkeypatch.setattr(verify.subprocess, "run", run)
    with pytest.raises(Stop):
        verify.main()
    assert seen["encoding"] == "utf-8"
