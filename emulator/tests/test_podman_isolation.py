"""Hermetic public renderer/lifecycle tests. No engine access."""

import hashlib
import json
import os
import shutil
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from typing import cast

import docker
import pytest
import yaml
from docker.errors import NotFound

from tests.utils import helpers, isolation
from tests.utils.helpers import RUN_LABEL
from tests.utils.image_inventory import IMAGE_ID, ImageInventory
from tests.utils.run_journal import mutate_manifest


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    ports = iter(range(45000, 46000))

    def reserve_socket():
        port = next(ports)
        return SimpleNamespace(
            bind=lambda address: None,
            getsockname=lambda: ("127.0.0.1", port),
            close=lambda: None,
        )

    monkeypatch.setattr(isolation.socket, "socket", reserve_socket)
    monkeypatch.delenv("LOCAL_WORKSPACE_FOLDER", raising=False)
    monkeypatch.delenv("CONTAINER_HOST", raising=False)
    if isolation.platform.system() == "Windows":
        monkeypatch.setenv("LOCAL_WORKSPACE_FOLDER", "/engine/disposable")
        monkeypatch.setenv("DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT", "1")
    root = Path(__file__).resolve().parents[2]
    manifest_path = tmp_path / "run.json"
    manifest = isolation.prepare_run(
        root, manifest_path, ["pgadapter", "postgres"], telemetry=True
    )
    yield manifest, manifest_path
    shutil.rmtree(Path(manifest["snapshot"]).parent)


def test_all_canonical_declarations_and_shared_network_are_isolated(prepared):
    manifest, _ = prepared
    snapshot = Path(manifest["snapshot"])
    allocated = []
    for stack, settings in manifest["stacks"].items():
        canonical = yaml.safe_load(
            (snapshot / stack / "compose.yaml").read_text(encoding="utf-8")
        )
        rendered = yaml.safe_load(Path(settings["compose"]).read_text(encoding="utf-8"))
        assert len(rendered["services"]) == len(canonical["services"])
        for name, original in canonical["services"].items():
            service = rendered["services"][name]
            assert (
                service["container_name"]
                == manifest["containers"][original.get("container_name", name)]
            )
            assert service["container_name"].startswith(manifest["run_id"])
            assert service["labels"][RUN_LABEL] == manifest["run_id"]
            assert name in service["networks"]["default"]["aliases"]
            assert service["restart"] == "no"
            for original_port, mapped in zip(
                original.get("ports", []), service.get("ports", []), strict=True
            ):
                host, port, target = mapped.split(":")
                assert host == "127.0.0.1"
                assert mapped != original_port
                assert target == original_port.split(":")[-1]
                allocated.append(port)
            for original_mount, mapped in zip(
                original.get("volumes", []), service.get("volumes", []), strict=True
            ):
                source = mapped.split(":")[0]
                if original_mount.startswith("."):
                    bind = next(
                        b for b in manifest["binds"] if b["engine_source"] == source
                    )
                    local_source = Path(bind["source"])
                    assert local_source.is_relative_to(snapshot)
                    if not original_mount.endswith(":ro"):
                        assert local_source.is_relative_to(snapshot / ".run-data")
                    assert (
                        local_source
                        != Path(manifest["source"])
                        / stack
                        / original_mount.split(":")[0]
                    )
            if "build" in original:
                assert service["image"].startswith("localhost/" + manifest["run_id"])
        for volume in rendered.get("volumes", {}).values():
            assert volume["name"] in manifest["volumes"]
            assert volume["labels"][RUN_LABEL] == manifest["run_id"]
        for network in rendered["networks"].values():
            assert network == {"name": manifest["network"], "external": True}
    assert len(allocated) == len(set(allocated)) == len(manifest["host_ports"])
    assert manifest["network"] != "shared-otel-net"
    assert "spanner-emulator" in manifest["selected_containers"]
    assert "postgres-18" in manifest["selected_containers"]
    assert "grafana" in manifest["selected_containers"]
    assert not (snapshot / ".git").exists()
    assert not (snapshot / "emulator/firebase/data/firestore_export").exists()


