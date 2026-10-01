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


def test_a_logged_out_cli_is_blocked_not_failed() -> None:
    """Seen live (WSL): `claude -p` ended at once with this result, no Agent call
    ran, and the run was reported FAIL (a defect) although nothing was tested."""
    stream = [
        json.dumps(
            {
                "type": "result",
                "is_error": True,
                "result": "Not logged in · Please run /login",
            }
        )
    ]
    report = verify.analyze(stream, [], [], "")
    assert report.status == "blocked"
    assert "/login" in report.reason


def test_logged_out_text_from_the_model_does_not_block() -> None:
    stream = [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "Not logged in · Please run /login"}
                    ]
                },
            }
        )
    ]
    assert verify.analyze(stream, [], [], "").status == "fail"


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


CODEX_RECORD = {"kind": "codex-rescue", "model": "gpt-6-astra", "effort": "low"}
COMPANION = 'node "/p/codex-companion.mjs" task --write --model gpt-6-astra --effort low "fix it"'
CODEX_OK = {
    "agentType": "codex:codex-rescue",
    "name": None,
    "efforts": ["medium"],
    "commands": [COMPANION],
}


def test_pass_also_needs_the_codex_flags_to_reach_the_companion() -> None:
    report = verify.analyze(
        [], [RECORD, CODEX_RECORD], [OK, CODEX_OK], "", expect_codex=True
    )
    assert report.status == "pass"
    assert any("codex" in line for line in report.evidence)


def test_codex_flags_that_never_reached_the_companion_are_a_failure() -> None:
    dropped = {**CODEX_OK, "commands": ['node "/p/codex-companion.mjs" task "fix it"']}
    report = verify.analyze(
        [], [RECORD, CODEX_RECORD], [OK, dropped], "", expect_codex=True
    )
    assert report.status == "fail" and "codex" in report.reason


def test_a_model_that_differs_from_jevs_choice_is_a_failure() -> None:
    other = {**CODEX_OK, "commands": [COMPANION.replace("gpt-6-astra", "gpt-6-luna")]}
    assert (
        verify.analyze(
            [], [RECORD, CODEX_RECORD], [OK, other], "", expect_codex=True
        ).status
        == "fail"
    )


def test_no_codex_launch_is_unconfirmed_not_a_pass() -> None:
    report = verify.analyze([], [RECORD], [OK], "", expect_codex=True)
    assert report.status == "partial" and "codex" in report.reason


@pytest.mark.parametrize(
    "command",
    [
        COMPANION.replace("gpt-6-astra", "gpt-6-astra-other").replace(
            "--effort low", "--effort lower"
        ),
        'node "/p/codex-companion.mjs" task "say --model gpt-6-astra --effort low"',
        COMPANION.replace("--model gpt-6-astra", "-m=gpt-6-astra"),
        'node "/p/codex-companion.mjs" task # --model gpt-6-astra --effort low',
        COMPANION.replace("--model gpt-6-astra", '--cwd "--model"'),
        "echo 'node /p/codex-companion.mjs task --model gpt-6-astra --effort low'",
        'echo OK; node "/p/codex-companion.mjs" task --model gpt-6-astra --effort low "fix it"',
        COMPANION.replace(
            "--model gpt-6-astra", "--model gpt-6-astra --model gpt-6-luna"
        ),
        COMPANION.replace('"fix it"', '-- "--model gpt-6-astra --effort low"').replace(
            "--model gpt-6-astra --effort low ", "", 1
        ),
    ],
)
def test_codex_evidence_requires_actual_exact_arguments(command: str) -> None:
    report = verify.analyze(
        [],
        [RECORD, CODEX_RECORD],
        [OK, {**CODEX_OK, "commands": [command]}],
        "",
        expect_codex=True,
    )
    assert report.status != "pass"


@pytest.mark.parametrize(
    "command",
    [
        COMPANION,
        COMPANION.replace(
            "--model gpt-6-astra --effort low", "--model=gpt-6-astra --effort=low"
        ),
    ],
)
def test_a_direct_companion_invocation_with_exact_flags_passes(command: str) -> None:
    assert (
        verify._analyze_codex(
            [CODEX_RECORD], [{**CODEX_OK, "commands": [command]}]
        ).status
        == "pass"
    )


