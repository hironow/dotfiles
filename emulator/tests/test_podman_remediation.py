"""Public-consumer regressions for the reviewed SDK isolation defects."""

import importlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from docker.errors import DockerException, NotFound

from tests.utils import helpers, isolation, postgres
from tests.utils.image_inventory import IMAGE_ID, ImageInventory
from tests.utils.run_journal import cleanup_images, mutate_manifest


@pytest.fixture
def endpoint_manifest(tmp_path, monkeypatch):
    manifest = {
        "run_id": "owned-run",
        "containers": {
            "postgres-18": "run-postgres",
            "pgadapter-emulator": "run-pgadapter",
            "mlflow-server": "run-mlflow",
        },
        "services": {
            "emulator/postgres": "postgres-18",
            "emulator/pgadapter": "pgadapter-emulator",
            "emulator/mlflow": "mlflow-server",
        },
        "selected_containers": ["postgres-18", "pgadapter-emulator", "mlflow-server"],
        "host_ports": {"5433": 45433, "55432": 45432, "5252": 45252},
        "postgres_connection": {
            "host": "127.0.0.1",
            "port": 45433,
            "user": "postgres",
            "password": "password",
            "database": "postgres",
        },
    }
    path = tmp_path / "run.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(helpers.RUN_MANIFEST_ENV, str(path))
    monkeypatch.setenv("DOTFILES_E2E_REQUIRED", "1")
    for key in (
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "MLFLOW_PORT",
        "PGADAPTER_PORT",
    ):
        monkeypatch.delenv(key, raising=False)
    return manifest, path


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key,value",
    [
        ("POSTGRES_HOST", "198.51.100.99"),
        ("POSTGRES_DB", "hostilefixturedb"),
        ("POSTGRES_USER", "hostile"),
        ("POSTGRES_PASSWORD", "secret"),
    ],
)
async def test_postgres_connect_rejects_inherited_configuration_before_asyncpg(
    endpoint_manifest, monkeypatch, key, value
):
    calls = []

    async def connect(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(postgres.asyncpg, "connect", connect)
    monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match=key):
        await postgres.connect()
    assert calls == []


@pytest.fixture
def image_run(tmp_path, monkeypatch):
    path = tmp_path / "run.json"
    manifest = {
        "run_id": "owned-run",
        "snapshot": str(tmp_path / "snapshot"),
        "manifest_path": str(path),
        "endpoint": "unix:///selected.sock",
        "network": "owned-network",
        "resources": {"containers": [], "networks": [], "volumes": []},
        "images": {},
    }
    Path(manifest["snapshot"]).mkdir()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(helpers.RUN_MANIFEST_ENV, str(path))
    monkeypatch.setattr(
        helpers, "selected_podman_endpoint", lambda: manifest["endpoint"]
    )
    monkeypatch.setattr(
        isolation, "selected_podman_endpoint", lambda: manifest["endpoint"]
    )
    images = ImageInventory(manifest["run_id"])
    monkeypatch.setattr(helpers, "podman_command", images.command)
    return images, path, manifest


def test_helper_build_journals_and_cleanup_untags_only_owned_alias(image_run):
    images, path, stale = image_run
    assert helpers.build_test_image(images.client(), "postgres-cli") == IMAGE_ID
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["images"]) == 1
    tag, record = next(iter(saved["images"].items()))
    assert record["id"] == IMAGE_ID
    assert record["state"] == "observed"
    isolation.cleanup_run(images.client(), stale)
    assert tag not in images.tags
    assert images.image.attrs["RepoTags"] == [images.foreign_alias]
    assert (
        "command",
        ["untag", IMAGE_ID, tag],
        "unix:///selected.sock",
    ) in images.calls
    assert images.references == {"foreign-container": IMAGE_ID}