def test_manifest_consumers_resolve_all_canonical_services_and_ports(
    prepared, monkeypatch
):
    manifest, path = prepared
    monkeypatch.setenv("DOTFILES_PODMAN_RUN_MANIFEST", str(path))
    for canonical, unique in manifest["containers"].items():
        assert helpers.container_name(canonical) == unique
    for canonical, allocated in manifest["host_ports"].items():
        assert allocated not in manifest["canonical_ports"]
        assert helpers.host_port(int(canonical)) == allocated
        endpoint = f"http://localhost:{canonical}/health"
        mapped = f"http://localhost:{allocated}/health"
        assert helpers.host_endpoint(endpoint) == mapped
        assert helpers.host_endpoint(mapped) == mapped


def test_tracked_snapshot_excludes_untracked_and_git_metadata(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "tracked.txt").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "tracked.txt"], check=True)
    (source / "live-data").write_text("sentinel", encoding="utf-8")
    snapshot = tmp_path / "snapshot"
    isolation.tracked_snapshot(source, snapshot)
    assert {p.name for p in snapshot.iterdir()} == {"tracked.txt"}
    assert (source / "live-data").read_text(encoding="utf-8") == "sentinel"


def test_nested_translation_requires_both_fences(tmp_path):
    source = tmp_path / "checkout"
    snapshot = source / ".podman-runs/run/snapshot/file"
    with pytest.raises(RuntimeError, match="DISPOSABLE_CHECKOUT"):
        isolation.engine_path(
            snapshot, source, {"LOCAL_WORKSPACE_FOLDER": "/engine/checkout"}
        )
    env = {
        "LOCAL_WORKSPACE_FOLDER": "/engine/checkout",
        "DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT": "1",
    }
    assert (
        isolation.engine_path(snapshot, source, env)
        == "/engine/checkout/.podman-runs/run/snapshot/file"
    )
    with pytest.raises(RuntimeError, match="LOCAL_WORKSPACE_FOLDER"):
        isolation.engine_path(
            snapshot,
            source,
            {"CONTAINER_HOST": "unix:///run/dotfiles-podman/podman.sock"},
        )
    with pytest.raises(ValueError):
        isolation.engine_path(tmp_path / "outside", source, env)


class Inventory:
    """Tiny stateful SDK inventory adapter with unrelated sentinels."""

    def __init__(self, run_id, kind):
        self.kind = kind
        self.resources = {}
        self.add("sentinel", "unrelated")
        self.add("partial", run_id)

    def resource_id(self, name):
        identity = self.kind + "-" + name
        return (
            hashlib.sha256(identity.encode()).hexdigest()
            if self.kind == "containers"
            else identity
        )

    def add(self, name, owner):
        resource_id = self.resource_id(name)
        attrs = {"Labels": {RUN_LABEL: owner}, "Config": {"Labels": {RUN_LABEL: owner}}}
        resource = SimpleNamespace(
            id=resource_id,
            attrs=attrs,
            reload=lambda: None,
            remove=lambda **kw: self.resources.pop(resource_id),
        )
        self.resources[resource_id] = resource
        return resource

    def list(self, **kwargs):
        owner = kwargs["filters"]["label"].split("=", 1)[1]
        return [
            r for r in self.resources.values() if r.attrs["Labels"][RUN_LABEL] == owner
        ]

    def get(self, resource_id):
        if resource_id not in self.resources:
            raise NotFound("already removed")
        return self.resources[resource_id]

    def create(self, name, labels):
        return self.add(name, labels[RUN_LABEL])


@pytest.fixture
def inventory(prepared, monkeypatch):
    manifest, _ = prepared
    client = SimpleNamespace(
        **{kind: Inventory(manifest["run_id"], kind) for kind in manifest["resources"]},
        images=ImageInventory(manifest["run_id"]),
    )

    def native_inspect(args, **kwargs):
        assert args[:3] == ["podman", "container", "inspect"]
        assert len(args) == 4
        assert kwargs["env"]["CONTAINER_HOST"] == "unix:///selected.sock"
        resource = client.containers.get(args[3])
        return SimpleNamespace(
            stdout=json.dumps(
                [
                    {
                        "Id": resource.id,
                        "Config": resource.attrs["Config"],
                        "Dependencies": [],
                    }
                ]
            )
        )

    client.native_inspect = native_inspect
    monkeypatch.setattr(
        isolation, "selected_podman_endpoint", lambda: "unix:///selected.sock"
    )
    monkeypatch.setattr(helpers.subprocess, "run", native_inspect)
    return client


