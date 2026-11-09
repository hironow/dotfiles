"""Tracked-snapshot Compose lifecycle for emulator/telemetry acceptance tests.

The manifest is the only resource/endpoint authority. SIGKILL can leave labelled
resources; a later cleanup with this same manifest recovers them, never by port.
"""

import argparse
import copy
import json
import os
import platform
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import ExitStack
from graphlib import CycleError, TopologicalSorter
from os import open as open_descriptor
from pathlib import Path, PurePosixPath
from types import FrameType
from typing import NoReturn

import docker
import yaml
from docker.errors import NotFound
from docker.models.containers import Container
from docker.models.resource import Model

from tests.utils import helpers
from tests.utils.helpers import RUN_LABEL, podman_client, selected_podman_endpoint
from tests.utils.run_journal import (
    begin_creation,
    bind_endpoint,
    canonical_endpoint,
    cleanup_images,
    close_creations,
    complete_creation,
    finish_cleanup,
    journal_path,
    mutate_manifest,
    prepare_image,
    record_image_receipt,
)


def _mutate_run(manifest: dict, change) -> None:
    def checked(current):
        if current["run_id"] != manifest["run_id"]:
            raise RuntimeError("Manifest run identity changed")
        change(current)

    latest = mutate_manifest(journal_path(manifest), checked)
    manifest.clear()
    manifest.update(latest)


def _snapshot_stat(path: Path, *, directory: bool) -> os.stat_result:
    try:
        metadata = path.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or path.is_junction()
            or getattr(metadata, "st_file_attributes", 0) & 0x400
            or not (
                stat.S_ISDIR(metadata.st_mode)
                if directory
                else stat.S_ISREG(metadata.st_mode)
            )
        ):
            raise RuntimeError(
                f"Snapshot refuses links/reparse or nonregular paths: {path}"
            )
        return metadata
    except OSError as exc:
        raise RuntimeError(f"Snapshot cannot validate {path}: {exc}") from exc


def _snapshot_source(source: Path) -> tuple[Path, dict]:
    # absolute(), unlike resolve(), retains link evidence in the original input.
    source = source.absolute()
    metadata = {}
    for path in [*reversed(source.parents), source]:
        if path.name and path.name != "..":
            _snapshot_name(path.name)
        metadata[path] = _snapshot_stat(path, directory=True)
    # Only after validating the original lexical chain may '..' be canonicalized.
    return source.resolve(), {path.resolve(): value for path, value in metadata.items()}


def _snapshot_name(name: str) -> list[str]:
    parts = name.split("/")
    for part in parts:
        if (
            not part
            or part in {".", ".."}
            or part.casefold() == ".git"
            or part.endswith((".", " "))
            or any(
                ord(char) < 32 or ord(char) == 127 or char in '\\:*?"<>|'
                for char in part
            )
            or re.fullmatch(
                r"(?i:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³]|git~[1-9][0-9]*)(?:\..*)?",
                part,
            )
        ):
            raise RuntimeError(
                f"Snapshot refuses reserved/traversing tracked name: {name!r}"
            )
    return parts


def _snapshot_identity(actual: os.stat_result, expected: os.stat_result) -> None:
    fields = ("st_dev", "st_ino", "st_mode")
    if stat.S_ISREG(expected.st_mode):
        fields += ("st_size", "st_mtime_ns")
    if any(getattr(actual, field) != getattr(expected, field) for field in fields):
        raise RuntimeError("Snapshot source identity changed after validation")


