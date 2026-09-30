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


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), 10**400])
@pytest.mark.parametrize("field", ["score", "confidence", "noul"])
def test_nonfinite_or_overflowing_answers_do_not_raise_effort(
    field: str, value: float | int
) -> None:
    difficulty = {"score": 0, "confidence": 0.9}
    structure = {"noul": 0}
    if field == "noul":
        structure["noul"] = value
    else:
        difficulty = {"score": 2, "confidence": 0.9, field: value}
    assert (
        core.effort_from_answers(
            {"difficulty": difficulty, "strict_structure": structure}
        )
        == "medium"
    )


def test_valid_structure_still_raises_effort_when_difficulty_is_nonfinite() -> None:
    assert (
        core.effort_from_answers(
            {
                "difficulty": {"score": 2, "confidence": float("nan")},
                "strict_structure": {"noul": 1},
            }
        )
        == "high"
    )


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


def test_worker_agents_differ_only_by_effort() -> None:
    assert set(core.WORKER_AGENTS) == {"worker-medium", "worker-high"}
    for name, agent in core.WORKER_AGENTS.items():
        assert agent["effort"] == name.removeprefix("worker-")
        assert agent["model"] == "inherit"
    prompts = {agent["prompt"] for agent in core.WORKER_AGENTS.values()}
    assert len(prompts) == 1


@pytest.mark.parametrize("subagent_type", ["general-purpose", "worker", None, ""])
def test_default_worker_types_are_rewritten_to_the_chosen_effort(
    subagent_type: str | None,
) -> None:
    tool_input: dict[str, object] = {"prompt": "p", "description": "d"}
    if subagent_type is not None:
        tool_input["subagent_type"] = subagent_type
    original = dict(tool_input)
    assert core.plan_agent_rewrite(tool_input, "high") == {
        "prompt": "p",
        "description": "d",
        "subagent_type": "worker-high",
    }
    assert tool_input == original  # the input is never mutated


@pytest.mark.parametrize(
    "tool_input",
    [
        {"prompt": "p", "subagent_type": "Explore"},
        {"prompt": "p", "subagent_type": "my-reviewer"},
        {"prompt": "p", "subagent_type": "general-purpose", "model": "haiku"},
        {"subagent_type": "general-purpose"},
        {"prompt": 3, "subagent_type": "general-purpose"},
    ],
)
def test_other_launches_are_left_to_their_owner(tool_input: dict[str, object]) -> None:
    assert core.plan_agent_rewrite(tool_input, "high") is None


def test_hook_output_replaces_input_without_deciding_permission() -> None:
    output = core.hook_output({"prompt": "p", "subagent_type": "worker-high"})
    assert output == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": {"prompt": "p", "subagent_type": "worker-high"},
        }
    }
    assert "permissionDecision" not in output["hookSpecificOutput"]


def test_claude_session_args_inject_hook_and_agents_for_this_session_only() -> None:
    args = core.claude_session_args("py hook.py")
    assert args[0] == "--settings" and args[2] == "--agents"
    hooks = json.loads(args[1])["hooks"]["PreToolUse"]
    assert hooks[0]["matcher"] == "Agent|Task"
    assert hooks[0]["hooks"][0]["command"] == "py hook.py"
    assert hooks[0]["hooks"][0]["timeout"] == 15
    assert set(json.loads(args[3])) == set(core.WORKER_AGENTS)


def test_build_command_places_extra_args_before_the_task() -> None:
    command = core.build_command("claude", "task", "high", core.SONNET, ["--x", "1"])
    assert command[-3:] == ["--x", "1", "task"]


CODEX_CASES = json.loads(
    (Path(__file__).parent / "jev_codex_cases.json").read_text(encoding="utf-8")
)


@pytest.mark.parametrize(
    "case", CODEX_CASES, ids=[case["name"] for case in CODEX_CASES]
)
def test_codex_model_and_effort_follow_openai_guidance(case: dict[str, object]) -> None:
    answers = cast("dict[str, object]", case["answers"])
    assert list(core.codex_from_answers(answers)) == case["expected"]


