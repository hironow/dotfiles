#!/usr/bin/env python3
"""Live check of the Claude worker hook. Run it once the Claude usage limit has reset.

The verdict comes from records Claude Code leaves behind, not from model text:
the hook's own log, each subagent's sidecar (agentType, name) and the effort
recorded on each of its requests.

Exit 0 = pass, 1 = fail (a real defect), 2 = blocked (usage limit; nothing learned),
3 = partial (works, but the effort could not be confirmed; check /tasks by eye).
"""

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

from jev_core import SONNET, claude_session_args
from jev_launch import hook_command

SESSION_EFFORT = (
    "medium"  # A "high" recorded on a worker can then only come from the pick.
)
PROMPT = (
    "Make exactly three Agent tool calls. The first two use subagent_type general-purpose. "
    "Call 1 has no name. Call 2 has the name 'probe'. Both use this prompt: "
    "'Redesign the distributed lock protocol across three services, prove safety "
    "under partial failure, then plan the migration of all callers. Analysis only: "
    "do not use any tool and do not edit files; answer in one sentence.' "
    "Call 3 uses subagent_type codex:codex-rescue with the prompt: 'Read-only: "
    "reply with the single word OK and do not edit any file.' "
    "Then reply with the single word DONE."
)
EXIT = {"pass": 0, "fail": 1, "blocked": 2, "partial": 3}


@dataclass
class Report:
    status: str
    reason: str
    evidence: list[str] = field(default_factory=list)


def _analyze_worker(
    stream_lines: list[str],
    hook_records: list[dict],
    subagents: list[dict],
    debug_log: str,
) -> Report:
    """Functional core: pass/fail/blocked/partial from what the run left behind.

    Each subagent is {"agentType", "name" (or None), "efforts" (the effort recorded
    on each of its requests)}.
    """
    if "hit your weekly limit" in "\n".join(stream_lines):
        return Report("blocked", "Claude usage limit; try again after it resets")
    if not hook_records:
        return Report(
            "fail",
            "the hook never recorded a rewrite: it did not run, or Jev gave no answer",
        )
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
    record = hook_records[-1]
    target, want = record["to"], record["effort"]
    plain = [s for s in subagents if not s.get("name")]
    named = [s for s in subagents if s.get("name")]
    if not any(s["agentType"] == target for s in plain):
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
    efforts = {e for s in plain if s["agentType"] == target for e in s["efforts"]}
    if want == SESSION_EFFORT:
        return Report(
            "partial",
            "Jev chose the session effort, so the frontmatter effort cannot be told apart; rerun",
            evidence,
        )
    if not efforts:
        return Report(
            "partial", "no recorded effort found; confirm with /tasks", evidence
        )
    if efforts != {want}:
        return Report(
            "fail",
            f"the worker recorded effort {sorted(efforts)} instead of {want}: "
            "the frontmatter effort was not honoured",
            evidence,
        )
    if any(set(s["efforts"]) != {want} for s in named if s["agentType"] == target):
        evidence.append(
            "warning: a teammate (named) spawn dropped the effort "
            "(anthropics/claude-code#64706); plain spawns are fine"
        )
    return Report("pass", f"a plain worker ran as {target} at effort {want}", evidence)


SEVERITY = {"blocked": 3, "fail": 2, "partial": 1, "pass": 0}


def _companion_choice(command: str) -> tuple[str, str] | None:
    """Exact model/effort argv in a simple node companion task invocation.

    Evidence only, never execute the string. Compound shell commands, substitutions,
    duplicate flags and unknown options cannot prove the invocation and are refused.
    The task's quoted text is one argv item, not another source of flags.
    """
    if any(part in command for part in ("\n", "\r", "`", "$(")):
        return None
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        argv = list(lexer)
    except ValueError:
        return None
    if any(token and all(c in "();<>|&" for c in token) for token in argv):
        return None
    if len(argv) < 3:
        return None

    def basename(path: str) -> str:
        return path.replace("\\", "/").rsplit("/", 1)[-1]

    if basename(argv[0]) not in {"node", "node.exe"}:
        return None
    if basename(argv[1]) != "codex-companion.mjs" or argv[2] != "task":
        return None
    values: dict[str, str] = {}
    boolean_options = {"json", "write", "resume-last", "resume", "fresh", "background"}
    value_options = {"model", "effort", "cwd", "prompt-file"}
    index = 3
    while index < len(argv):
        token = argv[index]
        index += 1
        if token == "--":
            break
        if not token.startswith("-") or token == "-":
            continue
        option, separator, value = token.partition("=")
        # The companion's short-option parser only aliases the exact '-m' token.
        if option == "-m" and separator:
            return None
        name = "model" if option == "-m" else option.removeprefix("--")
        if name in boolean_options:
            continue
        if name not in value_options or name in values:
            return None
        if not separator:
            if index == len(argv):
                return None
            value = argv[index]
            index += 1
        values[name] = value
    if "model" not in values or "effort" not in values:
        return None
    return values["model"], values["effort"]


def _analyze_codex(hook_records: list[dict], subagents: list[dict]) -> Report:
    """Did Jev's model and effort reach the Codex plugin's companion command?"""
    records = [r for r in hook_records if r.get("kind") == "codex-rescue"]
    if not records:
        return Report(
            "partial", "codex-rescue was not launched, so the codex path is unconfirmed"
        )
    want_model, want_effort = records[-1]["model"], records[-1]["effort"]
    commands = [
        command
        for sub in subagents
        if str(sub.get("agentType", "")).endswith("codex-rescue")
        for command in sub.get("commands", [])
        if "codex-companion" in command
    ]
    evidence = [f"codex-rescue: Jev chose {want_model} / {want_effort}"]
    if any(_companion_choice(c) == (want_model, want_effort) for c in commands):
        return Report("pass", "the codex flags reached codex-companion", evidence)
    return Report(
        "fail",
        f"codex-companion did not receive --model {want_model} --effort {want_effort}: "
        "the codex-rescue wrapper dropped them or updatedInput was ignored",
        evidence,
    )


def analyze(
    stream_lines: list[str],
    hook_records: list[dict],
    subagents: list[dict],
    debug_log: str,
    expect_codex: bool = False,
) -> Report:
    """Worse of the worker verdict and (when the run included one) the codex verdict."""
    worker_records = [r for r in hook_records if "kind" not in r]
    report = _analyze_worker(stream_lines, worker_records, subagents, debug_log)
    if not expect_codex or report.status == "blocked":
        return report
    codex = _analyze_codex(hook_records, subagents)
    worse = max((report, codex), key=lambda r: SEVERITY[r.status])
    if report.status == codex.status == "pass":
        worse = Report("pass", f"{report.reason}; {codex.reason}")
    return Report(worse.status, worse.reason, [*report.evidence, *codex.evidence])


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
        efforts, commands = [], []
        for line in transcript.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("type") != "assistant":
                continue
            if row.get("effort"):
                efforts.append(row["effort"])
            content = row.get("message", {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("name") == "Bash":
                    commands.append(str(block.get("input", {}).get("command", "")))
        found.append(
            {
                "agentType": meta.get("agentType", ""),
                "name": meta.get("name"),
                "efforts": efforts,
                "commands": commands,
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
        run = subprocess.run(
            command, env=env, capture_output=True, text=True, timeout=600, check=False
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
        lines,
        records,
        collect_subagents(config, _session_id(lines)),
        debug,
        expect_codex=True,
    )
    print(f"{report.status.upper()}: {report.reason}")
    for line in report.evidence:
        print(f"  {line}")
    return EXIT[report.status]


if __name__ == "__main__":
    raise SystemExit(main())
