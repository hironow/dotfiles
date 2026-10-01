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


SEVERITY = {"fail": 3, "blocked": 2, "partial": 1, "pass": 0}


def _companion_arguments(command: str) -> dict[str, str] | None:
    """Recognized flags in a simple node companion task invocation.

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
    return values


def _companion_choice(command: str) -> tuple[str, str] | None:
    values = _companion_arguments(command)
    if values is None or "model" not in values or "effort" not in values:
        return None
    return values["model"], values["effort"]


def _tool_result_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    return ""


def codex_agent_missing(stream_lines: list[str]) -> bool:
    """Claude Code answered the codex-rescue call itself with "not found": the
    Codex plugin is not installed here, so the codex path cannot be checked."""
    calls: set[str] = set()
    for line in stream_lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            tool_input = block.get("input")
            if (
                block.get("type") == "tool_use"
                and block.get("name") in {"Agent", "Task"}
                and isinstance(tool_input, dict)
                and str(tool_input.get("subagent_type", "")).endswith("codex-rescue")
            ):
                calls.add(str(block.get("id")))
            elif (
                block.get("type") == "tool_result"
                and block.get("tool_use_id") in calls
                and block.get("is_error") is True
                and re.search(
                    r"Agent type\b.*\bnot found",
                    _tool_result_text(block.get("content")),
                    re.IGNORECASE,
                )
            ):
                return True
    return False


def _analyze_codex(
    hook_records: list[dict],
    subagents: list[dict],
    blocked: bool = False,
    plugin_missing: bool = False,
) -> Report:
    """Did Jev's model and effort reach the Codex plugin's companion command?"""
    if plugin_missing:
        return Report(
            "blocked",
            "the Codex plugin (codex:codex-rescue) is not installed in Claude Code, "
            "so the codex path cannot be checked here",
        )
    records = [r for r in hook_records if r.get("kind") == "codex-rescue"]
    if not records:
        return Report(
            "blocked" if blocked else "partial",
            "codex-rescue was not launched, so the codex path is unconfirmed",
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
    arguments = [_companion_arguments(command) for command in commands]
    if any(
        values is not None
        and (values.get("model"), values.get("effort")) == (want_model, want_effort)
        for values in arguments
    ):
        return Report("pass", "the codex flags reached codex-companion", evidence)
    if blocked and not any(values is not None for values in arguments):
        return Report(
            "blocked",
            "Claude stopped before the codex invocation could be verified",
            evidence,
        )
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
    worker_subagents = (
        [
            s
            for s in subagents
            if not str(s.get("agentType", "")).endswith("codex-rescue")
        ]
        if expect_codex
        else subagents
    )
    report = _analyze_worker(stream_lines, worker_records, worker_subagents, debug_log)
    if not expect_codex:
        return report
    codex = _analyze_codex(
        hook_records,
        subagents,
        blocked=has_provider_limit(stream_lines) or report.status == "blocked",
        plugin_missing=codex_agent_missing(stream_lines),
    )
    worse = max((report, codex), key=lambda r: SEVERITY[r.status])
    if report.status == "pass":
        # Say what the workers proved even when the codex half falls short
        worse = Report(worse.status, f"{report.reason}; {codex.reason}")
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
