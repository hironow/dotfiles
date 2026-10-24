"""Canonical Windows Ollama ownership and fail-closed WSL sharing policy."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import copy
import json
import os
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ollama_host as host


def _windows() -> dict:
    root = r"C:\Users\dev\scoop\apps\ollama-full\0.40.10"
    return {
        "full_dir": root,
        "full_bucket": "extras",
        "duplicates": [],
        "listeners": [
            {"address": "127.0.0.1", "pid": 42, "path": root + r"\ollama.exe"}
        ],
        "python": r"C:\Users\dev\mise\installs\python\3.15.0\python.exe",
        "version": "0.40.10",
        "errors": [],
    }


def _wsl() -> dict:
    return {
        "native": [],
        "services": [],
        "models": False,
        "errors": [],
        "client_managed": True,
        "bridge_managed": True,
        "bridge_active": True,
        "bridge_owned": True,
        "loopback_only": True,
        "version": "0.40.10",
    }


def _has(rows: list, severity: str, name: str) -> bool:
    return any(row[0] == severity and row[1] == name for row in rows)


@pytest.mark.parametrize(
    ("system", "release", "expected"),
    [
        ("win32", "", "windows-full"),
        ("linux", "6.6-microsoft-standard-WSL2", "wsl-client"),
        ("linux", "6.8-generic", None),
        ("darwin", "", None),
    ],
)
def test_platform_policy(system: str, release: str, expected: str | None) -> None:
    assert host.host_policy(system, release) == expected


def test_checker_and_stable_deployment_can_have_different_paths(tmp_path: Path) -> None:
    checker = tmp_path / "checkout.py"
    deployed = tmp_path / "stable.py"
    content = f"#!/usr/bin/python3\n{host.HELPER_MARKER}\nprint('same')\n"
    checker.write_text(content, encoding="utf-8")
    deployed.write_text(content, encoding="utf-8", newline="\n")
    assert host.deployment_matches(deployed, checker)
    deployed.write_text(content + "# altered\n", encoding="utf-8", newline="\n")
    assert not host.deployment_matches(deployed, checker)


def test_canonical_windows_owner_is_healthy() -> None:
    rows = host.windows_findings(_windows())
    assert not any(row[0] != "OK" for row in rows)


@pytest.mark.parametrize(
    "duplicate", ["scoop/ollama", "winget/Ollama.Ollama", "standalone/Ollama"]
)
def test_installs_outside_path_still_violate_policy(duplicate: str) -> None:
    data = _windows()
    data["duplicates"] = [duplicate]
    assert _has(host.windows_findings(data), "ERR", "ollama-install")


@pytest.mark.parametrize(
    "path",
    [
        r"C:\other\ollama.exe",
        r"C:\Users\dev\scoop\apps\ollama-full\0.40.10-evil\ollama.exe",
        "",
    ],
)
def test_healthy_http_is_not_canonical_ownership(path: str) -> None:
    data = _windows()
    data["listeners"][0]["path"] = path
    assert _has(host.windows_findings(data), "ERR", "ollama-owner")
    assert not host.backend_owned(data)


@pytest.mark.parametrize("address", ["0.0.0.0", "::", "172.21.64.1"])
def test_non_loopback_exposure_is_an_error(address: str) -> None:
    data = _windows()
    data["listeners"][0]["address"] = address
    assert _has(host.windows_findings(data), "ERR", "ollama-exposure")
    assert not host.backend_owned(data)


def test_backend_down_cannot_forward_back_into_wsl() -> None:
    data = _windows()
    data["listeners"] = []
    assert not host.backend_owned(data)
    assert _has(host.windows_findings(data), "WARN", "ollama-owner")


def test_missing_full_or_wrong_bucket_is_not_accepted() -> None:
    for key, value in [("full_dir", ""), ("full_bucket", "main")]:
        data = _windows()
        data[key] = value
        assert _has(host.windows_findings(data), "ERR", "ollama-install")
        assert not host.backend_owned(data)


def test_canonical_scoop_shim_launcher_is_not_a_second_backend() -> None:
    data = _windows()
    data["processes"] = [
        {
            "path": r"C:\Users\dev\scoop\shims\ollama.exe",
            "pid": 100,
            "trusted_shim": True,
        }
    ]
    assert host.backend_owned(data)
    data["processes"][0]["trusted_shim"] = False
    assert not host.backend_owned(data)
    data["processes"][0]["trusted_shim"] = True
    data["listeners"].append(
        {
            "path": data["processes"][0]["path"],
            "pid": 100,
            "address": "127.0.0.1",
            "port": 11435,
        }
    )
    assert not host.backend_owned(data)


@pytest.mark.skipif(
    sys.platform != "win32",
    reason="exercise the Windows classifier, not a Python reimplementation",
)
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("valid", True),
        ("unsigned", False),
        ("wrong-signer", False),
        ("wrong-path", False),
        ("wrong-name", False),
        ("wrong-port", False),
        ("wildcard", False),
        ("ipv4", False),
        ("link-file", False),
        ("link-parent", False),
        ("inspection-error", False),
        ("signature-error", False),
    ],
)
def test_powershell_forwarder_classifier_is_narrow(mode: str, expected: bool) -> None:
    fixture = r"""
