"""Functional core of the Jev launchers: pure decisions, no I/O.

The imperative shells (jev_launch.py, and the Claude hook built on it) own every
side effect: environment, files, network, subprocesses. Everything here takes
its data as arguments and returns a value, so it is tested without mocks.
"""

import json
import math
import re
from collections.abc import Mapping, Sequence

JEV_URL = "https://api.typesafe.ai/v1/systemone"
SONNET = "claude-sonnet-5-5"
# Other subscriptions first, then the Claude Code subscription (kept for last so it is
# left for Claude Code itself), then the metered route. The Pi extension uses the same
# order if a provider reports a usage limit during the session.
PI_ROUTES = (
    ("github-copilot", "claude-sonnet-5.5"),
    ("cursor", "claude-sonnet-5-5"),
    ("anthropic", "claude-sonnet-5-5"),
    ("openrouter", "anthropic/claude-sonnet-5.5"),
)
# Sonnet 5.5 coding guidance: medium for well-specified work, high for harder
# work. Reserve xhigh/max until a workload-specific evaluation proves a gain.
# Jev answers atomic questions (docs.typesafe.ai): a Score for how hard the task
# is and a Noul for strict structure. This code combines them; thresholds live here.
QUESTIONS: dict[str, dict[str, object]] = {
    "difficulty": {
        "type": "score",
        "instructions": "How demanding is this coding-agent task for the model that performs it?",
        "criteria": [
            "Small, well-specified change or lookup with a clear finish line, such as a rename, a typo, or running one command.",
            "Routine multi-step engineering with a known approach, such as adding a test, a simple feature, or a focused bug fix.",
            "Hard or open-ended engineering: unclear cause, cross-cutting design, many files or services, migrations, or long-running multistep tool use.",
        ],
    },
    "strict_structure": {
        "type": "noul",
        "instructions": "Does the task require producing strictly structured output, such as a JSON schema, a typed contract, or a machine-checked format, where a formatting mistake would break a consumer?",
    },
}
HARD_SCORE = 1.5  # Nearest level is the top of the three-level difficulty scale.
STRICT_STRUCTURE = 0.7  # Acting on a false yes costs thinking tokens, so lean high.
CONFIDENCE_FLOOR = 0.5  # Below this Jev is saying "I don't know"; keep the default.
SESSION_RULES = (
    "The host selected the model and effort before this session. Keep both fixed; "
    "Pi may switch only to an approved Sonnet 5.5 provider on a usage limit. "
    "The host owns permissions and approvals. Follow existing repository rules, "
    "including mandatory independent plan review. Give any required reviewer "
    "the task, applicable files, limits, and completion criteria; report evidence. "
    "Complete the requested work, run a relevant check, then report and stop."
)


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def effort_from_answers(answers: dict[str, object]) -> str:
    """Compose Jev's typed answers into an effort; anything unusable means medium."""
    structure = answers.get("strict_structure")
    noul = _number(structure.get("noul")) if isinstance(structure, dict) else None
    if noul is not None and noul >= STRICT_STRUCTURE:
        return "high"
    difficulty = answers.get("difficulty")
    if not isinstance(difficulty, dict):
        return "medium"
    score = _number(difficulty.get("score"))
    confidence = _number(difficulty.get("confidence"))
    if score is None or confidence is None or confidence < CONFIDENCE_FLOOR:
        return "medium"
    return "high" if score >= HARD_SCORE else "medium"


def build_request_body(task: str) -> dict[str, object]:
    return {"model": "jev-latest", "state": task[:8000], "questions": QUESTIONS}


def parse_args(argv: list[str]) -> tuple[str, str]:
    """Return (host, task); raise ValueError with the message to show."""
    if len(argv) < 2 or argv[0] not in {"claude", "pi"}:
        raise ValueError("Usage: jev_launch.py {claude|pi} 'task description'")
    task = " ".join(argv[1:]).strip()
    if not task:
        raise ValueError("Give the task up front so Jev can select an effort profile.")
    return argv[0], task


