#!/usr/bin/env python3
"""Trust the Codex hooks dotfiles syncs, through Codex's own app-server API.

Codex runs a non-managed hook only when `hooks.state.<key>.trusted_hash` in
~/.codex/config.toml equals the hook's current hash (codex-rs hooks/src/engine/
discovery.rs). The TUI's /hooks review records it with two app-server calls,
`hooks/list` and `config/batchWrite` (codex-rs tui/src/hooks_rpc.rs); this does
the same, for exactly the entries the repo's .codex/hooks.json renders (event,
matcher, full command) in <codex home>/hooks.json, and only while every hook file
sync placed there is byte-identical to its source. Nothing else is trusted.

Usage: codex_hooks_trust.py [--check]   (--check reports without writing)
Prints doctor-style OK/WARN lines; exit 1 when a hook would not run.
"""

import contextlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path
from typing import Protocol

from doctor_lines import Line, failed, fmt
from sync_agents import (
    CODEX_HOOK_FRAGMENT,
    AgentTarget,
    _render_hook_command,
    _wants_hook,
)

ROOT = Path(__file__).resolve().parents[1]
NAME = "codex-hooks"
TRUSTABLE = {"untrusted", "modified"}

Hook = tuple[str, str | None, str]  # (eventName, matcher, command) as hooks/list shows


class Writer(Protocol):
    def write(self, text: str, /) -> object: ...
    def flush(self) -> None: ...


def _codex(home: Path) -> AgentTarget:
    return AgentTarget(
        directory=home, name="Codex", key="codex", receives_codex_hooks=True
    )


def _event_key(event: str) -> str:
    """The fragment's `PreToolUse` as hooks/list names it: `preToolUse`."""
    return event[:1].lower() + event[1:]


def expected_hooks(
    dotfiles_dir: Path, codex_home: Path, system: str | None = None
) -> set[Hook]:
    fragment = json.loads(
        (dotfiles_dir / CODEX_HOOK_FRAGMENT).read_text(encoding="utf-8")
    )
    agent = _codex(codex_home)
    return {
        (
            _event_key(event),
            block.get("matcher"),
            _render_hook_command(hook["command"], agent, system=system),
        )
        for event, blocks in fragment.get("hooks", {}).items()
        for block in blocks
        for hook in block.get("hooks", [])
    }


def changed_files(dotfiles_dir: Path, codex_home: Path) -> list[str]:
    """Hook files sync places for Codex that are missing or differ from their source."""
    agent = _codex(codex_home)
    changed = []
    for source in sorted(dotfiles_dir.glob("ROOT_AGENTS_hooks_*")):
        name = source.name.removeprefix("ROOT_AGENTS_hooks_")
        if not _wants_hook(agent, f"hooks/{name}"):
            continue
        placed = codex_home / "hooks" / name
        if not placed.is_file() or placed.read_bytes() != source.read_bytes():
            changed.append(name)
    return changed


def _same_path(a: str, b: Path) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(
        os.path.normpath(str(b))
    )


def _ours(entry: dict, codex_home: Path) -> bool:
    return (
        entry.get("source") == "user"
        and not entry.get("isManaged")
        and _same_path(str(entry.get("sourcePath", "")), codex_home / "hooks.json")
    )


def _ident(entry: dict) -> Hook:
    return (
        str(entry.get("eventName")),
        entry.get("matcher"),
        str(entry.get("command")),
    )


def select(
    entries: Iterable[dict], expected: set[Hook], codex_home: Path
) -> list[dict]:
    """The entries to trust: exactly a rendered fragment hook, in our hooks.json."""
    return [
        entry
        for entry in entries
        if _ours(entry, codex_home)
        and _ident(entry) in expected
        and entry.get("trustStatus") in TRUSTABLE
    ]