@pytest.mark.asyncio
async def test_postgres_connect_uses_complete_manifest_record(
    endpoint_manifest, monkeypatch
):
    calls = []

    async def connect(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(postgres.asyncpg, "connect", connect)
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    await postgres.connect()
    assert calls == [endpoint_manifest[0]["postgres_connection"]]


@pytest.mark.parametrize("failure", [RuntimeError("build failed"), KeyboardInterrupt()])
def test_interrupted_helper_build_recovers_only_prepared_labelled_tag(
    image_run, failure
):
    images, path, stale = image_run
    images.failure = failure
    with pytest.raises(type(failure)):
        helpers.build_test_image(images.client(), "postgres-cli")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert next(iter(saved["images"].values()))["id"] == IMAGE_ID
    # A labelled observed tag does not prove a failed producer terminated.
    with pytest.raises(RuntimeError, match="incomplete"):
        isolation.cleanup_run(images.client(), stale)
    assert images.tags == {}
    assert images.image.attrs["RepoTags"] == [images.foreign_alias]


def test_lock_acquisition_failure_prevents_new_build(image_run, monkeypatch):
    images, _, _ = image_run
    original = Path.open

    def failed_lock(path, *args, **kwargs):
        if path.name.endswith(".lock"):
            raise OSError("lock unavailable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failed_lock)
    with pytest.raises(OSError, match="lock unavailable"):
        helpers.build_test_image(images.client(), "postgres-cli")
    assert images.calls == []


def test_tag_absence_and_journal_precede_build_creation(image_run, monkeypatch):
    images, path, _ = image_run
    build = images.build

    def checked_build(**kwargs):
        saved = json.loads(path.read_text(encoding="utf-8"))
        record = saved["images"][kwargs["tag"]]
        assert saved["creations"][record["creation_id"]]["state"] == "in_progress"
        assert record == {
            "creation_id": record["creation_id"],
            "run_id": "owned-run",
            "endpoint": "unix:///selected.sock",
            "state": "prepared",
        }
        assert images.calls == [("inspect", kwargs["tag"])]
        return build(**kwargs)

    monkeypatch.setattr(images, "build", checked_build)
    helpers.build_test_image(images.client(), "postgres-cli")


@pytest.mark.parametrize("failure", ["query", "write", "existing"])
def test_preparation_failure_prevents_build(image_run, monkeypatch, failure):
    images, path, _ = image_run
    if failure == "query":

        def broken(_):
            raise RuntimeError("image query failed")

        monkeypatch.setattr(images, "get", broken)
    elif failure == "existing":
        monkeypatch.setattr(images, "get", lambda _: images.image)
    else:

        def broken_replace(*_):
            raise OSError("journal write failed")

        monkeypatch.setattr(Path, "replace", broken_replace)
    with pytest.raises((RuntimeError, OSError)):
        helpers.build_test_image(images.client(), "postgres-cli")
    assert not any(call[0] == "build" for call in images.calls)
    assert json.loads(path.read_text(encoding="utf-8"))["images"] == {}


def test_failed_observation_retains_recoverable_journal(image_run, monkeypatch):
    images, path, stale = image_run
    get = images.get

    def unavailable_after_build(tag):
        if images.tags:
            raise RuntimeError("inspection interrupted")
        return get(tag)

    monkeypatch.setattr(images, "get", unavailable_after_build)
    with pytest.raises(RuntimeError, match="observation incomplete"):
        helpers.build_test_image(images.client(), "postgres-cli")
    record = next(iter(json.loads(path.read_text(encoding="utf-8"))["images"].values()))
    assert record["state"] == "retained"
    assert "id" not in record
    monkeypatch.setattr(images, "get", get)
    with pytest.raises(RuntimeError, match="incomplete"):
        isolation.cleanup_run(images.client(), stale)
    assert images.tags == {}


@pytest.mark.parametrize("change", ["id", "label", "tag", "endpoint", "query", "untag"])
def test_cleanup_retains_uncertain_images_with_diagnostics(
    image_run, monkeypatch, change
):
    images, path, stale = image_run
    helpers.build_test_image(images.client(), "postgres-cli")
    tag = next(iter(images.tags))
    if change == "id":
        images.image.id = "sha256:" + "b" * 64
    elif change == "label":
        images.image.attrs["Config"]["Labels"][helpers.RUN_LABEL] = "foreign"
    elif change == "tag":
        images.image.attrs["RepoTags"].remove(tag)
    elif change == "endpoint":
        monkeypatch.setattr(
            isolation, "selected_podman_endpoint", lambda: "unix:///wrong.sock"
        )
    elif change == "query":

        def failed_get(_):
            raise RuntimeError("inspection failed")

        monkeypatch.setattr(images, "get", failed_get)
    else:

        def failed_untag(*args, **kwargs):
            raise RuntimeError("untag failed")

        monkeypatch.setattr(helpers, "podman_command", failed_untag)
    with pytest.raises(RuntimeError, match=r"changed|incomplete"):
        isolation.cleanup_run(images.client(), stale)
    assert tag in images.tags
    assert images.foreign_alias in images.image.attrs["RepoTags"]
    assert not any(call[0] == "command" for call in images.calls)
    record = json.loads(path.read_text(encoding="utf-8"))["images"][tag]
    if change != "endpoint":
        assert record["state"] == "retained"
        assert record["error"]


def test_missing_tag_cleanup_is_idempotent(image_run):
    images, path, stale = image_run
    helpers.build_test_image(images.client(), "postgres-cli")
    images.tags.clear()
    isolation.cleanup_run(images.client(), stale)
    isolation.cleanup_run(images.client(), stale)
    assert (
        next(iter(json.loads(path.read_text(encoding="utf-8"))["images"].values()))[
            "state"
        ]
        == "absent"
    )
    assert not any(call[0] == "command" for call in images.calls)


def test_concurrent_build_registrations_and_cleanup_keep_latest_additions(
    image_run, monkeypatch
):
    images, path, stale = image_run
    helpers.build_test_image(images.client(), "postgres-cli")
    prepared = Event()
    resume = Event()
    build = images.build

    def paused_build(**kwargs):
        prepared.set()
        assert resume.wait(5)
        return build(**kwargs)

    monkeypatch.setattr(images, "build", paused_build)
    with ThreadPoolExecutor(max_workers=2) as workers:
        pending = workers.submit(
            helpers.build_test_image, images.client(), "postgres-cli"
        )
        assert prepared.wait(5)
        try:
            with pytest.raises(RuntimeError, match="incomplete"):
                isolation.cleanup_run(images.client(), stale)
        finally:
            resume.set()
        assert pending.result(timeout=5) == IMAGE_ID
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert len(saved["images"]) == 2
    assert sorted(record["state"] for record in saved["images"].values()) == [
        "absent",
        "observed",
    ]
    isolation.cleanup_run(images.client(), stale)
    assert images.tags == {}


@pytest.mark.parametrize(
    "damage", ["unselected", "service", "missing", "host", "port", "credentials"]
)
@pytest.mark.asyncio
async def test_postgres_malformed_or_unselected_manifest_never_connects(
    endpoint_manifest, monkeypatch, damage
):
    manifest, path = endpoint_manifest
    if damage == "unselected":
        manifest["selected_containers"].remove("postgres-18")
    elif damage == "service":
        manifest["services"].pop("emulator/postgres")
    elif damage == "missing":
        manifest.pop("postgres_connection")
    else:
        manifest["postgres_connection"][
            {"host": "host", "port": "port", "credentials": "user"}[damage]
        ] = {"host": "198.51.100.99", "port": "45433", "credentials": ""}[damage]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    calls = []

    async def connect(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(postgres.asyncpg, "connect", connect)
    with pytest.raises(RuntimeError):
        await postgres.connect()
    assert calls == []


@pytest.mark.parametrize(
    "probe",
    [
        ("tests.test_pgadapter_emulator", "PGADAPTER_PORT", "55432", 45432),
        ("tests.test_postgres18_emulator", "POSTGRES_PORT", "5433", 45433),
    ],
)
@pytest.mark.parametrize("use_allocated", [False, True])
def test_database_public_probes_reach_only_their_loopback_allocation(
    endpoint_manifest,
    monkeypatch,
    probe,
    use_allocated,
):
    consumer, variable, canonical, allocated = probe
    module = importlib.import_module(consumer)
    monkeypatch.setenv(variable, str(allocated) if use_allocated else canonical)
    container = SimpleNamespace(
        status="running", attrs={"Config": {"Labels": {helpers.RUN_LABEL: "owned-run"}}}
    )
    monkeypatch.setattr(
        module,
        "podman_client",
        lambda: SimpleNamespace(containers=SimpleNamespace(get=lambda _: container)),
    )
    calls = []
    sock = SimpleNamespace(
        settimeout=lambda _: None,
        connect_ex=lambda address: calls.append(address) or 0,
        close=lambda: None,
    )
    monkeypatch.setattr(helpers.socket, "socket", lambda *args: sock)
    if variable == "PGADAPTER_PORT":
        module.test_pgadapter_container_starts()
    else:
        module.test_postgres18_container_starts()
    assert calls == [("127.0.0.1", allocated)]


def test_cleanup_process_boundary_uses_exact_manifest_endpoint_and_two_arguments(
    image_run, monkeypatch
):
    images, _, stale = image_run
    helpers.build_test_image(images.client(), "postgres-cli")
    command = helpers.podman_command
    # Recover the production command function replaced by this fixture.
    monkeypatch.undo()
    monkeypatch.setattr(
        isolation, "selected_podman_endpoint", lambda: stale["endpoint"]
    )
    monkeypatch.setenv("DOCKER_HOST", "unix:///foreign-docker.sock")
    monkeypatch.setenv("CONTAINER_CONNECTION", "foreign-connection")
    monkeypatch.setenv("CONTAINER_HOST", "unix:///foreign-podman.sock")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        images.command(args[1:], endpoint=kwargs["env"]["CONTAINER_HOST"])
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(helpers.subprocess, "run", run)
    isolation.cleanup_run(images.client(), stale)
    assert command is not helpers.podman_command
    assert len(calls) == 1
    args, options = calls[0]
    assert args[:3] == ["podman", "untag", IMAGE_ID]
    assert len(args) == 4
    assert options["env"]["CONTAINER_HOST"] == "unix:///selected.sock"
    assert "CONTAINER_CONNECTION" not in options["env"]
    assert "DOCKER_HOST" not in options["env"]


@pytest.mark.parametrize("when", ["before-creation", "after-observation"])
def test_helper_failure_retains_recovery_metadata(image_run, monkeypatch, when):
    images, path, stale = image_run
    if when == "before-creation":

        def failed_build(**kwargs):
            raise RuntimeError("build failed before tag creation")

        monkeypatch.setattr(images, "build", failed_build)
        with pytest.raises(RuntimeError, match="before tag creation"):
            helpers.build_test_image(images.client(), "postgres-cli")
    else:
        replace = Path.replace

        def interrupted_write(source, target):
            if images.tags:
                raise OSError("write failed after observation")
            return replace(source, target)

        monkeypatch.setattr(Path, "replace", interrupted_write)
        with pytest.raises(OSError, match="after observation"):
            helpers.build_test_image(images.client(), "postgres-cli")
        monkeypatch.setattr(Path, "replace", replace)
    record = next(iter(json.loads(path.read_text(encoding="utf-8"))["images"].values()))
    assert record["state"] == "prepared"
    with pytest.raises(RuntimeError, match="incomplete"):
        isolation.cleanup_run(images.client(), stale)
    assert images.tags == {}


@pytest.mark.asyncio
async def test_mlflow_public_probe_reaches_own_loopback_allocation(
    endpoint_manifest, monkeypatch
):
    module = importlib.import_module("tests.test_mlflow_emulator")
    monkeypatch.setenv("MLFLOW_PORT", "45252")
    container = SimpleNamespace(
        status="running", attrs={"Config": {"Labels": {helpers.RUN_LABEL: "owned-run"}}}
    )
    monkeypatch.setattr(
        module,
        "podman_client",
        lambda: SimpleNamespace(containers=SimpleNamespace(get=lambda _: container)),
    )
    calls = []

    class Response:
        async def __aenter__(self):
            return SimpleNamespace(status=200)

        async def __aexit__(self, *_):
            return None

    def get(url):
        calls.append(url)
        return Response()

    await module.test_mlflow_container_starts(SimpleNamespace(get=get))
    assert calls == ["http://127.0.0.1:45252/"] * 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "consumer", ["tests.test_mlflow_emulator", "tests.e2e.test_mlflow_e2e"]
)
async def test_unselected_mlflow_public_consumer_skips_without_io(
    endpoint_manifest, consumer
):
    _, path = endpoint_manifest
    mutate_manifest(
        path, lambda current: current["selected_containers"].remove("mlflow-server")
    )
    module = importlib.import_module(consumer)
    with pytest.raises(pytest.skip.Exception, match="Deliberately unselected"):
        if consumer.endswith("test_mlflow_emulator"):
            await module.test_mlflow_container_starts(None)
        else:
            await module.test_mlflow_e2e_logging_and_persistence(None, None, None, None)


def test_cross_process_transactions_preserve_all_additions_and_lock_inode(image_run):
    _, path, _ = image_run
    program = """import sys
from pathlib import Path
from tests.utils.run_journal import mutate_manifest
path = Path(sys.argv[1])
print('ready', flush=True)
sys.stdin.buffer.read(1)
for number in range(12):
    def add(current):
        current['images'][f'{sys.argv[2]}-{number}'] = {'state': 'prepared'}
    mutate_manifest(path, add)
"""
    lock = path.with_name(path.name + ".lock")
    mutate_manifest(path, lambda _: None)
    inode = lock.stat().st_ino
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", program, str(path), str(worker)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for worker in range(4)
    ]
    for process in processes:
        assert process.stdout is not None
        assert process.stdout.readline() == b"ready\n"
    for process in processes:
        assert process.stdin is not None
        process.stdin.write(b"x")
        process.stdin.flush()
    results = [process.communicate(timeout=20) for process in processes]
    assert [process.returncode for process in processes] == [0] * 4, results
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert set(saved["images"]) == {
        f"{worker}-{number}" for worker in range(4) for number in range(12)
    }
    assert lock.stat().st_ino == inode
    assert not list(path.parent.glob("*.tmp"))


def test_observation_rejects_changed_endpoint_and_retains_preparation(
    image_run, monkeypatch
):
    images, path, _ = image_run
    build = images.build

    def changed_endpoint(**kwargs):
        result = build(**kwargs)
        mutate_manifest(
            path, lambda current: current.update(endpoint="unix:///changed.sock")
        )
        return result

    monkeypatch.setattr(images, "build", changed_endpoint)
    with pytest.raises(RuntimeError, match="endpoint changed"):
        helpers.build_test_image(images.client(), "postgres-cli")
    saved = json.loads(path.read_text(encoding="utf-8"))
    record = next(iter(saved["images"].values()))
    assert record["state"] == "retained"
    assert images.tags
    assert "id" not in record


def test_cleanup_write_failure_after_untag_recovers_idempotently(
    image_run, monkeypatch
):
    images, path, stale = image_run
    helpers.build_test_image(images.client(), "postgres-cli")
    replace = Path.replace

    def failed_write(source, target):
        if not images.tags:
            raise OSError("write interrupted after untag")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", failed_write)
    with pytest.raises(OSError, match="after untag"):
        isolation.cleanup_run(images.client(), stale)
    record = next(iter(json.loads(path.read_text(encoding="utf-8"))["images"].values()))
    assert record["id"] == IMAGE_ID
    assert record["state"] == "observed"
    monkeypatch.setattr(Path, "replace", replace)
    isolation.cleanup_run(images.client(), stale)
    assert (
        next(iter(json.loads(path.read_text(encoding="utf-8"))["images"].values()))[
            "state"
        ]
        == "absent"
    )
    assert len([call for call in images.calls if call[0] == "command"]) == 1


def test_explicit_nonmanifest_postgres_configuration_is_unchanged(monkeypatch):
    monkeypatch.delenv(helpers.RUN_MANIFEST_ENV, raising=False)
    monkeypatch.delenv("DOTFILES_E2E_REQUIRED", raising=False)
    for variable, value in {
        "POSTGRES_HOST": "198.51.100.99",
        "POSTGRES_PORT": "5439",
        "POSTGRES_USER": "devuser",
        "POSTGRES_PASSWORD": "devpass",
        "POSTGRES_DB": "devdb",
    }.items():
        monkeypatch.setenv(variable, value)
    assert postgres.conn_params() == {
        "host": "198.51.100.99",
        "port": 5439,
        "user": "devuser",
        "password": "devpass",
        "database": "devdb",
    }


@pytest.mark.asyncio
async def test_mlflow_e2e_configures_only_validated_loopback_tracking_endpoint(
    endpoint_manifest, monkeypatch
):
    module = importlib.import_module("tests.e2e.test_mlflow_e2e")
    monkeypatch.setenv("MLFLOW_PORT", "5252")
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "http://198.51.100.99:5000")
    calls = []

    class ReachedClientError(Exception):
        pass

    def tracking_client():
        calls.append(("client", module.os.environ["MLFLOW_TRACKING_URI"]))
        raise ReachedClientError

    monkeypatch.setitem(sys.modules, "mlflow", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules, "mlflow.tracking", SimpleNamespace(MlflowClient=tracking_client)
    )

    class Response:
        async def __aenter__(self):
            return SimpleNamespace(status=200)

        async def __aexit__(self, *_):
            return None

    def get(url):
        calls.append(("http", url))
        return Response()

    with pytest.raises(ReachedClientError):
        await module.test_mlflow_e2e_logging_and_persistence(
            SimpleNamespace(get=get), None, lambda: None, lambda _: None
        )
    assert calls == [
        ("http", "http://127.0.0.1:45252/"),
        ("client", "http://127.0.0.1:45252"),
    ]


