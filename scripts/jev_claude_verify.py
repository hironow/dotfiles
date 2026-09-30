#!/usr/bin/env python3
"""Live check of the Claude worker hook. Run it once the Claude usage limit has reset.

The verdict comes from records Claude Code leaves behind, not from model text:
the hook's own log, each subagent's sidecar (agentType, name) and the effort
recorded on each of its requests.

Exit 0 = pass, 1 = fail (a real defect), 2 = blocked (usage limit or no login; nothing learned),
3 = partial (works, but the effort could not be confirmed; check /tasks by eye).
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from jev_core import SONNET, claude_session_args
from jev_launch import hook_command

SESSION_EFFORT = (
    "medium"  # A "high" recorded on a worker can then only come from the pick.
)
PROMPT = (
    "Make exactly two Agent tool calls with subagent_type general-purpose. "
    "Call 1 has no name. Call 2 has the name 'probe'. Both use this prompt: "
    "'Redesign the distributed lock protocol across three services, prove safety "
    "under partial failure, then plan the migration of all callers. Analysis only: "
    "do not use any tool and do not edit files; answer in one sentence.' "
    "Then reply with the single word DONE."
)
EXIT = {"pass": 0, "fail": 1, "blocked": 2, "partial": 3}


@dataclass
class Report:
    status: str
    reason: str
    evidence: list[str] = field(default_factory=list)


def has_provider_limit(stream_lines: list[str]) -> bool:
    """Read only the CLI's provider-error fields, never quoted user/tool text."""
    for line in stream_lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "assistant" and event.get("error") == "rate_limit":
            # stream-json may omit the transcript-only marker; if present it
            # must be a real boolean true, not a string or an ordinary message.
            if "isApiErrorMessage" not in event or event["isApiErrorMessage"] is True:
                return True
        if event.get("type") == "result" and event.get("is_error") is True:
            result = event.get("result")
            if isinstance(result, str) and re.match(
                r"^You've hit your (?:(?:weekly|daily|session|5-hour) )?limit\b", result
            ):
                return True
    return False


def is_logged_out(stream_lines: list[str]) -> bool:
    """The CLI ended before any request because it has no login (its own result
    event, never quoted model text): nothing was tested, so this is not a defect."""
    for line in stream_lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if (
            isinstance(event, dict)
            and event.get("type") == "result"
            and event.get("is_error") is True
            and isinstance(event.get("result"), str)
            and re.match(r"^Not logged in\b", event["result"])
        ):
            return True
    return False


