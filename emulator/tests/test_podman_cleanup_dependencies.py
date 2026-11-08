"""Hermetic cleanup_run regressions for native Podman --requires dependencies."""

import copy
import itertools
import json
import subprocess
from types import SimpleNamespace
from typing import cast

import docker
import pytest
from docker.errors import APIError, NotFound

from tests.utils import helpers, isolation
from tests.utils.helpers import RUN_LABEL
from tests.utils.run_journal import begin_creation, complete_creation, mutate_manifest

RUN_ID = "dotfiles-ad79b26397a74e519f9bab8f5c41f323"
ENDPOINT = "unix:///selected.sock"
SPANNER = "0a9124dfe1bbafb66d71a1fb599e06d735cb3113adf8218512ab9d38fa44d754"
PGADAPTER = "bb806f9f4a60cc2745d2d6b40465a90d0aab3bbb6ea76e66f4b5b6b678aeaa03"
TEMPO = "d4e928751438400fa83723b94710eaa24cb834addf6dec5e9e5115b5a056f34c"
PROMETHEUS = "cb2d084c2c68b837b5e41e2ae60346d51a1d29fac32368a9a9dc5a49f6ef65f2"
LOKI = "81d6d34ddf647e91fbc8e2159a280b3ad213e2f5abd5cb90c1f9a9483fa37ae6"
COLLECTOR = "a26ec16fdb3d82cbd4c655f8d635765540261e33e3b9b00c7849929a9dc1fa4d"
GRAFANA = "c564325f2a90904d8e77ff2eefffec0408e46f62c069141074ae3b1be5fed560"
FOREIGN = "f" * 64
PAIR = {SPANNER: [], PGADAPTER: [SPANNER]}
TELEMETRY = {
    TEMPO: [],
    PROMETHEUS: [],
    LOKI: [],
    COLLECTOR: [PROMETHEUS, TEMPO],
    GRAFANA: [PROMETHEUS, LOKI, TEMPO],
}


class CleanupEngine:
    """Fake the SDK and native process boundaries, not cleanup internals."""

    def __init__(self, path, dependencies, order):
        self.path = path
        self.dependencies = copy.deepcopy(dependencies)
        self.live = {}
        self.removed = []
        self.attempts = []
        self.commands = []
        self.lookups = []
        self.reloads = []
        self.before_get = lambda resource_id: None
        self.before_reload = lambda resource_id: None
        self.native_response = lambda rows: rows
        self.native_failure = False
        self.before_inspect = lambda resource_id: None
        for resource_id in dependencies:
            self.live[resource_id] = SimpleNamespace(
                id=resource_id,
                attrs={"Config": {"Labels": {RUN_LABEL: RUN_ID}}},
                reload=lambda resource_id=resource_id: self.reload(resource_id),
                remove=lambda resource_id=resource_id, **kwargs: self.remove(
                    resource_id, kwargs
                ),
            )
        self.order = order
        self.later = []
        other = SimpleNamespace(
            list=lambda **kwargs: [],
            get=lambda resource_id: SimpleNamespace(
                id=resource_id,
                attrs={"Labels": {RUN_LABEL: RUN_ID}},
                reload=lambda: None,
                remove=lambda: self.later.append(resource_id),
            ),
        )
        self.client = SimpleNamespace(
            containers=SimpleNamespace(list=self.list_containers, get=self.get),
            networks=other,
            volumes=other,
        )
        self.manifest: dict = {
            "run_id": RUN_ID,
            "endpoint": ENDPOINT,
            "manifest_path": str(path),
            "resources": {
                "containers": list(order),
                "networks": ["owned-network"],
                "volumes": ["owned-volume"],
            },
            "creations": {},
            "images": {},
        }
        path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def list_containers(self, **kwargs):
        assert kwargs == {"all": True, "filters": {"label": f"{RUN_LABEL}={RUN_ID}"}}
        return [self.live[key] for key in self.order if key in self.live]

    def get(self, resource_id):
        self.lookups.append(resource_id)
        self.before_get(resource_id)
        if resource_id not in self.live:
            raise NotFound("exact container is absent")
        return self.live[resource_id]

    def reload(self, resource_id):
        self.reloads.append(resource_id)
        self.before_reload(resource_id)
        if resource_id not in self.live:
            raise NotFound("exact container disappeared during reload")

    def remove(self, resource_id, kwargs):
        assert kwargs == {"force": True}
        self.attempts.append(resource_id)
        if any(resource_id in self.dependencies[key] for key in self.live):
            raise APIError(
                "container has dependent containers which must be removed before it"
            )
        self.removed.append(resource_id)
        del self.live[resource_id]

    def process(self, args, **kwargs):
        assert args[:3] == ["podman", "container", "inspect"]
        assert len(args) == 4
        resource_id = args[3]
        assert resource_id in self.manifest["resources"]["containers"]
        assert resource_id != FOREIGN
        assert kwargs["env"]["CONTAINER_HOST"] == ENDPOINT
        assert "DOCKER_HOST" not in kwargs["env"]
        assert "CONTAINER_CONNECTION" not in kwargs["env"]
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "replace"
        assert self.attempts == []
        self.commands.append(resource_id)
        self.before_inspect(resource_id)
        if self.native_failure or resource_id not in self.live:
            raise subprocess.CalledProcessError(125, args, stderr="no such container")
        row = {
            "Id": resource_id,
            "Config": copy.deepcopy(self.live[resource_id].attrs["Config"]),
            "Dependencies": self.dependencies[resource_id],
        }
        result = self.native_response([row])
        return SimpleNamespace(
            stdout=result if isinstance(result, str) else json.dumps(result)
        )

    def cleanup(self):
        isolation.cleanup_run(cast(docker.DockerClient, self.client), self.manifest)

    def assert_incomplete(self):
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        assert saved["cleanup_state"] != "closed"
        assert saved["creations"] == self.manifest["creations"]
        assert self.later == []