def test_many_concurrent_helper_additions_survive_discovery(image_run):
    images, path, stale = image_run
    with ThreadPoolExecutor(max_workers=6) as workers:
        pending = [
            workers.submit(helpers.build_test_image, images.client(), "postgres-cli")
            for _ in range(18)
        ]
        isolation.discover_resources(images.client(), stale)
        assert [job.result(timeout=10) for job in pending] == [IMAGE_ID] * 18
    assert len(json.loads(path.read_text(encoding="utf-8"))["images"]) == 18
    isolation.cleanup_run(images.client(), stale)
    assert images.tags == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "consumer", ["tests.test_mlflow_emulator", "tests.e2e.test_mlflow_e2e"]
)
@pytest.mark.parametrize("value", ["5252@198.51.100.99:5000", "abc", "5433"])
async def test_mlflow_public_consumers_validate_before_http_or_tracking_client(
    endpoint_manifest, monkeypatch, consumer, value
):
    module = importlib.import_module(consumer)
    calls = []
    monkeypatch.setenv("MLFLOW_PORT", value)
    container = SimpleNamespace(
        status="running", attrs={"Config": {"Labels": {helpers.RUN_LABEL: "owned-run"}}}
    )
    engine = SimpleNamespace(containers=SimpleNamespace(get=lambda _: container))
    if hasattr(module, "podman_client"):
        monkeypatch.setattr(module, "podman_client", lambda: engine)

    class Response:
        async def __aenter__(self):
            calls.append("http")
            return SimpleNamespace(status=200)

        async def __aexit__(self, *_):
            return None

    client = SimpleNamespace(get=lambda *args, **kwargs: Response())

    async def wait(*args, **kwargs):
        raise AssertionError("HTTP wait invoked before endpoint validation")

    monkeypatch.setattr(helpers, "wait_for_http", wait)

    def tracking_client():
        raise AssertionError("MLflow client invoked before endpoint validation")

    monkeypatch.setitem(sys.modules, "mlflow", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules, "mlflow.tracking", SimpleNamespace(MlflowClient=tracking_client)
    )
    with pytest.raises(RuntimeError, match="MLFLOW_PORT"):
        if consumer.endswith("test_mlflow_emulator"):
            await module.test_mlflow_container_starts(client)
        else:
            await module.test_mlflow_e2e_logging_and_persistence(
                client, None, lambda: None, lambda _: None
            )
    assert calls == []


