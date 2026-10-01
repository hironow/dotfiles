"""j-cc routes its Claude session through a headroom proxy on a free port.

Only the Claude process j-cc starts gets ANTHROPIC_BASE_URL: a custom base URL
turns off Remote Control, so plain `claude` stays direct. The proxy is started
once and reused while /health says it is a ready headroom proxy; the state file
is only a hint (no lock, no PID). Any problem on the way means "launch without
headroom", never "j-cc does not start".
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import jev_headroom as hr  # noqa: E402
import jev_launch as launcher  # noqa: E402

READY = {"service": "headroom-proxy", "ready": True}


@pytest.mark.parametrize("value", ["0", "off", "false", "no", "OFF"])
def test_jev_headroom_off_skips_the_proxy(value: str) -> None:
    assert hr.disabled({"JEV_HEADROOM": value})


@pytest.mark.parametrize("environ", [{}, {"JEV_HEADROOM": "1"}, {"JEV_HEADROOM": "on"}])
def test_headroom_is_on_by_default(environ: dict[str, str]) -> None:
    assert not hr.disabled(environ)


@pytest.mark.parametrize(
    ("content", "port"),
    [
        (None, None),
        ("not json", None),
        ('{"port": "x"}', None),
        ('{"port": 70000}', None),
        ('{"port": 4321}', 4321),
    ],
)
def test_the_state_is_only_a_hint(
    tmp_path: Path, content: str | None, port: int | None
) -> None:
    state = tmp_path / "headroom.json"
    if content is not None:
        state.write_text(content, encoding="utf-8")
    assert hr.read_state(state) == port


@pytest.mark.parametrize(
    ("answer", "reusable"),
    [
        (READY, True),
        ({"service": "headroom-proxy", "ready": False}, False),
        ({"service": "something-else", "ready": True}, False),
        (None, False),
    ],
)
def test_only_a_ready_headroom_proxy_is_reused(
    answer: dict | None, reusable: bool
) -> None:
    assert hr.is_headroom(answer) is reusable


def test_the_proxy_runs_on_loopback_with_its_beacon_off() -> None:
    assert hr.proxy_command("headroom", 4321) == [
        "headroom",
        "proxy",
        "--host",
        "127.0.0.1",
        "--port",
        "4321",
    ]
    # Both telemetry switches, forced: the proxy reads neither Claude's
    # settings nor an interactive shell's mise env (tests/unit/
    # test_agent_tool_telemetry.py owns the posture).
    env = hr.proxy_env({"HEADROOM_BEACON": "on", "DO_NOT_TRACK": "0", "PATH": "p"})
    assert env["HEADROOM_BEACON"] == "off"
    assert env["DO_NOT_TRACK"] == "1"
    assert env["PATH"] == "p"


def test_claude_gets_the_proxy_and_tool_search() -> None:
    environ = {"PATH": "p"}
    env = hr.claude_env(environ, 4321)
    assert env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:4321"
    # MCP tool search is off behind a non-first-party base URL unless set
    assert env["ENABLE_TOOL_SEARCH"] == "true"
    assert env["PATH"] == "p"
    assert "ANTHROPIC_BASE_URL" not in environ


def test_a_free_port_can_be_bound() -> None:
    port = hr.free_port()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", port))


def test_the_state_is_replaced_atomically(tmp_path: Path) -> None:
    state = tmp_path / "jev" / "headroom.json"
    hr.write_state(state, 1111)
    hr.write_state(state, 2222)
    assert json.loads(state.read_text(encoding="utf-8")) == {"port": 2222}
    assert sorted(p.name for p in state.parent.iterdir()) == ["headroom.json"]


class FakeProxy:
    def __init__(self) -> None:
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True


class World:
    """The imperative edges ensure_proxy touches, faked."""

    def __init__(self, tmp_path: Path, *, exe: str | None = "headroom") -> None:
        self.home = tmp_path
        self.exe = exe
        self.health: dict[int, dict] = {}
        self.started: list[tuple[list[str], dict[str, str]]] = []
        self.proxy = FakeProxy()
        self.ready_after_start = True
        self.start_error: OSError | None = None

    def which(self, _name: str) -> str | None:
        return self.exe

    def probe(self, port: int) -> dict | None:
        return self.health.get(port)

    def start(self, command: list[str], env: dict[str, str], _log: Path) -> FakeProxy:
        if self.start_error:
            raise self.start_error
        self.started.append((command, env))
        if self.ready_after_start:
            self.health[int(command[-1])] = READY
        return self.proxy

    def ensure(self) -> int | None:
        return hr.ensure_proxy(
            {"PATH": "p"},
            self.home,
            which=self.which,
            probe=self.probe,
            start=self.start,
            free_port=lambda: 5555,
            wait_seconds=0.0,
        )

    @property
    def state(self) -> Path:
        return hr.state_path(self.home)


def test_a_running_proxy_is_reused(tmp_path: Path) -> None:
    world = World(tmp_path)
    hr.write_state(world.state, 4321)
    world.health[4321] = READY
    assert world.ensure() == 4321
    assert world.started == []


def test_without_a_proxy_one_starts_on_a_free_port(tmp_path: Path) -> None:
    world = World(tmp_path)
    assert world.ensure() == 5555
    [(command, env)] = world.started
    assert command[-2:] == ["--port", "5555"]
    assert env["HEADROOM_BEACON"] == "off"
    assert hr.read_state(world.state) == 5555


def test_a_stale_state_starts_a_new_proxy(tmp_path: Path) -> None:
    world = World(tmp_path)
    hr.write_state(world.state, 4321)  # nothing answers there any more
    assert world.ensure() == 5555


def test_no_headroom_launches_without_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = World(tmp_path, exe=None)
    assert world.ensure() is None
    assert "headroom not found" in capsys.readouterr().err


def test_a_proxy_that_never_gets_ready_is_stopped(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = World(tmp_path)
    world.ready_after_start = False
    assert world.ensure() is None
    assert world.proxy.terminated
    assert hr.read_state(world.state) is None
    assert "launching without it" in capsys.readouterr().err


def test_a_start_error_launches_without_headroom(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = World(tmp_path)
    world.start_error = OSError("no such file")
    assert world.ensure() is None
    assert "launching without it" in capsys.readouterr().err


def test_a_state_that_cannot_be_written_stops_the_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = World(tmp_path)

    def fail(_path: Path, _port: int) -> None:
        raise PermissionError("read-only cache")

    monkeypatch.setattr(hr, "write_state", fail)
    assert world.ensure() is None
    assert world.proxy.terminated


def test_j_cc_gets_the_proxy_and_plain_launches_do_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def ensure(environ: dict[str, str], _home: Path, **_kwargs: object) -> int:
        calls.append("ensure")
        return 4321

    monkeypatch.setattr(launcher.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(launcher, "ensure_proxy", ensure)
    claude_env = launcher.headroom_env("claude", {"PATH": "p"})
    assert claude_env["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:4321"

    pi_env = launcher.headroom_env("pi", {"PATH": "p"})
    assert "ANTHROPIC_BASE_URL" not in pi_env
    off_env = launcher.headroom_env("claude", {"PATH": "p", "JEV_HEADROOM": "off"})
    assert "ANTHROPIC_BASE_URL" not in off_env
    assert calls == ["ensure"]


def test_an_unexpected_failure_still_launches_claude(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_environ: dict[str, str], _home: Path, **_kwargs: object) -> int:
        raise OSError("cache is a file")

    monkeypatch.setattr(launcher.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(launcher, "ensure_proxy", broken)
    env = launcher.headroom_env("claude", {"PATH": "p"})
    assert env == {"PATH": "p"}
    assert "launching without it" in capsys.readouterr().err


def test_a_corrupt_state_starts_a_new_proxy_and_replaces_it(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.state.parent.mkdir(parents=True)
    world.state.write_text("{not json", encoding="utf-8")
    assert world.ensure() == 5555
    assert hr.read_state(world.state) == 5555


def test_terminate_stops_the_whole_proxy_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    # On Windows headroom.exe is a trampoline over python.exe children, so
    # killing only the started PID would leave the proxy listening
    calls: list[object] = []
    monkeypatch.setattr(hr.subprocess, "run", lambda args, **_kw: calls.append(args))
    monkeypatch.setattr(
        hr.os,
        "killpg",
        lambda pid, sig: calls.append(("killpg", pid, sig)),
        raising=False,
    )
    proxy = hr.ProxyProcess(1234)

    monkeypatch.setattr(hr.sys, "platform", "win32")
    proxy.terminate()
    monkeypatch.setattr(hr.sys, "platform", "linux")
    proxy.terminate()

    assert calls[0] == ["taskkill", "/T", "/F", "/PID", "1234"]
    assert calls[1] == ("killpg", 1234, hr.signal.SIGTERM)


def test_codex_gets_the_proxy_as_its_openai_base_url() -> None:
    env = hr.codex_env({"PATH": "p"}, 4321)
    assert env["OPENAI_BASE_URL"] == "http://127.0.0.1:4321/v1"
    assert hr.codex_base_url(4321) == "http://127.0.0.1:4321/v1"


def test_proxy_port_never_stops_the_launch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken(_environ: Mapping[str, str], _home: Path) -> int:
        raise OSError("cache is a file")

    assert hr.proxy_port({}, tmp_path, ensure=broken) is None
    assert "launching without it" in capsys.readouterr().err
    called: list[bool] = []
    assert (
        hr.proxy_port(
            {"JEV_HEADROOM": "off"}, tmp_path, ensure=lambda *_a: called.append(True)
        )
        is None
    )
    assert called == []


def test_the_state_dir_can_be_pointed_elsewhere(tmp_path: Path) -> None:
    # The live check hands a runner its dedicated proxy this way
    world = World(tmp_path / "home")
    other = tmp_path / "verify"
    hr.write_state(other / "headroom.json", 4321)
    world.health[4321] = READY
    port = hr.ensure_proxy(
        {"JEV_HEADROOM_STATE_DIR": str(other)},
        world.home,
        which=world.which,
        probe=world.probe,
        start=world.start,
        free_port=lambda: 5555,
        wait_seconds=0.0,
    )
    assert port == 4321
    assert world.started == []