@pytest.fixture
def engine(tmp_path, monkeypatch):
    def create(dependencies=None, order=None):
        dependencies = PAIR if dependencies is None else dependencies
        fake = CleanupEngine(
            tmp_path / "run.json",
            dependencies,
            list(dependencies) if order is None else order,
        )
        monkeypatch.setattr(isolation, "selected_podman_endpoint", lambda: ENDPOINT)
        monkeypatch.setenv("DOCKER_HOST", "unix:///foreign-docker.sock")
        monkeypatch.setenv("CONTAINER_HOST", "unix:///foreign-podman.sock")
        monkeypatch.setenv("CONTAINER_CONNECTION", "foreign-connection")
        monkeypatch.setattr(helpers.subprocess, "run", fake.process)
        return fake

    return create


def assert_dependent_first(order, dependencies):
    positions = {resource_id: index for index, resource_id in enumerate(order)}
    assert set(positions) == set(dependencies)
    assert len(order) == len(dependencies)
    for child, parents in dependencies.items():
        for parent in parents:
            if parent in positions:
                assert positions[child] < positions[parent]


@pytest.mark.parametrize("discovered_only", [False, True])
@pytest.mark.parametrize("order", list(itertools.permutations(PAIR)))
def test_cleanup_run_captured_pgadapter_spanner_every_enumeration(
    engine, order, discovered_only
):
    fake = engine(order=order)
    if discovered_only:
        mutate_manifest(
            fake.path, lambda current: current["resources"].update(containers=[])
        )
    fake.cleanup()
    assert_dependent_first(fake.removed, PAIR)
    assert fake.removed == [PGADAPTER, SPANNER]
    assert set(fake.commands) == set(PAIR)
    assert fake.later == ["owned-network", "owned-volume"]


@pytest.mark.parametrize("discovered_only", [False, True])
@pytest.mark.parametrize("order", list(itertools.permutations(TELEMETRY)))
def test_cleanup_run_captured_telemetry_every_enumeration(
    engine, order, discovered_only
):
    fake = engine(TELEMETRY, order)
    if discovered_only:
        mutate_manifest(
            fake.path, lambda current: current["resources"].update(containers=[])
        )
    fake.cleanup()
    assert_dependent_first(fake.removed, TELEMETRY)
    assert set(fake.commands) == set(TELEMETRY)
    assert fake.later == ["owned-network", "owned-volume"]


