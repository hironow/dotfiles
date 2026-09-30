"""The Pi worker check judges from pi-subagents' own run records.

`j-pi` sets a worker's effort by rewriting the subagent launch's model to
`<route>:<effort>`. The session transcript keeps the launch as the model sent
it, so it cannot show the rewrite; the worker's `<run>_worker_meta.json` in
the session's `subagent-artifacts/` records the model the worker actually ran
with and whether it succeeded. A macOS check could only say "Pi exited 0";
these pin how that record becomes a verdict.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "jev_pi_verify", SCRIPTS / "jev_pi_verify.py"
)
assert spec is not None and spec.loader is not None
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def _meta(model: str, exit_code: int = 0) -> dict[str, object]:
    return {
        "agent": "worker",
        "model": model,
        "exitCode": exit_code,
        "modelAttempts": [{"model": model, "success": exit_code == 0}],
    }


def test_a_worker_run_at_high_passes() -> None:
    report = verify.analyze(0, "", [_meta("anthropic/claude-sonnet-5-5:high")])
    assert report.status == "pass"
    assert any("anthropic/claude-sonnet-5-5:high" in line for line in report.evidence)


def test_a_worker_at_medium_cannot_be_told_from_the_session() -> None:
    report = verify.analyze(0, "", [_meta("github-copilot/claude-sonnet-5.5:medium")])
    assert report.status == "partial"


def test_a_worker_without_an_effort_suffix_means_the_rewrite_never_happened() -> None:
    report = verify.analyze(0, "", [_meta("github-copilot/claude-sonnet-5.5")])
    assert report.status == "fail"


def test_a_failed_worker_is_a_failure() -> None:
    report = verify.analyze(1, "", [_meta("anthropic/claude-sonnet-5-5:high", 1)])
    assert report.status == "fail"


def test_no_worker_after_a_usage_limit_is_blocked() -> None:
    report = verify.analyze(1, "Error: 429 quota exceeded", [])
    assert report.status == "blocked"


def test_a_subagent_call_that_left_no_worker_record_is_a_failure() -> None:
    report = verify.analyze(0, "", [], subagent_calls=1)
    assert report.status == "fail"


def test_a_session_that_never_called_subagent_learned_nothing() -> None:
    # seen in WSL: after a provider switch the model only *said* it called the
    # worker; that says nothing about the Jev rewrite
    report = verify.analyze(0, "", [], subagent_calls=0)
    assert report.status == "blocked"
    assert "no subagent call" in report.reason


def test_subagent_calls_are_counted_from_this_runs_transcript(tmp_path: Path) -> None:
    session = tmp_path / "sessions" / "--tmp-tmpxyz--"
    session.mkdir(parents=True)
    call = {"type": "toolCall", "name": "subagent", "arguments": {"agent": "worker"}}
    text = {"type": "text", "text": "Calling the worker subagent once."}
    lines = [
        {"type": "message", "message": {"role": "assistant", "content": [text]}},
        {"type": "message", "message": {"role": "assistant", "content": [call]}},
    ]
    (session / "s.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    assert verify.subagent_calls(tmp_path / "sessions", "tmpxyz") == 1
    assert verify.subagent_calls(tmp_path / "sessions", "other") == 0


def test_one_high_worker_among_several_passes() -> None:
    metas = [
        _meta("github-copilot/claude-sonnet-5.5:medium"),
        _meta("anthropic/claude-sonnet-5-5:high"),
    ]
    assert verify.analyze(0, "", metas).status == "pass"


def test_worker_metas_are_read_from_this_runs_session_only(tmp_path: Path) -> None:
    # given two session dirs, one for this run's working directory
    ours = (
        tmp_path / "sessions" / "--C--Users-x-Temp-tmpabc123--" / "subagent-artifacts"
    )
    other = tmp_path / "sessions" / "--C--Users-x-work--" / "subagent-artifacts"
    for folder in (ours, other):
        folder.mkdir(parents=True)
    (ours / "r1_worker_meta.json").write_text(
        json.dumps(_meta("anthropic/claude-sonnet-5-5:high")), encoding="utf-8"
    )
    (ours / "r1_worker_output.md").write_text("done", encoding="utf-8")
    (other / "r2_worker_meta.json").write_text(
        json.dumps(_meta("x/y:low")), encoding="utf-8"
    )

    # when this run's worker records are collected
    metas = verify.worker_metas(tmp_path / "sessions", "tmpabc123")

    # then only its own meta comes back
    assert [m["model"] for m in metas] == ["anthropic/claude-sonnet-5-5:high"]


def test_pi_gets_an_empty_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    # `pi -p` also reads a non-terminal stdin as input and waits for its EOF; a
    # parent's open pipe (just -> uv -> python) left the check hanging for good
    seen: dict[str, object] = {}

    def run(_command: list[str], **kwargs: object) -> Mock:
        seen.update(kwargs)
        return Mock(returncode=0, stderr="")

    monkeypatch.setattr(verify, "jev_key", lambda: "key")
    monkeypatch.setattr(verify, "extension_installed", lambda: True)
    monkeypatch.setattr(verify, "pi_route", lambda: "github-copilot/claude-sonnet-5.5")
    monkeypatch.setattr(verify.subprocess, "run", run)
    verify.main()
    assert seen["stdin"] is subprocess.DEVNULL
