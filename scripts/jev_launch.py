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
PROFILES = {"routine": "medium", "complex": "high", "json": "high"}
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


def choose_effort(task: str, key: str | None) -> str:
    """One bounded Jev choice; a failed or unknown choice keeps the host profile."""
    if not key:
        print("Jev: no TYPESAFE_API_KEY; using Sonnet 5.5 medium", file=sys.stderr)
        return "medium"
    body = {
        "model": "jev-latest",
        "state": task[:8000],
        "questions": {
            "profile": {
                "type": "choice",
                "instructions": "Select effort for one coding-agent session. Pick routine for well-specified coding, complex for hard or long-running agentic coding and multistep tool use, json for difficult structured JSON tasks.",
                "criteria": {
                    "routine": "Clear coding or straightforward work; Sonnet 5.5 medium",
                    "complex": "Hard or long agentic coding, complex reasoning, multistep tools; Sonnet 5.5 high",
                    "json": "Difficult JSON or constrained structured work; Sonnet 5.5 high",
                },
            }
        },
    }
    request = urllib.request.Request(
        JEV_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            answer = json.load(response)["answers"]["profile"]
        if answer.get("type") != "choice":
            raise ValueError("unexpected answer type")
        return PROFILES[answer["choice"]]
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
    effort = choose_effort(task, jev_key())
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
    else:
        env.setdefault("RUNOPS_ACTOR_TYPE", "ai-agent")
    if os.name == "nt":
        # Resolve mise's .cmd/.exe shim via PATHEXT before CreateProcess.
        command[0] = shutil.which(command[0]) or command[0]
        raise SystemExit(subprocess.run(command, env=env, check=False).returncode)
    os.execvpe(command[0], command, env)


if __name__ == "__main__":
    main()
