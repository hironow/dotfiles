#!/usr/bin/env python3
"""Live check that j-cc's session and its workers reach the model through headroom.

Starts a dedicated proxy on a free port that logs each request's messages, runs
one print-mode session with j-cc's environment and worker hook, and asks it to
launch one plain worker. The verdict comes from the proxy's own log (the main
session's first user message carries MAIN, the worker's carries WORKER) and the
hook's record of the worker rewrite, never from model text. The log holds
message content, so it lives in a temp dir removed afterwards.

The `codex` target runs the real Codex worker runner (jev_codex_exec.py) against
the same kind of dedicated proxy, handed to it through JEV_HEADROOM_STATE_DIR,
and needs a proxied request carrying CODEX plus the runner's final message.

The `rtk` target checks that both layers work in one j-cc session: it runs a
session with j-cc's environment through the same kind of proxy, in an empty
temp dir, and asks it to run `ls -la` once with Bash. It needs a proxied request
carrying RTK and rtk's own count of commands in that dir (`rtk gain -p`), which
only the Claude rtk hook can have raised. It needs no Jev key.

Usage: jev_headroom_verify.py [claude|codex|rtk ...]  (default: all)
Exit 0 = pass, 1 = fail, 2 = blocked (no key, no headroom, usage limit, no
login, or the model launched no worker; nothing learned).
"""

import contextlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator, Sequence
from pathlib import Path

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
    write_state,
)
from jev_launch import hook_command, jev_key

EXIT = {"pass": 0, "fail": 1, "blocked": 2}
SEVERITY = {"pass": 0, "blocked": 1, "fail": 2}
TARGETS = ("claude", "codex", "rtk")
MAIN = "JEV-HEADROOM-MAIN"
WORKER = "JEV-HEADROOM-WORKER"
PROMPT = (
    f"{MAIN} This is a routing check. Use the Agent tool exactly once with "
    f"subagent_type general-purpose and the prompt '{WORKER} Reply with the single "
    "word OK.' Do nothing else. After the worker returns, reply DONE."
)
CODEX = "JEV-HEADROOM-CODEX"
RTK = "JEV-HEADROOM-RTK"
RTK_PROMPT = (
    f"{RTK} This is a routing check. Run the shell command `ls -la` exactly once "
    "with the Bash tool, then reply DONE. Do nothing else."
)
CODEX_PROMPT = f"{CODEX} Reply with the single word OK."
_CODEX_LIMIT = re.compile(r"usage limit|rate limit|\b429\b", re.IGNORECASE)


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


def proxied_rows(log: Path) -> list[dict]:
    """Every request row the proxy logged (JSONL, --log-file)."""
    try:
        lines = log.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def proxied_requests(log: Path) -> list[list]:
    """The messages of every request the proxy logged with --log-messages."""
    return [
        row["request_messages"]
        for row in proxied_rows(log)
        if isinstance(row.get("request_messages"), list)
    ]


def _is_codex(row: dict) -> bool:
    # headroom logs a Codex (Responses API) request without its messages but
    # tags its client; the dedicated proxy serves only the runner under test
    tags = row.get("tags")
    messages = row.get("request_messages")
    return (isinstance(tags, dict) and tags.get("client") == "codex") or (
        isinstance(messages, list) and CODEX in first_user_text(messages)
    )


def _launched_agent(stream_lines: list[str]) -> bool:
    return _used_tool(stream_lines, {"Agent", "Task"})


def _used_tool(stream_lines: list[str], names: set[str]) -> bool:
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
                and block.get("name") in names
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
        return Report(
            "blocked",
            "Claude Code is not logged in or its login expired (run claude, then /login)",
        )
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


def analyze_codex(
    returncode: int, final: str, stderr: str, port: int, rows: list[dict]
) -> Report:
    """Functional core for the Codex worker: runner result plus the proxy log."""
    if returncode != 0 and _CODEX_LIMIT.search(stderr):
        return Report("blocked", "a Codex usage limit stopped the check")
    hits = sum(_is_codex(row) for row in rows)
    evidence = [f"proxied requests: {len(rows)} (Codex worker {hits})"]
    if returncode != 0 or not final.strip():
        return Report(
            "fail",
            f"the Codex runner failed (exit {returncode}) or wrote no final message",
            evidence,
        )
    if f"127.0.0.1:{port}" not in stderr:
        return Report("fail", "the runner did not reuse the dedicated proxy", evidence)
    if hits == 0:
        return Report(
            "fail", "the Codex worker's requests did not go through the proxy", evidence
        )
    return Report("pass", "the Codex worker went through headroom", evidence)


def rtk_commands(out: str | None) -> int | None:
    """rtk's count of commands in one dir, from `rtk gain -p --format json`."""
    try:
        summary = json.loads(out or "").get("summary")
    except (ValueError, AttributeError):
        return None
    count = summary.get("total_commands") if isinstance(summary, dict) else None
    return count if isinstance(count, int) else None


