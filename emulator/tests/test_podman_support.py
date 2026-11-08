"""Hermetic tests for the public Podman test-support API."""

import json
from types import SimpleNamespace
from typing import cast

import docker
import pytest
from docker.errors import NotFound

from tests.utils import helpers
from tests.utils.image_inventory import IMAGE_ID
from tests.utils.result import Error


def test_get_container_uses_run_manifest(monkeypatch, tmp_path):
    manifest = tmp_path / "run.json"
    manifest.write_text(
        json.dumps({"containers": {"postgres-18": "run-postgres"}}), encoding="utf-8"
    )
    monkeypatch.setenv("DOTFILES_PODMAN_RUN_MANIFEST", str(manifest))
    requested = []
    client = SimpleNamespace(
        containers=SimpleNamespace(get=lambda name: requested.append(name))
    )
    helpers.get_container(cast(docker.DockerClient, client), "postgres-18")
    assert requested == ["run-postgres"]


def test_public_factory_is_explicit_podman_only(monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "unix:///must-not-use-docker.sock")
    monkeypatch.setenv("CONTAINER_HOST", "unix:///selected.sock")
    commands = []
    monkeypatch.setattr(
        helpers,
        "podman_command",
        lambda args: commands.append(args) or "podman version 6.1.4",
    )
    created = []
    client = SimpleNamespace(
        version=lambda: {
            "Platform": {"Name": "linux/arm64/fedora-42"},
            "Components": [{"Name": "Podman Engine", "Version": "5.6.2"}],
        },
        ping=lambda: True,
    )
    monkeypatch.setattr(
        helpers.docker, "DockerClient", lambda **kw: created.append(kw) or client
    )
    assert helpers.podman_client() is client
    assert created == [{"base_url": "unix:///selected.sock", "version": "1.41"}]
    assert commands == [["--version"]]


@pytest.mark.parametrize(
    "components",
    [
        [],
        [{"Name": "Engine", "Version": "28.0.0"}],
        [{"Name": "Podman Engine", "Version": "4.9.0"}],
    ],
)
def test_public_factory_rejects_docker_and_old_server(monkeypatch, components):
    monkeypatch.setattr(
        helpers, "selected_podman_endpoint", lambda: "unix:///selected.sock"
    )
    closed = []
    client = SimpleNamespace(
        version=lambda: {"Components": components}, close=lambda: closed.append(True)
    )
    monkeypatch.setattr(helpers.docker, "DockerClient", lambda **kw: client)
    with pytest.raises(RuntimeError, match="Podman"):
        helpers.podman_client()
    assert closed == [True]


@pytest.mark.parametrize(
    "endpoint", ["tcp://localhost:2375", "ssh://root@remote/run/podman.sock"]
)
def test_remote_explicit_endpoint_refused(monkeypatch, endpoint):
    monkeypatch.setattr(helpers, "podman_command", lambda args: "podman version 6.1.4")
    monkeypatch.setenv("CONTAINER_HOST", endpoint)
    with pytest.raises(RuntimeError, match="no TCP/SSH fallback"):
        helpers.selected_podman_endpoint()


def test_new_client_does_not_mask_old_client(monkeypatch):
    monkeypatch.setattr(helpers, "podman_command", lambda args: "podman version 4.9.0")
    with pytest.raises(RuntimeError, match="CLI requires Podman >=5"):
        helpers.selected_podman_endpoint()


def test_wrong_selected_machine_is_not_defaulted(monkeypatch):
    monkeypatch.delenv("CONTAINER_HOST", raising=False)
    monkeypatch.delenv("CONTAINER_CONNECTION", raising=False)
    monkeypatch.setattr(helpers.platform, "system", lambda: "Darwin")
    responses = [
        "podman version 6.1.4",
        json.dumps(
            [
                {
                    "Name": "other",
                    "URI": "ssh://core@127.0.0.1:555/run/user/501/podman/podman.sock",
                    "Default": True,
                    "Identity": "/key",
                }
            ]
        ),
        json.dumps(
            [
                {
                    "Name": "default",
                    "SSHConfig": {
                        "Port": 555,
                        "RemoteUsername": "core",
                        "IdentityPath": "/key",
                    },
                    "ConnectionInfo": {"PodmanSocket": {"Path": "/tmp/default.sock"}},
                }
            ]
        ),
    ]
    monkeypatch.setattr(helpers, "podman_command", lambda args: responses.pop(0))
    with pytest.raises(RuntimeError, match="refusing default-machine guessing"):
        helpers.selected_podman_endpoint()


