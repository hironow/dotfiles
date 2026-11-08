"""Locked fresh-state transactions and exact run-owned build-tag recovery.

The stable lock inode is deliberately retained. Image cleanup removes a single
prepared alias, never IDs/layers/cache; untrappable interruption can leave work.
"""

import json
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import docker
from docker.errors import NotFound

if os.name == "nt":
    import msvcrt
else:
    import fcntl

RUN_LABEL = "io.hironow.dotfiles.test-run"
RUN_MANIFEST_ENV = "DOTFILES_PODMAN_RUN_MANIFEST"
_THREAD_LOCK = threading.RLock()


@contextmanager
def _manifest_lock(path: Path) -> Generator[None]:
    with _THREAD_LOCK, path.with_name(path.name + ".lock").open("a+b") as lock:
        if os.name == "nt":
            if lock.seek(0, 2) == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def mutate_manifest(
    path: Path, change: Callable[[dict], None], *, initial: dict | None = None
) -> dict:
    """Read latest INSIDE the lock; no stale whole-manifest replacement API."""
    with _manifest_lock(path):
        if initial is not None:
            if path.exists():
                raise RuntimeError("Manifest already exists; preserve recoverable run")
            current = initial.copy()
        else:
            current = json.loads(path.read_text(encoding="utf-8"))
        change(current)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(json.dumps(current, indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return current


def journal_path(manifest: dict) -> Path:
    path = manifest.get("manifest_path") or os.environ.get(RUN_MANIFEST_ENV)
    if not path:
        raise RuntimeError("Resource mutations require the run manifest path")
    return Path(path)


def _endpoint_text(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or any(
            ord(char) < 32 or 127 <= ord(char) <= 159 or char.isspace()
            for char in value
        )
    ):
        raise RuntimeError("Invalid local socket endpoint: raw controls/whitespace")


def unix_socket_path(value: str) -> str:
    """Accept only a bare absolute Unix path or a local unix:/// URI."""
    _endpoint_text(value)
    if any(char in value for char in "?#%\\"):
        raise RuntimeError("Invalid local Unix socket endpoint")
    if value.startswith("unix:///"):
        parsed = urlsplit(value)
        if parsed.netloc or parsed.query or parsed.fragment or parsed.scheme != "unix":
            raise RuntimeError("Invalid local Unix socket endpoint")
        value = parsed.path
    if not value.startswith("/") or value.startswith("//") or value == "/":
        raise RuntimeError(
            "Expected an absolute local Unix socket; no TCP/SSH fallback"
        )
    if (
        value.endswith("/")
        or "//" in value
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise RuntimeError("Ambiguous local Unix socket endpoint")
    return value


def canonical_endpoint(value: str) -> str:
    _endpoint_text(value)
    if value.startswith("npipe:////./pipe/"):
        return value
    return "unix://" + unix_socket_path(value)


def bind_endpoint(path: Path, endpoint: str) -> dict:
    endpoint = canonical_endpoint(endpoint)

    def bind(current):
        if canonical_endpoint(current.get("endpoint", endpoint)) != endpoint:
            raise RuntimeError(
                "Selected Podman endpoint changed since this run started"
            )
        current["endpoint"] = endpoint

    return mutate_manifest(path, bind)


def _authorize_creation(current: dict, endpoint: str, kind: str) -> str:
    if current.get("cleanup_state"):
        raise RuntimeError(
            "Run is closing/closed; prepare a new isolated run before creation"
        )
    if canonical_endpoint(current.get("endpoint", "")) != canonical_endpoint(endpoint):
        raise RuntimeError("Selected Podman endpoint changed before creation")
    creation = uuid.uuid4().hex
    current.setdefault("creations", {})[creation] = {
        "kind": kind,
        "state": "in_progress",
        "run_id": current["run_id"],
        "endpoint": canonical_endpoint(endpoint),
    }
    return creation


def begin_creation(path: Path, endpoint: str, kind: str) -> str:
    authorized = []
    mutate_manifest(
        path,
        lambda current: authorized.append(_authorize_creation(current, endpoint, kind)),
    )
    return authorized[0]


def _complete_creation(current: dict, creation: str, receipt: str) -> None:
    record = current["creations"][creation]
    if not isinstance(receipt, str) or not receipt:
        raise RuntimeError("Creation completion requires a positive checked receipt")
    if record["run_id"] != current["run_id"] or record[
        "endpoint"
    ] != canonical_endpoint(current["endpoint"]):
        raise RuntimeError("Creation receipt ownership/endpoint mismatch")
    # Completion by the authorized producer is additive, even after closing.
    kind = {"container": "containers", "network": "networks"}.get(record["kind"])
    if kind is not None:
        resources = current.setdefault("resources", {}).setdefault(kind, [])
        if receipt not in resources:
            resources.append(receipt)
    record.update(state="completed", receipt=receipt)


def complete_creation(path: Path, creation: str, receipt: str) -> None:
    mutate_manifest(
        path, lambda current: _complete_creation(current, creation, receipt)
    )


def _unresolved_creations(current: dict) -> bool:
    return any(
        record.get("state") != "completed"
        or not isinstance(record.get("receipt"), str)
        or not record["receipt"]
        or record.get("run_id") != current["run_id"]
        or record.get("endpoint") != canonical_endpoint(current.get("endpoint", ""))
        for record in current.get("creations", {}).values()
    ) or any(
        record.get("creation_id") not in current.get("creations", {})
        for record in current.get("images", {}).values()
    )


def close_creations(path: Path) -> bool:
    """Latch this invocation's uncertainty BEFORE discovery; never recompute it away."""
    latched = []

    def close(current):
        current["cleanup_state"] = "closing"
        latched.append(_unresolved_creations(current))

    mutate_manifest(path, close)
    return latched[0]


def finish_cleanup(path: Path, *, incomplete: bool) -> None:
    unresolved = []

    def finish(current):
        unresolved.append(incomplete or _unresolved_creations(current))
        current["cleanup_state"] = "incomplete" if unresolved[0] else "closed"

    mutate_manifest(path, finish)
    if unresolved[0]:
        raise RuntimeError(
            "Cleanup incomplete: creation in-progress/unknown at closing; retain manifest and retry fresh discovery later"
        )


def prepare_image(
    client: docker.DockerClient, path: Path, tag: str, endpoint: str
) -> None:
    endpoint = canonical_endpoint(endpoint)

    def prepare(current):
        if current.get("cleanup_state"):
            raise RuntimeError(
                "Run is closing/closed; prepare a new isolated run before creation"
            )
        if canonical_endpoint(current.get("endpoint", "")) != endpoint:
            raise RuntimeError(
                "Selected Podman endpoint changed before image preparation"
            )
        if not tag.startswith(f"localhost/{current['run_id']}/"):
            raise RuntimeError("Image tag must belong to this exact run")
        images = current.setdefault("images", {})
        if tag in images:
            raise RuntimeError(
                "Build tag already prepared; recover this run before rebuilding"
            )
        try:
            client.images.get(tag)
        except NotFound:
            images[tag] = {
                "run_id": current["run_id"],
                "endpoint": endpoint,
                "state": "prepared",
                "creation_id": _authorize_creation(current, endpoint, "image"),
            }
        else:
            raise RuntimeError("Build tag already exists; refusing overwrite")

    mutate_manifest(path, prepare)


def _inspect_image(
    client: docker.DockerClient, current: dict, tag: str, record: dict
) -> str | None:
    if (
        record.get("run_id") != current["run_id"]
        or canonical_endpoint(record.get("endpoint", ""))
        != canonical_endpoint(current.get("endpoint", ""))
        or not tag.startswith(f"localhost/{current['run_id']}/")
    ):
        raise RuntimeError(
            f"Image preparation ownership/endpoint mismatch; retained {tag}"
        )
    try:
        image = client.images.get(tag)
    except NotFound:
        return None
    image.reload()
    image_id = image.id
    labels = (image.attrs.get("Config") or {}).get("Labels") or {}
    if (
        not isinstance(image_id, str)
        or not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id)
        or labels.get(RUN_LABEL) != current["run_id"]
        or tag not in (image.attrs.get("RepoTags") or [])
        or (record.get("id") is not None and record["id"] != image_id)
    ):
        raise RuntimeError(f"Image identity/label/tag mismatch; retained {tag}")
    return image_id


def observe_image(
    client: docker.DockerClient,
    path: Path,
    tag: str,
    *,
    expected: str | None = None,
    allow_absent: bool = False,
) -> str | None:
    errors = []
    observed = []

    def observe(current):
        record = current["images"][tag]
        try:
            if canonical_endpoint(current.get("endpoint", "")) != canonical_endpoint(
                record.get("endpoint", "")
            ):
                raise RuntimeError(
                    "Selected Podman endpoint changed before image observation"
                )
            image_id = _inspect_image(client, current, tag, record)
            if image_id is None and not allow_absent:
                raise RuntimeError(
                    f"Prepared image tag not observed; retained recovery record {tag}"
                )
            if expected is not None and image_id != expected:
                raise RuntimeError(
                    f"Built image identity differs from prepared tag; retained {tag}"
                )
            if image_id is not None:
                record.update(id=image_id, state="observed")
                record.pop("error", None)
            observed.append(image_id)
        except Exception as exc:
            record.update(state="retained", error=str(exc))
            errors.append(exc)

    mutate_manifest(path, observe)
    if errors:
        raise RuntimeError(f"Image observation incomplete: {errors[0]}") from errors[0]
    return observed[0]


def record_image_receipt(
    client: docker.DockerClient, path: Path, tag: str, *, expected: str | None = None
) -> None:
    """Only the producer's positive build/Compose result authorizes this receipt."""
    image_id = observe_image(client, path, tag, expected=expected)
    if image_id is None:
        raise RuntimeError("Positive image receipt requires a checked immutable ID")
    mutate_manifest(
        path,
        lambda current: _complete_creation(
            current, current["images"][tag]["creation_id"], image_id
        ),
    )


def _recover_images(client: docker.DockerClient, path: Path, endpoint: str) -> dict:
    errors = []

    def cleanup(current):
        if canonical_endpoint(current.get("endpoint", "")) != canonical_endpoint(
            endpoint
        ):
            raise RuntimeError("Selected Podman endpoint changed before image cleanup")
        for tag, record in current.get("images", {}).items():
            try:
                image_id = _inspect_image(client, current, tag, record)
                if image_id is None:
                    record.update(state="absent")
                    record.pop("error", None)
                    continue
                # Persist the observed ID before attempting untag in a separate
                # transaction. This loop only validates/recoveries identities.
                record.update(id=image_id, state="observed")
                record.pop("error", None)
            except Exception as exc:
                record.update(state="retained", error=str(exc))
                errors.append(exc)

    current = mutate_manifest(path, cleanup)
    if errors:
        raise RuntimeError(f"Image cleanup incomplete: {errors[0]}") from errors[0]
    return current


def cleanup_images(
    client: docker.DockerClient,
    path: Path,
    endpoint: str,
    command: Callable[[list[str]], str],
    *,
    closing_incomplete: bool | None = None,
) -> None:
    endpoint = canonical_endpoint(endpoint)
    # Always close here too; a caller may only ADD its earlier latched uncertainty.
    incomplete = close_creations(path) or bool(closing_incomplete)
    current = _recover_images(client, path, endpoint)
    errors = []
    for tag, record in current.get("images", {}).items():
        if record["state"] == "absent":
            continue

        def untag(latest, tag=tag):
            item = latest["images"][tag]
            if canonical_endpoint(latest.get("endpoint", "")) != endpoint:
                raise RuntimeError("Selected Podman endpoint changed before untag")
            try:
                image_id = _inspect_image(client, latest, tag, item)
                if image_id is not None:
                    command(["untag", image_id, tag])
                item.update(state="absent")
                item.pop("error", None)
            except Exception as exc:
                item.update(state="retained", error=str(exc))
                errors.append(exc)

        mutate_manifest(path, untag)
    if errors:
        raise RuntimeError(f"Image cleanup incomplete: {errors[0]}") from errors[0]
    finish_cleanup(path, incomplete=incomplete)
