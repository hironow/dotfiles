#!/usr/bin/env python3
"""Trust the Codex hooks dotfiles syncs, through Codex's own app-server API.

Codex runs a non-managed hook only when `hooks.state.<key>.trusted_hash` in
~/.codex/config.toml equals the hook's current hash (codex-rs hooks/src/engine/
discovery.rs). The TUI's /hooks review records it with two app-server calls,
`hooks/list` and `config/batchWrite` (codex-rs tui/src/hooks_rpc.rs); this does
the same, for exactly the entries sync renders from the one source,
.claude/settings.hooks.json (event, matcher, full command), in <codex
home>/hooks.json, and only while every hook file sync placed there is
byte-identical to its source. While hooks.json holds an agent-hook group, it
also trusts agent-hook's three guards exactly as agent-hook renders them
through the home's stable link (G, PR 3d.2). Nothing else is trusted. It also
reports a project hook in the dotfiles checkout that runs one of those again.

Usage: codex_hooks_trust.py [--check]   (--check reports without writing)
Prints doctor-style OK/WARN lines; exit 1 when a hook would not run.
"""

import contextlib
import json
import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Generator, Iterable, Mapping, Sequence
from pathlib import Path
from threading import Thread
from typing import Protocol

import agent_hook_release as release_tools
from agent_hook_codex_plan import codex_guards
from agent_hook_wiring import Roots
from doctor_lines import Line, failed, fmt
from sync_agents import (
    AgentTarget,
    _is_agent_hook_group,
    _render_hook_command,
    _wants_hook,
    hook_fragment,
)

ROOT = Path(__file__).resolve().parents[1]
NAME = "codex-hooks"
TRUSTABLE = {"untrusted", "modified"}
# How long one app-server request may take. A run makes at most five (75 s),
# plus a render (30 s), inside sync's 120 s for the step
# (sync_agents.CODEX_STEP_TIMEOUT); a server that fails one is killed at once.
REQUEST_TIMEOUT = 15
# The hook an agent-hook command runs, as its render writes it.
HOOK_ID = re.compile(r"--hook ([a-z0-9-]+)")

Hook = tuple[str, str | None, str]  # (eventName, matcher, command) as hooks/list shows
Hooks = dict[str, list[dict]]  # a hooks.json `hooks` value: event to groups
Render = Callable[[Path, str], tuple[Hooks | None, str]]


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
    dotfiles_dir: Path,
    codex_home: Path,
    system: str | None = None,
    binary: Mapping[str, Sequence[dict]] | None = None,
) -> set[Hook]:
    """The hooks to trust: the fragment's scripts as sync renders them, and
    `binary`'s (G, guards_to_trust) as agent-hook rendered them."""
    agent = _codex(codex_home)
    fragment = hook_fragment(dotfiles_dir, agent) or {}
    scripts = {
        (
            _event_key(event),
            block.get("matcher"),
            _render_hook_command(hook["command"], agent, system=system),
        )
        for event, blocks in fragment.get("hooks", {}).items()
        for block in blocks
        for hook in block.get("hooks", [])
    }
    return scripts | {
        (_event_key(event), group.get("matcher"), hook["command"])
        for event, groups in (binary or {}).items()
        for group in groups
        for hook in group.get("hooks", [])
    }


def render_codex(link: Path, system: str) -> tuple[Hooks | None, str]:
    """R: agent-hook's render for Codex through the home's stable link, in
    the sh form sync writes; or None and why not."""
    os_name = {"Darwin": "darwin", "Linux": "linux"}.get(system, system.lower())
    outcome = release_tools.run(
        [
            str(link),
            "render",
            "--harness",
            "codex",
            "--os",
            os_name,
            "--shell",
            "sh",
            "--binary",
            str(link),
        ],
        timeout=release_tools.PROGRAM_TIMEOUT,
    )
    if not outcome.ok:
        return None, str(outcome.reason)
    try:
        hooks = json.loads(outcome.stdout)["hooks"]
    except (ValueError, KeyError, TypeError) as error:
        return None, f"output does not parse: {error}"
    if not isinstance(hooks, dict):
        return None, "output does not parse: hooks is not an object"
    return hooks, ""