def test_cleanup_recovers_partial_ids_preserves_sentinels_and_data(
    prepared, inventory, tmp_path
):
    manifest, _ = prepared
    data = tmp_path / "sentinel-data"
    data.write_text("do not touch", encoding="utf-8")
    isolation.cleanup_run(inventory, manifest)
    isolation.cleanup_run(inventory, manifest)
    for kind in manifest["resources"]:
        collection = getattr(inventory, kind)
        assert list(collection.resources) == [collection.resource_id("sentinel")]
        assert collection.resource_id("partial") in manifest["resources"][kind]
    assert data.read_text(encoding="utf-8") == "do not touch"


def test_cleanup_metadata_failure_retains_every_resource(
    prepared, inventory, monkeypatch
):
    manifest, _ = prepared
    invalid = SimpleNamespace(
        id=None, attrs={"Labels": {RUN_LABEL: manifest["run_id"]}}
    )
    monkeypatch.setattr(inventory.containers, "list", lambda **kwargs: [invalid])
    with pytest.raises(RuntimeError, match="missing identity"):
        isolation.cleanup_run(inventory, manifest)
    assert all(
        len(getattr(inventory, kind).resources) == 2 for kind in manifest["resources"]
    )


def test_cleanup_rechecks_recorded_id_ownership(prepared, inventory):
    manifest, _ = prepared
    mutate_manifest(
        prepared[1],
        lambda current: current["resources"]["containers"].append(
            inventory.containers.resource_id("sentinel")
        ),
    )
    with pytest.raises(RuntimeError, match="unowned"):
        isolation.cleanup_run(inventory, manifest)
    assert (
        inventory.containers.resource_id("sentinel") in inventory.containers.resources
    )


@pytest.mark.parametrize(
    "failure", [RuntimeError("compose failed"), KeyboardInterrupt()]
)
def test_start_failure_and_interruption_cleanup_preserve_sentinels(
    prepared, inventory, monkeypatch, failure
):
    manifest, path = prepared
    monkeypatch.setattr(
        isolation, "selected_podman_endpoint", lambda: "unix:///selected.sock"
    )
    monkeypatch.setenv("COMPOSE_PROFILES", "full,cli")
    commands = []

    def fail_compose(command, **kwargs):
        if command[:3] == ["podman", "container", "inspect"]:
            return inventory.native_inspect(command, **kwargs)
        commands.append((command, kwargs))
        inventory.containers.add("new-during-start", manifest["run_id"])
        raise failure

    monkeypatch.setattr(isolation.subprocess, "run", fail_compose)
    with pytest.raises(type(failure)):
        isolation.start_run(inventory, manifest, path)
    command, kwargs = commands[0]
    assert command[:3] == ["podman", "compose", "--in-pod=false"]
    assert kwargs["env"]["PODMAN_COMPOSE_PROVIDER"] == "podman-compose"
    assert kwargs["env"]["CONTAINER_HOST"] == "unix:///selected.sock"
    assert "DOCKER_HOST" not in kwargs["env"]
    assert "COMPOSE_PROFILES" not in kwargs["env"]
    for kind in manifest["resources"]:
        collection = getattr(inventory, kind)
        assert list(collection.resources) == [collection.resource_id("sentinel")]
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert (
        inventory.containers.resource_id("new-during-start")
        in saved["resources"]["containers"]
    )


