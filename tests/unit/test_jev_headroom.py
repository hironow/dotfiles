"""j-cc routes its Claude session through a headroom proxy on a free port.

Only the Claude process j-cc starts gets ANTHROPIC_BASE_URL: a custom base URL
turns off Remote Control, so plain `claude` stays direct. The proxy is started
once and reused while /health says it is a ready headroom proxy; the state file
is only a hint (no lock, no PID). Any problem on the way means "launch without
headroom", never "j-cc does not start".
"""

from __future__ import annotations

import json
import socket
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import jev_headroom as hr
import jev_launch as launcher

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

    def ensure(self, on_start: Callable[[int], None] | None = None) -> int | None:
        return hr.ensure_proxy(
            {"PATH": "p"},
            self.home,
            which=self.which,
            probe=self.probe,
            start=self.start,
            free_port=lambda: 5555,
            wait_seconds=0.0,
            on_start=on_start,
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


def test_j_cc_routes_through_the_proxy_and_j_pi_only_readies_it(
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

    # j-pi readies the proxy for its Codex workers; Pi's own traffic stays direct
    pi_env = launcher.headroom_env("pi", {"PATH": "p"})
    assert "ANTHROPIC_BASE_URL" not in pi_env
    off_env = launcher.headroom_env("claude", {"PATH": "p", "JEV_HEADROOM": "off"})
    assert "ANTHROPIC_BASE_URL" not in off_env
    assert calls == ["ensure", "ensure"]


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


# --- just headroom-dashboard: open the dashboard of j-cc's proxy -----------
# `headroom dashboard` opens port 8787, where j-cc never runs its proxy (it
# takes a free port and records it), so the plain command opened nothing.

HEALTHY = {"service": "headroom-proxy", "ready": True}


def test_the_dashboard_of_the_recorded_running_proxy_is_opened() -> None:
    assert hr.dashboard_plan("headroom", 62103, HEALTHY) == [
        "headroom",
        "dashboard",
        "-p",
        "62103",
    ]


@pytest.mark.parametrize(
    ("port", "health", "hint"),
    [
        (None, None, "no j-cc proxy is recorded"),
        (62103, None, "not running"),
        (62103, {"status": "ok"}, "not running"),
    ],
)
def test_without_a_running_proxy_it_says_to_start_j_cc(
    port: int | None, health: dict | None, hint: str
) -> None:
    plan = hr.dashboard_plan("headroom", port, health)
    assert isinstance(plan, str)
    assert hint in plan
    assert "j-cc" in plan


def test_the_recipe_runs_it() -> None:
    justfile = (Path(__file__).resolve().parents[2] / "justfile").read_text(
        encoding="utf-8"
    )
    assert "headroom-dashboard:" in justfile
    assert "scripts/jev_headroom.py dashboard" in justfile


# --- the dashboard at launch: URL every time, the browser once per proxy ---


def test_on_start_is_called_only_for_a_proxy_this_launch_started(
    tmp_path: Path,
) -> None:
    opened: list[int] = []
    world = World(tmp_path)
    assert world.ensure(on_start=opened.append) == 5555
    assert opened == [5555]
    assert world.ensure(on_start=opened.append) == 5555  # reused: not again
    assert opened == [5555]


def test_the_dashboard_url_names_the_proxys_port() -> None:
    assert hr.dashboard_url(4321) == "http://127.0.0.1:4321/dashboard"


@pytest.mark.parametrize(
    ("environ", "wanted"),
    [
        ({}, True),
        ({"JEV_HEADROOM_DASHBOARD": "off"}, False),
        ({"JEV_HEADROOM_DASHBOARD": "0"}, False),
    ],
)
def test_opening_the_dashboard_can_be_turned_off(
    environ: dict[str, str], wanted: bool
) -> None:
    assert hr.dashboard_wanted(environ) is wanted


@pytest.mark.parametrize(
    ("host", "started"), [("claude", True), ("pi", True), ("claude", False)]
)
def test_a_launch_shows_the_url_and_opens_it_only_for_a_new_proxy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    host: str,
    started: bool,
) -> None:
    opened: list[str] = []

    def ensure(_environ: dict[str, str], _home: Path, **kwargs: object) -> int:
        on_start = kwargs.get("on_start")
        if started and callable(on_start):
            on_start(4321)
        return 4321

    monkeypatch.setattr(launcher.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(launcher, "ensure_proxy", ensure)
    monkeypatch.setattr(launcher, "open_url", opened.append)
    launcher.headroom_env(host, {"PATH": "p"})
    assert "http://127.0.0.1:4321/dashboard" in capsys.readouterr().err
    assert opened == (["http://127.0.0.1:4321/dashboard"] if started else [])


def test_a_launch_with_the_dashboard_off_never_opens_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []

    def ensure(_environ: dict[str, str], _home: Path, **kwargs: object) -> int:
        on_start = kwargs.get("on_start")
        if callable(on_start):
            on_start(4321)
        return 4321

    monkeypatch.setattr(launcher.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(launcher, "ensure_proxy", ensure)
    monkeypatch.setattr(launcher, "open_url", opened.append)
    launcher.headroom_env("claude", {"PATH": "p", "JEV_HEADROOM_DASHBOARD": "off"})
    assert opened == []


@pytest.mark.parametrize(
    ("platform", "environ", "can"),
    [
        ("win32", {}, True),
        ("darwin", {}, True),
        ("linux", {"WSL_DISTRO_NAME": "Ubuntu"}, True),
        ("linux", {"DISPLAY": ":0"}, True),
        ("linux", {"WAYLAND_DISPLAY": "wayland-0"}, True),
        # a headless box: a terminal browser would take over the launch's tty
        ("linux", {}, False),
    ],
)
def test_a_browser_is_tried_only_where_one_can_show(
    platform: str, environ: dict[str, str], can: bool
) -> None:
    assert hr.can_open_browser(platform, environ) is can


def test_the_browser_opens_in_a_process_the_launch_never_waits_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # webbrowser can wait for the browser it starts (lynx, a foreground
    # $BROWSER, osascript); a separate process cannot hold the launch up
    started: list[list[str]] = []
    monkeypatch.setattr(hr.sys, "platform", "darwin")
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(hr.subprocess, "Popen", lambda argv, **_k: started.append(argv))
    hr.open_url("http://127.0.0.1:1/dashboard")
    [argv] = started
    assert argv[0] == hr.sys.executable
    assert argv[-1] == "http://127.0.0.1:1/dashboard"