def test_wait_uses_manifest_host_port(monkeypatch, tmp_path):
    manifest = tmp_path / "run.json"
    manifest.write_text(json.dumps({"host_ports": {"5433": 45678}}), encoding="utf-8")
    monkeypatch.setenv("DOTFILES_PODMAN_RUN_MANIFEST", str(manifest))
    endpoints = []
    sock = SimpleNamespace(
        settimeout=lambda _: None,
        connect_ex=lambda endpoint: endpoints.append(endpoint) or 0,
        close=lambda: None,
    )
    monkeypatch.setattr(helpers.socket, "socket", lambda *_: sock)
    helpers.wait_for_tcp("localhost", 5433, retries=1)
    assert endpoints == [("localhost", 45678)]


def test_linux_native_selected_service_is_discovered_not_guessed(monkeypatch):
    monkeypatch.delenv("CONTAINER_HOST", raising=False)
    monkeypatch.delenv("CONTAINER_CONNECTION", raising=False)
    monkeypatch.setattr(helpers.platform, "system", lambda: "Linux")
    responses = [
        "podman version 5.4.2",
        "[]",
        json.dumps(
            {"host": {"remoteSocket": {"path": "/run/user/1234/podman/podman.sock"}}}
        ),
    ]
    monkeypatch.setattr(helpers, "podman_command", lambda args: responses.pop(0))
    assert (
        helpers.selected_podman_endpoint() == "unix:///run/user/1234/podman/podman.sock"
    )


@pytest.mark.parametrize(
    "system,forwarding,endpoint",
    [
        (
            "Darwin",
            {"PodmanSocket": {"Path": "/tmp/selected-forward.sock"}},
            "unix:///tmp/selected-forward.sock",
        ),
        (
            "Darwin",
            {"PodmanSocket": {"Path": "unix:///tmp/selected-forward.sock"}},
            "unix:///tmp/selected-forward.sock",
        ),
        (
            "Windows",
            {"PodmanPipe": {"Path": "\\\\.\\pipe\\selected-api"}},
            "npipe:////./pipe/selected-api",
        ),
    ],
)
def test_selected_machine_forwarding_uses_named_machine_not_default(
    monkeypatch, system, forwarding, endpoint
):
    monkeypatch.delenv("CONTAINER_HOST", raising=False)
    monkeypatch.setenv("CONTAINER_CONNECTION", "chosen")
    monkeypatch.setattr(helpers.platform, "system", lambda: system)
    connection = {
        "Name": "chosen",
        "URI": "ssh://core@127.0.0.1:555/run/user/501/podman/podman.sock",
        "Default": False,
        "Identity": "/key",
    }
    machine = {
        "Name": "chosen",
        "Rootful": False,
        "SSHConfig": {"Port": 555, "RemoteUsername": "core", "IdentityPath": "/key"},
        "ConnectionInfo": forwarding,
    }
    responses = [
        "podman version 6.1.4",
        json.dumps([connection]),
        json.dumps([machine]),
        json.dumps(
            {"host": {"remoteSocket": {"path": "/run/user/501/podman/podman.sock"}}}
        ),
    ]
    commands = []

    def command(args):
        commands.append(args)
        return responses.pop(0)

    monkeypatch.setattr(helpers, "podman_command", command)
    assert helpers.selected_podman_endpoint() == endpoint
    assert ["machine", "inspect", "chosen"] in commands
    assert ["--connection", "chosen", "info", "--format", "json"] in commands