def build_command(
    host: str, task: str, effort: str, model: str, extra: Sequence[str] = ()
) -> list[str]:
    flag = "--effort" if host == "claude" else "--thinking"
    return [
        host,
        "--model",
        model,
        flag,
        effort,
        "--append-system-prompt",
        SESSION_RULES,
        *extra,
        task,
    ]


# ---- Claude Code workers ----
# Claude Code fixes a subagent's effort in its definition; the Agent tool takes no
# effort argument. So each effort gets a definition, and a PreToolUse hook swaps
# the launch onto the one Jev picked. Both are injected with --settings/--agents,
# so only a j-cc session is affected.
_WORKER_PROMPT = (
    "You are a worker agent inside a coding session. Complete the delegated task "
    "fully with the tools available. Report what you changed or found, with "
    "evidence such as the commands you ran and their results. Do not ask the user "
    "questions; state assumptions instead."
)
WORKER_AGENTS: dict[str, dict[str, str]] = {
    f"worker-{effort}": {
        "description": f"General-purpose worker running at {effort} effort",
        "prompt": _WORKER_PROMPT,
        "model": "inherit",
        "effort": effort,
    }
    for effort in ("medium", "high")
}
REWRITABLE_TYPES = {"general-purpose", "worker", ""}


def plan_agent_rewrite(tool_input: Mapping[str, object], effort: str) -> dict | None:
    """The Agent input to run instead, or None to leave the launch alone.

    Only default workers move; a named specialist or an explicit model stays as the
    caller chose it. updatedInput replaces the whole input, so copy every field.
    """
    if not isinstance(tool_input.get("prompt"), str) or tool_input.get("model"):
        return None
    if str(tool_input.get("subagent_type") or "") not in REWRITABLE_TYPES:
        return None
    return {**tool_input, "subagent_type": f"worker-{effort}"}


def hook_output(updated_input: Mapping[str, object]) -> dict:
    """No permissionDecision: the rewrite must not skip any approval prompt."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "updatedInput": dict(updated_input),
        }
    }


def claude_session_args(hook_command: str) -> list[str]:
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Agent|Task",
                    "hooks": [
                        {"type": "command", "command": hook_command, "timeout": 15}
                    ],
                }
            ]
        }
    }
    return ["--settings", json.dumps(settings), "--agents", json.dumps(WORKER_AGENTS)]


def build_env(
    environ: Mapping[str, str],
    host: str,
    key: str | None,
    extension_ready: bool,
    codex_agents_ready: bool = False,
) -> dict[str, str]:
    """The child's environment. Neither agent gets the Jev secret in its env."""
    env = {
        name: value
        for name, value in environ.items()
        if name not in {"TYPESAFE_API_KEY", "TYPESAFE_AI_API_KEY"}
    }
    if host == "pi":
        env["JEV_ROUTED_SESSION"] = "1"
        if key and extension_ready:
            # Consumed and removed by the extension at load; bash tool and child
            # sessions never see it. Absent extension, the key stays out of Pi.
            env["JEV_KEY_HANDOFF"] = key
        if codex_agents_ready:
            env["JEV_CODEX_AGENTS"] = "1"
    else:
        env.setdefault("RUNOPS_ACTOR_TYPE", "ai-agent")
    return env


