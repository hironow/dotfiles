"""Opt-in Jev launcher: typed answers, host validation, and subscription order."""

import importlib.util
import io
import os
import json
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock
from typing import cast

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/jev_launch.py"
spec = importlib.util.spec_from_file_location("jev_launch", SCRIPT)
assert spec is not None and spec.loader is not None
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


HARD = (
    b'{"answers":{"difficulty":{"type":"score","score":1.9,"confidence":0.9},'
    b'"strict_structure":{"type":"noul","noul":0.1}}}'
)


def test_jev_selects_high_without_exposing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def reply(request: urllib.request.Request, timeout: int) -> io.BytesIO:
        assert timeout == 5
        assert isinstance(request.data, bytes)
        assert "secret" not in request.data.decode("utf-8")
        assert request.get_header("Authorization") == "Bearer secret"
        return io.BytesIO(HARD)

    monkeypatch.setattr(launcher.urllib.request, "urlopen", reply)
    assert launcher.choose_effort("fix a complex bug", "secret") == "high"


@pytest.mark.parametrize(
    "answer",
    [b'{"answers":{"difficulty":{"type":"choice"}}}', b'{"answers":{}}', b"[]"],
)
def test_unusable_answer_falls_back(
    monkeypatch: pytest.MonkeyPatch, answer: bytes
) -> None:
    monkeypatch.setattr(
        launcher.urllib.request, "urlopen", lambda *_args, **_kwargs: io.BytesIO(answer)
    )
    assert launcher.choose_effort("task", "secret") == "medium"


def test_private_home_env_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip(
            "Windows uses process env; POSIX ownership/mode checks do not apply"
        )
    secret = tmp_path / ".env"
    secret.write_text("TYPESAFE_API_KEY=secret\n", encoding="utf-8")
    monkeypatch.setattr(launcher.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_AI_API_KEY", raising=False)
    secret.chmod(0o644)
    assert launcher.jev_key() is None
    secret.chmod(0o600)
    assert launcher.jev_key() == "secret"


def test_network_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(launcher.urllib.request, "urlopen", fail)
    assert launcher.choose_effort("task", "secret") == "medium"


def test_pi_route_prefers_ready_subscription(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret")

    def check(args: list[str], **kwargs: object) -> Mock:
        seen.append(args[-1])
        assert "TYPESAFE_API_KEY" not in cast("dict[str, str]", kwargs["env"])
        return Mock(
            returncode=0, stdout="ready" if args[-1] == "cursor" else "not_ready"
        )

    monkeypatch.setattr(launcher.subprocess, "run", check)
    assert launcher.pi_route() == "cursor/claude-sonnet-5-5"
    assert seen == ["github-copilot", "cursor"]


def test_pi_route_uses_metered_only_after_subscriptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def check(args: list[str], **_kwargs: object) -> Mock:
        seen.append(args[-1])
        return Mock(
            returncode=0, stdout="ready" if args[-1] == "openrouter" else "not_ready"
        )

    monkeypatch.setattr(launcher.subprocess, "run", check)
    assert launcher.pi_route() == "openrouter/anthropic/claude-sonnet-5.5"
    assert seen == ["github-copilot", "cursor", "openrouter"]


def test_launcher_does_not_pass_jev_key_to_pi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launcher.sys, "argv", ["jev_launch.py", "pi", "hello"])
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret")
    monkeypatch.setattr(launcher, "choose_effort", lambda *_args: "medium")
    monkeypatch.setattr(
        launcher, "pi_route", lambda: "github-copilot/claude-sonnet-5.5"
    )

    def check_child(argv: list[str], env: dict[str, str]) -> None:
        assert Path(argv[0]).stem == "pi"
        assert argv[1:] == [
            "--model",
            "github-copilot/claude-sonnet-5.5",
            "--thinking",
            "medium",
            "--append-system-prompt",
            launcher.SESSION_RULES,
            "hello",
        ]
        assert "TYPESAFE_API_KEY" not in env
        assert env["JEV_ROUTED_SESSION"] == "1"

    if os.name == "nt":

        def child(argv: list[str], **kwargs: object) -> Mock:
            check_child(argv, cast("dict[str, str]", kwargs["env"]))
            return Mock(returncode=0)

        monkeypatch.setattr(launcher.subprocess, "run", child)
        with pytest.raises(SystemExit) as exit_status:
            launcher.main()
        assert exit_status.value.code == 0
    else:
        monkeypatch.setattr(
            launcher.os, "execvpe", lambda _file, argv, env: check_child(argv, env)
        )
        launcher.main()


def _run_pi_launch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, installed: bool
) -> dict[str, str]:
    agent = tmp_path / "agent"
    (agent / "extensions").mkdir(parents=True)
    if installed:
        (agent / "extensions/jev-sonnet-fallback.ts").write_text("x", encoding="utf-8")
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(agent))
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret")
    monkeypatch.setattr(launcher.sys, "argv", ["jev_launch.py", "pi", "hello"])
    monkeypatch.setattr(launcher, "choose_effort", lambda *_args: "medium")
    monkeypatch.setattr(
        launcher, "pi_route", lambda: "github-copilot/claude-sonnet-5.5"
    )
    seen: dict[str, str] = {}

    def child(_argv: list[str], **kwargs: object) -> Mock:
        seen.update(cast("dict[str, str]", kwargs["env"]))
        return Mock(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", child)
    monkeypatch.setattr(
        launcher.os, "execvpe", lambda _file, _argv, env: seen.update(env)
    )
    try:
        launcher.main()
    except SystemExit:
        pass
    return seen


def test_pi_receives_key_handoff_only_when_extension_is_installed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = _run_pi_launch(monkeypatch, tmp_path, installed=True)
    assert env["JEV_KEY_HANDOFF"] == "secret"
    assert "TYPESAFE_API_KEY" not in env


def test_pi_without_extension_never_receives_the_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env = _run_pi_launch(monkeypatch, tmp_path, installed=False)
    assert "JEV_KEY_HANDOFF" not in env
    assert "TYPESAFE_API_KEY" not in env


CASES = json.loads(
    (Path(__file__).parent / "jev_effort_cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_effort_composes_score_noul_and_confidence(case: dict[str, object]) -> None:
    answers = cast("dict[str, object]", case["answers"])
    assert launcher.effort_from_answers(answers) == case["expected"]


def test_request_asks_score_and_noul_in_one_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict[str, object]] = []

    def reply(request: urllib.request.Request, timeout: int) -> io.BytesIO:
        assert isinstance(request.data, bytes)
        sent.append(json.loads(request.data))
        return io.BytesIO(
            b'{"answers":{"difficulty":{"type":"score","score":1.8,"confidence":0.9},'
            b'"strict_structure":{"type":"noul","noul":0.1}}}'
        )

    monkeypatch.setattr(launcher.urllib.request, "urlopen", reply)
    assert launcher.choose_effort("hard task", "secret") == "high"
    questions = cast("dict[str, dict[str, object]]", sent[0]["questions"])
    assert {name: q["type"] for name, q in questions.items()} == {
        "difficulty": "score",
        "strict_structure": "noul",
    }
    assert len(cast("list[str]", questions["difficulty"]["criteria"])) == 3
