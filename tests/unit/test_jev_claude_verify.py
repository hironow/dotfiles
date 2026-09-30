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
            {"type": "result", "result": "You've hit your weekly limit · resets Oct 4"}
        )
    ]


def test_pass_needs_the_rewritten_type_and_the_chosen_effort_recorded() -> None:
    report = verify.analyze([], [RECORD], [OK], "")
    assert report.status == "pass"


def test_the_weekly_limit_is_blocked_not_failed() -> None:
    assert verify.analyze(limit_stream(), [], [], "").status == "blocked"


def test_no_hook_record_means_the_hook_never_ran() -> None:
    report = verify.analyze([], [], [OK], "")
    assert report.status == "fail" and "hook" in report.reason


def test_a_rejected_updated_input_schema_is_reported_from_the_debug_log() -> None:
    debug = "[DEBUG] Hook output ... unrecognized key(s) in object: updatedInput"
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