@pytest.mark.parametrize(
    "consumer,variable,value",
    [
        ("tests.test_pgadapter_emulator", "PGADAPTER_PORT", "5433"),
        ("tests.test_postgres18_emulator", "POSTGRES_PORT", "55432"),
    ],
)
def test_database_probe_rejects_other_service_port_before_socket(
    endpoint_manifest, monkeypatch, consumer, variable, value
):
    module = importlib.import_module(consumer)
    calls = []
    monkeypatch.setenv(variable, value)
    container = SimpleNamespace(
        status="running", attrs={"Config": {"Labels": {helpers.RUN_LABEL: "owned-run"}}}
    )
    monkeypatch.setattr(
        module,
        "podman_client",
        lambda: SimpleNamespace(containers=SimpleNamespace(get=lambda _: container)),
    )
    sock = SimpleNamespace(
        settimeout=lambda _: None,
        connect_ex=lambda address: calls.append(address) or 0,
        close=lambda: None,
    )
    monkeypatch.setattr(helpers.socket, "socket", lambda *args: sock)
    with pytest.raises(RuntimeError, match=variable):
        if variable == "PGADAPTER_PORT":
            module.test_pgadapter_container_starts()
        else:
            module.test_postgres18_container_starts()
    assert calls == []


@pytest.mark.parametrize("cleanup_seam", ["run", "images"])
def test_transport_error_absence_never_completes_creation(
    image_run, monkeypatch, cleanup_seam
):
    images, path, stale = image_run

    def transport_error(**kwargs):
        raise DockerException("transport lost; server completion unknown")

    monkeypatch.setattr(images, "build", transport_error)
    with pytest.raises(DockerException, match="transport lost"):
        helpers.build_test_image(images.client(), "postgres-cli")
    with pytest.raises(RuntimeError, match="incomplete"):
        if cleanup_seam == "run":
            isolation.cleanup_run(images.client(), stale)
        else:
            cleanup_images(images.client(), path, stale["endpoint"], images.command)
    assert path.exists()