def analyze(
    stream_lines: list[str],
    hook_records: list[dict],
    subagents: list[dict],
    debug_log: str,
) -> Report:
    """Functional core: pass/fail/blocked/partial from what the run left behind.

    Each subagent is {"agentType", "name" (or None), "efforts" (the effort recorded
    on each of its requests)}.
    """
    limited = has_provider_limit(stream_lines)
    # Match the rejected-key diagnostic itself, not words in unrelated hooks
    # or in the valid updatedInput payload (which may quote an error message).
    rejected_key = (
        r"^(?:.*?\[(?:DEBUG|ERROR)\]\s+)?Hook (?:JSON )?output[^\n{}]*"
        r"\bunrecognized key(?:s|\(s\))?(?: in object| \(ignored\))?:\s*"
        r"(?:[\"']?\w+[\"']?,\s*)*[\"']?updatedInput[\"']?(?:\s*[,.]|$)"
    )
    if any(re.search(rejected_key, line) for line in debug_log.splitlines()):
        return Report(
            "fail",
            "Claude Code rejected the hook output schema for updatedInput (see the debug log)",
        )
    if not hook_records and is_logged_out(stream_lines):
        return Report(
            "blocked",
            "Claude Code is not logged in (run claude, then /login); nothing was verified",
        )
    if not hook_records:
        return Report(
            "blocked" if limited else "fail",
            "Claude usage limit; no rewrite could be verified"
            if limited
            else "the hook never recorded a rewrite: it did not run, or Jev gave no answer",
        )
    record = hook_records[-1]
    target, want = record["to"], record["effort"]
    plain = [s for s in subagents if not s.get("name")]
    named = [s for s in subagents if s.get("name")]
    matched = [s for s in plain if s["agentType"] == target]
    if not matched:
        if limited and not plain:
            return Report("blocked", "Claude usage limit; no plain worker executed")
        return Report(
            "fail",
            f"the hook chose {target} but the plain worker ran as "
            f"{sorted({s['agentType'] for s in plain}) or 'nothing'}: "
            "updatedInput was ignored for Agent",
        )
    evidence = [
        f"{'teammate' if s.get('name') else 'plain'} {s['agentType']}: recorded effort "
        f"{sorted(set(s['efforts'])) or 'none'}"
        for s in subagents
    ]
    efforts = {e for s in matched for e in s["efforts"]}
    # A real observed mismatch wins over an unrelated quota event. Missing
    # evidence during a quota stop, however, is BLOCKED rather than a defect.
    if efforts and efforts != {want}:
        return Report(
            "fail",
            f"the worker recorded effort {sorted(efforts)} instead of {want}: "
            "the frontmatter effort was not honoured",
            evidence,
        )
    if any(not s["efforts"] for s in matched):
        return Report(
            "blocked" if limited else "partial",
            "not every plain worker has recorded effort; confirm with /tasks",
            evidence,
        )
    if want == SESSION_EFFORT:
        return Report(
            "blocked" if limited else "partial",
            "Jev chose the session effort, so the frontmatter effort cannot be told apart; rerun",
            evidence,
        )
    if any(set(s["efforts"]) != {want} for s in named if s["agentType"] == target):
        evidence.append(
            "warning: a teammate (named) spawn dropped the effort "
            "(anthropics/claude-code#64706); plain spawns are fine"
        )
    if limited:
        return Report(
            "blocked", "Claude usage limit; worker evidence retained", evidence
        )
    return Report("pass", f"a plain worker ran as {target} at effort {want}", evidence)


def collect_subagents(config_dir: Path, session_id: str) -> list[dict]:
    """Shell: read each subagent's sidecar and the effort recorded on its requests."""
    found = []
    pattern = f"projects/*/{session_id}/subagents/agent-*.jsonl"
    for transcript in sorted(config_dir.glob(pattern)):
        meta_path = transcript.with_suffix(".meta.json")
        meta = (
            json.loads(meta_path.read_text(encoding="utf-8"))
            if meta_path.exists()
            else {}
        )
        efforts = []
        for line in transcript.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") == "assistant" and row.get("effort"):
                efforts.append(row["effort"])
        found.append(
            {
                "agentType": meta.get("agentType", ""),
                "name": meta.get("name"),
                "efforts": efforts,
            }
        )
    return found


def _session_id(stream_lines: list[str]) -> str:
    for line in stream_lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("session_id"):
            return str(event["session_id"])
    return ""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        hook_log, debug_file = Path(tmp) / "hook.log", Path(tmp) / "debug.log"
        env = {**os.environ, "JEV_HOOK_LOG": str(hook_log)}
        command = [
            "claude",
            "-p",
            PROMPT,
            "--model",
            SONNET,
            "--effort",
            SESSION_EFFORT,
            *claude_session_args(hook_command()),
            "--output-format",
            "stream-json",
            "--verbose",
            "--debug-file",
            str(debug_file),
        ]
        # Claude Code writes UTF-8; the locale default (cp932 on Japanese Windows)
        # cannot decode it.
        run = subprocess.run(
            command,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        lines = run.stdout.splitlines()
        records = (
            [
                json.loads(line)
                for line in hook_log.read_text(encoding="utf-8").splitlines()
            ]
            if hook_log.exists()
            else []
        )
        debug = debug_file.read_text(encoding="utf-8") if debug_file.exists() else ""
    config = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    report = analyze(
        lines, records, collect_subagents(config, _session_id(lines)), debug
    )
    print(f"{report.status.upper()}: {report.reason}")
    for line in report.evidence:
        print(f"  {line}")
    return EXIT[report.status]


if __name__ == "__main__":
    raise SystemExit(main())