def guards_to_trust(
    codex_home: Path,
    env: Mapping[str, str],
    system: str,
    render: Render = render_codex,
) -> tuple[Hooks, Line | None]:
    """G, agent-hook's guards to trust beside the scripts: none while
    hooks.json holds no agent-hook group, else codex_guards of the render
    through the stable link. When there is no render, none, and a WARN line
    that says why."""
    try:
        value = json.loads((codex_home / "hooks.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, None  # Codex reports what it cannot read
    hooks = value.get("hooks") if isinstance(value, dict) else None
    if not isinstance(hooks, dict) or not any(
        _is_agent_hook_group(group, codex=True)
        for groups in hooks.values()
        if isinstance(groups, list)
        for group in groups
    ):
        return {}, None

    def unchecked(why: str) -> tuple[Hooks, Line]:
        detail = f"agent-hook's guards in hooks.json not checked: {why}"
        return {}, ("WARN", NAME, f"{detail}; the scripts still run")

    try:
        link = Roots.from_env(env).link("codex")
    except ValueError as error:
        return unchecked(str(error))
    if not link.is_file():
        return unchecked(f"no {link} (run just sync-agents x)")
    rendered, reason = render(link, system)
    if rendered is None:
        return unchecked(f"render: {reason}")
    return codex_guards(rendered), None


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
        label = f"{event} {matcher} {_name(command)}"
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


def _name(command: str) -> str:
    """What a report calls a command: an agent-hook command by its hook id,
    a script's by the end of its path."""
    hook = HOOK_ID.search(command)
    return hook.group(1) if hook else command.rsplit("/", 1)[-1].rstrip('"')


def _script(command: str) -> str:
    """The hook script a command runs: the last word ending in `.sh`."""
    words = [word.strip("\"'") for word in command.split()]
    scripts = [word.rsplit("/", 1)[-1] for word in words if word.endswith(".sh")]
    return scripts[-1] if scripts else ""


def _runs(command: str) -> tuple[str, str]:
    """What a command repeats when a project registers it too: the script it
    runs, or, for a command that runs none (agent-hook's), the whole command."""
    script = _script(command)
    return ("script", script) if script else ("command", command)


def project_duplicates(entries: Iterable[dict], expected: set[Hook]) -> list[str]:
    """Project hooks that run a dotfiles hook script again.

    For a trusted project Codex also loads `<project>/.codex/hooks.json`; an
    entry there that runs one of our scripts on the same event and matcher
    makes that hook run twice inside the project.
    """
    ours = {(event, matcher, _runs(command)) for event, matcher, command in expected}
    found = []
    for entry in entries:
        if entry.get("source") != "project":
            continue
        event, matcher, command = _ident(entry)
        if (event, matcher, _runs(command)) in ours:
            name = _script(command) or _name(command)
            found.append(
                f"{event} {matcher} {name}: also registered by "
                f"{entry.get('sourcePath')}, so it runs twice there (delete that file)"
            )
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
    """JSON-RPC over a `codex app-server`'s stdio (one JSON message per line).

    A thread reads the server's lines into a queue, so a request waits at
    most `timeout` seconds for its answer, and raises RuntimeError when none
    comes or the server closes first.
    """

    def __init__(
        self, writer: Writer, reader: Iterable[str], timeout: float = REQUEST_TIMEOUT
    ) -> None:
        self._writer, self._next, self._timeout = writer, 1, timeout
        self._lines: queue.Queue[str | None] = queue.Queue()
        # A daemon: a server that never closes must not keep this process.
        Thread(target=self._read, args=(reader,), daemon=True).start()
        self.request(
            "initialize",
            {"clientInfo": {"name": "dotfiles-codex-hooks-trust", "version": "1"}},
        )
        self._send({"method": "initialized"})

    def _send(self, message: dict) -> None:
        self._writer.write(json.dumps(message) + "\n")
        self._writer.flush()

    def _read(self, reader: Iterable[str]) -> None:
        try:
            for line in reader:
                self._lines.put(line)
        except (OSError, ValueError):
            pass  # a closed pipe ends the output as EOF does
        self._lines.put(None)

    def request(self, method: str, params: dict) -> dict:
        request_id, self._next = self._next, self._next + 1
        self._send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                line = self._lines.get(timeout=max(0, deadline - time.monotonic()))
            except queue.Empty:
                raise RuntimeError(
                    f"{method}: no answer within {self._timeout:g} s"
                ) from None
            if line is None:
                self._lines.put(None)  # later requests see the end too
                raise RuntimeError(f"{method}: closed without answering")
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result") or {}


@contextlib.contextmanager
def app_server(codex: str) -> Generator[AppServerClient]:
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
        yield AppServerClient(proc.stdin, proc.stdout, timeout=REQUEST_TIMEOUT)
    except BaseException:
        proc.kill()  # a server that failed a request is not waited for
        raise
    finally:
        with contextlib.suppress(OSError):
            proc.stdin.close()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        # the reader thread ends at EOF, or on the closed file (AppServerClient._read)
        with contextlib.suppress(OSError, ValueError):
            proc.stdout.close()


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
    binary, warning = guards_to_trust(codex_home, os.environ, platform.system())
    expected = expected_hooks(ROOT, codex_home, binary=binary)
    try:
        with app_server(codex) as client:
            entries = list_hooks(client, Path.home())
            chosen = [] if check else select(entries, expected, codex_home)
            if chosen:
                client.request("config/batchWrite", batch_write_params(chosen))
                entries = list_hooks(client, Path.home())
            found = problems(entries, expected, codex_home)
            # The dotfiles checkout is a trusted Codex project: anything it
            # ships as project hooks would run on top of the global ones there.
            found += project_duplicates(list_hooks(client, ROOT), expected)
    except (RuntimeError, OSError) as error:  # no answer, or a closed pipe
        print(fmt(("WARN", NAME, f"codex app-server: {error}")))
        return 1
    lines = [warning] if warning else []
    lines += trust_lines(len(chosen), found, len(expected))
    for line in lines:
        print(fmt(line))
    return 1 if failed(lines) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
