#!/usr/bin/env python3
"""Live check of Jev's per-worker effort in Pi (`j-pi`).

The launcher's Pi extension rewrites a subagent launch's model to
`<route>:<effort>`. The session transcript keeps the launch as the model sent
it, so the verdict comes from what pi-subagents records for the run instead:
`<session>/subagent-artifacts/<run>_worker_meta.json`, which holds the model
the worker actually ran with and whether it succeeded.

Exit 0 = pass, 1 = fail (a real defect), 2 = blocked (no key, no extension or a
usage limit; nothing learned), 3 = partial (works, but a medium pick cannot be
told apart from the session's own medium).
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

from jev_core import build_command, build_env
from jev_launch import extension_installed, jev_key, pi_route

SESSION_EFFORT = "medium"  # A worker at "high" can then only come from the pick.
PROMPT = (
    "Call the subagent tool exactly once with agent 'worker' and this task: "
    "'Analysis only, change nothing: redesign a distributed lock protocol across "
    "three services, prove safety under partial failure, and plan migrating every "
    "caller. Answer in one short sentence.' When it returns, reply DONE."
)
EXIT = {"pass": 0, "fail": 1, "blocked": 2, "partial": 3}
_EFFORT = re.compile(r":(medium|high)$")
_LIMIT = re.compile(r"\b429\b|rate_limit|insufficient_quota|RESOURCE_EXHAUSTED")


@dataclass
class Report:
    status: str
    reason: str
    evidence: list[str] = field(default_factory=list)


def analyze(returncode: int, stderr: str, metas: list[dict]) -> Report:
    """Functional core: the verdict from the run's exit, stderr and worker records."""
    if not metas:
        if returncode != 0 and _LIMIT.search(stderr):
            return Report(
                "blocked", "a usage limit stopped the session before a worker ran"
            )
        return Report(
            "fail", "no worker ran: pi-subagents recorded no run for this session"
        )
    evidence = [
        f"worker {m.get('agent', '?')}: {m.get('model', '?')} (exit {m.get('exitCode')})"
        for m in metas
    ]
    picks = []
    for meta in metas:
        model = str(meta.get("model", ""))
        suffix = _EFFORT.search(model)
        if not suffix:
            return Report(
                "fail",
                f"a worker ran as {model or 'an unknown model'} without a Jev effort suffix",
                evidence,
            )
        if meta.get("exitCode") != 0:
            return Report(
                "fail",
                f"the worker on {model} did not finish (exit {meta.get('exitCode')})",
                evidence,
            )
        picks.append(suffix[1])
    if "high" in picks:
        return Report(
            "pass",
            "a worker ran at the effort Jev picked (high, above the session's medium)",
            evidence,
        )
    return Report(
        "partial",
        "workers ran at medium, the session's own effort: the pick cannot be told apart",
        evidence,
    )


def worker_metas(sessions: Path, cwd_name: str) -> list[dict]:
    """The worker records of sessions started in a directory named `cwd_name`."""
    metas = []
    for path in sorted(sessions.glob("*/subagent-artifacts/*_meta.json")):
        if cwd_name not in path.parent.parent.name:
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(meta, dict):
            metas.append(meta)
    return metas


def main() -> int:
    key = jev_key()
    if not key:
        report = Report("blocked", "no TYPESAFE_API_KEY: Jev cannot pick an effort")
    elif not extension_installed():
        report = Report(
            "blocked",
            "the Jev Pi extension is not installed: run just pi-extensions-install",
        )
    else:
        route = pi_route()
        env = build_env(os.environ, "pi", key, True)
        command = build_command("pi", PROMPT, SESSION_EFFORT, route)
        command[0] = shutil.which("pi") or "pi"
        command.insert(1, "-p")
        agent_dir = Path(
            os.environ.get("PI_CODING_AGENT_DIR") or Path.home() / ".pi/agent"
        )
        with tempfile.TemporaryDirectory() as cwd:
            run = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                # `pi -p` also reads a non-terminal stdin as input and waits for
                # EOF; an inherited open pipe would hang the check.
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=900,
                check=False,
            )
            metas = worker_metas(agent_dir / "sessions", Path(cwd).name)
        report = analyze(run.returncode, run.stderr, metas)
        report.evidence.insert(0, f"session route: {route} at {SESSION_EFFORT}")
    print(f"{report.status.upper()}: {report.reason}")
    for line in report.evidence:
        print(f"  {line}")
    return EXIT[report.status]


if __name__ == "__main__":
    sys.exit(main())
