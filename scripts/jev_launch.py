#!/usr/bin/env python3
"""Opt-in Jev routing for a new Claude Code or Pi session."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

JEV_URL = "https://api.typesafe.ai/v1/systemone"
SONNET = "claude-sonnet-5-5"
# Subscription-backed routes precede the metered route. The Pi extension uses
# the same order if a provider reports a usage limit during the session.
PI_ROUTES = (
    ("github-copilot", "claude-sonnet-5.5"),
    ("cursor", "claude-sonnet-5-5"),
    ("openrouter", "anthropic/claude-sonnet-5.5"),
)
# Sonnet 5.5 coding guidance: medium for well-specified work, high for harder
# work. Reserve xhigh/max until a workload-specific evaluation proves a gain.
# Jev answers atomic questions (docs.typesafe.ai): a Score for how hard the task
# is and a Noul for strict structure. This code combines them; thresholds live here.
QUESTIONS = {
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


def jev_key() -> str | None:
    key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("TYPESAFE_AI_API_KEY")
    if key:
        return key
    # A local private file is convenient for interactive shell functions. Do
    # not source it: arbitrary shell content must never run during routing.
    path = Path.home() / ".env"
    if os.name == "nt" or not path.is_file():
        return None
    stat = path.stat()
    if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
        print("Jev: ~/.env must be owned by you and mode 0600", file=sys.stderr)
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            if name.removeprefix("export ").strip() == "TYPESAFE_API_KEY":
                return value.strip().strip("\"'") or None
    return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


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


def choose_effort(task: str, key: str | None) -> str:
    """One bounded Jev call; a failed or unusable answer keeps the host profile."""
    if not key:
        print("Jev: no TYPESAFE_API_KEY; using Sonnet 5.5 medium", file=sys.stderr)
        return "medium"
    body = {"model": "jev-latest", "state": task[:8000], "questions": QUESTIONS}
    request = urllib.request.Request(
        JEV_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            answers = json.load(response)["answers"]
        if not isinstance(answers, dict):
            raise TypeError("answers is not an object")
        return effort_from_answers(answers)
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        KeyError,
        TypeError,
    ) as error:
        # Never print exception bodies/headers: upstream errors may echo the key.
        print(
            f"Jev: no valid selection ({type(error).__name__}); using Sonnet 5.5 medium",
            file=sys.stderr,
        )
        return "medium"


def agent_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("TYPESAFE_API_KEY", None)  # Neither Pi nor Claude needs the Jev secret.
    env.pop("TYPESAFE_AI_API_KEY", None)
    return env


def extension_installed() -> bool:
    """The worker-effort extension consumes the key handoff; without it, hand off nothing."""
    agent = Path(os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent")
    return (agent / "extensions/jev-sonnet-fallback.ts").is_file()


def pi_route() -> str:
    env = agent_environment()
    for provider, model in PI_ROUTES:
        try:
            check = subprocess.run(
                [shutil.which("pi") or "pi", "auth", "check", "--provider", provider],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                env=env,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if check.returncode == 0 and check.stdout.strip() == "ready":
            return f"{provider}/{model}"
    raise RuntimeError("no authenticated Pi Sonnet 5.5 provider (run pi /login)")


def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in {"claude", "pi"}:
        raise SystemExit("Usage: jev_launch.py {claude|pi} 'task description'")
    host = sys.argv[1]
    task = " ".join(sys.argv[2:]).strip()
    if not task:
        raise SystemExit("Give the task up front so Jev can select an effort profile.")
    key = jev_key()
    effort = choose_effort(task, key)
    print(f"Jev: {host} Sonnet 5.5 / {effort}", file=sys.stderr)
    if host == "claude":
        command = [
            "claude",
            "--model",
            SONNET,
            "--effort",
            effort,
            "--append-system-prompt",
            SESSION_RULES,
            task,
        ]
    else:
        model = pi_route()
        print(f"Pi route: {model}", file=sys.stderr)
        command = [
            "pi",
            "--model",
            model,
            "--thinking",
            effort,
            "--append-system-prompt",
            SESSION_RULES,
            task,
        ]
    env = agent_environment()
    if host == "pi":
        env["JEV_ROUTED_SESSION"] = "1"
        if key and extension_installed():
            # Consumed and removed by the extension at load; bash tool and child
            # sessions never see it. Absent extension, the key stays out of Pi.
            env["JEV_KEY_HANDOFF"] = key
    else:
        env.setdefault("RUNOPS_ACTOR_TYPE", "ai-agent")
    if os.name == "nt":
        # Resolve mise's .cmd/.exe shim via PATHEXT before CreateProcess.
        command[0] = shutil.which(command[0]) or command[0]
        raise SystemExit(subprocess.run(command, env=env, check=False).returncode)
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