@pytest.mark.parametrize(
    "response",
    [
        "not-json",
        "null",
        "{}",
        "[]",
        "[null]",
        '["container"]',
        '[{"Id": "extra"}]',
    ],
)
def test_cleanup_run_invalid_native_json_or_rows_delete_nothing(engine, response):
    fake = engine()
    fake.native_response = lambda rows: response
    with pytest.raises(RuntimeError, match="native container"):
        fake.cleanup()
    assert fake.attempts == []
    fake.assert_incomplete()


@pytest.mark.parametrize(
    "damage",
    [
        "duplicate",
        "extra",
        "missing",
        "id",
        "config",
        "labels",
        "owner",
        "dependencies",
    ],
)
def test_cleanup_run_validates_entire_native_graph_before_removal(engine, damage):
    fake = engine()

    def response(rows):
        if rows[0]["Id"] != PGADAPTER:
            return rows
        row = rows[0]
        if damage == "duplicate":
            return [row, copy.deepcopy(row)]
        if damage == "extra":
            return [row, {**row, "Id": FOREIGN}]
        if damage == "missing":
            return []
        if damage == "id":
            row["Id"] = FOREIGN
        elif damage == "config":
            row["Config"] = None
        elif damage == "labels":
            row["Config"]["Labels"] = []
        elif damage == "owner":
            row["Config"]["Labels"][RUN_LABEL] = "foreign"
        else:
            row.pop("Dependencies")
        return rows

    fake.native_response = response
    with pytest.raises(RuntimeError, match="native container"):
        fake.cleanup()
    assert fake.commands == [SPANNER, PGADAPTER]
    assert fake.attempts == []
    fake.assert_incomplete()


@pytest.mark.parametrize(
    "parents",
    [
        None,
        {},
        "",
        [None],
        [True],
        [1],
        ["short"],
        ["a" * 63],
        ["a" * 65],
        ["A" * 64],
        ["sha256:" + SPANNER],
        [SPANNER + "\n"],
        [" " + SPANNER],
        [SPANNER, SPANNER],
        [[]],
    ],
)
def test_cleanup_run_rejects_missing_typed_full_dependency_identity(engine, parents):
    fake = engine()
    fake.native_response = lambda rows: [{**rows[0], "Dependencies": parents}]
    with pytest.raises(RuntimeError, match="dependency metadata"):
        fake.cleanup()
    assert fake.attempts == []
    fake.assert_incomplete()


@pytest.mark.parametrize("field", ["Id", "Config", "Labels", RUN_LABEL])
def test_cleanup_run_requires_native_identity_and_label_fields(engine, field):
    fake = engine()

    def response(rows):
        row = rows[0]
        target = (
            row
            if field in {"Id", "Config"}
            else row["Config"]
            if field == "Labels"
            else row["Config"]["Labels"]
        )
        target.pop(field)
        return rows

    fake.native_response = response
    with pytest.raises(RuntimeError, match="dependency metadata"):
        fake.cleanup()
    assert fake.attempts == []
    fake.assert_incomplete()


@pytest.mark.parametrize("failure", ["nonzero", "launch"])
def test_cleanup_run_native_failure_is_not_absence_or_retry(engine, failure):
    fake = engine()

    def inspect(resource_id):
        if resource_id == PGADAPTER:
            if failure == "launch":
                raise FileNotFoundError("fake executable unavailable")
            fake.native_failure = True

    fake.before_inspect = inspect
    with pytest.raises(RuntimeError, match="Podman"):
        fake.cleanup()
    assert fake.commands == [SPANNER, PGADAPTER]
    assert fake.lookups.count(PGADAPTER) == 2
    assert fake.attempts == []
    fake.assert_incomplete()


