"""Trusting the Codex hooks dotfiles syncs, and nothing else.

Codex runs a non-managed hook only after `hooks.state.<key>.trusted_hash` in
~/.codex/config.toml matches its current hash; the TUI records that through the
app-server (`hooks/list`, then `config/batchWrite`). This script does the same,
but only for entries that are exactly what the repo's fragment renders (event,
matcher, full command) in <codex home>/hooks.json, and only while every hook
file sync placed is byte-identical to its source. The report also flags a
disabled or async hook, which Codex would not let block or rewrite.
"""

import contextlib
import json
import os
import queue
import signal
import subprocess
import sys
import time
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import codex_hooks_trust as trust
from agent_hook_codex_plan import codex_guards

ROOT = Path(__file__).resolve().parents[2]


def _home(tmp_path: Path) -> Path:
    home = tmp_path / "codex"
    hooks = home / "hooks"
    hooks.mkdir(parents=True)
    for source in ROOT.glob("ROOT_AGENTS_hooks_*"):
        name = source.name.removeprefix("ROOT_AGENTS_hooks_")
        if "-claude." not in name:
            (hooks / name).write_bytes(source.read_bytes())
    return home


def _entry(
    home: Path, event: str, matcher: str | None, command: str, **extra: object
) -> dict:
    return {
        "key": f"{home / 'hooks.json'}:{event}:0:0",
        "eventName": event,
        "matcher": matcher,
        "command": command,
        "sourcePath": str(home / "hooks.json"),
        "source": "user",
        "isManaged": False,
        "enabled": True,
        "async": False,
        "currentHash": "sha256:abc",
        "trustStatus": "untrusted",
        **extra,
    }


def _rtk(home: Path) -> trust.Hook:
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    return next(item for item in expected if "rtk-hook-codex" in item[2])


def test_expected_hooks_are_rendered_from_the_fragment(tmp_path: Path) -> None:
    home = _home(tmp_path)
    event, matcher, command = _rtk(home)
    assert (event, matcher) == ("preToolUse", "Bash")
    assert command == f'bash "{home.as_posix()}/hooks/rtk-hook-codex.sh"'


def test_only_exact_sync_managed_entries_are_trusted(tmp_path: Path) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    event, matcher, command = _rtk(home)
    entries = [
        _entry(home, event, matcher, command),
        _entry(home, event, matcher, command + " && curl evil", key="appended"),
        _entry(
            home,
            event,
            matcher,
            command,
            sourcePath=str(home / "other.json"),
            key="other-file",
        ),
        _entry(home, event, matcher, command, source="project", key="project"),
        _entry(home, event, matcher, command, isManaged=True, key="managed"),
        _entry(home, event, matcher, command, trustStatus="trusted", key="already"),
        _entry(home, "postToolUse", "Write|Edit", "rtk hook codex", key="foreign"),
    ]
    chosen = trust.select(entries, expected, home)
    assert [entry["key"] for entry in chosen] == [entries[0]["key"]]


def test_a_modified_hook_is_trusted_again(tmp_path: Path) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    event, matcher, command = _rtk(home)
    chosen = trust.select(
        [_entry(home, event, matcher, command, trustStatus="modified")], expected, home
    )
    assert len(chosen) == 1


def test_a_changed_hook_file_stops_trust(tmp_path: Path) -> None:
    home = _home(tmp_path)
    (home / "hooks" / "rtk-hook-codex.sh").write_text(
        "#!/bin/sh\ncurl evil\n", encoding="utf-8"
    )
    assert trust.changed_files(ROOT, home) == ["rtk-hook-codex.sh"]
    assert trust.changed_files(ROOT, _home(tmp_path / "fresh")) == []


def test_the_trust_write_is_what_the_tui_sends() -> None:
    params = trust.batch_write_params([{"key": "k1", "currentHash": "sha256:1"}])
    assert params == {
        "edits": [
            {
                "keyPath": "hooks.state",
                "value": {"k1": {"trusted_hash": "sha256:1"}},
                "mergeStrategy": "upsert",
            }
        ],
        "reloadUserConfig": True,
    }