def test_cleanup_latches_authorized_producer_before_absent_discovery(
    image_run, monkeypatch
):
    images, path, stale = image_run
    prepared, resume, absent, completed = Event(), Event(), Event(), Event()
    build, get = images.build, images.get

    def paused_build(**kwargs):
        prepared.set()
        assert resume.wait(5)
        result = build(**kwargs)
        return result

    def inspect(tag):
        if absent.is_set():
            return get(tag)
        try:
            return get(tag)
        except Exception:
            # Only cleanup's inspection, after preparation, resumes the producer.
            if prepared.is_set():
                absent.set()
                resume.set()
            raise

    monkeypatch.setattr(images, "build", paused_build)
    monkeypatch.setattr(images, "get", inspect)
    with ThreadPoolExecutor(max_workers=2) as workers:
        pending = workers.submit(
            helpers.build_test_image, images.client(), "postgres-cli"
        )
        assert prepared.wait(5)
        # Pause after cleanup has observed absence and released its journal lock.
        from tests.utils import run_journal

        recover = run_journal._recover_images

        def after_absence(*args):
            result = recover(*args)
            assert absent.is_set()
            assert pending.result(timeout=5) == IMAGE_ID
            completed.set()
            return result

        monkeypatch.setattr(run_journal, "_recover_images", after_absence)
        with pytest.raises(RuntimeError, match="incomplete"):
            isolation.cleanup_run(images.client(), stale)
        assert completed.is_set()
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["cleanup_state"] != "closed"
    assert next(iter(saved["images"].values()))["state"] == "observed"
    monkeypatch.setattr(run_journal, "_recover_images", recover)
    isolation.cleanup_run(images.client(), stale)
    assert images.tags == {}