# ---- Codex workers: pick a gpt-6 model and its reasoning effort ----
# OpenAI's guidance (learn.chatgpt.com/docs/models, 2026-09-29): GPT-6.1 Sol has
# near-Astra performance for complex, repeated or long-running work at a lower cost, so
# it is the default for complex coding. Keep Astra for the most demanding end-to-end
# work (start at low); Luna suits clear, repeatable tasks (start at high). Astra costs
# far more than Sol, so it needs a confident "hard and end to end" read.
CODEX_QUESTIONS: dict[str, dict[str, object]] = {
    **QUESTIONS,
    "well_scoped": {
        "type": "noul",
        "instructions": "Is this a specific, repeatable task where a good result is easy to recognize, such as extraction, classification, transformation, a structured summary, or a focused code change?",
    },
    "end_to_end": {
        "type": "noul",
        "instructions": "Does the task span many steps across code, tools, applications or research, and need sustained judgment to reach a complete result?",
    },
}
WELL_SCOPED = 0.7
END_TO_END = 0.7
ASTRA_CONFIDENCE = 0.8
CODEX_DEFAULT = ("gpt-6.1-sol", "medium")
# A strict format means a slip breaks a consumer: one step up where there is room.
_ONE_STEP_UP = {("gpt-6.1-sol", "medium"): "high", ("gpt-6-astra", "low"): "medium"}
CODEX_SANDBOXES = ("read-only", "workspace-write")
CODEX_AGENT_TYPES = {"codex:codex-rescue", "codex-rescue"}


def build_codex_request_body(task: str) -> dict[str, object]:
    return {**build_request_body(task), "questions": CODEX_QUESTIONS}


def _noul(answers: Mapping[str, object], name: str) -> float:
    answer = answers.get(name)
    value = _number(answer.get("noul")) if isinstance(answer, dict) else None
    return -1.0 if value is None else value


def codex_from_answers(answers: Mapping[str, object]) -> tuple[str, str]:
    """(model, effort) for a Codex worker; anything unusable means Sol at medium."""
    difficulty = answers.get("difficulty")
    score = _number(difficulty.get("score")) if isinstance(difficulty, dict) else None
    confidence = (
        _number(difficulty.get("confidence")) if isinstance(difficulty, dict) else None
    )
    choice = CODEX_DEFAULT
    if score is not None and confidence is not None and confidence >= CONFIDENCE_FLOOR:
        if score >= HARD_SCORE:
            hard_and_sure = (
                _noul(answers, "end_to_end") >= END_TO_END
                and confidence >= ASTRA_CONFIDENCE
            )
            choice = (
                ("gpt-6-astra", "low") if hard_and_sure else ("gpt-6.1-sol", "high")
            )
        elif _noul(answers, "well_scoped") >= WELL_SCOPED:
            choice = ("gpt-6-luna", "high")
    if (
        _noul(answers, "strict_structure") >= STRICT_STRUCTURE
        and choice in _ONE_STEP_UP
    ):
        choice = (choice[0], _ONE_STEP_UP[choice])
    return choice


def build_codex_exec_command(
    model: str, effort: str, sandbox: str, final_message_path: str
) -> list[str]:
    """`codex exec` the way pi-subagents' own adapter runs it, plus the model and effort."""
    if sandbox not in CODEX_SANDBOXES:
        raise ValueError(f"sandbox must be one of {CODEX_SANDBOXES}")
    return [
        "codex",
        "exec",
        "--json",
        "--color",
        "never",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "-s",
        sandbox,
        "-m",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "-c",
        'approval_policy="never"',
        "--output-last-message",
        final_message_path,
        "-",
    ]


_EXPLICIT_CODEX_FLAG = re.compile(r"(?:^|\s)--(?:model|effort)(?:[=\s]|$)")


def plan_codex_rewrite(
    tool_input: Mapping[str, object], model: str, effort: str
) -> dict | None:
    """The Agent input that hands `codex:codex-rescue` a model and effort, or None.

    The plugin's wrapper forwards `--model`/`--effort` written in the request, so the
    flags go in front of the prompt. Anything the caller already chose wins.
    """
    prompt = tool_input.get("prompt")
    if tool_input.get("subagent_type") not in CODEX_AGENT_TYPES:
        return None
    if not isinstance(prompt, str) or _EXPLICIT_CODEX_FLAG.search(prompt):
        return None
    return {**tool_input, "prompt": f"--model {model} --effort {effort} {prompt}"}