@pytest.mark.parametrize(
    "mode, want_status, want_exit",
    [
        ("absent", "PARTIAL", 3),
        ("dropped", "FAIL", 1),
        ("wrong", "FAIL", 1),
        ("ok", "PASS", 0),
    ],
)
def test_main_checks_codex_using_real_session_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    want_status: str,
    want_exit: int,
) -> None:
    config = tmp_path / "claude"
    session = "verification-session"
    agents = config / "projects/example" / session / "subagents"
    agents.mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))

    def transcript(directory: Path, agent_id: str, meta: dict, content: list) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"agent-{agent_id}.meta.json").write_text(
            json.dumps(meta), encoding="utf-8"
        )
        (directory / f"agent-{agent_id}.jsonl").write_text(
            json.dumps(
                {"type": "assistant", "effort": "high", "message": {"content": content}}
            )
            + "\n",
            encoding="utf-8",
        )

    transcript(agents, "worker", {"agentType": "worker-high"}, [])
    transcript(
        config / "projects/example/decoy/subagents",
        "decoy",
        {"agentType": "worker-high"},
        [],
    )
    # A different session must never contaminate effort/command evidence.
    (config / "projects/example/decoy/subagents/agent-decoy.jsonl").write_text(
        json.dumps({"type": "assistant", "effort": "medium"}), encoding="utf-8"
    )
    if mode != "absent":
        command = (
            COMPANION if mode == "ok" else 'node "/p/codex-companion.mjs" task "fix it"'
        )
        if mode == "wrong":
            command = COMPANION.replace("gpt-6-astra", "gpt-6-luna")
        transcript(
            agents,
            "codex",
            {"agentType": "codex:codex-rescue"},
            [{"name": "Bash", "input": {"command": command}}],
        )

    def run(command: list[str], *, env: dict[str, str], **_kwargs: object) -> object:
        records = [RECORD] if mode == "absent" else [RECORD, CODEX_RECORD]
        Path(env["JEV_HOOK_LOG"]).write_text(
            "\n".join(json.dumps(r) for r in records), encoding="utf-8"
        )
        Path(command[command.index("--debug-file") + 1]).write_text(
            "", encoding="utf-8"
        )
        return verify.subprocess.CompletedProcess(
            command, 0, json.dumps({"session_id": session}), ""
        )

    monkeypatch.setattr(verify.subprocess, "run", run)
    assert verify.main() == want_exit
    assert capsys.readouterr().out.startswith(f"{want_status}:")


def test_the_worse_of_the_worker_and_codex_verdicts_wins() -> None:
    kept = {"agentType": "general-purpose", "name": None, "efforts": ["medium"]}
    report = verify.analyze(
        [], [RECORD, CODEX_RECORD], [kept, CODEX_OK], "", expect_codex=True
    )
    assert report.status == "fail" and "updatedInput" in report.reason


def genuine_codex_limit_stream() -> list[str]:
    return [
        json.dumps(
            {
                "type": "assistant",
                "error": "rate_limit",
                "isApiErrorMessage": True,
                "message": {
                    "content": [
                        {"type": "text", "text": "You've hit your weekly limit"}
                    ]
                },
            }
        )
    ]


@pytest.mark.parametrize(
    "command",
    [
        COMPANION.replace("gpt-6-astra", "gpt-6-luna"),
        COMPANION.replace("--effort low", "--effort high"),
        COMPANION.replace("--model gpt-6-astra", ""),
        COMPANION.replace("--effort low", ""),
    ],
)
def test_real_limit_does_not_hide_confirmed_codex_argument_defects(
    command: str,
) -> None:
    report = verify.analyze(
        genuine_codex_limit_stream(),
        [RECORD, CODEX_RECORD],
        [OK, {**CODEX_OK, "commands": [command]}],
        "",
        expect_codex=True,
    )
    assert report.status == "fail"
    assert "codex" in report.reason


@pytest.mark.parametrize("commands", [[], [f"cd /p && {COMPANION}"]])
def test_limit_with_missing_or_unrecognized_companion_evidence_is_blocked(
    commands: list[str],
) -> None:
    report = verify.analyze(
        genuine_codex_limit_stream(),
        [RECORD, CODEX_RECORD],
        [OK, {**CODEX_OK, "commands": commands}],
        "",
        expect_codex=True,
    )
    assert report.status == "blocked"


