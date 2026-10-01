"""Claude Code PreToolUse hook: rewrite default Agent launches onto Jev's effort."""

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "jev_claude_hook", SCRIPTS / "jev_claude_hook.py"
)
assert spec is not None and spec.loader is not None
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


def no_codex(_task: str) -> tuple[str, str]:
    raise AssertionError("Jev must not be asked about Codex")


CODEX = {
    "tool_name": "Agent",
    "tool_input": {
        "prompt": "fix the flaky test",
        "description": "d",
        "subagent_type": "codex:codex-rescue",
    },
}
AGENT = {
    "tool_name": "Agent",
    "tool_input": {
        "prompt": "hard task",
        "description": "d",
        "subagent_type": "general-purpose",
    },
}


def test_default_worker_moves_onto_the_effort_jev_chose() -> None:
    asked: list[str] = []

    def chooser(task: str) -> str:
        asked.append(task)
        return "high"

    result = hook.decide(AGENT, chooser, no_codex)
    assert asked == ["hard task"]
    assert result is not None
    updated = result.output["hookSpecificOutput"]["updatedInput"]
    assert updated["subagent_type"] == "worker-high"
    assert result.record == {
        "effort": "high",
        "from": "general-purpose",
        "to": "worker-high",
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        {
            "tool_name": "Agent",
            "tool_input": {"prompt": "p", "subagent_type": "Explore"},
        },
        {"tool_name": "Agent", "tool_input": "not an object"},
        {"tool_name": "Agent"},
        {},
    ],
)
def test_other_calls_never_reach_jev(payload: dict[str, object]) -> None:
    def chooser(_task: str) -> str:
        raise AssertionError("Jev must not be asked")

    assert hook.decide(payload, chooser, no_codex) is None


def _run(
    monkeypatch: pytest.MonkeyPatch,
    stdin: str,
    *,
    key: str | None,
    effort: str = "high",
) -> str:
    monkeypatch.setattr(hook, "jev_key", lambda: key)
    monkeypatch.setattr(hook, "choose_effort", lambda _task, _key: effort)
    monkeypatch.setattr(
        hook, "choose_codex", lambda _task, _key: ("gpt-6.1-sol", "medium")
    )
    out = io.StringIO()
    hook.main(io.StringIO(stdin), out)
    return out.getvalue()


def test_main_prints_the_updated_input(monkeypatch: pytest.MonkeyPatch) -> None:
    printed = _run(monkeypatch, json.dumps(AGENT), key="secret")
    assert (
        json.loads(printed)["hookSpecificOutput"]["updatedInput"]["subagent_type"]
        == "worker-high"
    )


@pytest.mark.parametrize(
    ("stdin", "key"),
    [
        (json.dumps(AGENT), None),
        ("not json", "secret"),
        ("", "secret"),
        ("[]", "secret"),
    ],
)
def test_main_fails_open_with_no_output(
    monkeypatch: pytest.MonkeyPatch, stdin: str, key: str | None
) -> None:
    assert _run(monkeypatch, stdin, key=key) == ""


def test_an_unexpected_error_still_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_task: str, _key: str | None) -> str:
        raise RuntimeError("Bearer secret leaked")

    monkeypatch.setattr(hook, "jev_key", lambda: "secret")
    monkeypatch.setattr(hook, "choose_effort", boom)
    out = io.StringIO()
    hook.main(io.StringIO(json.dumps(AGENT)), out)
    assert out.getvalue() == ""


def test_verification_log_records_the_rewrite(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "hook.log"
    monkeypatch.setenv("JEV_HOOK_LOG", str(log))
    _run(monkeypatch, json.dumps(AGENT), key="secret", effort="high")
    record = json.loads(log.read_text(encoding="utf-8"))
    assert record == {"effort": "high", "from": "general-purpose", "to": "worker-high"}
    assert "secret" not in log.read_text(encoding="utf-8")


def test_codex_rescue_gets_jevs_model_and_effort_in_front_of_its_prompt() -> None:
    asked: list[str] = []

    def codex_of(task: str) -> tuple[str, str]:
        asked.append(task)
        return "gpt-6-astra", "low"

    def effort_of(_task: str) -> str:
        raise AssertionError("a Codex launch is not given a Sonnet effort")

    result = hook.decide(CODEX, effort_of, codex_of)
    assert asked == ["fix the flaky test"]
    assert result is not None
    updated = result.output["hookSpecificOutput"]["updatedInput"]
    assert updated["prompt"] == "--model gpt-6-astra --effort low fix the flaky test"
    assert updated["subagent_type"] == "codex:codex-rescue"
    assert result.record == {
        "kind": "codex-rescue",
        "model": "gpt-6-astra",
        "effort": "low",
    }


def test_an_explicit_codex_choice_never_reaches_jev() -> None:
    payload = {
        "tool_name": "Agent",
        "tool_input": {
            "prompt": "--model gpt-6-luna go",
            "subagent_type": "codex:codex-rescue",
        },
    }
    assert hook.decide(payload, lambda _t: "high", no_codex) is None


def test_main_handles_a_codex_launch_and_logs_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "hook.log"
    monkeypatch.setenv("JEV_HOOK_LOG", str(log))
    printed = _run(monkeypatch, json.dumps(CODEX), key="secret")
    assert json.loads(printed)["hookSpecificOutput"]["updatedInput"][
        "prompt"
    ].startswith("--model gpt-6.1-sol --effort medium ")
    assert json.loads(log.read_text(encoding="utf-8")) == {
        "kind": "codex-rescue",
        "model": "gpt-6.1-sol",
        "effort": "medium",
    }