def test_wait_and_status_resolve_every_selected_container_from_manifest(prepared):
    manifest, _ = prepared
    requested = []
    containers = {}
    for canonical in manifest["selected_containers"]:
        unique = manifest["containers"][canonical]
        containers[unique] = SimpleNamespace(
            id=unique + "-id",
            reload=lambda: None,
            attrs={
                "Config": {"Labels": {RUN_LABEL: manifest["run_id"]}},
                "State": {"Status": "running", "Health": {"Status": "healthy"}},
                "NetworkSettings": {"Networks": {manifest["network"]: {}}},
            },
        )
    network = SimpleNamespace(
        reload=lambda: None, attrs={"Labels": {RUN_LABEL: manifest["run_id"]}}
    )

    def get_container(name):
        requested.append(name)
        return containers[name]

    client = cast(
        docker.DockerClient,
        SimpleNamespace(
            containers=SimpleNamespace(get=get_container),
            networks=SimpleNamespace(get=lambda _: network),
        ),
    )
    isolation.wait_run(client, manifest, timeout=1)
    statuses = isolation.status_run(client, manifest)
    assert set(statuses["services"]) == set(manifest["selected_containers"])
    assert statuses["host_ports"] == manifest["host_ports"]
    assert set(requested) == set(containers)
    first = next(iter(containers.values()))
    first.attrs["NetworkSettings"]["Networks"] = {"shared-otel-net": {}}
    with pytest.raises(RuntimeError, match="not attached"):
        isolation.wait_run(client, manifest, timeout=1)


def test_renderer_translates_all_nested_binds_and_rejects_escape(prepared):
    manifest, _ = prepared
    snapshot = Path(manifest["snapshot"])
    manifest["source"] = str(snapshot.parent)
    manifest["bind_env"] = {
        "LOCAL_WORKSPACE_FOLDER": "/engine/disposable",
        "DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT": "1",
    }
    manifest["binds"] = []
    manifest["host_ports"] = {}
    reservations = []
    config = yaml.safe_load(
        (snapshot / "emulator/compose.yaml").read_text(encoding="utf-8")
    )
    try:
        rendered = isolation.render_compose(config, "emulator", manifest, reservations)
        assert manifest["binds"]
        for bind in manifest["binds"]:
            relative = Path(bind["source"]).relative_to(snapshot.parent)
            assert bind["engine_source"] == "/engine/disposable/" + relative.as_posix()
        assert all(
            mount.startswith("/engine/disposable/")
            for mount in rendered["services"]["firebase-emulator"]["volumes"]
        )
        config["services"]["firebase-emulator"]["volumes"] = ["../../../outside:/data"]
        with pytest.raises(RuntimeError, match="escapes"):
            isolation.render_compose(config, "emulator", manifest, reservations)
    finally:
        for reservation in reservations:
            reservation.close()


@pytest.mark.parametrize("damage", ["field", "entry"])
def test_start_rejects_manifest_without_build_tag_journal_before_creation(
    prepared, inventory, monkeypatch, damage
):
    manifest, path = prepared
    if damage == "field":
        mutate_manifest(path, lambda current: current.pop("build_tags"))
    else:
        mutate_manifest(
            path, lambda current: current["build_tags"].pop("emulator/postgres")
        )
    monkeypatch.setattr(
        isolation, "selected_podman_endpoint", lambda: "unix:///selected.sock"
    )
    calls = []
    monkeypatch.setattr(
        isolation.subprocess, "run", lambda *args, **kwargs: calls.append(args)
    )
    with pytest.raises(RuntimeError, match="build-tag journal"):
        isolation.start_run(inventory, manifest, path)
    assert calls == []
    assert len(inventory.networks.resources) == 2