@pytest.mark.parametrize(
    "dependencies", [{SPANNER: [PGADAPTER], PGADAPTER: [SPANNER]}, {SPANNER: [SPANNER]}]
)
def test_cleanup_run_owned_cycle_deletes_nothing(engine, dependencies):
    fake = engine(dependencies)
    with pytest.raises(RuntimeError, match="dependency cycle"):
        fake.cleanup()
    assert fake.attempts == []
    fake.assert_incomplete()


def test_cleanup_run_external_parent_never_becomes_deletion_target(engine):
    fake = engine({PGADAPTER: [FOREIGN]})
    fake.dependencies[FOREIGN] = []
    fake.live[FOREIGN] = SimpleNamespace(
        attrs={"Config": {"Labels": {RUN_LABEL: "foreign"}}}
    )
    fake.cleanup()
    assert fake.removed == [PGADAPTER]
    assert fake.commands == [PGADAPTER]
    assert FOREIGN in fake.live
    assert FOREIGN not in fake.lookups


def test_cleanup_run_foreign_dependent_engine_error_propagates_without_retry(engine):
    fake = engine({SPANNER: []})
    fake.dependencies[FOREIGN] = [SPANNER]
    fake.live[FOREIGN] = SimpleNamespace(
        attrs={"Config": {"Labels": {RUN_LABEL: "foreign"}}}
    )
    with pytest.raises(APIError, match="dependent containers"):
        fake.cleanup()
    assert fake.commands == [SPANNER]
    assert fake.attempts == [SPANNER]
    assert fake.removed == []
    assert FOREIGN not in fake.lookups
    fake.assert_incomplete()


@pytest.mark.parametrize("phase", ["planning", "removal"])
@pytest.mark.parametrize("damage", ["id", "owner", "labels", "config", "attrs"])
def test_cleanup_run_fresh_sdk_identity_and_ownership_validation(engine, phase, damage):
    fake = engine()

    def change(resource_id):
        if resource_id != PGADAPTER or fake.reloads.count(resource_id) != (
            1 if phase == "planning" else 2
        ):
            return
        resource = fake.live[resource_id]
        if damage == "id":
            resource.id = FOREIGN
        elif damage == "owner":
            resource.attrs["Config"]["Labels"][RUN_LABEL] = "foreign"
        elif damage == "labels":
            resource.attrs["Config"]["Labels"] = None
        elif damage == "config":
            resource.attrs["Config"] = []
        else:
            resource.attrs = None

    fake.before_reload = change
    with pytest.raises(RuntimeError, match="unowned"):
        fake.cleanup()
    assert fake.attempts == []
    assert fake.commands == ([] if phase == "planning" else [SPANNER, PGADAPTER])
    fake.assert_incomplete()


@pytest.mark.parametrize("phase", ["planning", "removal"])
@pytest.mark.parametrize("operation", ["get", "reload"])
def test_cleanup_run_sdk_query_errors_are_not_absence(engine, phase, operation):
    fake = engine()

    def fail(resource_id):
        calls = fake.lookups if operation == "get" else fake.reloads
        if resource_id == PGADAPTER and calls.count(resource_id) == (
            1 if phase == "planning" else 2
        ):
            raise APIError("SDK transport failed")

    if operation == "get":
        fake.before_get = fail
    else:
        fake.before_reload = fail
    with pytest.raises(APIError, match="transport failed"):
        fake.cleanup()
    assert fake.attempts == []
    fake.assert_incomplete()


@pytest.mark.parametrize("phase", ["planning", "native", "removal"])
@pytest.mark.parametrize("operation", ["get", "reload"])
def test_cleanup_run_actual_sdk_notfound_receipt_allows_disappearance(
    engine, phase, operation
):
    fake = engine()

    def disappear(resource_id):
        calls = fake.lookups if operation == "get" else fake.reloads
        if resource_id == PGADAPTER and calls.count(resource_id) == (
            1 if phase == "planning" else 2
        ):
            fake.live.pop(resource_id, None)

    if phase == "native":
        fake.before_inspect = lambda resource_id: setattr(
            fake, "native_failure", resource_id == PGADAPTER
        )
    if operation == "get":
        fake.before_get = disappear
    else:
        fake.before_reload = disappear
    fake.cleanup()
    assert fake.removed == [SPANNER]
    assert fake.attempts == [SPANNER]
    assert fake.commands == ([SPANNER] if phase == "planning" else [SPANNER, PGADAPTER])
    assert fake.later == ["owned-network", "owned-volume"]


