"""The live verification for the Claude worker hook: analysis of a recorded run."""

import importlib.util
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "jev_claude_verify", SCRIPTS / "jev_claude_verify.py"
)
assert spec is not None and spec.loader is not None
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

RECORD = {"effort": "high", "from": "general-purpose", "to": "worker-high"}


def stream(*events: dict) -> list[str]:
    return [json.dumps(event) for event in events]


def test_pass_needs_the_hook_to_run_and_the_rewritten_type_to_appear() -> None:
    events = stream(
        {"type": "system", "subtype": "hook_started", "hook_event": "PreToolUse"},
        {
            "type": "system",
            "subtype": "subagent_start",
            "agent_type": "worker-high",
            "effort": "high",
        },
    )
    report = verify.analyze(events, [RECORD])
    assert report.status == "pass"
    assert any("effort" in line for line in report.evidence)


def test_hook_ran_but_the_subagent_kept_its_type_means_updated_input_was_ignored() -> (
    None
):
    events = stream(
        {"type": "system", "subtype": "subagent_start", "agent_type": "general-purpose"}
    )
    report = verify.analyze(events, [RECORD])
    assert report.status == "fail"
    assert "updatedInput" in report.reason


def test_no_hook_record_means_the_hook_never_ran() -> None:
    report = verify.analyze(stream({"type": "result", "result": "ok"}), [])
    assert report.status == "fail"
    assert "hook" in report.reason


def test_the_weekly_limit_is_blocked_not_failed() -> None:
    report = verify.analyze(
        stream(
            {"type": "result", "result": "You've hit your weekly limit · resets Oct 4"}
        ),
        [],
    )
    assert report.status == "blocked"


def test_unparseable_lines_are_skipped() -> None:
    report = verify.analyze(
        ["not json", *stream({"agent_type": "worker-high"})], [RECORD]
    )
    assert report.status == "pass"
