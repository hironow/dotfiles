"""Functional core of the Jev launchers: pure decisions with no I/O."""

import json
import sys
from pathlib import Path
from typing import cast

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import jev_core as core  # noqa: E402

CASES = json.loads(
    (Path(__file__).parent / "jev_effort_cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_effort_composes_score_noul_and_confidence(case: dict[str, object]) -> None:
    answers = cast("dict[str, object]", case["answers"])
    assert core.effort_from_answers(answers) == case["expected"]


def test_request_asks_one_score_and_one_noul() -> None:
    body = core.build_request_body("x" * 9000)
    assert body["model"] == "jev-latest"
    assert body["state"] == "x" * 8000
    questions = cast("dict[str, dict[str, object]]", body["questions"])
    assert {name: q["type"] for name, q in questions.items()} == {
        "difficulty": "score",
        "strict_structure": "noul",
    }
    assert len(cast("list[str]", questions["difficulty"]["criteria"])) == 3


def test_parse_task_joins_arguments_and_rejects_bad_usage() -> None:
    assert core.parse_args(["claude", "fix", "the", "bug"]) == ("claude", "fix the bug")
    for argv in (["claude"], ["gemini", "task"], ["pi", "  "]):
        with pytest.raises(ValueError, match="Usage|task"):
            core.parse_args(argv)


def test_build_command_pins_model_effort_and_rules() -> None:
    assert core.build_command("claude", "task", "high", core.SONNET) == [
        "claude",
        "--model",
        core.SONNET,
        "--effort",
        "high",
        "--append-system-prompt",
        core.SESSION_RULES,
        "task",
    ]
    assert core.build_command("pi", "task", "medium", "cursor/x")[:5] == [
        "pi",
        "--model",
        "cursor/x",
        "--thinking",
        "medium",
    ]


def test_build_env_never_leaks_the_key_and_leaves_the_input_alone() -> None:
    environ = {"TYPESAFE_API_KEY": "s", "TYPESAFE_AI_API_KEY": "s", "PATH": "/bin"}
    env = core.build_env(environ, "claude", "s", extension_ready=True)
    assert "TYPESAFE_API_KEY" not in env and "TYPESAFE_AI_API_KEY" not in env
    assert env["PATH"] == "/bin" and "JEV_KEY_HANDOFF" not in env
    assert env["RUNOPS_ACTOR_TYPE"] == "ai-agent"
    assert environ["TYPESAFE_API_KEY"] == "s"


def test_build_env_keeps_an_existing_actor_type() -> None:
    env = core.build_env({"RUNOPS_ACTOR_TYPE": "human"}, "claude", None, False)
    assert env["RUNOPS_ACTOR_TYPE"] == "human"


@pytest.mark.parametrize(
    ("key", "ready", "handed_off"),
    [("s", True, True), ("s", False, False), (None, True, False)],
)
def test_pi_gets_the_key_only_for_an_installed_extension(
    key: str | None, ready: bool, handed_off: bool
) -> None:
    env = core.build_env({}, "pi", key, extension_ready=ready)
    assert env["JEV_ROUTED_SESSION"] == "1"
    assert ("JEV_KEY_HANDOFF" in env) is handed_off
    assert "TYPESAFE_API_KEY" not in env