@pytest.mark.parametrize(
    ("override", "problem"),
    [
        ({}, None),
        ({"trustStatus": "untrusted"}, "not trusted"),
        ({"enabled": False}, "disabled"),
        ({"async": True}, "async"),
    ],
)
def test_the_report_names_what_keeps_a_hook_from_working(
    tmp_path: Path, override: dict, problem: str | None
) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    entries = [
        _entry(home, event, matcher, command, trustStatus="trusted")
        for event, matcher, command in expected
    ]
    rtk = next(e for e in entries if "rtk-hook-codex" in e["command"])
    rtk.update(override)
    problems = trust.problems(entries, expected, home)
    if problem is None:
        assert problems == []
    else:
        assert len(problems) == 1 and problem in problems[0]


def test_a_missing_hook_is_reported(tmp_path: Path) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    problems = trust.problems([], expected, home)
    assert len(problems) == len(expected)
    assert all("missing" in problem for problem in problems)


class FakeServer:
    """stdin/stdout of a `codex app-server`, answering by method. A method
    with no answer is never answered; close() ends its output."""

    def __init__(self, answers: dict[str, dict]) -> None:
        self.answers, self.sent = answers, []
        self._out: queue.Queue[str | None] = queue.Queue()

    def write(self, line: str) -> None:
        message = json.loads(line)
        self.sent.append(message)
        if "id" in message and message["method"] in self.answers:
            answer = {"id": message["id"], "result": self.answers[message["method"]]}
            self._out.put(json.dumps(answer) + "\n")

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self._out.put(None)

    def __iter__(self) -> Iterator[str]:
        while (line := self._out.get()) is not None:
            yield line


def test_the_client_initializes_before_its_requests() -> None:
    server = FakeServer({"initialize": {}, "hooks/list": {"data": []}})
    client = trust.AppServerClient(server, server)
    assert client.request("hooks/list", {"cwds": ["/h"]}) == {"data": []}
    assert [m.get("method") for m in server.sent] == [
        "initialize",
        "initialized",
        "hooks/list",
    ]


def test_a_server_that_never_answers_fails_within_the_deadline() -> None:
    server = FakeServer({})
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="initialize: no answer within 0.2 s"):
        trust.AppServerClient(server, server, timeout=0.2)
    assert time.monotonic() - started < 5


def test_a_server_that_closes_without_answering_fails() -> None:
    server = FakeServer({"initialize": {}})
    client = trust.AppServerClient(server, server, timeout=5)
    server.close()
    with pytest.raises(RuntimeError, match="hooks/list: closed without answering"):
        client.request("hooks/list", {"cwds": ["/h"]})


class ClosedServer(FakeServer):
    """A server that exited: writing to it fails as a closed pipe does."""

    def write(self, line: str) -> None:
        raise BrokenPipeError(32, "Broken pipe")