$ErrorActionPreference='Stop'
function Get-Item {
 param([string]$LiteralPath,[string]$ErrorAction)
 if($script:mode -eq 'inspection-error'){throw 'uninspectable'}
 $attributes=32
 if(($script:mode -eq 'link-file' -and $LiteralPath.EndsWith('.exe')) -or ($script:mode -eq 'link-parent' -and -not $LiteralPath.EndsWith('.exe'))){$attributes=1024}
 [pscustomobject]@{FullName=$LiteralPath;Attributes=[IO.FileAttributes]$attributes}
}
function Get-AuthenticodeSignature {
 param([string]$FilePath,[string]$ErrorAction)
 if($script:mode -eq 'signature-error'){throw 'signature unavailable'}
 $status=if($script:mode -eq 'unsigned'){'NotSigned'}else{'Valid'}
 $subject=if($script:mode -eq 'wrong-signer'){'CN=Unrelated, O=Other'}else{'CN=Microsoft Corporation, O=Microsoft Corporation, C=US'}
 [pscustomobject]@{Status=$status;SignerCertificate=[pscustomobject]@{Subject=$subject}}
}
$path=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'WSL\wslrelay.exe'
if($script:mode -eq 'wrong-path'){$path=Join-Path $env:TEMP 'wslrelay.exe'}
if($script:mode -eq 'wrong-name'){$path=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'WSL\wslhost.exe'}
$address=if($script:mode -eq 'wildcard'){'::'}elseif($script:mode -eq 'ipv4'){'127.0.0.1'}else{'::1'}
$port=if($script:mode -eq 'wrong-port'){11435}else{11434}
Test-DotfilesWslForwarder $path $address $port | ConvertTo-Json -Compress
"""
    script = (
        "$env:PSModulePath='C:/nonexistent-powershell7-modules'\n"
        + host.WINDOWS_FORWARDER_CLASSIFIER
        + f"\n$script:mode='{mode}'\n"
        + fixture
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [
            host.powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=True,
    )
    assert json.loads(result.stdout) is expected


@pytest.mark.skipif(sys.platform != "win32", reason="Windows builtin module isolation")
def test_windows_security_module_ignores_inherited_powershell7_paths() -> None:
    script = (
        "$env:PSModulePath='C:/nonexistent-powershell7-modules'\n"
        + host.WINDOWS_FORWARDER_CLASSIFIER
        + "\n(Get-AuthenticodeSignature -FilePath (Join-Path $PSHOME 'powershell.exe')).Status -eq 'Valid' | ConvertTo-Json"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [
            host.powershell(),
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            encoded,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
        check=True,
    )
    assert json.loads(result.stdout) is True


def test_signed_windows_ipv6_forwarder_is_not_a_second_ollama() -> None:
    data = _windows()
    data["listeners"].append(
        {
            "address": "::1",
            "port": 11434,
            "pid": 99,
            "path": r"C:\Program Files\WSL\wslrelay.exe",
            "windows_forwarder": True,
        }
    )
    assert host.backend_owned(data)
    assert not _has(host.windows_findings(data), "ERR", "ollama-owner")


def test_healthy_ipv6_backend_cannot_authorize_a_forwarded_ipv4_target() -> None:
    data = _windows()
    data["listeners"][0]["address"] = "::1"
    data["listeners"].append(
        {
            "address": "127.0.0.1",
            "port": 11434,
            "pid": 99,
            "path": r"C:\Program Files\WSL\wslrelay.exe",
            "windows_forwarder": True,
        }
    )
    assert not host.backend_owned(data)


def test_ipv6_only_backend_does_not_own_the_fixed_ipv4_transport_target() -> None:
    data = _windows()
    data["listeners"][0]["address"] = "::1"
    assert not host.backend_owned(data)


def test_unsigned_or_exposed_forwarder_is_not_exempted() -> None:
    for address, trusted in [("::1", False), ("::", True)]:
        data = _windows()
        data["listeners"].append(
            {
                "address": address,
                "port": 11434,
                "pid": 99,
                "path": r"C:\Program Files\WSL\wslrelay.exe",
                "windows_forwarder": trusted,
            }
        )
        assert not host.backend_owned(data)


def test_additional_serving_backend_is_rejected() -> None:
    data = _windows()
    data["listeners"].append(
        {"address": "::1", "pid": 43, "path": data["full_dir"] + r"\ollama.exe"}
    )
    assert _has(host.windows_findings(data), "ERR", "ollama-owner")
    assert not host.backend_owned(data)


def test_uninspected_is_never_healthy() -> None:
    data = _windows()
    data["errors"] = ["stopped distribution: Ubuntu"]
    assert _has(host.windows_findings(data), "WARN", "ollama-inspection")


@pytest.mark.parametrize(
    "key,value,name",
    [
        ("native", ["/usr/local/bin/ollama"], "ollama-wsl-native"),
        ("services", ["system:ollama.service:enabled:inactive"], "ollama-wsl-native"),
        ("models", True, "ollama-wsl-models"),
        ("bridge_owned", False, "ollama-bridge"),
        ("bridge_managed", False, "ollama-bridge"),
        ("loopback_only", False, "ollama-exposure"),
        ("conflicting_config", True, "ollama-exposure"),
    ],
)
def test_wsl_violations_are_visible(key: str, value: object, name: str) -> None:
    data = _wsl()
    data[key] = value
    assert _has(host.wsl_findings(data), "ERR", name)


def test_wsl_bridge_version_must_match_canonical_backend() -> None:
    data = _wsl()
    data["version"] = "different"
    assert _has(
        host.wsl_findings(data, windows_version="0.40.10"), "ERR", "ollama-bridge"
    )


def test_missing_transport_and_invalid_version_fail_closed() -> None:
    data = _windows()
    data["python"] = ""
    assert _has(host.windows_findings(data), "WARN", "ollama-transport")
    assert host.backend_owned(data)  # Backend ownership is independent of transport.
    data = _windows()
    data["version"] = {"not": "a version"}
    assert not host.backend_owned(data)


@pytest.mark.parametrize(
    "args",
    [
        ["serve"],
        ["launch"],
        ["--verbose", "serve"],
        ["future-command"],
        ["--host=remote", "list"],
    ],
)
def test_client_refuses_daemon_menu_and_unknown_entrypoints(
    args: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(
        host,
        "windows_snapshot",
        lambda: pytest.fail("must reject before probing/launch"),
    )
    with pytest.raises(RuntimeError):
        host.client_command(args)


def test_client_preserves_args_and_wslenv_but_pins_windows_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    monkeypatch.setattr(
        host,
        "interop_environment",
        lambda: {"WSLENV": "KEEP/p:OLLAMA_HOST/p:OTHER/u", "OLLAMA_HOST": "remote"},
    )
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(host.subprocess, "run", run)
    args = ["run", "a-model", "a quote ' and space; $(not-a-shell)"]
    assert host.client_command(args) == 0
    command, kwargs = calls[0]
    assert command[1:] == args
    assert command[0].endswith("ollama.exe")
    assert kwargs["env"]["OLLAMA_HOST"] == "http://127.0.0.1:11434"
    assert kwargs["env"]["WSLENV"] == "KEEP/p:OTHER/u:OLLAMA_HOST"


def test_client_backend_down_never_autostarts_a_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = _windows()
    data["listeners"] = []
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "windows_snapshot", lambda: data)
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("unexpected replacement/CLI launch"),
    )
    with pytest.raises(RuntimeError, match="no daemon or native fallback"):
        host.client_command(["list"])


def test_stable_client_install_is_idempotent_and_preserves_user_edits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(host.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(host, "DURABLE_PYTHON", sys.executable)
    host.install_client_files()
    helper = host.deployment_source()
    shim = tmp_path / ".local/bin/ollama"
    assert host.deployment_matches(helper, host.SOURCE)
    assert host.managed_cli(shim, helper)
    unit = tmp_path / ".config/systemd/user" / host.UNIT
    assert host.managed_unit(unit.read_text(encoding="utf-8"), str(helper))
    first = helper.read_bytes(), shim.read_bytes(), unit.read_bytes()
    host.install_client_files()
    assert first == (helper.read_bytes(), shim.read_bytes(), unit.read_bytes())
    shim.write_text("# user changed this", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing"):
        host.install_client_files()
    assert shim.read_text(encoding="utf-8") == "# user changed this"


def test_client_files_precede_backend_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    order = []
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "install_client_files", lambda: order.append("files"))

    def unavailable():
        assert order == ["files"]
        raise RuntimeError("interop unavailable")

    monkeypatch.setattr(host, "windows_snapshot", unavailable)
    with pytest.raises(RuntimeError, match="interop unavailable"):
        host.setup()


def test_owned_write_refuses_unrelated_files_and_updates_matching_hash(
    tmp_path: Path,
) -> None:
    path = tmp_path / "owned"
    path.write_text("user-owned", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing"):
        host._write_owned(path, "managed", None, 0o600)
    assert path.read_text(encoding="utf-8") == "user-owned"
    previous = host._source_hash(path)
    host._write_owned(path, "managed", previous, 0o600)
    assert path.read_text(encoding="utf-8") == "managed"


def test_probe_errors_fail_closed() -> None:
    data = _windows()
    data["errors"] = ["could not inspect listeners"]
    assert not host.backend_owned(data)


def test_systemd_unit_has_fixed_loopback_transport_and_managed_identity() -> None:
    unit = host.bridge_unit(
        "/usr/bin/python3", "/home/user/dotfiles/scripts/ollama_host.py"
    )
    assert host.UNIT_MARKER in unit
    assert "--serve" in unit
    assert "Restart=on-failure" in unit
    assert "ollama serve" not in unit
    assert "WSL_INTEROP=" not in unit  # Session-specific sockets must not be pinned.


def test_managed_unit_rejects_extra_commands_and_wrong_source() -> None:
    source = "/home/user/dotfiles/scripts/ollama_host.py"
    unit = host.bridge_unit("/usr/bin/python3", source)
    assert host.managed_unit(unit, source)
    assert not host.managed_unit(unit + "ExecStartPre=touch /tmp/side-effect\n", source)
    assert not host.managed_unit(unit, "/other/source.py")


@pytest.mark.parametrize(
    "address,trusted,allowed",
    [
        (None, False, True),
        ("::1", True, True),
        ("::1", False, False),
        ("127.0.0.1", True, False),
        ("::", True, False),
    ],
)
def test_windows_startup_distinguishes_forwarder_from_backend(
    monkeypatch: pytest.MonkeyPatch, address: str | None, trusted: bool, allowed: bool
) -> None:
    data = _windows()
    data["version"] = ""
    data["listeners"] = (
        []
        if address is None
        else [
            {
                "address": address,
                "port": 11434,
                "pid": 99,
                "path": r"C:\Program Files\WSL\wslrelay.exe",
                "windows_forwarder": trusted,
            }
        ]
    )
    monkeypatch.setattr(host, "host_policy", lambda: "windows-full")
    monkeypatch.setattr(host, "windows_snapshot", lambda: data)
    calls = []
    monkeypatch.setattr(
        host.subprocess, "Popen", lambda args, **kwargs: calls.append(args)
    )
    if allowed:
        host.setup()
        assert calls == [[str(Path(data["full_dir"]) / "ollama app.exe")]]
    else:
        with pytest.raises(RuntimeError, match="violations"):
            host.setup()
        assert not calls


def test_windows_startup_does_not_launch_another_healthy_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "windows-full")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    calls = []
    monkeypatch.setattr(
        host.subprocess, "Popen", lambda *args, **kwargs: calls.append(args)
    )
    host.setup()
    assert not calls


def test_non_windows_non_wsl_setup_never_probes_windows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: None)
    monkeypatch.setattr(
        host, "windows_snapshot", lambda: pytest.fail("unexpected Windows probe")
    )
    host.setup()


def test_no_arbitrary_windows_transport_target() -> None:
    command = host.transport_command("/mnt/c/python.exe")
    assert command[-2:] == ["127.0.0.1", "11434"]
    assert all(flag in command for flag in ("-I", "-S", "-B", "-u"))
    compile(host.WINDOWS_STREAM, "<fixed-windows-transport>", "exec")


@pytest.mark.skipif(sys.platform != "win32", reason="the byte adapter runs in Windows")
def test_fixed_windows_code_refuses_noncanonical_target_without_connecting() -> None:
    command = host.transport_command(sys.executable)
    command[-1] = "9"
    result = subprocess.run(command, capture_output=True, timeout=10, check=False)
    assert result.returncode == 2
    assert result.stdout == b""


@pytest.mark.skipif(
    sys.platform != "win32", reason="Windows byte adapter timeout semantics"
)
def test_receive_timeout_also_applies_during_active_upload() -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    received = []

    def consume_without_response():
        try:
            connection, _address = listener.accept()
            with connection:
                while data := connection.recv(1024):
                    received.append(data)
        except OSError:
            pass

    server = threading.Thread(target=consume_without_response, daemon=True)
    server.start()
    command = host.transport_command(sys.executable)
    command[-1] = str(port)
    command[-3] = (
        command[-3]
        .replace("11434", str(port))
        .replace("backend.settimeout(300)", "backend.settimeout(0.2)")
    )
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    input_pipe = process.stdin
    assert input_pipe is not None

    def upload():
        try:
            for _ in range(100):
                input_pipe.write(b"x")
                input_pipe.flush()
                time.sleep(0.02)
        except (OSError, ValueError):
            pass

    sender = threading.Thread(target=upload, daemon=True)
    sender.start()
    try:
        assert process.wait(timeout=5) != 0
        assert received, "the upload must have started before receive timeout"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        sender.join(timeout=2)
        process.communicate(timeout=5)
        listener.close()
        server.join(timeout=2)


def test_findings_do_not_mutate_input() -> None:
    data = _windows()
    original = copy.deepcopy(data)
    host.windows_findings(data)
    assert data == original


def test_conflicting_effective_host_configuration_is_an_error() -> None:
    data = _windows()
    data["conflicting_config"] = True
    assert _has(host.windows_findings(data), "ERR", "ollama-exposure")
    assert not host.backend_owned(data)


def test_port_conflict_does_not_remove_an_existing_bridge_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state = tmp_path / "state.json"
    state.write_text('{"pid":123}', encoding="utf-8")
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "_state_path", lambda: state)

    async def conflict(*args, **kwargs):
        raise OSError("port occupied")

    monkeypatch.setattr(host.asyncio, "start_server", conflict)
    with pytest.raises(OSError, match="port occupied"):
        asyncio.run(host.serve())
    assert json.loads(state.read_text(encoding="utf-8"))["pid"] == 123


@pytest.mark.parametrize("backend", ["up", "down"])
def test_opaque_relay_streaming_eof_and_backend_down(
    backend: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _windows()
    if backend == "down":
        data["listeners"] = []
    monkeypatch.setattr(host, "windows_snapshot", lambda: data)
    monkeypatch.setattr(host, "interop_environment", os.environ.copy)
    original_spawn = asyncio.create_subprocess_exec
    children = []

    async def spawn(*args, **kwargs):
        assert list(args)[-2:] == ["127.0.0.1", "11434"]
        process = await original_spawn(
            sys.executable,
            "-u",
            "-c",
            "import sys\nwhile data := sys.stdin.buffer.read1(32768):\n sys.stdout.buffer.write(data); sys.stdout.buffer.flush()\n",
            **kwargs,
        )
        children.append(process)
        return process

    monkeypatch.setattr(host.asyncio, "create_subprocess_exec", spawn)

    async def exercise():
        done = asyncio.Event()

        async def handle(reader, writer):
            try:
                await host._relay(reader, writer, asyncio.Semaphore(1))
            finally:
                done.set()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        try:
            reader, writer = await asyncio.open_connection(
                "127.0.0.1", server.sockets[0].getsockname()[1]
            )
            writer.write(b"first")
            await writer.drain()
            if backend == "up":
                # Incremental response must arrive BEFORE stdin EOF/full body.
                assert await asyncio.wait_for(reader.readexactly(5), 5) == b"first"
                payload = bytes(range(256)) * 8192

                async def receive():
                    return await reader.readexactly(len(payload))

                incoming = asyncio.create_task(receive())
                writer.write(payload)
                await writer.drain()
                assert await asyncio.wait_for(incoming, 10) == payload
            else:
                # Linux may reset a refused connection with unread request
                # bytes; both EOF and reset are valid fail-closed outcomes.
                with contextlib.suppress(ConnectionResetError):
                    assert await asyncio.wait_for(reader.read(), 5) == b""
            writer.close()
            with contextlib.suppress(ConnectionResetError):
                await writer.wait_closed()
            await asyncio.wait_for(done.wait(), 10)
        finally:
            server.close()
            await server.wait_closed()
        assert all(child.returncode is not None for child in children)
        assert len(children) == (1 if backend == "up" else 0)

    asyncio.run(exercise())


def test_client_reset_reaps_a_helper_blocked_without_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    monkeypatch.setattr(host, "interop_environment", os.environ.copy)
    original_spawn = asyncio.create_subprocess_exec
    children = []

    async def exercise():
        started = asyncio.Event()
        done = asyncio.Event()
        slots = asyncio.Semaphore(1)

        async def spawn(*args, **kwargs):
            process = await original_spawn(
                sys.executable, "-u", "-c", "import time; time.sleep(300)", **kwargs
            )
            children.append(process)
            started.set()
            return process

        async def handle(reader, writer):
            try:
                await host._relay(reader, writer, slots)
            finally:
                done.set()

        monkeypatch.setattr(host.asyncio, "create_subprocess_exec", spawn)
        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        client = socket.socket()
        try:
            client.connect(("127.0.0.1", server.sockets[0].getsockname()[1]))
            client.sendall(b"request")
            await asyncio.wait_for(started.wait(), 5)
            # Use closesocket without asyncio's shutdown-before-close path:
            # a graceful FIN deliberately keeps the response half alive.
            linger = struct.pack("HH" if os.name == "nt" else "ii", 1, 0)
            client.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, linger)
            client.close()
            await asyncio.wait_for(done.wait(), 10)
            assert len(children) == 1 and children[0].returncode is not None
            assert slots._value == 1
        finally:
            client.close()
            server.close()
            # Surface assertion/time-out failures, never hang in Server cleanup.
            for child in children:
                if child.returncode is None:
                    child.kill()
                    await asyncio.wait_for(child.wait(), 5)
            await asyncio.wait_for(server.wait_closed(), 10)

    asyncio.run(exercise())


def test_service_shutdown_reaps_active_helper_before_server_closure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    monkeypatch.setattr(host, "interop_environment", os.environ.copy)
    state = tmp_path / "bridge-state.json"
    monkeypatch.setattr(host, "_state_path", lambda: state)
    original_server = asyncio.start_server
    original_spawn = asyncio.create_subprocess_exec
    servers, children = [], []

    async def exercise():
        started = asyncio.Event()

        async def start(callback, address, port, **kwargs):
            server = await original_server(callback, address, 0, **kwargs)
            servers.append(server)
            return server

        async def spawn(*args, **kwargs):
            process = await original_spawn(
                sys.executable, "-u", "-c", "import time; time.sleep(300)", **kwargs
            )
            children.append(process)
            started.set()
            return process

        monkeypatch.setattr(host.asyncio, "start_server", start)
        monkeypatch.setattr(host.asyncio, "create_subprocess_exec", spawn)
        service = asyncio.create_task(host.serve())
        client = None
        try:
            async with asyncio.timeout(5):
                while not state.exists():
                    await asyncio.sleep(0.01)
            assert len(servers) == 2
            _reader, client = await asyncio.open_connection(
                "127.0.0.1", servers[0].sockets[0].getsockname()[1]
            )
            client.write(b"request")
            await client.drain()
            await asyncio.wait_for(started.wait(), 5)
            service.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(service, 15)
            assert not state.exists()
            assert len(children) == 1 and children[0].returncode is not None
            assert all(not server.is_serving() for server in servers)
        finally:
            if client:
                client.close()
                with contextlib.suppress(OSError):
                    await client.wait_closed()
            for child in children:
                if child.returncode is None:
                    child.kill()
                    await asyncio.wait_for(child.wait(), 5)
            if not service.done():
                service.cancel()
                with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                    await asyncio.wait_for(service, 15)

    asyncio.run(exercise())


def test_service_closes_client_cancelled_before_handler_first_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "wsl-client")
    state = tmp_path / "early-cancel-state.json"
    monkeypatch.setattr(host, "_state_path", lambda: state)
    callbacks, entered = [], []
    original_create = asyncio.create_task

    class Writer:
        closed = False

        def close(self):
            self.closed = True

    writer = Writer()

    class Server:
        def close(self):
            pass

        async def wait_closed(self):
            assert writer.closed

    async def start(callback, *args, **kwargs):
        callbacks.append(callback)
        return Server()

    async def blocked_relay(*args):
        entered.append(True)
        await asyncio.Future()

    def create(coroutine):
        task = original_create(coroutine)
        task.cancel()  # before the coroutine can install its finally
        return task

    monkeypatch.setattr(host.asyncio, "start_server", start)
    monkeypatch.setattr(host.asyncio, "create_task", create)
    monkeypatch.setattr(host, "_relay", blocked_relay)

    async def exercise():
        service = original_create(host.serve())
        try:
            async with asyncio.timeout(5):
                while not state.exists():
                    await asyncio.sleep(0.01)
            callbacks[0](None, writer)
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            assert not entered and writer.closed
            service.cancel()
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(service, 2)
            assert not state.exists()
        finally:
            writer.close()
            if not service.done():
                service.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.wait_for(service, 2)

    asyncio.run(exercise())


def test_doctor_inspects_only_running_distros_and_never_repairs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(host, "host_policy", lambda: "windows-full")
    monkeypatch.setattr(host, "windows_snapshot", _windows)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        names = (
            "Ubuntu\n"
            if "--running" in command
            else "Ubuntu\nStopped\ndocker-desktop\n"
        )
        return subprocess.CompletedProcess(command, 0, names.encode("utf-16-le"), b"")

    def run_text(command, **kwargs):
        calls.append(command)
        output = "/mapped/checker.py" if "wslpath" in command else json.dumps(_wsl())
        return subprocess.CompletedProcess(command, 0, output, "")

    monkeypatch.setattr(host.subprocess, "run", run)
    monkeypatch.setattr(host, "_run", run_text)
    rows = host.check()
    assert any(
        row[0] == "WARN" and "Stopped" in row[2] and "uninspected" in row[2]
        for row in rows
    )
    assert not any(
        "Stopped" in command or "docker-desktop" in command for command in calls
    )
    assert not any(
        arg
        in {"--install", "install", "enable", "start", "stop", "restart", "uninstall"}
        for command in calls
        for arg in command
    )
