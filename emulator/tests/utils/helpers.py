"""Helper functions for tests using the Result type."""

import asyncio
import json
import os
import platform
import re
import socket
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import docker
import pytest
from aiohttp import ClientSession
from docker.errors import DockerException, NotFound
from docker.models.containers import Container

from tests.utils.result import Error, Ok, Result
from tests.utils.run_journal import (
    RUN_LABEL,
    RUN_MANIFEST_ENV,
    _endpoint_text,
    begin_creation,
    bind_endpoint,
    canonical_endpoint,
    complete_creation,
    journal_path,
    observe_image,
    prepare_image,
    record_image_receipt,
    unix_socket_path,
)


def get_container(client: docker.DockerClient, name: str) -> Result[Container, str]:
    """Get a container by name."""
    try:
        container = owned_container(client, name)
        return Ok(container)
    except NotFound:
        return Error(f"Container '{name}' not found.")
    except Exception as e:
        return Error(f"Error getting container '{name}': {e}")


async def wait_for_http(
    client: ClientSession, url: str, retries: int = 30
) -> Result[bool, str]:
    """Wait for an HTTP endpoint to be available."""
    url = host_endpoint(url)
    last_error = ""
    for _ in range(retries):
        try:
            async with client.get(url) as response:
                if response.status == 200:
                    return Ok(True)
                last_error = f"Status {response.status}"
        except Exception as e:
            last_error = str(e)
        await asyncio.sleep(1)
    return Error(f"HTTP endpoint {url} not accessible: {last_error}")