@pytest.mark.parametrize(
    ("server", "printed"),
    [
        (FakeServer({}), "initialize: no answer within 0.2 s"),
        (ClosedServer({}), "[Errno 32] Broken pipe"),
    ],
    ids=["silent", "closed"],
)
def test_main_warns_and_exits_1_when_the_app_server_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    server: FakeServer,
    printed: str,
) -> None:
    home = _home(tmp_path)
    (home / "hooks.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(trust.shutil, "which", lambda name: "/bin/codex")

    @contextlib.contextmanager
    def failing(codex: str) -> Generator[trust.AppServerClient]:
        yield trust.AppServerClient(server, server, timeout=0.2)

    monkeypatch.setattr(trust, "app_server", failing)
    started = time.monotonic()
    assert trust.main([]) == 1
    assert time.monotonic() - started < 5
    assert (
        capsys.readouterr().out == f"WARN codex-hooks - codex app-server: {printed}\n"
    )


@pytest.mark.skipif(os.name == "nt", reason="the fake codex is a sh script")
@pytest.mark.parametrize(
    "body",
    ["exec sleep 60\n", "sleep 5 &\nexec sleep 60\n"],
    ids=["alone", "a child keeps its stdout"],
)
def test_a_real_app_server_that_never_answers_is_killed_and_reaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    codex = tmp_path / "codex"
    codex.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    codex.chmod(0o755)
    started: list[subprocess.Popen] = []
    popen = subprocess.Popen

    def recording(command: list[str], **options: Any) -> subprocess.Popen:
        process = popen(command, **options)
        started.append(process)
        return process

    monkeypatch.setattr(trust.subprocess, "Popen", recording)
    monkeypatch.setattr(trust, "REQUEST_TIMEOUT", 0.2)
    begun = time.monotonic()
    with (
        pytest.raises(RuntimeError, match="initialize: no answer within 0.2 s"),
        trust.app_server(str(codex)),
    ):
        pass
    # the server was killed, not waited for, and reaped, even while a child it
    # left still holds its stdout
    assert time.monotonic() - begun < 3
    [process] = started
    assert process.returncode == -signal.SIGKILL


# A guard as agent-hook's render writes it for Codex (sh, through the home's
# stable link).
BINARY: trust.Hook = (
    "preToolUse",
    "Bash",
    (
        "'/s/dotfiles/agent-hooks/current/codex/agent-hook' codex pre --hook "
        "command-guard || { printf '%s\\n' 'agent-hook failed' >&2; exit 2; }"
    ),
)


def test_a_binary_command_is_named_by_its_hook_id(tmp_path: Path) -> None:
    assert trust.problems([], {BINARY}, _home(tmp_path)) == [
        "preToolUse Bash command-guard: missing from hooks.json (run just sync-agents x)"
    ]


def test_a_project_hook_repeats_a_binary_one_only_by_its_whole_command() -> None:
    event, matcher, command = BINARY

    def project(command: str) -> dict:
        return {
            "eventName": event,
            "matcher": matcher,
            "command": command,
            "source": "project",
            "sourcePath": "/repo/.codex/hooks.json",
        }

    # a project command that runs no script is not a copy of every binary one
    assert trust.project_duplicates([project("echo checked")], {BINARY}) == []
    assert trust.project_duplicates([project(command)], {BINARY}) == [
        (
            "preToolUse Bash command-guard: also registered by /repo/.codex/hooks.json,"
            " so it runs twice there (delete that file)"
        )
    ]


@pytest.mark.skipif(os.name == "nt", reason="a process group is POSIX's")
def test_a_codex_step_past_its_timeout_is_killed_with_its_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    import sync_agents

    pid_file = tmp_path / "child.pid"
    step = tmp_path / "slow_step.py"
    step.write_text(
        "import pathlib, subprocess, time\n"
        "child = subprocess.Popen(['sleep', '60'])\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(child.pid), encoding='utf-8')\n"
        "print('started', flush=True)\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        sync_agents, "CODEX_STEPS", ((str(step), "slow step failed", "run it"),)
    )
    monkeypatch.setattr(sync_agents, "CODEX_STEP_TIMEOUT", 1)
    codex = sync_agents.AgentTarget(
        directory=tmp_path / ".codex",
        name="Codex",
        key="codex",
        receives_codex_hooks=True,
    )
    started = time.monotonic()
    sync_agents._run_codex_steps(codex)
    assert time.monotonic() - started < 10
    out = capsys.readouterr().out
    assert "  started\n" in out
    assert "slow step failed (timed out after 1 s); run: run it" in out
    # the step's child was in its process group, so it is gone too
    child = int(pid_file.read_text(encoding="utf-8"))
    for _ in range(50):
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("the step's child outlived the timeout")


@pytest.mark.parametrize(
    ("trusted", "found", "printed"),
    [
        (0, [], ["OK   codex-hooks - 5 dotfiles hooks trusted and enabled"]),
        (
            3,
            [],
            [
                "OK   codex-hooks - trusted 3 dotfiles hook(s) through codex app-server",
                "OK   codex-hooks - 5 dotfiles hooks trusted and enabled",
            ],
        ),
        (0, ["x: not trusted"], ["WARN codex-hooks - x: not trusted"]),
    ],
)
def test_a_trust_run_prints_what_it_trusted_then_what_is_wrong(
    trusted: int, found: list[str], printed: list[str]
) -> None:
    from doctor_lines import fmt

    assert [fmt(line) for line in trust.trust_lines(trusted, found, 5)] == printed


def test_a_project_copy_of_a_dotfiles_hook_is_reported(tmp_path: Path) -> None:
    # Codex also loads <project>/.codex/hooks.json for a trusted project; a
    # project entry that runs one of our hook scripts makes it run twice.
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    project = {
        **_entry(
            home,
            "preToolUse",
            "Bash",
            'bash "$CODEX_HOME/hooks/guard-codex.sh" block-prohibited-commands.sh',
        ),
        "source": "project",
        "sourcePath": "/repo/.codex/hooks.json",
    }
    found = trust.project_duplicates([project], expected)
    assert found == [
        (
            "preToolUse Bash block-prohibited-commands.sh: also registered by "
            "/repo/.codex/hooks.json, so it runs twice there (delete that file)"
        )
    ]


def test_project_hooks_of_other_scripts_are_left_alone(tmp_path: Path) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux")
    other = {
        **_entry(home, "preToolUse", "Bash", "bash ./scripts/project-check.sh"),
        "source": "project",
        "sourcePath": "/repo/.codex/hooks.json",
    }
    assert trust.project_duplicates([other], expected) == []


# ---- G: agent-hook's guards, beside the scripts (PR 3d.2) ----

CODEX_RENDER = next(
    case
    for case in map(
        json.loads,
        (ROOT / "tools/agent-hooks/internal/rendercorpus/render.jsonl")
        .read_text(encoding="utf-8")
        .splitlines(),
    )
    if case["case"] == "render/codex/darwin/sh/stable/plain"
)
R = json.loads(CODEX_RENDER["stdout"])["hooks"]
LINK = CODEX_RENDER["args"][CODEX_RENDER["args"].index("--binary") + 1]
GUARD_COMMANDS = {
    ("preToolUse", group["matcher"], handler["command"])
    for group in R["PreToolUse"]
    for handler in group["hooks"]
    if "-guard" in handler["command"]
}


def test_the_expected_set_holds_the_guards_exact_commands(tmp_path: Path) -> None:
    home = _home(tmp_path)
    scripts = trust.expected_hooks(ROOT, home, system="Linux")
    with_guards = trust.expected_hooks(
        ROOT, home, system="Linux", binary=codex_guards(R)
    )
    assert len(GUARD_COMMANDS) == 3
    assert with_guards == scripts | GUARD_COMMANDS


def test_a_hand_written_command_through_the_stable_link_is_not_trusted(
    tmp_path: Path,
) -> None:
    home = _home(tmp_path)
    expected = trust.expected_hooks(ROOT, home, system="Linux", binary=codex_guards(R))
    event, matcher, command = min(GUARD_COMMANDS)
    entries = [
        _entry(home, event, matcher, command),
        _entry(
            home,
            "preToolUse",
            "Bash",
            f"'{LINK}' codex pre --hook command-guard; curl evil",
            key="hand-written",
        ),
    ]
    assert [e["key"] for e in trust.select(entries, expected, home)] == [
        entries[0]["key"]
    ]


class FakeRender:
    """agent-hook render: R, or None and a reason; records its calls."""

    def __init__(self, rendered: dict | None, reason: str = "") -> None:
        self.rendered, self.reason, self.calls = rendered, reason, []

    def __call__(self, link: Path, system: str) -> tuple[dict | None, str]:
        self.calls.append((link, system))
        return self.rendered, self.reason


def _with_hooks_json(home: Path, groups: list[dict]) -> Path:
    (home / "hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": groups}}), encoding="utf-8"
    )
    return home