def test_selected_required_missing_service_fails_not_skips(monkeypatch, tmp_path):
    manifest = tmp_path / "run.json"
    manifest.write_text(
        json.dumps(
            {
                "selected_containers": ["postgres-18"],
                "containers": {"postgres-18": "run-postgres"},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DOTFILES_PODMAN_RUN_MANIFEST", str(manifest))
    monkeypatch.setenv("DOTFILES_E2E_REQUIRED", "1")
    client = cast(
        docker.DockerClient,
        SimpleNamespace(containers=SimpleNamespace(list=lambda: [])),
    )
    with pytest.raises(pytest.fail.Exception, match="Required Podman containers"):
        helpers.require_running(client, ["postgres-18"])


def test_get_container_rejects_unowned_manifest_name(monkeypatch, tmp_path):
    manifest = tmp_path / "run.json"
    manifest.write_text(
        json.dumps(
            {"run_id": "owned-run", "containers": {"postgres-18": "run-postgres"}}
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DOTFILES_PODMAN_RUN_MANIFEST", str(manifest))
    container = SimpleNamespace(
        attrs={"Config": {"Labels": {helpers.RUN_LABEL: "unrelated"}}}
    )
    client = cast(
        docker.DockerClient,
        SimpleNamespace(containers=SimpleNamespace(get=lambda _: container)),
    )
    result = helpers.get_container(client, "postgres-18")
    assert isinstance(result, Error)
    assert "ownership" in result.value


@pytest.mark.parametrize(
    "build_failure,run_status", [(False, 0), (True, 0), (False, 17)]
)
def test_build_and_run_use_current_immutable_image_and_fail_loudly(
    monkeypatch, tmp_path, build_failure, run_status
):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    manifest = tmp_path / "run.json"
    manifest.write_text(
        json.dumps(
            {
                "run_id": "owned-run",
                "snapshot": str(snapshot),
                "network": "owned-network",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DOTFILES_PODMAN_RUN_MANIFEST", str(manifest))
    monkeypatch.setattr(
        helpers, "selected_podman_endpoint", lambda: "unix:///selected.sock"
    )
    calls = []
    built = {}
    removed = []
    container = SimpleNamespace(
        id="owned-container-id",
        wait=lambda **_: {"StatusCode": run_status},
        logs=lambda **_: b"real-output",
        reload=lambda: None,
        attrs={"Config": {"Labels": {helpers.RUN_LABEL: "owned-run"}}},
        remove=lambda **kwargs: removed.append(kwargs),
    )

    def build(**kwargs):
        calls.append(("build", kwargs))
        if build_failure:
            raise RuntimeError("build failed")
        image = SimpleNamespace(
            id=IMAGE_ID,
            attrs={"RepoTags": [kwargs["tag"]], "Config": {"Labels": kwargs["labels"]}},
            reload=lambda: None,
        )
        built[kwargs["tag"]] = image
        return image, []

    def run(**kwargs):
        calls.append(("run", kwargs))
        return container

    def get_image(tag):
        if tag not in built:
            raise NotFound("absent exact tag")
        return built[tag]

    client = cast(
        docker.DockerClient,
        SimpleNamespace(
            images=SimpleNamespace(build=build, get=get_image),
            containers=SimpleNamespace(run=run),
        ),
    )
    if build_failure:
        with pytest.raises(RuntimeError, match="build failed"):
            helpers.build_test_image(client, "postgres-cli")
        assert [c[0] for c in calls] == ["build"]
        return
    image = helpers.build_test_image(client, "postgres-cli")
    if run_status:
        with pytest.raises(RuntimeError, match="status 17"):
            helpers.run_test_image(client, image, "script", {})
    else:
        assert helpers.run_test_image(client, image, "script", {}) == "real-output"
    assert calls[1][1]["image"] == IMAGE_ID
    assert calls[1][1]["network"] == "owned-network"
    assert calls[0][1]["path"] == str(snapshot / "emulator/postgres-cli")
    assert calls[0][1]["tag"].startswith("localhost/owned-run/build-")
    assert removed == [{"force": True}]
    with pytest.raises(RuntimeError, match="image ID"):
        helpers.run_test_image(client, "postgres-cli:latest", "script", {})


def test_unselected_capability_can_skip(monkeypatch, tmp_path):
    manifest = tmp_path / "run.json"
    manifest.write_text(
        json.dumps({"selected_containers": ["postgres-18"]}), encoding="utf-8"
    )
    monkeypatch.setenv("DOTFILES_PODMAN_RUN_MANIFEST", str(manifest))
    monkeypatch.setenv("DOTFILES_E2E_REQUIRED", "1")
    client = cast(docker.DockerClient, SimpleNamespace())
    with pytest.raises(pytest.skip.Exception, match="Deliberately unselected"):
        helpers.require_running(client, ["qdrant-emulator"])


@pytest.mark.parametrize(
    "reported", ["/run/user/501/podman.sock", "unix:///run/user/501/podman.sock"]
)
def test_linux_socket_representation_equivalence(monkeypatch, reported):
    monkeypatch.delenv("CONTAINER_HOST", raising=False)
    monkeypatch.delenv("CONTAINER_CONNECTION", raising=False)
    monkeypatch.setattr(helpers.platform, "system", lambda: "Linux")
    responses = [
        "podman version 5.4.2",
        "[]",
        json.dumps({"host": {"remoteSocket": {"path": reported}}}),
    ]
    monkeypatch.setattr(helpers, "podman_command", lambda args: responses.pop(0))
    assert helpers.selected_podman_endpoint() == "unix:///run/user/501/podman.sock"


@pytest.mark.parametrize(
    "reported", ["/run/user/501/podman.sock", "unix:///run/user/501/podman.sock"]
)
def test_machine_socket_representation_equivalence(monkeypatch, reported):
    monkeypatch.setattr(
        helpers,
        "podman_command",
        lambda args: json.dumps({"host": {"remoteSocket": {"path": reported}}}),
    )
    helpers._verify_machine_socket({"Name": "chosen"}, "/run/user/501/podman.sock")


@pytest.mark.parametrize(
    "endpoint", ["/run/selected.sock", "unix:///run/selected.sock"]
)
def test_explicit_unix_and_persisted_binding_are_canonical(
    monkeypatch, tmp_path, endpoint
):
    from tests.utils.run_journal import bind_endpoint

    monkeypatch.setenv("CONTAINER_HOST", endpoint)
    monkeypatch.setattr(helpers, "podman_command", lambda args: "podman version 5.6.0")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"endpoint": "/run/selected.sock"}), encoding="utf-8")
    assert bind_endpoint(path, endpoint)["endpoint"] == "unix:///run/selected.sock"
    client = SimpleNamespace(
        version=lambda: {"Components": [{"Name": "Podman Engine", "Version": "5.6.0"}]},
        ping=lambda: True,
    )
    created = []
    monkeypatch.setattr(
        helpers.docker,
        "DockerClient",
        lambda **kwargs: created.append(kwargs) or client,
    )
    assert helpers.podman_client(endpoint="/run/selected.sock") is client
    assert created == [{"base_url": "unix:///run/selected.sock", "version": "1.41"}]


@pytest.mark.parametrize(
    "endpoint",
    [
        "unix://remote/run/api.sock",
        "unix://user@localhost/run/api.sock",
        "unix:///run/api.sock?query",
        "unix:///run/api.sock#fragment",
        "unix:///run/api.sock?",
        "unix:///run/api.sock#",
        "relative.sock",
        "unix:relative.sock",
        "tcp://localhost:2375",
        "ssh://root@remote/run/api.sock",
        "//remote/api.sock",
        "unix:////remote/api.sock",
        "unix:///run/%61pi.sock",
        "unix:///run/../api.sock",
        "unix:///run/api.sock/",
        "/run//api.sock",
        "unix:///run/./api.sock",
        "\nunix:///run/api.sock",
        "unix:///run/a\tpi.sock",
        "unix:///run/api.sock\r",
        "unix:///run/api\x00.sock",
        "",
        "/run/api.sock?query",
        "/run/api.sock#fragment",
    ],
)
def test_explicit_malformed_unix_never_reaches_api(monkeypatch, endpoint):
    # A fake environment also exercises NUL, which native environ cannot store.
    monkeypatch.setattr(helpers.os, "environ", {"CONTAINER_HOST": endpoint})
    monkeypatch.setattr(helpers, "podman_command", lambda args: "podman version 5.6.0")
    created = []
    monkeypatch.setattr(
        helpers.docker, "DockerClient", lambda **kwargs: created.append(kwargs)
    )
    with pytest.raises(RuntimeError):
        helpers.podman_client()
    assert created == []


def test_machine_socket_rejects_different_inventory(monkeypatch):
    monkeypatch.setattr(
        helpers,
        "podman_command",
        lambda args: json.dumps(
            {"host": {"remoteSocket": {"path": "unix:///different.sock"}}}
        ),
    )
    with pytest.raises(RuntimeError, match="different inventory"):
        helpers._verify_machine_socket({"Name": "chosen"}, "/selected.sock")


@pytest.mark.parametrize("locus", ["linux", "machine-reported", "forwarded"])
@pytest.mark.parametrize(
    "value",
    [
        "unix://remote/run/api.sock",
        "unix:///run/api.sock?",
        "unix:///run/a\npi.sock",
        "relative.sock",
    ],
)
def test_discovered_unix_socket_validation_at_every_source(monkeypatch, locus, value):
    monkeypatch.delenv("CONTAINER_HOST", raising=False)
    monkeypatch.delenv("CONTAINER_CONNECTION", raising=False)
    info = json.dumps({"host": {"remoteSocket": {"path": value}}})
    if locus == "linux":
        monkeypatch.setattr(helpers.platform, "system", lambda: "Linux")
        responses = ["podman version 5.6.0", "[]", info]
        action = helpers.selected_podman_endpoint
    elif locus == "machine-reported":
        responses = [info]

        def action():
            return helpers._verify_machine_socket({"Name": "chosen"}, "/run/api.sock")
    else:
        monkeypatch.setattr(helpers.platform, "system", lambda: "Darwin")
        responses = [
            json.dumps(
                [
                    {
                        "Name": "chosen",
                        "SSHConfig": {
                            "Port": 555,
                            "RemoteUsername": "core",
                            "IdentityPath": "/key",
                        },
                        "ConnectionInfo": {"PodmanSocket": {"Path": value}},
                    }
                ]
            ),
            json.dumps({"host": {"remoteSocket": {"path": "/run/api.sock"}}}),
        ]

        def action():
            return helpers._machine_endpoint(
                {
                    "Name": "chosen",
                    "URI": "ssh://core@127.0.0.1:555/run/api.sock",
                    "Identity": "/key",
                }
            )

    monkeypatch.setattr(helpers, "podman_command", lambda args: responses.pop(0))
    with pytest.raises(RuntimeError):
        action()
