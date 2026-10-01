#!/usr/bin/env python3
"""Live check that j-cc's session and its workers reach the model through headroom.

Starts a dedicated proxy on a free port that logs each request's messages, runs
one print-mode session with j-cc's environment and worker hook, and asks it to
launch one plain worker. The verdict comes from the proxy's own log (the main
session's first user message carries MAIN, the worker's carries WORKER) and the
hook's record of the worker rewrite, never from model text. The log holds
message content, so it lives in a temp dir removed afterwards.

Exit 0 = pass, 1 = fail, 2 = blocked (no key, no headroom, usage limit, no
login, or the model launched no worker; nothing learned).
"""

from collections.abc import Sequence
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

from jev_claude_verify import Report, has_provider_limit, is_logged_out
from jev_core import SONNET, build_env, claude_session_args
from jev_headroom import (
    claude_env,
    free_port,
    probe,
    proxy_command,
    proxy_env,
    start,
    wait_ready,
)
from jev_launch import hook_command, jev_key

EXIT = {"pass": 0, "fail": 1, "blocked": 2}
MAIN = "JEV-HEADROOM-MAIN"
WORKER = "JEV-HEADROOM-WORKER"
PROMPT = (
    f"{MAIN} This is a routing check. Use the Agent tool exactly once with "
    f"subagent_type general-purpose and the prompt '{WORKER} Reply with the single "
    "word OK.' Do nothing else. After the worker returns, reply DONE."
)


def first_user_text(messages: Sequence[object]) -> str:
    for message in messages:
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    str(block.get("text", ""))
                    for block in content
                    if isinstance(block, dict)
                )
            return ""
    return ""


def proxied_requests(log: Path) -> list[list]:
    """The messages of every request the proxy logged (JSONL, --log-messages)."""
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    requests = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict) and isinstance(row.get("request_messages"), list):
            requests.append(row["request_messages"])
    return requests


def _launched_agent(stream_lines: list[str]) -> bool:
    for line in stream_lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") in {"Agent", "Task"}
            ):
                return True
    return False


def analyze(
    stream_lines: list[str], hook_records: list[dict], proxied: list[list]
) -> Report:
    """Functional core: the verdict from the session stream, hook log and proxy log."""
    if has_provider_limit(stream_lines):
        return Report("blocked", "a Claude usage limit stopped the check")
    if is_logged_out(stream_lines):
        return Report("blocked", "Claude Code is not logged in")
    texts = [first_user_text(messages) for messages in proxied]
    main = sum(MAIN in text for text in texts)
    worker = sum(WORKER in text and MAIN not in text for text in texts)
    rewrites = [record for record in hook_records if "kind" not in record]
    evidence = [f"proxied requests: {len(texts)} (session {main}, worker {worker})"]
    evidence += [
        f"hook: {r.get('from')} -> {r.get('to')} ({r.get('effort')})" for r in rewrites
    ]
    if not rewrites and not _launched_agent(stream_lines):
        return Report("blocked", "the model launched no worker; rerun", evidence)
    if main == 0:
        return Report("fail", "no request of the session reached the proxy", evidence)
    if not rewrites:
        return Report(
            "fail", "the worker hook recorded no rewrite for the launch", evidence
        )
    if worker == 0:
        return Report(
            "fail", "the worker's requests did not go through the proxy", evidence
        )
    return Report(
        "pass", "the session and its worker both went through headroom", evidence
    )


def _run(exe: str, key: str) -> Report:
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        log, hook_log = Path(tmp) / "requests.jsonl", Path(tmp) / "hook.log"
        port = free_port()
        command = [*proxy_command(exe, port), "--log-file", str(log), "--log-messages"]
        proxy = start(command, proxy_env(os.environ), Path(tmp) / "proxy.out")
        try:
            if not wait_ready(port, probe, 90.0):
                return Report("fail", f"the headroom proxy did not get ready on {port}")
            env = claude_env(
                {
                    **build_env(os.environ, "claude", key, False),
                    "JEV_HOOK_LOG": str(hook_log),
                },
                port,
            )
            claude = [
                shutil.which("claude") or "claude",
                "-p",
                PROMPT,
                "--model",
                SONNET,
                "--effort",
                "medium",
                *claude_session_args(hook_command()),
                "--output-format",
                "stream-json",
                "--verbose",
            ]
            # Claude Code writes UTF-8; the locale default (cp932) cannot decode it
            run = subprocess.run(
                claude,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                check=False,
            )
            records = (
                [
                    json.loads(line)
                    for line in hook_log.read_text(encoding="utf-8").splitlines()
                ]
                if hook_log.exists()
                else []
            )
            return analyze(run.stdout.splitlines(), records, proxied_requests(log))
        finally:
            proxy.terminate()
            time.sleep(1)  # let Windows release the log before the dir goes


def main() -> int:
    key = jev_key()
    exe = shutil.which("headroom")
    if not key:
        report = Report(
            "blocked", "no TYPESAFE_API_KEY: the worker hook rewrites nothing"
        )
    elif not exe:
        report = Report(
            "blocked", "headroom not found (mise installs pypi:headroom-ai)"
        )
    else:
        report = _run(exe, key)
    print(f"{report.status.upper()}: {report.reason}")
    for line in report.evidence:
        print(f"  {line}")
    return EXIT[report.status]


if __name__ == "__main__":
    raise SystemExit(main())
