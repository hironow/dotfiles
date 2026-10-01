#!/usr/bin/env python3
"""headroom proxy for j-cc: reuse a ready one, else start one on a free port.

Only the Claude process j-cc starts is pointed at the proxy (ANTHROPIC_BASE_URL
disables Remote Control, so plain `claude` stays direct). The proxy outlives the
launch and later launches reuse it. The state file is only a hint that /health
re-verifies on every launch; there is no lock and no stored PID, so two launches
in the same startup window may each start a proxy, and each uses its own. Every
failure means "launch without headroom", never "j-cc does not start".
"""

from collections.abc import Callable, Mapping, Sequence
import contextlib
import http.client
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
from typing import Protocol

HOST = "127.0.0.1"
OFF = {"0", "off", "false", "no"}


class Proxy(Protocol):
    def terminate(self) -> None: ...


class ProxyProcess:
    """A started proxy, stopped as a whole tree: on Windows headroom.exe is a
    trampoline over python.exe children; on POSIX it leads its own session."""

    def __init__(self, pid: int) -> None:
        self.pid = pid

    def terminate(self) -> None:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(self.pid)],
                capture_output=True,
                check=False,
            )
        else:
            with contextlib.suppress(OSError):
                os.killpg(self.pid, signal.SIGTERM)


def disabled(environ: Mapping[str, str]) -> bool:
    return environ.get("JEV_HEADROOM", "").strip().lower() in OFF


def _state_dir(home: Path, environ: Mapping[str, str] | None = None) -> Path:
    # JEV_HEADROOM_STATE_DIR: the live check hands a runner its dedicated proxy
    override = (environ or {}).get("JEV_HEADROOM_STATE_DIR")
    return Path(override) if override else home / ".cache" / "jev"


def state_path(home: Path, environ: Mapping[str, str] | None = None) -> Path:
    return _state_dir(home, environ) / "headroom.json"


def log_path(home: Path, environ: Mapping[str, str] | None = None) -> Path:
    return _state_dir(home, environ) / "headroom-proxy.log"


def read_state(path: Path) -> int | None:
    """The port the last launch recorded, or None when there is no usable hint."""
    try:
        port = json.loads(path.read_text(encoding="utf-8")).get("port")
    except (OSError, ValueError, AttributeError):
        return None
    return port if isinstance(port, int) and 0 < port < 65536 else None