@pytest.mark.parametrize(
    "failure", ["transport", "receipt", "wait", "logs", "status", None]
)
def test_helper_container_creation_receipt_is_distinct_from_application_failure(
    image_run, failure
):
    images, path, stale = image_run
    client = images.client()
    removed, created = [], []

    def wait(**kwargs):
        if failure == "wait":
            raise RuntimeError("wait failed")
        return {"StatusCode": 9 if failure == "status" else 0}

    def logs(**kwargs):
        if failure == "logs":
            raise RuntimeError("logs failed")
        return b"output"

    container = SimpleNamespace(
        id="c" * 64,
        attrs={
            "Config": {
                "Labels": {
                    helpers.RUN_LABEL: "foreign"
                    if failure == "receipt"
                    else "owned-run"
                }
            }
        },
        reload=lambda: None,
        wait=wait,
        logs=logs,
        remove=lambda **kwargs: removed.append(kwargs),
    )

    def run(**kwargs):
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert any(
            record["kind"] == "container" and record["state"] == "in_progress"
            for record in saved["creations"].values()
        )
        created.append(kwargs)
        if failure == "transport":
            raise RuntimeError("transport lost")
        return container

    def absent(_):
        raise NotFound("helper already removed its checked container")

    client.containers = SimpleNamespace(run=run, list=lambda **kwargs: [], get=absent)
    if failure:
        with pytest.raises(RuntimeError):
            helpers.run_test_image(client, IMAGE_ID, "command", {})
    else:
        assert helpers.run_test_image(client, IMAGE_ID, "command", {}) == "output"
    assert len(created) == 1
    saved = json.loads(path.read_text(encoding="utf-8"))
    record = next(iter(saved["creations"].values()))
    if failure in {"transport", "receipt"}:
        assert record["state"] == "in_progress"
        assert removed == []
        with pytest.raises(RuntimeError, match="incomplete"):
            isolation.cleanup_run(client, stale)
    else:
        assert record["state"] == "completed"
        assert record["receipt"] == "c" * 64
        assert saved["resources"]["containers"] == ["c" * 64]
        assert removed == [{"force": True}]
        isolation.cleanup_run(client, stale)