@pytest.mark.parametrize(
    "failure",
    [
        None,
        RuntimeError("partial Compose build"),
        subprocess.CalledProcessError(17, ["podman", "compose"]),
        subprocess.TimeoutExpired(["podman", "compose"], timeout=1),
        KeyboardInterrupt(),
    ],
)
def test_compose_builds_prepare_observe_and_untag_after_containers(
    prepared, inventory, monkeypatch, failure
):
    manifest, path = prepared
    endpoint = "unix:///selected.sock"
    monkeypatch.setattr(isolation, "selected_podman_endpoint", lambda: endpoint)
    untag = inventory.images.command
    native_command = helpers.podman_command

    def command(args, **kwargs):
        if args[:2] == ["container", "inspect"]:
            return native_command(args, **kwargs)
        assert list(inventory.containers.resources) == [
            inventory.containers.resource_id("sentinel")
        ]
        return untag(args, **kwargs)

    monkeypatch.setattr(helpers, "podman_command", command)
    built = []

    def compose(args, **kwargs):
        if args[:3] == ["podman", "container", "inspect"]:
            return inventory.native_inspect(args, **kwargs)
        saved = json.loads(path.read_text(encoding="utf-8"))
        stack = next(
            stack
            for stack, settings in saved["stacks"].items()
            if settings["compose"] == args[4]
        )
        settings = saved["stacks"][stack]
        tags = [
            saved["build_tags"][f"{stack}/{name}"]
            for name in settings["selected"]
            if f"{stack}/{name}" in saved["build_tags"]
        ]
        assert all(saved["images"][tag]["state"] == "prepared" for tag in tags)
        for tag in tags:
            inventory.images.build(tag=tag, labels={RUN_LABEL: manifest["run_id"]})
            built.append(tag)
            if failure:
                raise failure

    monkeypatch.setattr(isolation.subprocess, "run", compose)
    if failure:
        with pytest.raises(type(failure)):
            isolation.start_run(inventory, manifest, path)
    else:
        isolation.start_run(inventory, manifest, path)
        observed = json.loads(path.read_text(encoding="utf-8"))["images"]
        assert all(observed[tag]["state"] == "observed" for tag in built)
        isolation.cleanup_run(inventory, manifest)
    assert built
    saved = json.loads(path.read_text(encoding="utf-8"))
    if failure:
        assert any(
            record["kind"] == "compose" and record["state"] == "in_progress"
            for record in saved["creations"].values()
        )
        with pytest.raises(RuntimeError, match="incomplete"):
            isolation.cleanup_run(inventory, manifest)
    else:
        assert all(
            record["state"] == "completed" for record in saved["creations"].values()
        )
    assert inventory.images.tags == {}
    assert inventory.images.image.attrs["RepoTags"] == [inventory.images.foreign_alias]
    assert all(
        item["state"] == "absent"
        for item in json.loads(path.read_text(encoding="utf-8"))["images"].values()
    )


@pytest.mark.parametrize(
    "build",
    [
        "./postgres",
        {
            "context": "./postgres",
            "dockerfile": "Dockerfile",
            "args": {"VERSION": "18"},
            "labels": {"existing": "retained"},
        },
        {"context": "./postgres", "labels": ["existing=retained"]},
    ],
)
def test_render_build_labels_preserve_actual_build_graph(prepared, build):
    manifest, _ = prepared
    config = {"services": {"sample": {"build": build}}, "networks": {"default": {}}}
    rendered = isolation.render_compose(config, "emulator", manifest, [])
    result = rendered["services"]["sample"]["build"]
    assert result["context"] == "./postgres"
    assert result["labels"][RUN_LABEL] == manifest["run_id"]
    if isinstance(build, dict):
        assert result["labels"]["existing"] == "retained"
        assert {key: value for key, value in result.items() if key != "labels"} == {
            key: value for key, value in build.items() if key != "labels"
        }


def test_prepared_postgres_record_comes_from_canonical_service_not_environment(
    prepared, monkeypatch
):
    manifest, path = prepared
    monkeypatch.setenv(helpers.RUN_MANIFEST_ENV, str(path))
    assert manifest["postgres_connection"] == {
        "host": "127.0.0.1",
        "port": manifest["host_ports"]["5433"],
        "user": "postgres",
        "password": "password",
        "database": "postgres",
    }
    canonical = yaml.safe_load(
        (Path(manifest["snapshot"]) / "emulator/compose.yaml").read_text(
            encoding="utf-8"
        )
    )["services"]["postgres"]
    assert "POSTGRES_USER=postgres" in canonical["environment"]
    assert "POSTGRES_PASSWORD=password" in canonical["environment"]
    assert "POSTGRES_DB=postgres" in canonical["environment"]