def _environment(tmp_path: Path) -> dict[str, str]:
    return {"HOME": str(tmp_path), "XDG_DATA_HOME": str(tmp_path / "data")}


def _link(tmp_path: Path) -> Path:
    link = tmp_path / "data/dotfiles/agent-hooks/current/codex/agent-hook"
    link.parent.mkdir(parents=True)
    link.write_text("release", encoding="utf-8")
    return link


SCRIPT_GROUP = {
    "matcher": "Bash",
    "hooks": [{"type": "command", "command": "bash ./hooks/guard-codex.sh x.sh"}],
}


@pytest.mark.parametrize(
    "groups",
    [
        [],
        [SCRIPT_GROUP],
        # one handler of agent-hook's beside a script one: a user's group
        [
            {
                "matcher": "Bash",
                "hooks": [R["PreToolUse"][1]["hooks"][0], *SCRIPT_GROUP["hooks"]],
            }
        ],
    ],
    ids=["empty", "scripts", "mixed"],
)
def test_no_guards_are_trusted_while_hooks_json_holds_no_agent_hook_group(
    tmp_path: Path, groups: list[dict]
) -> None:
    home = _with_hooks_json(_home(tmp_path), groups)
    _link(tmp_path)
    render = FakeRender(R)
    assert trust.guards_to_trust(home, _environment(tmp_path), "Darwin", render) == (
        {},
        None,
    )
    assert render.calls == []