def test_codex_success_does_not_make_an_unstarted_plain_worker_a_defect() -> None:
    report = verify.analyze(
        genuine_codex_limit_stream(),
        [RECORD, CODEX_RECORD],
        [CODEX_OK],
        "",
        expect_codex=True,
    )
    assert report.status == "blocked"


def test_confirmed_codex_defect_wins_even_if_plain_worker_did_not_start() -> None:
    wrong = {**CODEX_OK, "commands": [COMPANION.replace("gpt-6-astra", "gpt-6-luna")]}
    report = verify.analyze(
        genuine_codex_limit_stream(),
        [RECORD, CODEX_RECORD],
        [wrong],
        "",
        expect_codex=True,
    )
    assert report.status == "fail"


def test_successful_codex_does_not_hide_a_confirmed_plain_worker_defect_during_limit() -> (
    None
):
    wrong = {**OK, "efforts": ["medium"]}
    report = verify.analyze(
        genuine_codex_limit_stream(),
        [RECORD, CODEX_RECORD],
        [wrong, CODEX_OK],
        "",
        expect_codex=True,
    )
    assert report.status == "fail"


def test_ordinary_limit_quote_cannot_hide_wrong_codex_arguments() -> None:
    quote = [
        json.dumps(
            {
                "type": "assistant",
                "message": {"content": "fixture: hit your weekly limit"},
            }
        )
    ]
    wrong = {**CODEX_OK, "commands": [COMPANION.replace("gpt-6-astra", "gpt-6-luna")]}
    report = verify.analyze(
        quote, [RECORD, CODEX_RECORD], [OK, wrong], "", expect_codex=True
    )
    assert report.status == "fail"


@pytest.mark.parametrize(
    ("records", "subagents", "status"),
    [
        ([], [], "blocked"),
        ([CODEX_RECORD], [{**CODEX_OK, "commands": []}], "blocked"),
        (
            [CODEX_RECORD],
            [
                {
                    **CODEX_OK,
                    "commands": [COMPANION.replace("gpt-6-astra", "gpt-6-luna")],
                }
            ],
            "fail",
        ),
    ],
)
def test_login_block_does_not_hide_codex_defects_or_invent_missing_evidence(
    records: list[dict], subagents: list[dict], status: str
) -> None:
    stream = [
        json.dumps(
            {
                "type": "result",
                "is_error": True,
                "result": "Not logged in · Please run /login",
            }
        )
    ]
    report = verify.analyze(stream, records, subagents, "", expect_codex=True)
    assert report.status == status
    if status == "blocked":
        assert "/login" in report.reason


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


def codex_call_stream(result: object, *, tool_use_id: str = "call-3") -> list[str]:
    """The codex-rescue Agent call and the tool result Claude Code sent back."""
    return [
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": "call-3",
                            "name": "Agent",
                            "input": {
                                "subagent_type": "codex:codex-rescue",
                                "prompt": "--model gpt-6-astra --effort low fix it",
                            },
                        }
                    ]
                },
            }
        ),
        json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "is_error": True,
                            "content": result,
                        }
                    ]
                },
            }
        ),
    ]


NOT_FOUND = (
    "<tool_use_error>Agent type 'codex:codex-rescue' not found. "
    "Available agents: general-purpose, worker-medium, worker-high</tool_use_error>"
)


@pytest.mark.parametrize("result", [NOT_FOUND, [{"type": "text", "text": NOT_FOUND}]])
def test_a_missing_codex_plugin_is_blocked_not_a_failure(result: object) -> None:
    # Without the Codex plugin the codex path cannot be checked on this machine;
    # the workers still prove their part
    report = verify.analyze(
        codex_call_stream(result), [RECORD, CODEX_RECORD], [OK], "", expect_codex=True
    )
    assert report.status == "blocked"
    assert "plugin" in report.reason
    assert any("worker" in line for line in report.evidence)


def test_not_found_from_another_call_does_not_excuse_the_codex_path() -> None:
    report = verify.analyze(
        codex_call_stream(NOT_FOUND, tool_use_id="call-9"),
        [RECORD, CODEX_RECORD],
        [OK],
        "",
        expect_codex=True,
    )
    assert report.status == "fail"


def test_another_error_from_the_codex_call_is_still_a_failure() -> None:
    report = verify.analyze(
        codex_call_stream("<tool_use_error>Invalid tool parameters</tool_use_error>"),
        [RECORD, CODEX_RECORD],
        [OK],
        "",
        expect_codex=True,
    )
    assert report.status == "fail"