def wait_for_tcp(host: str, port: int, retries: int = 30) -> Result[bool, str]:
    """Wait for a TCP port to be open (synchronous)."""
    port = host_port(port)
    last_error = ""
    for _ in range(retries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return Ok(True)
            last_error = f"Connect result: {result}"
        except Exception as e:
            last_error = str(e)
        time.sleep(1)
    return Error(f"TCP endpoint {host}:{port} not accessible: {last_error}")


def skip_unless_container_running(name: str) -> None:
    """pytest.skip the calling test unless a container named `name` is running.

    lite-default (ADR 0016 / PR #120): capability emulators (search/graph/vector/
    bigtable/inspect/ml) sit behind compose profiles and are NOT started by the
    default lite stack, so their integration tests must skip rather than fail when
    the container is absent. Mirrors the e2e `require_services` fixture for the
    non-e2e suite.
    """
    client = podman_client()
    try:
        require_running(client, [name])
    finally:
        client.close()


def run_manifest() -> dict:
    path = os.environ.get(RUN_MANIFEST_ENV)
    if not path:
        if os.environ.get("DOTFILES_E2E_REQUIRED") == "1":
            raise RuntimeError(
                f"Required tests need {RUN_MANIFEST_ENV}; prepare an isolated run first"
            )
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def container_name(name: str) -> str:
    manifest = run_manifest()
    if not manifest:
        return name
    names = manifest["containers"]
    if name in names.values():
        return name
    if name not in names:
        raise RuntimeError(f"Container {name!r} is not declared by the run manifest")
    return names[name]


def owned_container(client: docker.DockerClient, name: str) -> Container:
    container = client.containers.get(container_name(name))
    manifest = run_manifest()
    if manifest.get("run_id"):
        labels = (container.attrs.get("Config") or {}).get("Labels") or {}
        if labels.get(RUN_LABEL) != manifest["run_id"]:
            raise RuntimeError(f"Container ownership mismatch for {name}")
    return container


def host_port(port: int) -> int:
    manifest = run_manifest()
    if not manifest:
        return port
    ports = manifest["host_ports"]
    if str(port) in ports:
        return int(ports[str(port)])
    if port in ports.values():
        return port
    raise RuntimeError(f"Port {port} is not declared by the run manifest")


def host_endpoint(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname in {"localhost", "127.0.0.1"} and parsed.port:
        return url.replace(f":{parsed.port}", f":{host_port(parsed.port)}", 1)
    return url


def service_address(
    container: str, canonical_port: int, variable: str
) -> tuple[str, int]:
    """Resolve a configurable probe only against its own selected service."""
    manifest = run_manifest()
    override = os.environ.get(variable, str(canonical_port))
    if not manifest:
        return "localhost", int(override)
    service = {
        "mlflow-server": "emulator/mlflow",
        "pgadapter-emulator": "emulator/pgadapter",
        "postgres-18": "emulator/postgres",
    }.get(container)
    if service is None or manifest.get("services", {}).get(service) != container:
        raise RuntimeError(f"Missing manifest service for {container}")
    if container not in manifest.get("selected_containers", []):
        pytest.skip(f"Deliberately unselected services: {container}")
    allocated = manifest.get("host_ports", {}).get(str(canonical_port))
    if type(allocated) is not int or not 1 <= allocated <= 65535:
        raise RuntimeError(f"Invalid manifest port for {container}")
    if not re.fullmatch(r"[0-9]{1,5}", override) or int(override) not in {
        canonical_port,
        allocated,
    }:
        raise RuntimeError(
            f"Conflicting {variable}; use this service's canonical or allocated port"
        )
    return "127.0.0.1", allocated


def mlflow_endpoint() -> str:
    host, port = service_address("mlflow-server", 5252, "MLFLOW_PORT")
    return f"http://{host}:{port}"


def require_running(client: docker.DockerClient, names: list[str]) -> None:
    manifest = run_manifest()
    selected = set(manifest.get("selected_containers", []))
    unselected = [name for name in names if manifest and name not in selected]
    if unselected:
        pytest.skip(f"Deliberately unselected services: {', '.join(unselected)}")
    running = {c.name for c in client.containers.list()}
    missing = [name for name in names if container_name(name) not in running]
    if missing:
        message = f"Required Podman containers not running: {', '.join(missing)}"
        if os.environ.get("DOTFILES_E2E_REQUIRED") == "1":
            pytest.fail(message)
        pytest.skip(message)
    for name in names:
        owned_container(client, name)


def build_test_image(client: docker.DockerClient, path: str) -> str:
    manifest = run_manifest()
    if not manifest:
        raise RuntimeError("Test image builds require an isolated run manifest")
    snapshot = Path(manifest["snapshot"]).resolve()
    context = (snapshot / "emulator" / path).resolve()
    if not context.is_relative_to(snapshot):
        raise RuntimeError("Build context escapes tracked snapshot")
    manifest_path = journal_path(manifest)
    endpoint = selected_podman_endpoint()
    bind_endpoint(manifest_path, endpoint)
    tag = f"localhost/{manifest['run_id']}/build-{uuid.uuid4().hex}:test"
    prepare_image(client, manifest_path, tag, endpoint)
    try:
        image, _ = client.images.build(
            path=str(context),
            tag=tag,
            rm=True,
            labels={RUN_LABEL: manifest["run_id"]},
        )
    except BaseException:
        observe_image(client, manifest_path, tag, allow_absent=True)
        raise
    record_image_receipt(client, manifest_path, tag, expected=image.id)
    return image.id


def run_test_image(
    client: docker.DockerClient, image: str, command: str, env: dict[str, str]
) -> str:
    manifest = run_manifest()
    if not manifest or not image.startswith("sha256:"):
        raise RuntimeError(
            "Test execution requires a manifest and an immutable image ID"
        )
    path = journal_path(manifest)
    endpoint = selected_podman_endpoint()
    bind_endpoint(path, endpoint)
    creation = begin_creation(path, endpoint, "container")
    container = client.containers.run(
        image=image,
        command=["sh", "-lc", command],
        environment=env,
        network=manifest["network"],
        detach=True,
        stdout=True,
        stderr=True,
        labels={RUN_LABEL: manifest["run_id"]},
    )
    container_id = container.id
    container.reload()
    if (
        not isinstance(container_id, str)
        or not container_id
        or container.id != container_id
        or (container.attrs.get("Config") or {}).get("Labels", {}).get(RUN_LABEL)
        != manifest["run_id"]
    ):
        raise RuntimeError("Container creation receipt identity/ownership mismatch")
    complete_creation(path, creation, container_id)
    try:
        status = container.wait(timeout=300)
        logs = container.logs(stdout=True, stderr=True).decode(
            "utf-8", errors="replace"
        )
        if status["StatusCode"] != 0:
            raise RuntimeError(
                f"Test container exited with status {status['StatusCode']}: {logs}"
            )
        return logs
    finally:
        container.reload()
        if (
            container.attrs["Config"].get("Labels", {}).get(RUN_LABEL)
            != manifest["run_id"]
        ):
            raise RuntimeError("Refusing to remove unowned CLI container")
        container.remove(force=True)


def podman_command(args: list[str], *, endpoint: str | None = None) -> str:
    env = dict(os.environ)
    env.pop("DOCKER_HOST", None)
    env["PODMAN_COMPOSE_PROVIDER"] = "podman-compose"
    if endpoint:
        env["CONTAINER_HOST"] = endpoint
        env.pop("CONTAINER_CONNECTION", None)
    try:
        result = subprocess.run(
            ["podman", *args],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Podman CLI >=5 is required; use the repository's native Podman installer separately"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Podman discovery failed: {exc.stderr}; activate the selected socket/machine separately; no automatic startup"
        ) from exc
    return result.stdout


def _minimum_version(value: str, subject: str) -> None:
    match = re.search(r"(?:^|\s)(\d+)\.", value)
    if not match or int(match[1]) < 5:
        raise RuntimeError(
            f"{subject} requires Podman >=5, got {value!r}; update separately"
        )


def selected_podman_endpoint() -> str:
    """Resolve only the explicit socket or selected connection, never DOCKER_HOST."""
    _minimum_version(podman_command(["--version"]), "CLI")
    explicit = os.environ.get("CONTAINER_HOST")
    if explicit is not None:
        if explicit.startswith("npipe:") and platform.system() != "Windows":
            raise RuntimeError(
                "CONTAINER_HOST pipe requires Windows; no TCP/SSH fallback"
            )
        return canonical_endpoint(explicit)
    connections = json.loads(
        podman_command(["system", "connection", "list", "--format", "json"])
    )
    name = os.environ.get("CONTAINER_CONNECTION")
    selected = (
        [c for c in connections if c.get("Name") == name]
        if name
        else [c for c in connections if c.get("Default") is True]
    )
    if not connections and not name and platform.system() == "Linux":
        info = json.loads(podman_command(["info", "--format", "json"]))
        path = info.get("host", {}).get("remoteSocket", {}).get("path", "")
        return "unix://" + unix_socket_path(path)
    if len(selected) != 1:
        raise RuntimeError(
            "Select exactly one Podman connection; activate its socket/machine separately"
        )
    connection = selected[0]
    uri = connection["URI"]
    _endpoint_text(uri)
    if (
        uri.startswith("unix:") or uri.startswith("/")
    ) and platform.system() == "Linux":
        return canonical_endpoint(uri)
    if platform.system() not in {"Darwin", "Windows"} or not uri.startswith("ssh://"):
        raise RuntimeError(
            f"Unsupported selected Podman endpoint {uri!r}; use an explicit local socket"
        )
    return _machine_endpoint(connection)


def _machine_endpoint(connection: dict) -> str:
    _endpoint_text(connection["URI"])
    parsed = urlparse(connection["URI"])
    if parsed.query or parsed.fragment or parsed.params:
        raise RuntimeError("Invalid selected machine connection URI")
    rootful = parsed.username == "root"
    machine_name = (
        connection["Name"].removesuffix("-root") if rootful else connection["Name"]
    )
    machines = json.loads(podman_command(["machine", "inspect", machine_name]))
    matches = []
    for machine in machines:
        ssh = machine.get("SSHConfig", {})
        rootful = machine.get("Rootful", False)
        expected_name = machine["Name"] + ("-root" if rootful else "")
        if (
            connection["Name"] == expected_name
            and parsed.hostname in {"localhost", "127.0.0.1"}
            and parsed.port == ssh.get("Port")
            and connection.get("Identity") == ssh.get("IdentityPath")
            and parsed.username == ("root" if rootful else ssh.get("RemoteUsername"))
        ):
            matches.append(machine)
    if len(matches) != 1:
        raise RuntimeError(
            "Selected connection does not uniquely match a Podman machine; refusing default-machine guessing"
        )
    _verify_machine_socket(connection, parsed.path)
    info = matches[0].get("ConnectionInfo", {})
    if platform.system() == "Windows":
        path = info.get("PodmanPipe", {}).get("Path")
        if path:
            _endpoint_text(path)
            return canonical_endpoint(
                "npipe:////./pipe/" + path.replace("\\", "/").split("/")[-1]
            )
    else:
        path = info.get("PodmanSocket", {}).get("Path")
        if path:
            return "unix://" + unix_socket_path(path)
    raise RuntimeError(
        "Selected machine has no host-forwarded API socket/pipe; start forwarding separately"
    )


def _verify_machine_socket(connection: dict, socket_path: str) -> None:
    info = json.loads(
        podman_command(["--connection", connection["Name"], "info", "--format", "json"])
    )
    reported = info.get("host", {}).get("remoteSocket", {}).get("path")
    if unix_socket_path(reported) != unix_socket_path(socket_path):
        raise RuntimeError(
            "Selected machine API socket differs from the selected connection; refusing a different inventory"
        )


def podman_client(*, endpoint: str | None = None) -> docker.DockerClient:
    """Docker SDK is a protocol client, exclusively for the selected Podman API."""
    selected = canonical_endpoint(selected_podman_endpoint())
    endpoint = endpoint or run_manifest().get("endpoint")
    if endpoint is not None and canonical_endpoint(endpoint) != selected:
        raise RuntimeError("Selected Podman endpoint changed before client creation")
    endpoint = selected
    try:
        client = docker.DockerClient(base_url=endpoint, version="1.41")
    except DockerException as exc:
        raise RuntimeError(
            f"Cannot create Podman API client for {endpoint}: {exc}; Windows pipes require the locked pywin32 dependency"
        ) from exc
    try:
        version = client.version()
        engines = [
            c for c in version.get("Components", []) if c.get("Name") == "Podman Engine"
        ]
        if len(engines) != 1:
            raise RuntimeError(
                "Selected API is not positively identified as Podman Engine"
            )
        _minimum_version(engines[0].get("Version", ""), "Server")
        client.ping()
    except Exception as exc:
        client.close()
        raise RuntimeError(
            f"Podman API at {endpoint}: {exc}; activate the selected socket/machine separately; no automatic startup"
        ) from exc
    except BaseException:
        client.close()
        raise
    return client