@pytest.mark.parametrize(
    "environment",
    [
        {
            "POSTGRES_USER": "fixture-user",
            "POSTGRES_PASSWORD": "fixture-password",
            "POSTGRES_DB": "fixture-db",
        },
        [
            "POSTGRES_USER=fixture-user",
            "POSTGRES_PASSWORD=fixture-password",
            "POSTGRES_DB=fixture-db",
        ],
    ],
)
def test_prepare_derives_complete_record_from_both_compose_environment_forms(
    prepared, monkeypatch, environment
):
    manifest, path = prepared
    snapshot_source = Path(manifest["snapshot"])

    def snapshot(_, target):
        shutil.copytree(snapshot_source, target)
        compose = target / "emulator/compose.yaml"
        config = yaml.safe_load(compose.read_text(encoding="utf-8"))
        config["services"]["postgres"]["environment"] = environment
        compose.write_text(yaml.safe_dump(config), encoding="utf-8")

    monkeypatch.setattr(isolation, "tracked_snapshot", snapshot)
    monkeypatch.setenv("POSTGRES_HOST", "198.51.100.99")
    monkeypatch.setenv("POSTGRES_DB", "hostilefixturedb")
    derived = isolation.prepare_run(
        Path(manifest["source"]), path.with_name("derived.json"), ["postgres"]
    )
    assert derived["postgres_connection"] == {
        "host": "127.0.0.1",
        "port": derived["host_ports"]["5433"],
        "user": "fixture-user",
        "password": "fixture-password",
        "database": "fixture-db",
    }
    shutil.rmtree(Path(derived["snapshot"]).parent)


@pytest.mark.parametrize(
    "environment",
    [
        {
            "POSTGRES_USER": "postgres",
            "POSTGRES_PASSWORD": "${INHERITED}",
            "POSTGRES_DB": "postgres",
        },
        ["POSTGRES_USER=postgres", "POSTGRES_PASSWORD", "POSTGRES_DB=postgres"],
        {"POSTGRES_USER": "postgres", "POSTGRES_PASSWORD": "password"},
    ],
)
def test_prepare_rejects_unresolved_or_incomplete_postgres_configuration(
    prepared, monkeypatch, environment
):
    manifest, path = prepared
    snapshots = []

    def snapshot(_, target):
        snapshots.append(target)
        shutil.copytree(Path(manifest["snapshot"]), target)
        compose = target / "emulator/compose.yaml"
        config = yaml.safe_load(compose.read_text(encoding="utf-8"))
        config["services"]["postgres"]["environment"] = environment
        compose.write_text(yaml.safe_dump(config), encoding="utf-8")

    monkeypatch.setattr(isolation, "tracked_snapshot", snapshot)
    target = path.with_name("invalid.json")
    with pytest.raises(RuntimeError):
        isolation.prepare_run(Path(manifest["source"]), target, ["postgres"])
    assert not target.exists()
    for source in snapshots:
        shutil.rmtree(source.parent)


@pytest.mark.parametrize(
    "substitution", ["internal", "external", "leaf", "dangling", "git"]
)
def test_tracked_snapshot_rejects_every_link_before_copy(tmp_path, substitution):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "first").write_text("ordinary", encoding="utf-8")
    nested = source / "nested"
    nested.mkdir()
    (nested / "file").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    private = source / "private" if substitution == "internal" else tmp_path / "private"
    private.mkdir()
    (private / "file").write_text("UNTRACKED_SENTINEL", encoding="utf-8")
    if substitution == "leaf":
        (nested / "file").unlink()
        (nested / "file").symlink_to(private / "file")
    else:
        shutil.rmtree(nested)
        target = {"git": source / ".git", "dangling": source / "missing"}.get(
            substitution, private
        )
        nested.symlink_to(target, target_is_directory=True)
    snapshot = tmp_path / "snapshot"
    with pytest.raises(RuntimeError, match="Snapshot"):
        isolation.tracked_snapshot(source, snapshot)
    assert not snapshot.exists()


@pytest.mark.parametrize("source_link", ["ancestor", "root"])
def test_prepare_rejects_original_source_ancestor_link_before_resolve(
    tmp_path, source_link
):
    real = tmp_path / "real"
    real.mkdir()
    (real / "source").mkdir()
    link = tmp_path / "linked"
    link.symlink_to(
        real if source_link == "ancestor" else real / "source", target_is_directory=True
    )
    original_source = link / "source" if source_link == "ancestor" else link
    with pytest.raises(RuntimeError, match="Snapshot"):
        isolation.prepare_run(original_source, tmp_path / "run.json", [])
    assert not (tmp_path / "run.json").exists()