def problems(
    entries: Sequence[dict], expected: set[Hook], codex_home: Path
) -> list[str]:
    """Why an expected hook would not run (empty when all of them would)."""
    found = []
    for event, matcher, command in sorted(
        expected, key=lambda hook: (hook[0], hook[2])
    ):
        name = command.rsplit("/", 1)[-1].rstrip('"')
        label = f"{event} {matcher} {name}"
        matches = [
            e
            for e in entries
            if _ours(e, codex_home) and _ident(e) == (event, matcher, command)
        ]
        if not matches:
            found.append(f"{label}: missing from hooks.json (run just sync-agents x)")
            continue
        entry = matches[0]
        if entry.get("trustStatus") != "trusted":
            found.append(f"{label}: not trusted (run just codex-hooks-trust)")
        elif entry.get("enabled") is False:
            found.append(f"{label}: disabled in Codex (enable it in Codex's /hooks)")
        elif entry.get("async"):
            found.append(f"{label}: async, so it can neither block nor rewrite")
    return found


def batch_write_params(entries: Iterable[dict]) -> dict:
    return {
        "edits": [
            {
                "keyPath": "hooks.state",
                "value": {
                    entry["key"]: {"trusted_hash": entry["currentHash"]}
                    for entry in entries
                },
                "mergeStrategy": "upsert",
            }
        ],
        "reloadUserConfig": True,
    }


class AppServerClient:
    """JSON-RPC over a `codex app-server`'s stdio (one JSON message per line)."""

    def __init__(self, writer: Writer, reader: Iterable[str]) -> None:
        self._writer, self._reader, self._next = writer, reader, 1
        self.request(
            "initialize",
            {"clientInfo": {"name": "dotfiles-codex-hooks-trust", "version": "1"}},
        )
        self._send({"method": "initialized"})

    def _send(self, message: dict) -> None:
        self._writer.write(json.dumps(message) + "\n")
        self._writer.flush()

    def request(self, method: str, params: dict) -> dict:
        request_id, self._next = self._next, self._next + 1
        self._send({"id": request_id, "method": method, "params": params})
        for line in self._reader:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result") or {}
        raise RuntimeError(f"{method}: codex app-server closed without answering")


@contextlib.contextmanager
def app_server(codex: str) -> Iterator[AppServerClient]:
    proc = subprocess.Popen(
        [codex, "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.stdin is not None and proc.stdout is not None
    try:
        yield AppServerClient(proc.stdin, proc.stdout)
    finally:
        proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def list_hooks(client: AppServerClient, cwd: Path) -> list[dict]:
    result = client.request("hooks/list", {"cwds": [str(cwd)]})
    return [hook for item in result.get("data", []) for hook in item.get("hooks", [])]


def trust_lines(trusted: int, found: Sequence[str], expected: int) -> list[Line]:
    """The doctor lines for one trust run: what it trusted, then what is wrong."""
    lines: list[Line] = []
    if trusted:
        lines.append(
            (
                "OK",
                NAME,
                f"trusted {trusted} dotfiles hook(s) through codex app-server",
            )
        )
    lines += [("WARN", NAME, problem) for problem in found]
    if not found:
        lines.append(("OK", NAME, f"{expected} dotfiles hooks trusted and enabled"))
    return lines


def main(argv: Sequence[str]) -> int:
    check = "--check" in argv
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    codex = shutil.which("codex")
    if not codex:
        print(fmt(("OK", NAME, "codex not on PATH; nothing to trust")))
        return 0
    if not (codex_home / "hooks.json").is_file():
        print(fmt(("WARN", NAME, "no ~/.codex/hooks.json: run just sync-agents x")))
        return 1
    changed = changed_files(ROOT, codex_home)
    if changed:
        detail = (
            f"hook files differ from the repo ({', '.join(changed)}): "
            "run just sync-agents x"
        )
        print(fmt(("WARN", NAME, detail)))
        return 1
    expected = expected_hooks(ROOT, codex_home)
    with app_server(codex) as client:
        entries = list_hooks(client, Path.home())
        chosen = [] if check else select(entries, expected, codex_home)
        if chosen:
            client.request("config/batchWrite", batch_write_params(chosen))
            entries = list_hooks(client, Path.home())
        found = problems(entries, expected, codex_home)
    lines = trust_lines(len(chosen), found, len(expected))
    for line in lines:
        print(fmt(line))
    return 1 if failed(lines) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