def test_cleanup_run_disappears_between_sdk_receipt_and_native_command(engine):
    fake = engine()
    fake.before_inspect = lambda resource_id: (
        fake.live.pop(resource_id) if resource_id == PGADAPTER else None
    )
    fake.cleanup()
    assert fake.removed == [SPANNER]
    assert fake.commands == [SPANNER, PGADAPTER]
    assert fake.lookups.count(PGADAPTER) == 2


def test_cleanup_run_actual_remove_notfound_is_idempotent(engine, monkeypatch):
    fake = engine()
    remove = fake.remove

    def disappeared(resource_id, kwargs):
        if resource_id == PGADAPTER:
            assert kwargs == {"force": True}
            fake.live.pop(resource_id)
            raise NotFound("disappeared just before DELETE")
        return remove(resource_id, kwargs)

    monkeypatch.setattr(fake, "remove", disappeared)
    fake.cleanup()
    assert fake.removed == [SPANNER]
    assert fake.later == ["owned-network", "owned-volume"]


@pytest.mark.parametrize(
    "resource_id",
    ["short", "a" * 63, "A" * 64, "sha256:" + SPANNER, SPANNER + "\n", 1, None],
)
def test_cleanup_run_invalid_recorded_container_identity_never_reaches_process(
    engine, resource_id
):
    fake = engine()
    mutate_manifest(
        fake.path, lambda current: current["resources"].update(containers=[resource_id])
    )
    with pytest.raises(RuntimeError, match="full container ID"):
        fake.cleanup()
    assert fake.commands == []
    assert fake.attempts == []
    fake.assert_incomplete()


def test_cleanup_run_changed_endpoint_fails_before_inspection_or_deletion(
    engine, monkeypatch
):
    fake = engine()
    monkeypatch.setattr(
        isolation, "selected_podman_endpoint", lambda: "unix:///other.sock"
    )
    with pytest.raises(RuntimeError, match="endpoint changed"):
        fake.cleanup()
    assert fake.commands == []
    assert fake.attempts == []
    assert fake.later == []


@pytest.mark.parametrize("late_receipt", [False, True])
def test_cleanup_run_dependency_inspection_cannot_complete_unknown_creator(
    engine, late_receipt
):
    fake = engine()
    creation = begin_creation(fake.path, ENDPOINT, "compose")
    if late_receipt:

        def complete(resource_id):
            if resource_id == SPANNER:
                complete_creation(fake.path, creation, "positive compose completion")

        fake.before_inspect = complete
    with pytest.raises(RuntimeError, match="incomplete"):
        fake.cleanup()
    assert_dependent_first(fake.removed, PAIR)
    saved = json.loads(fake.path.read_text(encoding="utf-8"))
    assert saved["cleanup_state"] == "incomplete"
    assert saved["creations"][creation]["state"] == (
        "completed" if late_receipt else "in_progress"
    )


@pytest.mark.parametrize(
    "native_id", ["short", "A" * 64, "sha256:" + SPANNER, SPANNER + "\n", None]
)
def test_cleanup_run_native_id_must_equal_requested_full_identity(engine, native_id):
    fake = engine()
    fake.native_response = lambda rows: [{**rows[0], "Id": native_id}]
    with pytest.raises(RuntimeError, match="dependency metadata"):
        fake.cleanup()
    assert fake.attempts == []
    fake.assert_incomplete()


def test_cleanup_run_corrupt_native_json_is_not_an_absence_receipt(engine):
    fake = engine()

    def corrupt(rows):
        if rows[0]["Id"] == PGADAPTER:
            fake.live.pop(PGADAPTER)
            return "invalid-json"
        return rows

    fake.native_response = corrupt
    with pytest.raises(RuntimeError, match="inspect JSON"):
        fake.cleanup()
    assert fake.attempts == []
    fake.assert_incomplete()