def write_state(path: Path, port: int) -> None:
    """Replace the state atomically: a concurrent reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"port": port}), encoding="utf-8")
    tmp.replace(path)


def is_headroom(answer: object) -> bool:
    return (
        isinstance(answer, dict)
        and answer.get("service") == "headroom-proxy"
        and answer.get("ready") is True
    )


def probe(port: int, timeout: float = 2.0) -> dict | None:
    """GET /health on loopback (http.client never routes through HTTP(S)_PROXY)."""
    connection = http.client.HTTPConnection(HOST, port, timeout=timeout)
    try:
        connection.request("GET", "/health")
        answer = json.loads(connection.getresponse().read().decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException):
        return None
    finally:
        connection.close()
    return answer if isinstance(answer, dict) else None


def free_port() -> int:
    with socket.socket() as probe_socket:
        probe_socket.bind((HOST, 0))
        return probe_socket.getsockname()[1]


def proxy_command(exe: str, port: int) -> list[str]:
    return [exe, "proxy", "--host", HOST, "--port", str(port)]


def proxy_env(environ: Mapping[str, str]) -> dict[str, str]:
    # The beacon runs in the proxy process, which reads neither Claude's
    # settings nor an interactive shell's mise env, so both switches are set
    # here: HEADROOM_BEACON is headroom's own, DO_NOT_TRACK the cross-vendor
    # opt-out it also honours. Forced, not defaulted -- an inherited "on" from
    # a stale environment must not win.
    return {**environ, "HEADROOM_BEACON": "off", "DO_NOT_TRACK": "1"}


def claude_env(environ: Mapping[str, str], port: int) -> dict[str, str]:
    # Claude Code turns MCP tool search off behind a non-first-party base URL
    return {
        **environ,
        "ANTHROPIC_BASE_URL": f"http://{HOST}:{port}",
        "ENABLE_TOOL_SEARCH": "true",
    }


def codex_base_url(port: int) -> str:
    return f"http://{HOST}:{port}/v1"


def codex_env(environ: Mapping[str, str], port: int) -> dict[str, str]:
    # headroom's own per-process recipe sets this next to `-c openai_base_url=`
    return {**environ, "OPENAI_BASE_URL": codex_base_url(port)}


def proxy_port(
    environ: Mapping[str, str],
    home: Path,
    *,
    ensure: Callable[[Mapping[str, str], Path], int | None],
) -> int | None:
    """The port to route through, or None: JEV_HEADROOM=off, no proxy, or any
    failure on the way. It never stops the launch."""
    if disabled(environ):
        return None
    try:
        port = ensure(environ, home)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(
            f"Jev: headroom unavailable ({error}); launching without it",
            file=sys.stderr,
        )
        return None
    if port is not None:
        print(f"Headroom: http://{HOST}:{port}", file=sys.stderr)
    return port


def start(command: list[str], env: dict[str, str], log: Path) -> ProxyProcess:
    """Start the proxy detached from this launch, so it outlives j-cc."""
    return ProxyProcess(_spawn(command, env, log).pid)


def _spawn(command: list[str], env: dict[str, str], log: Path) -> subprocess.Popen:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("ab") as output:
        if sys.platform != "win32":
            return subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        # Leave a kill-on-close job (some terminals) so the proxy survives it;
        # a job that forbids breakaway rejects the flag, so retry without it
        for creationflags in (flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, flags):
            try:
                return subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=creationflags,
                )
            except OSError:
                if creationflags == flags:
                    raise
        raise AssertionError("unreachable")


def wait_ready(port: int, check: Callable[[int], object], wait_seconds: float) -> bool:
    deadline = time.monotonic() + wait_seconds
    while True:
        if is_headroom(check(port)):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.5)


def ensure_proxy(
    environ: Mapping[str, str],
    home: Path,
    *,
    which: Callable[[str], str | None] = shutil.which,
    probe: Callable[[int], dict | None] = probe,
    start: Callable[[list[str], dict[str, str], Path], Proxy] = start,
    free_port: Callable[[], int] = free_port,
    wait_seconds: float = 60.0,
) -> int | None:
    """The port of a ready headroom proxy, or None (with a notice) to go direct."""
    exe = which("headroom")
    if not exe:
        print("Jev: headroom not found; launching without it", file=sys.stderr)
        return None
    state = state_path(home, environ)
    port = read_state(state)
    if port is not None and is_headroom(probe(port)):
        return port
    port = free_port()
    log = log_path(home, environ)
    try:
        proxy = start(proxy_command(exe, port), proxy_env(environ), log)
    except (OSError, subprocess.SubprocessError) as error:
        print(
            f"Jev: headroom proxy did not start ({error}); launching without it",
            file=sys.stderr,
        )
        return None
    try:
        if not wait_ready(port, probe, wait_seconds):
            raise TimeoutError(f"not ready on port {port} after {wait_seconds:.0f}s")
        write_state(state, port)
    except (OSError, ValueError) as error:
        # Never leave behind a proxy no state points at
        proxy.terminate()
        print(
            f"Jev: headroom proxy did not start ({error}; see {log}); "
            "launching without it",
            file=sys.stderr,
        )
        return None
    return port


def dashboard_plan(exe: str, port: int | None, health: object) -> list[str] | str:
    """The command that opens j-cc's proxy dashboard, or what to do instead.

    `headroom dashboard` defaults to port 8787; j-cc's proxy runs on the free
    port recorded in its state file, so the port is always passed.
    """
    if port is None:
        return "no j-cc proxy is recorded: start j-cc, which starts one"
    if not is_headroom(health):
        return f"the recorded proxy (port {port}) is not running: start j-cc again"
    return [exe, "dashboard", "-p", str(port)]


def main(argv: Sequence[str]) -> int:
    """`dashboard`: open the dashboard of the proxy j-cc recorded."""
    if list(argv) != ["dashboard"]:
        print("usage: jev_headroom.py dashboard", file=sys.stderr)
        return 2
    exe = shutil.which("headroom")
    if not exe:
        print("headroom not found: mise install", file=sys.stderr)
        return 1
    port = read_state(state_path(Path.home(), os.environ))
    plan = dashboard_plan(exe, port, probe(port) if port is not None else None)
    if isinstance(plan, str):
        print(plan, file=sys.stderr)
        return 1
    return subprocess.run(plan, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