@pytest.mark.parametrize("portable", [False, True])
def test_tracked_snapshot_keeps_working_staged_bytes_modes_and_omits_gitlinks(
    tmp_path, monkeypatch, portable
):
    if portable:
        monkeypatch.setattr(isolation.os, "supports_dir_fd", set())
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    working, staged = source / "working", source / "staged"
    working.write_text("INDEX_BYTES", encoding="utf-8")
    staged.write_text("STAGED_BYTES", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    working.write_text("WORKING_BYTES", encoding="utf-8")
    working.chmod(0o755)
    subprocess.run(
        [
            "git",
            "-C",
            str(source),
            "update-index",
            "--add",
            "--cacheinfo",
            "160000," + "a" * 40 + ",submodule",
        ],
        check=True,
    )
    (source / "submodule").mkdir()
    (source / "submodule/private").write_text("UNTRACKED_SENTINEL", encoding="utf-8")
    snapshot = tmp_path / "snapshot"
    (source / "child").mkdir()
    isolation.tracked_snapshot(source / "child" / "..", snapshot)
    assert (snapshot / "working").read_text(encoding="utf-8") == "WORKING_BYTES"
    assert (snapshot / "staged").read_text(encoding="utf-8") == "STAGED_BYTES"
    assert stat.S_IMODE((snapshot / "working").stat().st_mode) == stat.S_IMODE(
        working.stat().st_mode
    )
    assert sorted(p.name for p in snapshot.iterdir()) == ["staged", "working"]


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        ".git/config",
        "x/.Git/config",
        "CON",
        "aux.txt",
        "CONIN$",
        "COM¹",
        "git~1/config",
        "x:stream",
        "x\\y",
        "x//y",
        "x/./y",
        "trailing.",
        "trailing ",
    ],
)
def test_snapshot_rejects_reserved_index_paths_before_output(
    tmp_path, monkeypatch, name
):
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(
        isolation.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout=("100644 " + "a" * 40 + " 0\t" + name + "\0").encode()
        ),
    )
    target = tmp_path / "snapshot"
    with pytest.raises(RuntimeError, match="Snapshot"):
        isolation.tracked_snapshot(source, target)
    assert not target.exists()


@pytest.mark.parametrize("replacement", ["reparse", "junction", "fifo"])
def test_snapshot_rejects_reparse_junction_and_nonregular_before_copy(
    tmp_path, monkeypatch, replacement
):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    leaf = source / "tracked"
    leaf.write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        metadata = original(path, *args, **kwargs)
        if path == leaf and replacement != "junction":
            return SimpleNamespace(
                st_mode=stat.S_IFIFO if replacement == "fifo" else metadata.st_mode,
                st_file_attributes=0x400 if replacement == "reparse" else 0,
            )
        return metadata

    monkeypatch.setattr(Path, "lstat", lstat)
    if replacement == "junction":
        monkeypatch.setattr(Path, "is_junction", lambda path: path == leaf)
    target = tmp_path / "snapshot"
    with pytest.raises(RuntimeError, match="Snapshot"):
        isolation.tracked_snapshot(source, target)
    assert not target.exists()


@pytest.mark.parametrize("portable", [False, True])
def test_snapshot_rechecks_open_file_identity(tmp_path, monkeypatch, portable):
    source = tmp_path / "source"
    source.mkdir()
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    (source / "tracked").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "-C", str(source), "add", "."], check=True)
    if portable:
        monkeypatch.setattr(isolation.os, "supports_dir_fd", set())
    fstat = os.fstat

    def changed(descriptor):
        metadata = fstat(descriptor)
        if stat.S_ISREG(metadata.st_mode):
            return SimpleNamespace(
                st_mode=metadata.st_mode,
                st_dev=metadata.st_dev,
                st_ino=metadata.st_ino + 1,
                st_size=metadata.st_size,
                st_mtime_ns=metadata.st_mtime_ns,
            )
        return metadata

    monkeypatch.setattr(isolation.os, "fstat", changed)
    target = tmp_path / "snapshot"
    with pytest.raises(RuntimeError, match="identity changed"):
        isolation.tracked_snapshot(source, target)
    assert not list(target.rglob("tracked"))