def _copy_snapshot_file(original: Path, target: Path, metadata: dict) -> None:
    with ExitStack() as stack:
        if os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
            directory = open_descriptor(
                original.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            )
            stack.callback(os.close, directory)
            _snapshot_identity(os.fstat(directory), metadata[Path(original.anchor)])
            parent = Path(original.anchor)
            for part in original.parts[1:-1]:
                parent /= part
                directory = open_descriptor(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                stack.callback(os.close, directory)
                _snapshot_identity(os.fstat(directory), metadata[parent])
            descriptor = open_descriptor(
                original.name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
            stream = stack.enter_context(os.fdopen(descriptor, "rb"))
        else:
            # Portable fail-closed validation, not a malicious concurrent-writer fence.
            for parent in reversed(original.parents):
                _snapshot_identity(
                    _snapshot_stat(parent, directory=True), metadata[parent]
                )
            _snapshot_identity(
                _snapshot_stat(original, directory=False), metadata[original]
            )
            stream = stack.enter_context(original.open("rb"))
        _snapshot_identity(os.fstat(stream.fileno()), metadata[original])
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            shutil.copyfileobj(stream, output)
        _snapshot_identity(os.fstat(stream.fileno()), metadata[original])
        target.chmod(stat.S_IMODE(metadata[original].st_mode))
        os.utime(
            target, ns=(metadata[original].st_atime_ns, metadata[original].st_mtime_ns)
        )


def tracked_snapshot(source: Path, snapshot: Path) -> None:
    """Prevalidate ALL tracked components, then copy working bytes with identities.

    No untracked/gitlink content or index blobs; no concurrent malicious-writer guarantee.
    """
    source, metadata = _snapshot_source(source)
    entries = (
        subprocess.run(
            ["git", "-C", str(source), "ls-files", "--stage", "-z"],
            check=True,
            capture_output=True,
        )
        .stdout.decode("utf-8")
        .split("\0")
    )
    files = []
    for entry in filter(None, entries):
        header, name = entry.split("\t", 1)
        mode, _, stage = header.split()
        parts = _snapshot_name(name)
        if stage != "0":
            raise RuntimeError("Snapshot refuses unresolved index entries")
        if mode == "160000":
            ancestor = source
            for part in parts[:-1]:
                ancestor /= part
                metadata[ancestor] = _snapshot_stat(ancestor, directory=True)
            continue
        if mode not in {"100644", "100755"}:
            raise RuntimeError(f"Snapshot refuses nonregular index mode: {name}")
        original = source
        for index, part in enumerate(parts):
            original /= part
            metadata[original] = _snapshot_stat(
                original, directory=index < len(parts) - 1
            )
        files.append(original)
    snapshot.mkdir(parents=True)
    for original in files:
        _copy_snapshot_file(original, snapshot / original.relative_to(source), metadata)


def engine_path(path: Path, source: Path, env: dict[str, str]) -> str:
    workspace = env.get("LOCAL_WORKSPACE_FOLDER")
    if not workspace:
        if (
            platform.system() == "Windows"
            or env.get("CONTAINER_HOST") == "unix:///run/dotfiles-podman/podman.sock"
        ):
            raise RuntimeError(
                "Nested binds require LOCAL_WORKSPACE_FOLDER and disposable-checkout fence"
            )
        return str(path.resolve())
    if env.get("DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT") != "1":
        raise RuntimeError(
            "Nested binds require DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT=1"
        )
    if not workspace.startswith("/"):
        raise RuntimeError(
            "LOCAL_WORKSPACE_FOLDER must be an absolute engine-side Unix path"
        )
    relative = path.resolve().relative_to(source.resolve())
    return str(PurePosixPath(workspace) / relative.as_posix())


def _default(value: str) -> str:
    return re.sub(r"\$\{[A-Z0-9_]+:-([^}]+)\}", r"\1", value)


def _bind_source(source: str, stack: str, manifest: dict, readonly: bool) -> str:
    snapshot = Path(manifest["snapshot"])
    original = (snapshot / stack / source).resolve()
    if not original.is_relative_to(snapshot):
        raise RuntimeError(f"Bind escapes tracked snapshot: {source}")
    local = original
    if not readonly:
        local = snapshot / ".run-data" / stack / source.removeprefix("./")
        local.parent.mkdir(parents=True, exist_ok=True)
        if original.is_file():
            shutil.copy2(original, local)
        elif original.is_dir():
            shutil.copytree(original, local, dirs_exist_ok=True)
        else:
            local.mkdir(parents=True, exist_ok=True)
    if readonly and not original.exists():
        raise RuntimeError(f"Read-only bind missing from tracked snapshot: {source}")
    translated = engine_path(local, Path(manifest["source"]), manifest["bind_env"])
    manifest["binds"].append(
        {"source": str(local), "engine_source": translated, "readonly": readonly}
    )
    return translated


def _render_volumes(service: dict, stack: str, manifest: dict) -> None:
    mounts = []
    for entry in service.get("volumes", []):
        if not isinstance(entry, str):
            raise RuntimeError(
                "Unsupported long-form bind; extend renderer explicitly before use"
            )
        source, target, *options = entry.split(":")
        if source.startswith("."):
            source = _bind_source(source, stack, manifest, "ro" in options)
        elif source not in manifest["volume_keys"][stack]:
            raise RuntimeError(f"Undeclared volume {source}")
        mounts.append(":".join([source, target, *options]))
    if mounts:
        service["volumes"] = mounts


def _allocate_port(manifest: dict, reservations: list[socket.socket]) -> int:
    # Never allocate another canonical port: endpoint translation stays unambiguous.
    for _ in range(100):
        reservation = socket.socket()
        reservation.bind(("127.0.0.1", 0))
        allocated = reservation.getsockname()[1]
        if allocated not in manifest["canonical_ports"]:
            reservations.append(reservation)
            return allocated
        reservation.close()
    raise RuntimeError("Could not allocate an isolated noncanonical host port")


def _render_ports(
    service: dict, manifest: dict, reservations: list[socket.socket]
) -> None:
    ports = []
    for entry in service.get("ports", []):
        match = re.fullmatch(r"127\.0\.0\.1:(\d+):(\d+)(/\w+)?", _default(entry))
        if not match:
            raise RuntimeError(f"Unsupported port declaration: {entry}")
        original, target, protocol = match.groups()
        if protocol and protocol != "/tcp":
            raise RuntimeError(f"Unsupported port protocol: {entry}")
        allocated = _allocate_port(manifest, reservations)
        if original in manifest["host_ports"]:
            raise RuntimeError(f"Ambiguous canonical published port {original}")
        manifest["host_ports"][original] = allocated
        ports.append(f"127.0.0.1:{allocated}:{target}")
    if ports:
        service["ports"] = ports


def _render_build(service: dict, key: str, manifest: dict) -> None:
    spec = service["build"]
    if isinstance(spec, str):
        build: dict = {"context": spec}
    elif isinstance(spec, dict):
        build = copy.deepcopy(spec)
    else:
        raise RuntimeError("Unsupported Compose build specification")
    build_labels = build.get("labels", {})
    if isinstance(build_labels, list):
        pairs = [
            label.split("=", 1) for label in build_labels if isinstance(label, str)
        ]
        if len(pairs) != len(build_labels) or any(len(pair) != 2 for pair in pairs):
            raise RuntimeError("Malformed Compose build labels")
        build_labels = dict(pairs)
    if not isinstance(build_labels, dict):
        raise RuntimeError("Malformed Compose build labels")
    build["labels"] = {**build_labels, RUN_LABEL: manifest["run_id"]}
    service["build"] = build
    service["image"] = f"localhost/{manifest['run_id']}/{key.replace('/', '-')}:test"
    manifest.setdefault("build_tags", {})[key] = service["image"]


def render_compose(
    config: dict, stack: str, manifest: dict, reservations: list[socket.socket]
) -> dict:
    """Render every canonical declaration; reject unsupported forms fail-closed."""
    result = copy.deepcopy(config)
    labels = {RUN_LABEL: manifest["run_id"]}
    manifest["volume_keys"][stack] = list(result.get("volumes", {}))
    for key in result.get("volumes", {}):
        name = f"{manifest['run_id']}-{stack}-{key}"
        result["volumes"][key] = {"name": name, "labels": labels}
        manifest["volumes"].append(name)
    for key in result.get("networks", {}):
        result["networks"][key] = {"name": manifest["network"], "external": True}
    for name, service in result["services"].items():
        canonical = service.get("container_name", name)
        unique = f"{manifest['run_id']}-{stack}-{name}"
        manifest["containers"][canonical] = unique
        manifest["services"][f"{stack}/{name}"] = canonical
        service["container_name"] = unique
        service["labels"] = {**service.get("labels", {}), **labels}
        service["restart"] = "no"
        service["networks"] = {"default": {"aliases": sorted({name, canonical})}}
        if "build" in service:
            _render_build(service, f"{stack}/{name}", manifest)
        _render_volumes(service, stack, manifest)
        _render_ports(service, manifest, reservations)
    # MCP browser origins must use the same remapped published port.
    for service in result["services"].values():
        environment = service.get("environment", [])
        if isinstance(environment, list):
            service["environment"] = [
                re.sub(
                    r"\$\{MCP_INSPECTOR_PORT:-6274\}",
                    str(manifest["host_ports"].get("6274", 6274)),
                    item,
                )
                for item in environment
            ]
    return result


def _postgres_connection(service: dict, manifest: dict) -> dict:
    environment = service.get("environment", {})
    if isinstance(environment, list):
        pairs = [item.split("=", 1) for item in environment if isinstance(item, str)]
        if (
            len(pairs) != len(environment)
            or any(len(pair) != 2 for pair in pairs)
            or len({pair[0] for pair in pairs}) != len(pairs)
        ):
            raise RuntimeError("Malformed PostgreSQL Compose environment")
        environment = dict(pairs)
    if not isinstance(environment, dict):
        raise RuntimeError("Malformed PostgreSQL Compose environment")
    record = {"host": "127.0.0.1", "port": manifest["host_ports"].get("5433")}
    if service.get("container_name") != "postgres-18" or "127.0.0.1:5433:5432" not in [
        _default(port) for port in service.get("ports", [])
    ]:
        raise RuntimeError("Expected canonical PostgreSQL service and published port")
    for key, field in (
        ("POSTGRES_USER", "user"),
        ("POSTGRES_PASSWORD", "password"),
        ("POSTGRES_DB", "database"),
    ):
        value = environment.get(key)
        if not isinstance(value, str) or not value or "$" in value:
            raise RuntimeError(f"Missing or unresolved canonical {key}")
        record[field] = value
    if type(record["port"]) is not int or not 1 <= record["port"] <= 65535:
        raise RuntimeError("Missing allocated PostgreSQL port")
    return record


def _selected(config: dict, requested: list[str]) -> list[str]:
    selected = set(requested)
    if not selected <= config["services"].keys():
        raise RuntimeError(f"Unknown services: {selected - config['services'].keys()}")
    pending = list(selected)
    while pending:
        service = pending.pop()
        for dependency in config["services"][service].get("depends_on", []):
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
    return sorted(selected)


def prepare_run(
    source: Path, path: Path, services: list[str], *, telemetry: bool = False
) -> dict:
    if path.exists():
        raise RuntimeError(
            "Manifest already exists; do not overwrite a recoverable run"
        )
    source, _ = _snapshot_source(source)
    run_id = "dotfiles-" + uuid.uuid4().hex
    env = dict(os.environ)
    engine_path(source, source, env)
    if env.get("LOCAL_WORKSPACE_FOLDER"):
        # The translated snapshot must stay inside the explicitly disposable checkout.
        engine_path(source, source, env)
        parent = source / ".podman-runs" / run_id
        parent.mkdir(parents=True)
    else:
        parent = Path(tempfile.mkdtemp(prefix=run_id + "-"))
    snapshot = parent.resolve() / "snapshot"
    tracked_snapshot(source, snapshot)
    manifest = {
        "run_id": run_id,
        "manifest_path": str(path.resolve()),
        "images": {},
        "build_tags": {},
        "creations": {},
        "source": str(source),
        "snapshot": str(snapshot),
        "bind_env": {
            key: env[key]
            for key in (
                "LOCAL_WORKSPACE_FOLDER",
                "DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT",
                "CONTAINER_HOST",
            )
            if key in env
        },
        "network": run_id + "-otel",
        "containers": {},
        "services": {},
        "volumes": [],
        "volume_keys": {},
        "binds": [],
        "host_ports": {},
        "selected_containers": [],
        "stacks": {},
        "resources": {"containers": [], "networks": [], "volumes": []},
    }
    configs = {
        stack: yaml.safe_load(
            (snapshot / stack / "compose.yaml").read_text(encoding="utf-8")
        )
        for stack in (["emulator", "telemetry"] if telemetry else ["emulator"])
    }
    manifest["canonical_ports"] = [
        int(_default(port).split(":")[1])
        for config in configs.values()
        for service in config["services"].values()
        for port in service.get("ports", [])
    ]
    reservations = []
    try:
        for stack, config in configs.items():
            requested = services if stack == "emulator" else list(config["services"])
            selected = _selected(config, requested)
            rendered = render_compose(config, stack, manifest, reservations)
            if stack == "emulator" and "postgres" in selected:
                manifest["postgres_connection"] = _postgres_connection(
                    config["services"]["postgres"], manifest
                )
            manifest["selected_containers"].extend(
                manifest["services"][f"{stack}/{s}"] for s in selected
            )
            compose = snapshot / stack / "compose.isolated.yaml"
            compose.write_text(
                yaml.safe_dump(rendered, sort_keys=False), encoding="utf-8"
            )
            manifest["stacks"][stack] = {"compose": str(compose), "selected": selected}
        mutate_manifest(path, lambda _: None, initial=manifest)
    finally:
        for reservation in reservations:
            reservation.close()
    return manifest


def _labels(resource: Model) -> dict:
    attrs = resource.attrs or {}
    return attrs.get("Labels") or (attrs.get("Config") or {}).get("Labels") or {}


def discover_resources(client: docker.DockerClient, manifest: dict) -> None:
    def discover(current):
        for kind in ("containers", "networks", "volumes"):
            collection = getattr(client, kind)
            kwargs = {"filters": {"label": f"{RUN_LABEL}={current['run_id']}"}}
            if kind == "containers":
                kwargs["all"] = True
            for resource in collection.list(**kwargs):
                if (
                    not resource.id
                    or _labels(resource).get(RUN_LABEL) != current["run_id"]
                ):
                    raise RuntimeError(
                        "Engine returned missing identity or an unowned resource for ownership filter"
                    )
                if resource.id not in current["resources"][kind]:
                    current["resources"][kind].append(resource.id)

    _mutate_run(manifest, discover)


def _checked_container(
    client: docker.DockerClient, resource_id: str, run_id: str
) -> Container | None:
    if not isinstance(resource_id, str) or not re.fullmatch(
        r"[0-9a-f]{64}", resource_id
    ):
        raise RuntimeError(f"Invalid full container ID: {resource_id!r}")
    try:
        resource = client.containers.get(resource_id)
        resource.reload()
    except NotFound:
        return None
    attrs = resource.attrs
    config = attrs.get("Config") if isinstance(attrs, dict) else None
    labels = config.get("Labels") if isinstance(config, dict) else None
    if (
        resource.id != resource_id
        or not isinstance(labels, dict)
        or labels.get(RUN_LABEL) != run_id
    ):
        raise RuntimeError(f"Refusing cleanup of unowned containers ID {resource_id}")
    return resource


def _container_cleanup_order(
    client: docker.DockerClient, manifest: dict, endpoint: str
) -> list[str]:
    run_id = manifest["run_id"]
    surviving = [
        resource_id
        for resource_id in manifest["resources"]["containers"]
        if _checked_container(client, resource_id, run_id) is not None
    ]
    dependencies = {}
    for resource_id in surviving:
        try:
            raw = helpers.podman_command(
                ["container", "inspect", resource_id], endpoint=endpoint
            )
        except RuntimeError:
            # Native stderr is not an absence receipt. Only a fresh SDK NotFound is.
            if _checked_container(client, resource_id, run_id) is None:
                continue
            raise
        try:
            rows = json.loads(raw)
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                f"Invalid native container inspect JSON: {resource_id}"
            ) from exc
        if (
            not isinstance(rows, list)
            or len(rows) != 1
            or not isinstance(rows[0], dict)
        ):
            raise RuntimeError(f"Ambiguous native container inspect: {resource_id}")
        row = rows[0]
        config = row.get("Config")
        labels = config.get("Labels") if isinstance(config, dict) else None
        parents = row.get("Dependencies")
        if (
            row.get("Id") != resource_id
            or not isinstance(labels, dict)
            or labels.get(RUN_LABEL) != run_id
            or not isinstance(parents, list)
            or any(
                not isinstance(parent, str) or not re.fullmatch(r"[0-9a-f]{64}", parent)
                for parent in parents
            )
            or len(set(parents)) != len(parents)
        ):
            raise RuntimeError(
                f"Invalid native container dependency metadata: {resource_id}"
            )
        dependencies[resource_id] = parents
    # External parents never acquire deletion authority through dependency metadata.
    owned_graph = {
        resource_id: [parent for parent in parents if parent in dependencies]
        for resource_id, parents in dependencies.items()
    }
    try:
        return list(reversed(tuple(TopologicalSorter(owned_graph).static_order())))
    except CycleError as exc:
        raise RuntimeError(
            "Owned container dependency cycle; refusing cleanup"
        ) from exc


def _cleanup_containers(
    client: docker.DockerClient, manifest: dict, endpoint: str
) -> None:
    order = _container_cleanup_order(client, manifest, endpoint)
    for resource_id in order:
        resource = _checked_container(client, resource_id, manifest["run_id"])
        if resource is not None:
            try:
                resource.remove(force=True)
            except NotFound:
                pass


def cleanup_run(client: docker.DockerClient, manifest: dict) -> None:
    """Remove exact recorded/discovered IDs only after rechecking ownership."""
    _mutate_run(manifest, lambda _: None)
    endpoint = selected_podman_endpoint() if manifest.get("endpoint") else None
    if endpoint and canonical_endpoint(endpoint) != canonical_endpoint(
        manifest["endpoint"]
    ):
        raise RuntimeError("Selected Podman endpoint changed before cleanup")
    incomplete = close_creations(journal_path(manifest))
    discover_resources(client, manifest)
    if manifest["resources"]["containers"]:
        _cleanup_containers(client, manifest, endpoint or selected_podman_endpoint())
    for kind in ("networks", "volumes"):
        collection = getattr(client, kind)
        for resource_id in manifest["resources"][kind]:
            try:
                resource = collection.get(resource_id)
            except NotFound:
                continue
            resource.reload()
            if (
                resource.id != resource_id
                or _labels(resource).get(RUN_LABEL) != manifest["run_id"]
            ):
                raise RuntimeError(
                    f"Refusing cleanup of unowned {kind} ID {resource_id}"
                )
            resource.remove()
    if manifest.get("images"):
        endpoint = selected_podman_endpoint()
        cleanup_images(
            client,
            journal_path(manifest),
            endpoint,
            lambda args: helpers.podman_command(args, endpoint=endpoint),
            closing_incomplete=incomplete,
        )
    else:
        finish_cleanup(journal_path(manifest), incomplete=incomplete)
    _mutate_run(manifest, lambda _: None)


def _selected_build_tags(stack: str, settings: dict, manifest: dict) -> list[str]:
    config = yaml.safe_load(Path(settings["compose"]).read_text(encoding="utf-8"))
    tags = []
    for name in settings["selected"]:
        service = config["services"][name]
        if "build" not in service:
            continue
        tag = manifest["build_tags"].get(f"{stack}/{name}")
        if (
            not isinstance(tag, str)
            or tag != service.get("image")
            or not tag.startswith(f"localhost/{manifest['run_id']}/")
            or service["build"].get("labels", {}).get(RUN_LABEL) != manifest["run_id"]
        ):
            raise RuntimeError(
                f"Incomplete build-tag journal or build label for {stack}/{name}"
            )
        tags.append(tag)
    return tags


def start_run(client: docker.DockerClient, manifest: dict, path: Path) -> None:
    endpoint = selected_podman_endpoint()
    latest = bind_endpoint(path, endpoint)
    manifest.clear()
    manifest.update(latest)
    if not isinstance(manifest.get("build_tags"), dict):
        raise RuntimeError(
            "Manifest has no build-tag journal; prepare a new isolated run"
        )
    build_tags = {
        stack: _selected_build_tags(stack, settings, manifest)
        for stack, settings in manifest["stacks"].items()
    }
    env = dict(os.environ)
    env.pop("DOCKER_HOST", None)
    env.pop("CONTAINER_CONNECTION", None)
    env.pop("COMPOSE_PROFILES", None)
    env["CONTAINER_HOST"] = endpoint
    env["PODMAN_COMPOSE_PROVIDER"] = "podman-compose"
    try:
        creation = begin_creation(path, endpoint, "network")
        network = client.networks.create(
            manifest["network"], labels={RUN_LABEL: manifest["run_id"]}
        )
        network_id = network.id
        network.reload()
        if (
            not isinstance(network_id, str)
            or not network_id
            or network.id != network_id
            or _labels(network).get(RUN_LABEL) != manifest["run_id"]
        ):
            raise RuntimeError("Network creation receipt identity/ownership mismatch")
        complete_creation(path, creation, network_id)
        for stack, settings in manifest["stacks"].items():
            tags = build_tags[stack]
            for tag in tags:
                prepare_image(client, path, tag, endpoint)
            creation = begin_creation(path, endpoint, "compose")
            subprocess.run(
                [
                    "podman",
                    "compose",
                    "--in-pod=false",
                    "-f",
                    settings["compose"],
                    "-p",
                    manifest["run_id"] + "-" + stack,
                    "up",
                    "-d",
                    "--build",
                    *settings["selected"],
                ],
                cwd=Path(settings["compose"]).parent,
                env=env,
                check=True,
            )
            for tag in tags:
                record_image_receipt(client, path, tag)
            discover_resources(client, manifest)
            complete_creation(path, creation, "compose up completed")
    except BaseException as exc:
        try:
            cleanup_run(client, manifest)
        except Exception as cleanup_error:
            exc.add_note(str(cleanup_error))
        raise


def wait_run(
    client: docker.DockerClient, manifest: dict, *, timeout: int = 180
) -> None:
    deadline = time.monotonic() + timeout
    pending = set(manifest["selected_containers"])
    while pending and time.monotonic() < deadline:
        for canonical in list(pending):
            container = client.containers.get(manifest["containers"][canonical])
            container.reload()
            if _labels(container).get(RUN_LABEL) != manifest["run_id"]:
                raise RuntimeError(f"Unowned selected service: {canonical}")
            state = container.attrs["State"]
            if state["Status"] in {"exited", "dead"}:
                raise RuntimeError(
                    f"Selected service {canonical} stopped: {container.logs()!r}"
                )
            if (
                state["Status"] == "running"
                and state.get("Health", {}).get("Status", "healthy") == "healthy"
            ):
                pending.remove(canonical)
        if pending:
            time.sleep(1)
    if pending:
        raise RuntimeError(f"Selected services did not become ready: {sorted(pending)}")
    verify_run_network(client, manifest)


def verify_run_network(client: docker.DockerClient, manifest: dict) -> None:
    """Both stacks must join the exact same owned network, never shared-otel-net."""
    network = client.networks.get(manifest["network"])
    network.reload()
    if _labels(network).get(RUN_LABEL) != manifest["run_id"]:
        raise RuntimeError("Shared run network has wrong ownership")
    for canonical in manifest["selected_containers"]:
        container = client.containers.get(manifest["containers"][canonical])
        container.reload()
        if manifest["network"] not in container.attrs["NetworkSettings"]["Networks"]:
            raise RuntimeError(f"{canonical} is not attached to the shared run network")


def status_run(client: docker.DockerClient, manifest: dict) -> dict:
    statuses = {}
    for canonical in manifest["selected_containers"]:
        container = client.containers.get(manifest["containers"][canonical])
        container.reload()
        if _labels(container).get(RUN_LABEL) != manifest["run_id"]:
            raise RuntimeError(f"Unowned selected container: {canonical}")
        statuses[canonical] = {"id": container.id, "state": container.attrs["State"]}
    return {
        "services": statuses,
        "host_ports": manifest["host_ports"],
        "network": manifest["network"],
    }


def _interrupt(signum: int, _frame: FrameType | None) -> NoReturn:
    raise KeyboardInterrupt(f"signal {signum}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "operation", choices=["prepare", "start", "wait", "cleanup", "status", "logs"]
    )
    parser.add_argument("--service", help="canonical selected container name for logs")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--source", type=Path, default=Path(__file__).resolve().parents[3]
    )
    parser.add_argument(
        "--services", default="firebase-emulator,spanner-emulator,pgadapter,postgres"
    )
    parser.add_argument("--telemetry", action="store_true")
    args = parser.parse_args()
    if args.operation == "prepare":
        prepare_run(
            args.source,
            args.manifest,
            args.services.split(","),
            telemetry=args.telemetry,
        )
        return
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    endpoint = selected_podman_endpoint()
    if canonical_endpoint(manifest.get("endpoint", endpoint)) != canonical_endpoint(
        endpoint
    ):
        raise RuntimeError(
            "Selected Podman endpoint changed; restore the recorded connection before cleanup"
        )
    manifest = bind_endpoint(args.manifest, endpoint)
    client = podman_client(endpoint=endpoint)
    previous_handler = signal.signal(signal.SIGTERM, _interrupt)
    try:
        if args.operation == "start":
            start_run(client, manifest, args.manifest)
        elif args.operation == "wait":
            wait_run(client, manifest)
        elif args.operation == "status":
            sys.stdout.write(json.dumps(status_run(client, manifest), indent=2) + "\n")
        elif args.operation == "logs":
            status_run(client, manifest)
            if args.service not in manifest["selected_containers"]:
                raise RuntimeError(
                    "Logs require --service with a selected canonical container name"
                )
            container = client.containers.get(manifest["containers"][args.service])
            sys.stdout.write(container.logs().decode("utf-8", errors="replace"))
        else:
            cleanup_run(client, manifest)
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
        try:
            discover_resources(client, manifest)
        finally:
            client.close()


if __name__ == "__main__":
    main()