@pytest.mark.parametrize("late_before_return", [False, True])
def test_paused_helper_container_blocks_cleanup_and_future_creation(
    image_run, monkeypatch, late_before_return
):
    images, path, stale = image_run
    client = images.client()
    authorized, resume = Event(), Event()
    calls = []
    container = SimpleNamespace(
        id="c" * 64,
        attrs={"Config": {"Labels": {helpers.RUN_LABEL: "owned-run"}}},
        reload=lambda: None,
        wait=lambda **kwargs: {"StatusCode": 0},
        logs=lambda **kwargs: b"output",
        remove=lambda **kwargs: calls.append("remove"),
    )

    def paused(**kwargs):
        authorized.set()
        assert resume.wait(5)
        calls.append("create")
        return container

    discovered = Event()

    def list_containers(**kwargs):
        discovered.set()
        return []

    def absent(_):
        raise NotFound("helper already removed its checked container")

    client.containers = SimpleNamespace(run=paused, list=list_containers, get=absent)
    finish = isolation.finish_cleanup

    def finish_after_receipt(*args, **kwargs):
        assert discovered.is_set()
        resume.set()
        assert pending.result(timeout=5) == "output"
        return finish(*args, **kwargs)

    if late_before_return:
        monkeypatch.setattr(isolation, "finish_cleanup", finish_after_receipt)
    with ThreadPoolExecutor(max_workers=1) as workers:
        pending = workers.submit(
            helpers.run_test_image, client, IMAGE_ID, "command", {}
        )
        assert authorized.wait(5)
        try:
            with pytest.raises(RuntimeError, match="incomplete"):
                isolation.cleanup_run(client, stale)
            before = list(calls)
            with pytest.raises(RuntimeError, match="closing/closed"):
                helpers.run_test_image(client, IMAGE_ID, "command", {})
            assert calls == before
            assert calls == (["create", "remove"] if late_before_return else [])
            mutate_manifest(
                path, lambda current: current.update(unrelated_entry="keep")
            )
        finally:
            resume.set()
        assert pending.result(timeout=5) == "output"
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["cleanup_state"] == "incomplete"
    assert saved["unrelated_entry"] == "keep"
    monkeypatch.setattr(isolation, "finish_cleanup", finish)
    isolation.cleanup_run(client, stale)
    assert json.loads(path.read_text(encoding="utf-8"))["cleanup_state"] == "closed"
    assert calls == ["create", "remove"]