def test_closing_rejects_all_subsequent_public_creators_with_zero_creation_io(
    prepared, inventory, monkeypatch
):
    manifest, path = prepared
    endpoint = "unix:///selected.sock"
    monkeypatch.setenv(helpers.RUN_MANIFEST_ENV, str(path))
    monkeypatch.setattr(helpers, "selected_podman_endpoint", lambda: endpoint)
    monkeypatch.setattr(isolation, "selected_podman_endpoint", lambda: endpoint)
    native_command = helpers.podman_command

    def command(args, **kwargs):
        if args[:2] == ["container", "inspect"]:
            return native_command(args, **kwargs)
        return inventory.images.command(args, **kwargs)

    monkeypatch.setattr(helpers, "podman_command", command)
    authorized, resume = Event(), Event()
    calls = []
    build = inventory.images.build

    def paused(**kwargs):
        authorized.set()
        assert resume.wait(5)
        calls.append("image")
        return build(**kwargs)

    monkeypatch.setattr(inventory.images, "build", paused)
    monkeypatch.setattr(
        inventory.containers,
        "run",
        lambda **kwargs: calls.append("container"),
        raising=False,
    )
    monkeypatch.setattr(
        inventory.networks, "create", lambda *args, **kwargs: calls.append("network")
    )
    monkeypatch.setattr(
        inventory.volumes,
        "create",
        lambda *args, **kwargs: calls.append("volume"),
        raising=False,
    )
    monkeypatch.setattr(
        isolation.subprocess,
        "run",
        lambda args, **kwargs: (
            inventory.native_inspect(args, **kwargs)
            if args[:3] == ["podman", "container", "inspect"]
            else calls.append("compose")
        ),
    )
    with ThreadPoolExecutor(max_workers=1) as workers:
        pending = workers.submit(helpers.build_test_image, inventory, "postgres-cli")
        assert authorized.wait(5)
        try:
            mutate_manifest(
                path, lambda current: current.update(unrelated_entry="keep")
            )
            with pytest.raises(RuntimeError, match="incomplete"):
                isolation.cleanup_run(inventory, manifest)
            saved = json.loads(path.read_text(encoding="utf-8"))
            assert saved["cleanup_state"] == "incomplete"
            assert calls == []
            for create in (
                lambda: helpers.build_test_image(inventory, "postgres-cli"),
                lambda: helpers.run_test_image(inventory, IMAGE_ID, "true", {}),
                lambda: isolation.start_run(inventory, manifest, path),
            ):
                with pytest.raises(RuntimeError, match="closing/closed"):
                    create()
            assert calls == []
        finally:
            resume.set()
        assert pending.result(timeout=5) == IMAGE_ID
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["cleanup_state"] != "closed"
    assert saved["unrelated_entry"] == "keep"
    assert all(record["state"] == "completed" for record in saved["creations"].values())
    isolation.cleanup_run(inventory, manifest)
    assert inventory.images.tags == {}
    assert inventory.images.image.attrs["RepoTags"] == [inventory.images.foreign_alias]
    assert json.loads(path.read_text(encoding="utf-8"))["cleanup_state"] == "closed"
    assert calls == ["image"]


def test_network_transport_error_without_receipt_remains_incomplete(
    prepared, inventory, monkeypatch
):
    manifest, path = prepared
    monkeypatch.setattr(
        isolation, "selected_podman_endpoint", lambda: "unix:///selected.sock"
    )

    def transport_error(*args, **kwargs):
        raise RuntimeError("network transport lost")

    monkeypatch.setattr(inventory.networks, "create", transport_error)
    with pytest.raises(RuntimeError, match="network transport lost"):
        isolation.start_run(inventory, manifest, path)
    with pytest.raises(RuntimeError, match="incomplete"):
        isolation.cleanup_run(inventory, manifest)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert any(
        record["kind"] == "network" and record["state"] == "in_progress"
        for record in saved["creations"].values()
    )
