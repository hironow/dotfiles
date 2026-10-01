"""pi-subagents command runner: let Jev pick the Codex model and effort, then run codex exec."""

import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "jev_codex_exec", SCRIPTS / "jev_codex_exec.py"
)
assert spec is not None and spec.loader is not None
wrapper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapper)


def fake_codex(final: str | None = "DONE", returncode: int = 0):
    calls: list[dict[str, object]] = []

    def run(command: list[str], **kwargs: object) -> Mock:
        calls.append({"command": command, **kwargs})
        path = command[command.index("--output-last-message") + 1]
        if final is not None:
            Path(path).write_text(final, encoding="utf-8")
        return Mock(returncode=returncode)

    return run, calls


def run_wrapper(
    argv, prompt="do the work", *, run, choice=("gpt-6.1-sol", "medium"), port=None
):
    out = io.StringIO()
    code = wrapper.main(
        argv,
        io.StringIO(prompt),
        out,
        run=run,
        choose=lambda _task, _key: choice,
        key_of=lambda: "secret",
        proxy=lambda _environ: port,
    )
    return code, out.getvalue()


def test_codex_goes_through_headroom_when_a_proxy_is_ready() -> None:
    run, calls = fake_codex()
    code, _ = run_wrapper([], run=run, port=4321)
    assert code == 0
    command = calls[0]["command"]
    # The config key moves ChatGPT-login traffic; --ignore-user-config means
    # only a command-line override can set it
    assert (
        command[command.index('openai_base_url="http://127.0.0.1:4321/v1"') - 1] == "-c"
    )
    assert calls[0]["env"]["OPENAI_BASE_URL"] == "http://127.0.0.1:4321/v1"


def test_without_a_proxy_codex_runs_exactly_as_before() -> None:
    run, calls = fake_codex()
    run_wrapper([], run=run, port=None)
    assert not any("openai_base_url" in part for part in calls[0]["command"])
    assert "OPENAI_BASE_URL" not in (calls[0].get("env") or {})


def test_the_prompt_goes_to_codex_with_jevs_model_effort_and_the_requested_sandbox() -> (
    None
):
    run, calls = fake_codex("all done")
    code, out = run_wrapper(
        ["--sandbox", "workspace-write"], run=run, choice=("gpt-6-astra", "low")
    )
    command = calls[0]["command"]
    assert code == 0 and out == "all done"
    assert calls[0]["input"] == "do the work"
    assert command[command.index("-m") + 1] == "gpt-6-astra"
    assert 'model_reasoning_effort="low"' in command
    assert command[command.index("-s") + 1] == "workspace-write"


def test_read_only_is_the_default_sandbox() -> None:
    run, calls = fake_codex()
    run_wrapper([], run=run)
    command = calls[0]["command"]
    assert command[command.index("-s") + 1] == "read-only"


def test_a_failed_codex_run_returns_its_exit_code_and_prints_nothing() -> None:
    run, _ = fake_codex("partial", returncode=3)
    code, out = run_wrapper([], run=run)
    assert code == 3 and out == ""


def test_a_missing_final_message_is_a_failure() -> None:
    run, _ = fake_codex(final=None)
    code, out = run_wrapper([], run=run)
    assert code == 1 and out == ""


@pytest.mark.parametrize(
    "argv", [["--sandbox", "danger-full-access"], ["--sandbox"], ["--bogus"]]
)
def test_an_unknown_sandbox_or_flag_never_reaches_codex(argv: list[str]) -> None:
    run, calls = fake_codex()
    code, _ = run_wrapper(argv, run=run)
    assert code == 2 and calls == []


def test_the_choice_is_logged_for_the_live_verification(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log = tmp_path / "hook.log"
    monkeypatch.setenv("JEV_HOOK_LOG", str(log))
    run, _ = fake_codex()
    run_wrapper([], run=run, choice=("gpt-6-luna", "high"))
    record = json.loads(log.read_text(encoding="utf-8"))
    assert record == {"kind": "codex-exec", "model": "gpt-6-luna", "effort": "high"}
    assert "secret" not in log.read_text(encoding="utf-8")


def test_the_real_runner_is_subprocess_run() -> None:
    assert wrapper.main.__kwdefaults__["run"] is subprocess.run