def test_codex_request_adds_two_atomic_questions_to_the_shared_ones() -> None:
    body = core.build_codex_request_body("task")
    questions = cast("dict[str, dict[str, object]]", body["questions"])
    assert set(questions) == {
        "difficulty",
        "strict_structure",
        "well_scoped",
        "end_to_end",
    }
    assert questions["well_scoped"]["type"] == questions["end_to_end"]["type"] == "noul"
    assert cast(
        "dict[str, object]", core.build_request_body("task")["questions"]
    ).keys() == {
        "difficulty",
        "strict_structure",
    }


def test_codex_only_uses_the_gpt_6_family_and_efforts_the_cli_accepts() -> None:
    models = {c["expected"][0] for c in CODEX_CASES}
    efforts = {c["expected"][1] for c in CODEX_CASES}
    assert models == {"gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"}
    assert efforts <= {"low", "medium", "high"}  # the Claude plugin stops at xhigh


def test_exec_command_owns_the_sandbox_and_pins_model_and_effort() -> None:
    command = core.build_codex_exec_command(
        "gpt-6.1-sol", "high", "workspace-write", "/tmp/out.txt"
    )
    assert command[:2] == ["codex", "exec"]
    assert command[command.index("-s") + 1] == "workspace-write"
    assert command[command.index("-m") + 1] == "gpt-6.1-sol"
    assert 'model_reasoning_effort="high"' in command
    assert 'approval_policy="never"' in command
    assert "--ignore-user-config" in command and command[-1] == "-"
    assert command[command.index("--output-last-message") + 1] == "/tmp/out.txt"


def test_exec_command_refuses_an_unknown_sandbox() -> None:
    with pytest.raises(ValueError, match="sandbox"):
        core.build_codex_exec_command(
            "gpt-6.1-sol", "high", "danger-full-access", "/tmp/x"
        )


@pytest.mark.parametrize("agent", ["codex:codex-rescue", "codex-rescue"])
def test_codex_rescue_gets_flags_prepended_to_its_prompt(agent: str) -> None:
    tool_input = {
        "prompt": "fix the flaky test",
        "subagent_type": agent,
        "description": "d",
    }
    original = dict(tool_input)
    planned = core.plan_codex_rewrite(tool_input, "gpt-6.1-sol", "medium")
    assert planned == {
        **original,
        "prompt": "--model gpt-6.1-sol --effort medium fix the flaky test",
    }
    assert tool_input == original


@pytest.mark.parametrize(
    "tool_input",
    [
        {"prompt": "--model gpt-6-luna fix it", "subagent_type": "codex:codex-rescue"},
        {"prompt": "fix it --effort high", "subagent_type": "codex:codex-rescue"},
        {"prompt": "--model=gpt-6-luna fix it", "subagent_type": "codex:codex-rescue"},
        {"prompt": "fix it", "subagent_type": "general-purpose"},
        {"prompt": "fix it", "subagent_type": "codex:other"},
        {"subagent_type": "codex:codex-rescue"},
    ],
)
def test_an_explicit_choice_or_another_agent_is_left_alone(
    tool_input: dict[str, object],
) -> None:
    assert core.plan_codex_rewrite(tool_input, "gpt-6.1-sol", "medium") is None


@pytest.mark.parametrize(
    ("host", "ready", "flag"),
    [("pi", True, True), ("pi", False, False), ("claude", True, False)],
)
def test_pi_learns_whether_the_codex_agents_are_installed(
    host: str, ready: bool, flag: bool
) -> None:
    env = core.build_env({}, host, None, extension_ready=True, codex_agents_ready=ready)
    assert (env.get("JEV_CODEX_AGENTS") == "1") is flag


ME = "S-1-5-21-1-2-3-1001"
OTHER = "S-1-5-21-1-2-3-1002"


@pytest.mark.parametrize(
    ("owner", "allowed", "private"),
    [
        (ME, [ME], True),
        # a default profile file: the user plus SYSTEM and Administrators
        (ME, ["S-1-5-18", "S-1-5-32-544", ME], True),
        (ME, [ME, "S-1-1-0"], False),  # Everyone
        (ME, [ME, "S-1-5-11"], False),  # Authenticated Users
        (ME, [ME, "S-1-5-32-545"], False),  # Users
        (ME, [ME, OTHER], False),
        (OTHER, [ME], False),  # someone else owns it and can rewrite the ACL
    ],
)
def test_windows_env_file_is_private_only_to_the_user(
    owner: str, allowed: list[str], private: bool
) -> None:
    assert core.windows_acl_is_private(ME, owner, allowed) is private