def analyze_rtk(
    stream_lines: list[str], proxied: list[list], rtk_commands: int | None
) -> Report:
    """Functional core: one j-cc session through headroom, its Bash through rtk."""
    if has_provider_limit(stream_lines):
        return Report("blocked", "a Claude usage limit stopped the check")
    if is_logged_out(stream_lines):
        return Report(
            "blocked",
            "Claude Code is not logged in or its login expired (run claude, then /login)",
        )
    session = sum(RTK in first_user_text(messages) for messages in proxied)
    evidence = [
        f"proxied requests: {len(proxied)} (session {session})",
        f"rtk commands in the session's dir: {rtk_commands}",
    ]
    if not _used_tool(stream_lines, {"Bash"}):
        return Report("blocked", "the model ran no Bash command; rerun", evidence)
    if rtk_commands is None:
        return Report("blocked", "rtk's count could not be read", evidence)
    if session == 0:
        return Report("fail", "no request of the session reached the proxy", evidence)
    if rtk_commands == 0:
        return Report("fail", "the Bash command did not go through rtk", evidence)
    return Report(
        "pass", "the session went through headroom and its Bash through rtk", evidence
    )


def targets(argv: Sequence[str]) -> list[str]:
    chosen = list(argv) or list(TARGETS)
    unknown = [target for target in chosen if target not in TARGETS]
    if unknown:
        raise SystemExit(f"usage: jev_headroom_verify.py [{'|'.join(TARGETS)} ...]")
    return chosen


@contextlib.contextmanager
def _dedicated_proxy(exe: str) -> Iterator[tuple[bool, int, Path, Path]]:
    """A proxy that logs request messages to a temp dir, removed afterwards."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_name:
        tmp = Path(tmp_name)
        log, port = tmp / "requests.jsonl", free_port()
        command = [*proxy_command(exe, port), "--log-file", str(log), "--log-messages"]
        proxy = start(command, proxy_env(os.environ), tmp / "proxy.out")
        try:
            yield wait_ready(port, probe, 90.0), port, log, tmp
        finally:
            proxy.terminate()
            time.sleep(1)  # let Windows release the log before the dir goes


def _run_claude(exe: str, key: str) -> Report:
    with _dedicated_proxy(exe) as (ready, port, log, tmp):
        if not ready:
            return Report("fail", f"the headroom proxy did not get ready on {port}")
        hook_log = tmp / "hook.log"
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


def _run_codex(exe: str) -> Report:
    with _dedicated_proxy(exe) as (ready, port, log, tmp):
        if not ready:
            return Report("fail", f"the headroom proxy did not get ready on {port}")
        # Hand the runner this proxy the way a real launch finds one: the state
        write_state(tmp / "headroom.json", port)
        env = {**os.environ, "JEV_HEADROOM_STATE_DIR": str(tmp)}
        env.pop("JEV_HEADROOM", None)
        run = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("jev_codex_exec.py"))],
            input=CODEX_PROMPT,
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        return analyze_codex(
            run.returncode, run.stdout, run.stderr, port, proxied_rows(log)
        )


def _rtk_exe() -> str | None:
    if found := shutil.which("rtk"):
        return found
    mise = shutil.which("mise")
    if not mise:
        return None
    done = subprocess.run(
        [mise, "which", "rtk"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return done.stdout.strip() or None if done.returncode == 0 else None


def _run_rtk(exe: str) -> Report:
    rtk = _rtk_exe()
    if not rtk:
        return Report("blocked", "rtk not found (mise installs rtk)")
    with _dedicated_proxy(exe) as (ready, port, log, tmp):
        if not ready:
            return Report("fail", f"the headroom proxy did not get ready on {port}")
        work = tmp / "work"  # empty: rtk counts only what this session ran
        work.mkdir()
        env = claude_env(build_env(os.environ, "claude", None, False), port)
        claude = [
            shutil.which("claude") or "claude",
            "-p",
            RTK_PROMPT,
            "--model",
            SONNET,
            "--effort",
            "medium",
            "--allowedTools",
            "Bash",
            "--output-format",
            "stream-json",
            "--verbose",
        ]
        run = subprocess.run(
            claude,
            cwd=work,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=600,
            check=False,
        )
        counted = subprocess.run(
            [rtk, "gain", "-p", "--format", "json"],
            cwd=work,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return analyze_rtk(
            run.stdout.splitlines(),
            proxied_requests(log),
            rtk_commands(counted.stdout if counted.returncode == 0 else None),
        )


def _report_for(target: str, exe: str | None) -> Report:
    if not exe:
        return Report("blocked", "headroom not found (mise installs pypi:headroom-ai)")
    if target == "codex":
        return _run_codex(exe)
    if target == "rtk":
        return _run_rtk(exe)
    key = jev_key()
    if not key:
        return Report(
            "blocked", "no TYPESAFE_API_KEY: the worker hook rewrites nothing"
        )
    return _run_claude(exe, key)


def main(argv: Sequence[str]) -> int:
    exe = shutil.which("headroom")
    worst = "pass"
    for target in targets(argv):
        report = _report_for(target, exe)
        print(f"{target}: {report.status.upper()}: {report.reason}")
        for line in report.evidence:
            print(f"  {line}")
        worst = max(worst, report.status, key=SEVERITY.__getitem__)
    return EXIT[worst]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