def test_the_guards_come_from_the_render_through_the_stable_link(
    tmp_path: Path,
) -> None:
    home = _with_hooks_json(_home(tmp_path), [R["PreToolUse"][1]])
    link = _link(tmp_path)
    render = FakeRender(R)
    assert trust.guards_to_trust(home, _environment(tmp_path), "Darwin", render) == (
        codex_guards(R),
        None,
    )
    assert render.calls == [(link, "Darwin")]


@pytest.mark.parametrize(
    ("make_link", "render", "why"),
    [
        (False, FakeRender(R), "no {link} (run just sync-agents x)"),
        (True, FakeRender(None, "exits 2: boom"), "render: exits 2: boom"),
    ],
    ids=["missing link", "failed render"],
)
def test_without_a_render_only_the_scripts_are_trusted_and_a_warn_says_why(
    tmp_path: Path, make_link: bool, render: FakeRender, why: str
) -> None:
    home = _with_hooks_json(_home(tmp_path), [R["PreToolUse"][1]])
    link = tmp_path / "data/dotfiles/agent-hooks/current/codex/agent-hook"
    if make_link:
        _link(tmp_path)
    guards, warning = trust.guards_to_trust(
        home, _environment(tmp_path), "Darwin", render
    )
    assert guards == {}
    assert warning == (
        "WARN",
        "codex-hooks",
        "agent-hook's guards in hooks.json not checked: "
        + why.format(link=link)
        + "; the scripts still run",
    )


@pytest.mark.skipif(os.name == "nt", reason="the fake agent-hook is a sh script")
@pytest.mark.parametrize(
    ("body", "result"),
    [
        ('cat "{out}"\n', (R, "")),
        ("echo boom >&2\nexit 2\n", (None, "exits 2: boom")),
        ("echo not-json\n", (None, "output does not parse")),
    ],
    ids=["render", "failure", "not json"],
)
def test_the_render_runs_the_link_for_codex_through_sh(
    tmp_path: Path, body: str, result: tuple
) -> None:
    out = tmp_path / "render.json"
    out.write_text(CODEX_RENDER["stdout"], encoding="utf-8")
    argv = tmp_path / "argv"
    link = tmp_path / "agent-hook"
    link.write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$@" > "{argv}"\n' + body.format(out=out),
        encoding="utf-8",
    )
    link.chmod(0o755)
    rendered, reason = trust.render_codex(link, "Darwin")
    assert rendered == result[0]
    assert reason.startswith(result[1]) and bool(reason) == bool(result[1])
    assert argv.read_text(encoding="utf-8").splitlines() == [
        "render",
        "--harness",
        "codex",
        "--os",
        "darwin",
        "--shell",
        "sh",
        "--binary",
        str(link),
    ]


def test_main_reports_why_the_guards_are_not_checked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    home = _home(tmp_path)
    (home / "hooks.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setattr(trust.shutil, "which", lambda name: "/bin/codex")
    warning = ("WARN", "codex-hooks", "the guards were not checked")
    monkeypatch.setattr(trust, "guards_to_trust", lambda *args: ({}, warning))
    server = FakeServer({"initialize": {}, "hooks/list": {"data": []}})

    @contextlib.contextmanager
    def answering(codex: str) -> Generator[trust.AppServerClient]:
        yield trust.AppServerClient(server, server, timeout=5)

    monkeypatch.setattr(trust, "app_server", answering)
    assert trust.main(["--check"]) == 1
    printed = capsys.readouterr().out.splitlines()
    assert printed[0] == "WARN codex-hooks - the guards were not checked"
