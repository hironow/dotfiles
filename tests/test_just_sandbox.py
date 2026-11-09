import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from os import open as open_file_descriptor
from pathlib import Path, PurePosixPath
from typing import Literal

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER_JSON = ROOT / ".devcontainer" / "devcontainer.json"
RUN_LABEL = "io.hironow.dotfiles.sandbox-run"
RUN_NONCE_ENV = "DOTFILES_SANDBOX_RUN_ID"
BUILD_STATES = {"not-started", "running", "succeeded", "interrupted"}
OPERATION_STATES = {"not-started", "pending", "unknown", "completed"}

# CI sets this (the `env:` block of .github/workflows/test-just.yaml) to state
# that the checkout at LOCAL_WORKSPACE_FOLDER is a runner checkout thrown away
# with the job, and may therefore be bind-mounted and written to.
DISPOSABLE_CHECKOUT_ENV = "DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT"


def _mount_mode(env: Mapping[str, str]) -> Literal["bind", "snapshot"]:
    """Decide what `run_in_sandbox` may mount at /root/dotfiles.

    Every sandbox script is prefixed with `_GIT_INIT`, which runs `git init`,
    OVERWRITES `.git/info/exclude` and `git add -A` in the mounted tree, and
    recipes like `just fmt` write to it as well. That is only ever safe on a
    disposable copy.

    LOCAL_WORKSPACE_FOLDER is NOT that proof: devcontainer.json exports it
    inside the dev container too, so `just test` from a dev container on a
    developer machine would point it at the real working repo. Only CI knows
    its checkout is disposable, so CI has to say so explicitly.

    The remaining case -- LOCAL_WORKSPACE_FOLDER set, nothing declaring it
    disposable -- is refused rather than silently snapshotted: a snapshot made
    inside the dev container is a CONTAINER path that the outer daemon cannot
    resolve, so `-v` would mount an empty dir and the whole suite would fail
    obscurely. Fail loudly with the reason instead.
    """
    local_workspace = env.get("LOCAL_WORKSPACE_FOLDER")
    if local_workspace is None:
        return "snapshot"
    if env.get(DISPOSABLE_CHECKOUT_ENV) == "1":
        return "bind"
    raise RuntimeError(
        f"refusing to bind-mount {local_workspace!r} into the sandbox: it looks "
        "like a real working checkout, and the sandbox runs `git init`, "
        "overwrites .git/info/exclude and `git add -A` in whatever it mounts. "
        f"Only CI may bind a checkout, by setting {DISPOSABLE_CHECKOUT_ENV}=1. "
        "Run `just test` from the host, not from inside the dev container."
    )


def _host_workspace_path() -> str:
    """Resolve the explicit engine-side workspace for nested one-shot binds.

    The outside Podman engine resolves bind sources in its own namespace.
    LOCAL_WORKSPACE_FOLDER supplies that mapping; it does not prove the
    checkout disposable. `_mount_mode` independently enforces that fence.
    """
    return os.environ.get("LOCAL_WORKSPACE_FOLDER", str(ROOT))


def _run(
    cmd: list[str] | str, cwd: Path | None = None, env: dict | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        shell=isinstance(cmd, str),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )


def _docker_available() -> bool:
    """Compatibility name for the required Podman client/server check.

    The client from `podman version`, the selected engine from `podman info`
    (as .devcontainer/require-podman-socket.sh reads it): native Podman, as on
    the CI runner, prints only `Client` from `podman version`. Both must be 5
    or newer; anything missing or malformed counts as not available."""

    def major(text: str) -> int:
        # the whole string, as require-podman-socket.sh matches it
        match = re.fullmatch(r"([0-9]+)\.[0-9]+\.[0-9]+(?:[-.+][^\s]+)?", text)
        if match is None:
            raise ValueError(text)
        return int(match.group(1))

    try:
        version = _run(["podman", "version", "--format", "json"])
        if version.returncode:
            return False
        client = json.loads(version.stdout)["Client"]["Version"]
        info = _run(["podman", "info", "--format", "json"])
        if info.returncode:
            return False
        engine = json.loads(info.stdout)["version"]["Version"]
        if not isinstance(client, str) or not isinstance(engine, str):
            return False
        return major(client) >= 5 and major(engine) >= 5
    except (FileNotFoundError, ValueError, KeyError, TypeError):
        # json.JSONDecodeError is a ValueError
        return False


def _checked(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = _run(cmd, **kwargs)
    if result.returncode:
        raise RuntimeError(
            f"{cmd!r} failed ({result.returncode})\n{result.stdout}\n{result.stderr}"
        )
    return result


def _json_output(result: subprocess.CompletedProcess) -> dict:
    # devcontainer may emit progress before its final JSON receipt.
    for line in reversed(result.stdout.splitlines()):
        if line.startswith("{"):
            return json.loads(line)
    raise RuntimeError(f"missing devcontainer JSON receipt: {result.stdout}")


def _selected_engine_identity() -> dict:
    info = json.loads(_checked(["podman", "info", "--format", "json"]).stdout)
    host = info["host"]
    socket = host["remoteSocket"]["path"]
    hostname = host["hostname"]
    graph_root = info["store"]["graphRoot"]
    if not all(
        isinstance(value, str) and value for value in (socket, hostname, graph_root)
    ):
        raise RuntimeError("selected engine identity unavailable")
    endpoint = os.environ.get("CONTAINER_HOST")
    if not endpoint and host.get("serviceIsRemote"):
        connections = json.loads(
            _checked(
                ["podman", "system", "connection", "list", "--format", "json"]
            ).stdout
        )
        selected_name = os.environ.get("CONTAINER_CONNECTION")
        selected = (
            [
                connection
                for connection in connections
                if connection.get("Name") == selected_name
            ]
            if selected_name
            else [
                connection
                for connection in connections
                if connection.get("Default") is True
            ]
        )
        if len(selected) != 1 or not selected[0].get("URI"):
            raise RuntimeError("selected remote connection is missing/ambiguous")
        endpoint = selected[0]["URI"]
    return {
        "hostname": hostname,
        "graph_root": graph_root,
        "socket": socket,
        "endpoint": endpoint or "native-local",
    }


def _validate_run_record(record: dict) -> None:
    required = {
        "run_id",
        "tag",
        "tag_was_absent",
        "image_id",
        "container_ids",
        "engine",
        "complete",
        "build_state",
        "snapshot_path",
        "up_state",
        "exec_state",
        "create_state",
    }
    if not isinstance(record, dict) or set(record) != required:
        raise RuntimeError("partial/invalid devcontainer record; retaining resources")
    if not isinstance(record["run_id"], str) or not re.fullmatch(
        r"[0-9a-f]{32}", record["run_id"]
    ):
        raise RuntimeError("invalid devcontainer run identity; retaining resources")
    if (
        not isinstance(record["build_state"], str)
        or record["build_state"] not in BUILD_STATES
    ):
        raise RuntimeError("invalid build completion state")
    for operation in ("up", "exec", "create"):
        value = record[f"{operation}_state"]
        if not isinstance(value, str) or value not in OPERATION_STATES:
            raise RuntimeError("invalid resource-operation completion state")
    if (
        (
            record["tag"] is None
            and any(record[f"{op}_state"] != "not-started" for op in ("up", "exec"))
        )
        or (record["tag"] is not None and record["create_state"] != "not-started")
        or (
            record["up_state"] != "not-started" and record["build_state"] != "succeeded"
        )
        or (record["exec_state"] != "not-started" and record["up_state"] != "completed")
        or (
            any(record[f"{op}_state"] == "completed" for op in ("up", "create"))
            and not record["container_ids"]
        )
    ):
        raise RuntimeError("inconsistent resource-operation accounting record")
    # Diagnostic metadata only: recovery must never use this as deletion authority.
    snapshot_path = record["snapshot_path"]
    if snapshot_path is not None and (
        not isinstance(snapshot_path, str)
        or not snapshot_path
        or "\x00" in snapshot_path
    ):
        raise RuntimeError("invalid snapshot diagnostic path")
    if record["build_state"] != "not-started" and snapshot_path is None:
        raise RuntimeError("missing build snapshot diagnostic path")
    if record["tag"] is None:
        if (
            record["tag_was_absent"] is not False
            or record["image_id"] is not None
            or record["build_state"] != "not-started"
        ):
            raise RuntimeError("invalid container-only ownership record")
    elif (
        record["tag"] != f"localhost/dotfiles-sandbox:{record['run_id']}"
        or record["tag_was_absent"] is not True
    ):
        raise RuntimeError("invalid fresh image ownership record")
    if not isinstance(record["container_ids"], list) or not all(
        isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value)
        for value in record["container_ids"]
    ):
        raise RuntimeError("invalid immutable container record")
    if len(record["container_ids"]) != len(set(record["container_ids"])):
        raise RuntimeError("duplicate immutable container record")
    if record["tag"] is not None and (
        (
            record["build_state"] == "not-started"
            and (record["image_id"] is not None or record["container_ids"])
        )
        or (record["container_ids"] and record["image_id"] is None)
        or (
            record["build_state"] == "succeeded"
            and record["complete"]
            and record["image_id"] is None
        )
    ):
        raise RuntimeError("inconsistent build/image accounting record")
    identity = record.get("engine")
    if (
        not isinstance(identity, dict)
        or set(identity) != {"hostname", "graph_root", "socket", "endpoint"}
        or not all(isinstance(value, str) and value for value in identity.values())
    ):
        raise RuntimeError("invalid selected engine identity record")
    if type(record.get("complete")) is not bool or (
        record["complete"]
        and (
            record["build_state"] in {"running", "interrupted"}
            or any(
                record[f"{op}_state"] in {"pending", "unknown"}
                for op in ("up", "exec", "create")
            )
            or (record["tag"] is None and record["create_state"] != "completed")
        )
    ):
        raise RuntimeError("invalid cleanup state")
    image_id = record.get("image_id")
    if image_id is not None and (
        not isinstance(image_id, str)
        or not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", image_id)
    ):
        raise RuntimeError("invalid immutable image record")


def _validate_run_journal(journal: object) -> None:
    if not isinstance(journal, dict) or set(journal) != {"version", "runs"}:
        raise RuntimeError("invalid devcontainer journal envelope")
    if (
        type(journal["version"]) is not int
        or journal["version"] != 4
        or not isinstance(journal["runs"], list)
    ):
        raise RuntimeError("invalid devcontainer journal version/runs")
    run_ids = set()
    container_ids = set()
    for entry in journal["runs"]:
        _validate_run_record(entry)
        if entry["run_id"] in run_ids:
            raise RuntimeError("duplicate run identity in devcontainer journal")
        run_ids.add(entry["run_id"])
        if container_ids.intersection(entry["container_ids"]):
            raise RuntimeError("duplicate container identity in devcontainer journal")
        container_ids.update(entry["container_ids"])


def _journal_record(record: dict, path: Path | None = None) -> None:
    _validate_run_record(record)
    if path is None:
        filename = os.environ.get("DOTFILES_DEVCONTAINER_MANIFEST")
        if filename:
            path = Path(filename)
        else:
            path = ROOT / ".pi/tasks" / f"devcontainer-{record['run_id']}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        print(f"Devcontainer recovery journal: {path}", file=sys.stderr)
    journal: dict = (
        json.loads(path.read_text(encoding="utf-8"))
        if path.exists()
        else {"version": 4, "runs": []}
    )
    _validate_run_journal(journal)
    journal["runs"] = [
        entry for entry in journal["runs"] if entry["run_id"] != record["run_id"]
    ] + [record]
    _validate_run_journal(journal)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(journal, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _assert_selected_engine(engine: dict) -> None:
    if _selected_engine_identity() != engine:
        raise RuntimeError("selected engine changed; retaining run resources")


def _owned_image_id(tag: str, run_id: str) -> str:
    image = json.loads(_checked(["podman", "image", "inspect", tag]).stdout)
    if not isinstance(image, list) or len(image) != 1 or not isinstance(image[0], dict):
        raise RuntimeError("ambiguous run image metadata; retaining image")
    image = image[0]
    image_id = image.get("Id")
    try:
        metadata = json.loads(image["Config"]["Labels"]["devcontainer.metadata"])
        if not isinstance(metadata, list) or not all(
            isinstance(item, dict) for item in metadata
        ):
            raise ValueError("invalid metadata")
        nonces = [
            item["containerEnv"][RUN_NONCE_ENV]
            for item in metadata
            if isinstance(item.get("containerEnv"), dict)
            and RUN_NONCE_ENV in item["containerEnv"]
        ]
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "run image metadata/nonce unavailable; retaining image"
        ) from error
    if (
        not isinstance(image_id, str)
        or not re.fullmatch(r"(?:sha256:)?[0-9a-f]{64}", image_id)
        or not nonces
        or any(nonce != run_id for nonce in nonces)
        or not isinstance(image.get("RepoTags"), list)
        or tag not in image["RepoTags"]
    ):
        raise RuntimeError("run image identity/nonce unverified; retaining image")
    return image_id


def _cleanup_run_record(record: dict, path: Path | None = None) -> None:
    _validate_run_record(record)
    _assert_selected_engine(record["engine"])
    if record["tag"] and record["image_id"] is None:
        exists = _run(["podman", "image", "exists", record["tag"]])
        if exists.returncode == 0:
            if record["build_state"] == "not-started":
                raise RuntimeError(
                    "unexpected tag for never-started build; retaining image"
                )
            record["image_id"] = _owned_image_id(record["tag"], record["run_id"])
            _journal_record(record, path)  # persist recovered ownership BEFORE cleanup
        elif exists.returncode != 1:
            raise RuntimeError(
                "run tag lookup failed; retaining incomplete recovery state"
            )
        elif record["build_state"] == "succeeded":
            raise RuntimeError(
                "successful build image unaccounted for; retaining incomplete recovery state"
            )
    if record["build_state"] in {"running", "interrupted"}:
        raise RuntimeError(
            "build completion unknown/interrupted; retaining resources and incomplete journal; "
            "review checkpoint required to establish terminal build accounting; "
            "--cleanup-manifest remains retryable but cannot automatically adopt unknown completion"
        )
    if any(
        record[f"{op}_state"] in {"pending", "unknown"}
        for op in ("up", "exec", "create")
    ) or (record["tag"] is None and record["create_state"] != "completed"):
        raise RuntimeError(
            "resource-operation completion unknown; retaining resources and incomplete journal; "
            "review checkpoint required for terminal accounting"
        )
    _cleanup_run_containers(
        record["run_id"], record["container_ids"], record["image_id"], record["engine"]
    )
    if record["image_id"]:
        _untag_run_image(record["tag"], record["image_id"], record["engine"])
    record["complete"] = True
    try:
        _journal_record(record, path)
    except BaseException:
        record["complete"] = False
        raise


def cleanup_devcontainer_manifest(path: Path) -> None:
    journal = json.loads(path.read_text(encoding="utf-8"))
    # Validate the ENTIRE journal before performing any cleanup.
    _validate_run_journal(journal)
    for record in journal["runs"]:
        if not record["complete"]:
            _cleanup_run_record(record, path)


def _cleanup_run_containers(
    run_id: str,
    recorded_ids: tuple | list = (),
    image_id: str | None = None,
    engine: dict | None = None,
) -> None:
    # Discovery cannot prove recorded IDs absent: labels may have changed.
    discovered = _checked(
        ["podman", "ps", "-aq", "--no-trunc", "--filter", f"label={RUN_LABEL}={run_id}"]
    ).stdout.split()
    owned = []
    for container_id in dict.fromkeys([*recorded_ids, *discovered]):
        if not re.fullmatch(r"[0-9a-f]{64}", container_id):
            raise RuntimeError("invalid discovered immutable container identity")
        exists = _run(["podman", "container", "exists", container_id])
        if exists.returncode == 1:
            continue  # actual NotFound, not merely absent from label discovery
        if exists.returncode != 0:
            raise RuntimeError("container existence query failed; retaining resources")
        inspected = _run(["podman", "container", "inspect", container_id])
        if inspected.returncode:
            if _run(["podman", "container", "exists", container_id]).returncode == 1:
                continue
            raise RuntimeError("container inspect failed; retaining resources")
        infos = json.loads(inspected.stdout)
        if (
            not isinstance(infos, list)
            or len(infos) != 1
            or not isinstance(infos[0], dict)
        ):
            raise RuntimeError("invalid container inspect; retaining resources")
        info = infos[0]
        if (
            info.get("Id") != container_id
            or info.get("Config", {}).get("Labels", {}).get(RUN_LABEL) != run_id
            or (
                image_id is not None
                and info.get("Image", "").removeprefix("sha256:")
                != image_id.removeprefix("sha256:")
            )
        ):
            raise RuntimeError(f"refusing cleanup of unowned container {container_id}")
        owned.append(container_id)
    for container_id in owned:
        if engine is not None:
            _assert_selected_engine(engine)
        removed = _run(["podman", "rm", "-f", container_id])
        if (
            removed.returncode
            and _run(["podman", "container", "exists", container_id]).returncode != 1
        ):
            raise RuntimeError(
                "exact-ID removal unacknowledged; retaining incomplete journal"
            )


def _inspect_owned_container(container_id: object, record: dict) -> str:
    if not isinstance(container_id, str) or not re.fullmatch(
        r"[0-9a-f]{64}", container_id
    ):
        raise RuntimeError("missing/invalid immutable container receipt")
    infos = json.loads(
        _checked(["podman", "container", "inspect", container_id]).stdout
    )
    if not isinstance(infos, list) or len(infos) != 1 or not isinstance(infos[0], dict):
        raise RuntimeError("invalid container ownership receipt")
    info = infos[0]
    if (
        info.get("Id") != container_id
        or info.get("Config", {}).get("Labels", {}).get(RUN_LABEL) != record["run_id"]
        or (
            record["image_id"] is not None
            and info.get("Image", "").removeprefix("sha256:")
            != record["image_id"].removeprefix("sha256:")
        )
    ):
        raise RuntimeError("unowned container receipt")
    return container_id


def _create_start_owned(
    record: dict, command: list[str]
) -> subprocess.CompletedProcess:
    if record["create_state"] != "not-started" or command[:2] != ["podman", "create"]:
        raise RuntimeError("one checked create is required per owned run")
    record["create_state"] = "pending"
    _journal_record(record)
    try:
        container_id = _checked(command).stdout.strip()
        _inspect_owned_container(container_id, record)
        record["container_ids"].append(container_id)
        _journal_record(record)  # persist checked ownership BEFORE completing creation
        record["create_state"] = "completed"
        _journal_record(record)
    except BaseException:
        record["create_state"] = "unknown"
        _journal_record(record)
        raise
    # A failed attached start may be an intentional application status. Creation
    # is already known; cleanup must acknowledge exact-ID removal or NotFound.
    return _run(["podman", "start", "--attach", container_id])


@contextmanager
def owned_container_run(run_id: str, *, snapshot_path: str | None = None):
    record = {
        "run_id": run_id,
        "tag": None,
        "tag_was_absent": False,
        "image_id": None,
        "container_ids": [],
        "engine": _selected_engine_identity(),
        "complete": False,
        "build_state": "not-started",
        "snapshot_path": snapshot_path,
        "up_state": "not-started",
        "exec_state": "not-started",
        "create_state": "not-started",
    }
    _journal_record(record)

    def create_start(command: list[str]) -> subprocess.CompletedProcess:
        return _create_start_owned(record, command)

    try:
        yield create_start
    finally:
        _cleanup_run_record(record)


def run_saved_image(
    image: str, script: str, *, offline: bool = False
) -> subprocess.CompletedProcess:
    """Saved-image checks only; uniquely label even one-shot containers."""
    run_id = uuid.uuid4().hex
    command = ["podman", "create", "--rm", "--label", f"{RUN_LABEL}={run_id}"]
    if offline:
        command += ["--network", "none"]
    with owned_container_run(run_id) as create_start:
        return create_start([*command, image, "bash", "-lc", script])


def _untag_run_image(tag: str, image_id: str, engine: dict | None = None) -> None:
    # An ID can predate the run or acquire another alias/reference. Only untag
    # our fresh random tag; retain ALL image/cache IDs (never rmi/prune).
    if engine is not None:
        _assert_selected_engine(engine)
    exists = _run(["podman", "image", "exists", tag])
    if exists.returncode == 1:
        return  # already untagged before an interrupted journal update
    if exists.returncode != 0:
        raise RuntimeError("run tag lookup failed; retaining image")
    info = json.loads(_checked(["podman", "image", "inspect", tag]).stdout)[0]
    if info["Id"] != image_id:
        raise RuntimeError(f"run image tag changed: {tag}")
    if engine is not None:
        _assert_selected_engine(engine)
    _checked(["podman", "untag", image_id, tag])


def _assert_snapshot_has_no_git_ancestry(snapshot: Path) -> None:
    for ancestor in (snapshot.resolve(), *snapshot.resolve().parents):
        marker = ancestor / ".git"
        if marker.exists() or marker.is_symlink():
            raise RuntimeError(
                f"refusing snapshot inside an enclosing Git worktree: {ancestor}"
            )


def _engine_snapshot_path(snapshot: Path) -> str:
    if _mount_mode(os.environ) == "bind":
        # A path in the engine's (Linux) namespace, whatever OS builds it.
        relative = snapshot.relative_to(ROOT).as_posix()
        return str(PurePosixPath(_host_workspace_path()) / relative)
    return str(snapshot)


@contextmanager
def devcontainer_session():
    """Required fresh build -> actual up -> exec, on a tracked-only snapshot."""
    if not _docker_available():
        pytest.fail(
            "Podman >=5 client AND selected server are required; activate the selected engine separately"
        )
    for executable in ("devcontainer", "podman-compose"):
        if not shutil.which(executable):
            pytest.fail(
                f"required executable missing: {executable}; install canonical mise tools"
            )
    _mount_mode(os.environ)  # refuse nested real-checkout paths before any writes
    if os.environ.get("LOCAL_WORKSPACE_FOLDER"):
        raise RuntimeError(
            "run required devcontainer build/up/exec from the host: nested workspace mapping does not authorize a sibling snapshot outside the real Git ancestry"
        )
    launcher_bash = shutil.which("bash")
    if os.name == "nt":
        # System32/bash.exe is WSL, not Git Bash (windows-host runbook).
        git_sh = shutil.which("sh")
        launcher_bash = str(Path(git_sh).with_name("bash.exe")) if git_sh else None
    if not launcher_bash:
        pytest.fail("launcher requires Bash (Git Bash on native Windows)")
    _checked([launcher_bash, ".devcontainer/require-podman-socket.sh"], cwd=ROOT)
    run_id = uuid.uuid4().hex
    tag = f"localhost/dotfiles-sandbox:{run_id}"
    exists = _run(["podman", "image", "exists", tag])
    if exists.returncode != 1:
        raise RuntimeError(
            f"run tag must be absent (lookup rc={exists.returncode}): {tag}"
        )
    image_id = None
    record = {
        "run_id": run_id,
        "tag": tag,
        "tag_was_absent": True,
        "image_id": None,
        "container_ids": [],
        "engine": _selected_engine_identity(),
        "complete": False,
        "build_state": "not-started",
        "snapshot_path": None,
        "up_state": "not-started",
        "exec_state": "not-started",
        "create_state": "not-started",
    }
    _journal_record(record)  # atomically BEFORE any build/up creates resources
    env = dict(os.environ, PODMAN_COMPOSE_PROVIDER="podman-compose")
    env.pop("DOCKER_HOST", None)
    for variable in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
        env.pop(variable, None)
    snapshot = Path(_snapshot_tracked_worktree(str(ROOT)))
    try:
        record["snapshot_path"] = str(snapshot)
        _journal_record(record)  # retain diagnostic context BEFORE invoking a builder
        _assert_snapshot_has_no_git_ancestry(snapshot)
        config_path = snapshot / ".devcontainer/devcontainer.json"
        raw = config_path.read_text(encoding="utf-8")
        config = json.loads(re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE))
        engine_path = _engine_snapshot_path(snapshot)
        config["workspaceMount"] = (
            f"source={engine_path},target=/root/dotfiles,type=bind"
        )
        config["containerEnv"]["LOCAL_WORKSPACE_FOLDER"] = engine_path
        config["containerEnv"][DISPOSABLE_CHECKOUT_ENV] = "1"
        config["containerEnv"][RUN_NONCE_ENV] = run_id
        config.setdefault("runArgs", []).append(f"--label={RUN_LABEL}={run_id}")
        config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
        common = [
            "--workspace-folder",
            str(snapshot),
            "--config",
            str(config_path),
            "--docker-path",
            "podman",
            "--docker-compose-path",
            "podman-compose",
        ]
        record["build_state"] = "running"
        _journal_record(record)
        try:
            build = _run(
                [
                    "devcontainer",
                    "build",
                    *common,
                    "--buildkit",
                    "never",
                    "--image-name",
                    tag,
                ],
                cwd=snapshot,
                env=env,
            )
            if build.returncode:
                raise RuntimeError(
                    f"devcontainer build failed ({build.returncode})\n{build.stdout}\n{build.stderr}"
                )
        except BaseException:
            # No nonzero/exceptional client receipt proves server termination.
            # Raise the original diagnostic before journal/cleanup can fail too.
            record["build_state"] = "interrupted"
            _journal_record(record)
            raise
        record["build_state"] = "succeeded"
        _journal_record(record)
        image_id = _owned_image_id(tag, run_id)
        record["image_id"] = image_id
        _journal_record(record)
        record["up_state"] = "pending"
        _journal_record(record)
        try:
            receipt = _json_output(
                _checked(
                    [
                        "devcontainer",
                        "up",
                        *common,
                        "--mount-workspace-git-root=false",
                        "--mount-git-worktree-common-dir=false",
                        "--buildkit",
                        "never",
                        "--id-label",
                        f"{RUN_LABEL}={run_id}",
                    ],
                    cwd=snapshot,
                    env=env,
                )
            )
            container_id = _inspect_owned_container(receipt.get("containerId"), record)
            record["container_ids"].append(container_id)
            _journal_record(record)
            record["up_state"] = "completed"
            _journal_record(record)
        except BaseException:
            record["up_state"] = "unknown"
            _journal_record(record)
            raise
        exec_marker = f"DOTFILES_SANDBOX_EXEC_COMPLETE={run_id}"
        script = (
            "set -eu; test ! -e /root/dotfiles/.git; "
            'test "$CONTAINER_HOST" = unix:///run/dotfiles-podman/podman.sock; '
            "podman version --format json | python3 -c 'import json,sys; "
            'v=json.load(sys.stdin); assert all(int(v[k]["Version"].split(".")[0]) >= 5 '
            'for k in ("Client", "Server"))\'; '
            f"test \"$(podman inspect --format '{{{{.Id}}}}' {container_id})\" = {container_id}; "
            f"podman run --rm --network none --label {RUN_LABEL}={run_id} "
            f"--entrypoint /bin/true {image_id}; "
            f"printf '\\n{exec_marker}\\n'"
        )
        record["exec_state"] = "pending"
        _journal_record(record)
        try:
            executed = _checked(
                [
                    "devcontainer",
                    "exec",
                    *common,
                    "--mount-workspace-git-root=false",
                    "--mount-git-worktree-common-dir=false",
                    "--container-id",
                    container_id,
                    "bash",
                    "-lc",
                    script,
                ],
                cwd=snapshot,
                env=env,
            )
            if executed.stdout.splitlines().count(exec_marker) != 1:
                raise RuntimeError("missing/invalid controlled exec completion receipt")
            record["exec_state"] = "completed"
            _journal_record(record)
        except BaseException:
            record["exec_state"] = "unknown"
            _journal_record(record)
            raise
        yield {
            "image_id": image_id,
            "container_id": container_id,
            "run_id": run_id,
            "snapshot": snapshot,
        }
    finally:
        _cleanup_run_record(record)
        # Only this process's snapshot, after cleanup RETURNS with persisted
        # completion; even complete=True in memory is insufficient on write failure.
        if record["complete"]:
            shutil.rmtree(snapshot)


@pytest.fixture(scope="session")
def docker_image():
    """Legacy fixture spelling; always a fresh immutable Podman image, no latest."""
    with devcontainer_session() as runtime:
        yield runtime["image_id"]


def _tracked_file_stat(root: Path, parts: tuple[str, ...]) -> os.stat_result | None:
    """Non-following validation; absent tracked files are intentionally omitted."""
    current = root
    for index, part in enumerate(parts):
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return None
        if stat.S_ISLNK(metadata.st_mode) or current.is_junction():
            raise RuntimeError(f"refusing tracked symlink/junction: {current}")
        expected = stat.S_ISREG if index == len(parts) - 1 else stat.S_ISDIR
        if not expected(metadata.st_mode):
            raise RuntimeError(f"refusing nonregular tracked path: {current}")
    resolved = current.resolve()
    if not resolved.is_relative_to(root.resolve()) or any(
        part.casefold() == ".git" for part in resolved.relative_to(root.resolve()).parts
    ):
        raise RuntimeError(f"refusing tracked path escape: {current}")
    return metadata


@contextmanager
def _open_tracked_file(root: Path, parts: tuple[str, ...], expected: os.stat_result):
    # POSIX anchors each ancestor and refuses links at open time. Windows lacks
    # dir_fd/O_NOFOLLOW: revalidate and compare fstat there. Neither branch claims
    # protection from malicious concurrent replacement (the lane has one writer).
    if open_file_descriptor in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW"):
        directory = open_file_descriptor(
            root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            for part in parts[:-1]:
                child = open_file_descriptor(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory
                )
                os.close(directory)
                directory = child
            descriptor = open_file_descriptor(
                parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory
            )
        finally:
            os.close(directory)
        stream = os.fdopen(descriptor, "rb")
    else:
        if _tracked_file_stat(root, parts) != expected:
            raise RuntimeError("tracked file changed before snapshot read")
        stream = root.joinpath(*parts).open("rb")
    with stream:
        observed = os.fstat(stream.fileno())
        if not stat.S_ISREG(observed.st_mode) or (
            observed.st_dev,
            observed.st_ino,
            observed.st_size,
            observed.st_mtime_ns,
        ) != (expected.st_dev, expected.st_ino, expected.st_size, expected.st_mtime_ns):
            raise RuntimeError("tracked file changed before snapshot read")
        yield stream


def _copy_tracked_into(src: str, snapshot: str) -> None:
    """Validate ALL tracked names before copying working-tree (not index) bytes."""
    root = Path(src).absolute()
    for ancestor in (root, *root.parents):
        if (
            ancestor.is_symlink()
            or ancestor.is_junction()
            or not stat.S_ISDIR(ancestor.lstat().st_mode)
        ):
            raise RuntimeError(
                f"refusing symlink/non-directory snapshot root ancestor: {ancestor}"
            )
    tracked = subprocess.run(
        ["git", "-C", src, "ls-files", "--stage", "-z"],
        check=True,
        stdout=subprocess.PIPE,
        env={
            key: value
            for key, value in os.environ.items()
            if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"}
        },
    ).stdout.decode("utf-8")
    files = {}
    for entry in tracked.split("\0"):
        if not entry:
            continue
        header, rel = entry.split("\t", 1)
        mode = header.split()[0]
        parts = tuple(rel.split("/"))
        if any(
            part in {"", ".", ".."}
            or part.casefold() == ".git"
            or "\\" in part
            or ":" in part
            or part.endswith((".", " "))
            for part in parts
        ):
            raise RuntimeError(f"refusing reserved/traversing tracked name: {rel!r}")
        # Gitlinks are never copied, but a substituted link is still refused.
        if mode == "160000":
            for length in range(1, len(parts) + 1):
                path = root.joinpath(*parts[:length])
                if path.is_symlink() or path.is_junction():
                    raise RuntimeError(f"refusing tracked symlink/junction: {path}")
            continue
        metadata = _tracked_file_stat(root, parts)
        if metadata is not None:
            files[parts] = metadata
    for parts, metadata in files.items():
        dest = Path(snapshot).joinpath(*parts)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with (
            _open_tracked_file(root, parts, metadata) as source,
            dest.open("wb") as target,
        ):
            shutil.copyfileobj(source, target)
        dest.chmod(stat.S_IMODE(metadata.st_mode))


def _snapshot_tracked_worktree(src: str) -> str:
    snapshot = Path(tempfile.mkdtemp(prefix=".dotfiles-sandbox-", dir=ROOT.parent))
    try:
        _assert_snapshot_has_no_git_ancestry(snapshot)
        _copy_tracked_into(src, str(snapshot))
        return str(snapshot)
    except BaseException:
        shutil.rmtree(snapshot)
        raise


def run_in_sandbox(image: str, script: str) -> subprocess.CompletedProcess:
    # The dev container image does NOT bake /root/dotfiles into its layers —
    # that path is the workspace mount. A fresh `podman run` starts empty, so we
    # recreate it. Under outside Podman the mount source must be
    # a host path and the checkout is ephemeral, so we bind-mount it directly.
    # Locally we snapshot only git-tracked files into a host tempdir and mount
    # THAT, so the real repo (and its .git) never enters the throwaway container
    # and tests can never pollute the host. `_mount_mode` holds that fence.
    full_script = textwrap.dedent(
        f"""
        set -e
        cd /root/dotfiles
        {script}
        """
    ).strip()
    src = _host_workspace_path()
    snapshot_dir = None
    if _mount_mode(os.environ) == "bind":
        mount_source = src
    else:
        snapshot_dir = _snapshot_tracked_worktree(src)
        mount_source = snapshot_dir
    run_id = uuid.uuid4().hex
    docker_args = [
        "podman",
        "create",
        # Reap orphaned descendants, as the host's init does. A just/go PID 1
        # leaves zombies that make the process-tree tests report live children.
        "--init",
        "--rm",
        "--label",
        f"{RUN_LABEL}={run_id}",
        "-v",
        f"{mount_source}:/root/dotfiles",
        "--security-opt",
        "label=disable",
        "--mount",
        f"type=bind,source={os.environ['DOTFILES_PODMAN_ENGINE_SOCKET']},destination=/run/dotfiles-podman/podman.sock",
        "-e",
        "CONTAINER_HOST=unix:///run/dotfiles-podman/podman.sock",
        "-e",
        "PODMAN_COMPOSE_PROVIDER=podman-compose",
        "-e",
        f"LOCAL_WORKSPACE_FOLDER={mount_source}",
        "-e",
        f"{DISPOSABLE_CHECKOUT_ENV}=1",
        "-w",
        "/root/dotfiles",
        # devcontainer CLI bakes the dev container's
        # containerEnv (including MISE_OFFLINE=1) into the saved
        # image as ENV layer. Inner test containers want a fresh
        # mise cache resolution, so override.
        "-e",
        "MISE_OFFLINE=0",
    ]
    # Forward GITHUB_TOKEN so mise's `latest` resolution against
    # api.github.com hits the authenticated 5000/hr quota. CI
    # surfaces it via the workflow's `env:` block; locally it is
    # only set if the operator already has GH_TOKEN/GITHUB_TOKEN
    # exported.
    gh_token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if gh_token:
        docker_args.extend(["-e", f"GITHUB_TOKEN={gh_token}"])
    docker_args.extend([image, "bash", "-lc", full_script])
    with owned_container_run(run_id, snapshot_path=snapshot_dir) as create_start:
        result = create_start(docker_args)
    # Reaching here acknowledges persisted cleanup; never trust a journal path.
    if snapshot_dir is not None:
        shutil.rmtree(snapshot_dir)
    return result


def _sh_single_quote(s: str) -> str:
    """Quote a string for single-quoted shell embedding.

    Replaces ' with the safe sequence '"'"'.
    """
    return "'" + s.replace("'", "'\"'\"'") + "'"


# Build git stub scripts using textwrap for clarity
GIT_STUB_SIMPLE = textwrap.dedent(
    """
    #!/bin/sh
    if [ "$1" = "clone" ]; then
      repo="$2"; dest="$3";
      case "$repo" in
        *tarjoilija/zgen*)
          mkdir -p "$dest"; exit 0 ;;
        *hironow/dotfiles*)
          mkdir -p "$(dirname "$dest")"; cp -a /root/dotfiles "$dest"; exit 0 ;;
      esac
    fi
    if [ "$1" = "ignore" ]; then
      exit 0
    fi
    exec /usr/bin/git "$@"
    """
).strip()

GIT_STUB_RERUN = textwrap.dedent(
    """
    #!/bin/sh
    if [ "$1" = "clone" ]; then
      repo="$2"; dest="$3";
      case "$repo" in
        *tarjoilija/zgen*)
          mkdir -p "$dest"; exit 0 ;;
        *hironow/dotfiles*)
          mkdir -p "$(dirname "$dest")"; cp -a /root/dotfiles "$dest"; exit 0 ;;
      esac
    fi
    if [ "$1" = "pull" ] || [ "$1" = "ignore" ]; then
      exit 0
    fi
    exec /usr/bin/git "$@"
    """
).strip()

SCRIPT_INSTALL_SUCCESS = textwrap.dedent(
    f"""
    STUBS=/tmp/stubs; mkdir -p "$STUBS";
    # sudo passthrough
    printf '#!/bin/sh\nexec "$@"\n' > "$STUBS/sudo" && chmod +x "$STUBS/sudo";
    # generic success stubs (keep heavy tools stubbed)
    for c in brew gcloud pnpm mise gh tldr code; do
      printf '#!/bin/sh\nexit 0\n' > "$STUBS/$c" && chmod +x "$STUBS/$c";
    done;
    # git: pass-through except clone of zgen/dotfiles and ignore; use skip flags for heavy steps
    printf %s {_sh_single_quote(GIT_STUB_SIMPLE)} > "$STUBS/git"; chmod +x "$STUBS/git";
    export PATH="$STUBS:$PATH";
    export DOTPATH=/root/sandbox/dotfiles-fresh;
    # gcloud is now installed via the google-cloud-cli devcontainer
    # feature, so install.sh's `command -v gcloud` returns true and
    # the install path no-ops naturally. No INSTALL_SKIP_GCLOUD needed.
    export INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_ADD_UPDATE=1;
    # run install and verify link
    bash ./install.sh && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc'
    """
).strip()

SCRIPT_INSTALL_RERUN = textwrap.dedent(
    f"""
    STUBS=/tmp/stubs; mkdir -p "$STUBS";
    # sudo passthrough
    printf '#!/bin/sh\nexec "$@"\n' > "$STUBS/sudo" && chmod +x "$STUBS/sudo";
    # generic success stubs (keep heavy tools stubbed)
    for c in brew gcloud pnpm mise gh tldr code; do
      printf '#!/bin/sh\nexit 0\n' > "$STUBS/$c" && chmod +x "$STUBS/$c";
    done;
    # git: only 'pull' is no-op in rerun path; use skip flags for heavy steps
    printf %s {_sh_single_quote(GIT_STUB_RERUN)} > "$STUBS/git"; chmod +x "$STUBS/git";
    export PATH="$STUBS:$PATH";
    export DOTPATH=/root/sandbox/dotfiles-fresh;
    # gcloud is now installed via the google-cloud-cli devcontainer
    # feature, so install.sh's `command -v gcloud` returns true and
    # the install path no-ops naturally. No INSTALL_SKIP_GCLOUD needed.
    export INSTALL_SKIP_HOMEBREW=1 INSTALL_SKIP_ADD_UPDATE=1;
    # first run (clone branch)
    bash ./install.sh;
    # Initialise a real git repo at DOTPATH to exercise stash/checkout.
    # The DOTPATH dir was `cp -a`'d from /root/dotfiles which already
    # contains a populated .git/ (the bind-mounted host repo). Wipe it
    # first so `git init` produces a fresh empty repo and the
    # subsequent commit has actual content to record.
    cd "$DOTPATH";
    rm -rf .git;
    git init;
    git add -A;
    git -c user.name=test -c user.email=test@example.com commit -m initial --allow-empty;
    git branch -M main;
    cd - >/dev/null;
    # second run (update branch)
    bash ./install.sh;
    # verify link remains correct
    test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc'
    """
).strip()


# A `mise` wrapper that records every invocation and no-ops the
# `install` subcommand. `just deploy` now provisions the host-global
# toolchain via `mise -C / install` (cwd=/ so only the global config
# resolves; see justfile). Without this stub the deploy sandbox tests
# would try to install the entire global config (rust/java/AI CLIs/...)
# inside the throwaway container. The wrapper logs argv to
# /tmp/mise-calls.log so a test can assert the HOME-independent
# `-C / install` wiring, and delegates every non-install call
# (e.g. `mise x -- sheldon lock`) to the real mise at /usr/bin/mise.
_MISE_RECORD_STUB = (
    "mkdir -p /tmp/stubs && "
    "printf '%s\\n' "
    "'#!/bin/sh' "
    "'echo \"$@\" >> /tmp/mise-calls.log' "
    '\'for a in "$@"; do [ "$a" = install ] && exit 0; done\' '
    "'exec /usr/bin/mise \"$@\"' "
    "> /tmp/stubs/mise && chmod +x /tmp/stubs/mise && "
    "export PATH=/tmp/stubs:$PATH && "
)


def _case_id(params):
    # Prefer the explicit human-friendly name (first param)
    if isinstance(params, (list, tuple)) and params:
        return str(params[0])
    values = getattr(params, "values", None)
    if isinstance(values, (list, tuple)) and values:
        return str(values[0])
    return None


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out, expect_err",
    [
        pytest.param(
            "help_lists_targets",
            "just help",
            0,
            "install",
            "",
            id="Help: lists targets",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "validate_path_duplicates",
            "mkdir -p /tmp/x1 /tmp/x2 && printf '#!/bin/sh\necho hi\n' > /tmp/x1/foo && chmod +x /tmp/x1/foo && cp /tmp/x1/foo /tmp/x2/foo && export PATH=/tmp/x1:/tmp/x2:$PATH && just validate-path-duplicates",
            2,
            "command: foo",
            "",
            id="Validate: duplicates found",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "validate_no_duplicates",
            "mkdir -p /tmp/only && printf '#!/bin/sh\necho ok\n' > /tmp/only/foo && chmod +x /tmp/only/foo && VALIDATE_PATH=/tmp/only just validate-path-duplicates",
            0,
            "No duplicate command names across PATH",
            "",
            id="Validate: no duplicates",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "validate_path_structural_roots",
            'H=$(mktemp -d) && mkdir -p "$H/.grok/bin" "$H/.local/bin" && '
            ': > "$H/.grok/bin/foo" && chmod +x "$H/.grok/bin/foo" && '
            'cp "$H/.grok/bin/foo" "$H/.local/bin/foo" && '
            'HOME="$H" VALIDATE_PATH="$H/.grok/bin:$H/.local/bin" '
            "just validate-path-duplicates",
            0,
            "structural duplicate(s) ignored",
            "",
            id="Validate: managed roots (.grok/.local/bin) ignored",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "validate_path_spaces",
            "mkdir -p /tmp/sa /tmp/sb && : > /tmp/sa/prog && "
            "chmod +x /tmp/sa/prog && "
            ': > "/tmp/sb/prog (variant)" && chmod +x "/tmp/sb/prog (variant)" && '
            "VALIDATE_PATH=/tmp/sa:/tmp/sb just validate-path-duplicates",
            0,
            "No duplicate command names across PATH",
            "",
            id="Validate: space-in-name not a false duplicate",
            marks=pytest.mark.validate,
        ),
        pytest.param(
            "deploy_and_clean_link",
            # `_MISE_RECORD_STUB` no-ops `just deploy`'s `mise -C / install`
            # so this case stays a fast symlink check (see stub comment).
            _MISE_RECORD_STUB
            + "rm -f ~/.zshrc && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
            0,
            "",
            "",
            id="Deploy: basic",
            marks=pytest.mark.deploy,
        ),
        pytest.param(
            "deploy_idempotent",
            _MISE_RECORD_STUB
            + "rm -f ~/.zshrc && just deploy && just deploy && test -L ~/.zshrc && readlink ~/.zshrc | grep '/root/dotfiles/.zshrc' && just clean && test ! -e ~/.zshrc",
            0,
            "",
            "",
            id="Deploy: idempotent",
            marks=pytest.mark.deploy,
        ),
        pytest.param(
            "install_sh_success",
            SCRIPT_INSTALL_SUCCESS,
            0,
            "",
            "",
            id="Install: first run",
            marks=pytest.mark.install,
        ),
        pytest.param(
            "install_sh_rerun",
            SCRIPT_INSTALL_RERUN,
            0,
            "",
            "",
            id="Install: rerun update path",
            marks=pytest.mark.install,
        ),
        pytest.param(
            "check_path_runs",
            "just check-path",
            0,
            "\n",
            "",
            id="Check: path prints",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "nvcc_version_ok",
            "just check-version-nvcc 12.3",
            0,
            "",
            "",
            id="Versions: NVCC ok",
            marks=pytest.mark.versions,
        ),
        pytest.param(
            "nvcc_version_mismatch",
            "just check-version-nvcc 11.4",
            1,
            "",
            "Expected NVCC version 11.4",
            id="Versions: NVCC mismatch",
            marks=pytest.mark.versions,
        ),
        pytest.param(
            "torch_not_installed",
            "just check-version-torch 2.5.1",
            1,
            "",
            "PyTorch is not installed",
            id="Versions: Torch missing",
            marks=pytest.mark.versions,
        ),
    ],
)
def test_just_commands_sandbox(
    docker_image, name, script, expect_rc, expect_out, expect_err
):
    # given: sandbox image with repository and stubs
    # when: run the just command inside container
    result = run_in_sandbox(docker_image, script)

    # then: verify exit code and expected output markers
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    if expect_out:
        assert expect_out in result.stdout, (
            f"{name}: expected stdout to contain: {expect_out!r}\nstdout:\n{result.stdout}"
        )


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out, expect_err",
    [
        pytest.param(
            "doctor_path_duplicates_warn",
            "mkdir -p /tmp/x1 /tmp/x2 && printf '#!/bin/sh\necho hi\n' > /tmp/x1/foo && chmod +x /tmp/x1/foo && cp /tmp/x1/foo /tmp/x2/foo && export VALIDATE_PATH=/tmp/x1:/tmp/x2 && just doctor",
            0,
            "duplicate command names found",
            "",
            id="Doctor: PATH duplicates warn",
            marks=pytest.mark.validate,
        ),
    ],
)
def test_additional_scenarios_sandbox(
    docker_image, name, script, expect_rc, expect_out, expect_err
):
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    if expect_out:
        assert expect_out in result.stdout


@pytest.mark.check
def test_doctor_reports_just(docker_image):
    # when
    result = run_in_sandbox(docker_image, "just doctor")
    # then
    assert result.returncode == 0, (
        f"doctor failed: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "OK   just" in result.stdout


@pytest.mark.parametrize(
    "name, script, expect_rc, expect_out",
    [
        pytest.param(
            "Check: my IP ok",
            "just check-myip",
            0,
            "",
            id="Check: my IP ok",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: selected Podman ports",
            "just check-podmanport",
            0,
            "",
            id="Check: selected Podman ports",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: brew guarded",
            "if command -v brew >/dev/null 2>&1; then just check-brew; else echo skip-brew; fi",
            0,
            "skip-brew",
            id="Check: brew guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            # gcloud is installed at devcontainer build time via the
            # local `dotfiles-tools` feature, so the guard's true
            # branch fires and the recipe runs end-to-end. Just
            # assert it succeeds (no specific stdout).
            "Check: gcloud guarded",
            "if command -v gcloud >/dev/null 2>&1; then just check-gcloud; else echo skip-gcloud; fi",
            0,
            "",
            id="Check: gcloud guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: bun globals available",
            # bun is shipped in the sandbox image (mise installs it from the
            # shared config), so the recipe always runs for real.
            # With no global package.json (a fresh machine) the recipe prints
            # 'no bun globals' and exits 0; `bun pm ls -g` alone would exit 1.
            "just check-bun-g",
            0,
            "",
            id="Check: bun globals available",
            marks=pytest.mark.check,
        ),
        pytest.param(
            # check-pnpm-dlx is a record-only listing (grep over dump/npm-dlx).
            # bunx itself is not required; the recipe always exits 0 and
            # prints the header line.
            "Check: pnpm dlx record listed",
            "just check-pnpm-dlx",
            0,
            "bunx packages",
            id="Check: pnpm dlx record listed",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: rust cfg guarded",
            "if command -v rustc >/dev/null 2>&1; then just check-rust; else echo skip-rust; fi",
            0,
            "skip-rust",
            id="Check: rust cfg guarded",
            marks=pytest.mark.check,
        ),
        pytest.param(
            "Check: watchman guarded",
            "if command -v watchman >/dev/null 2>&1; then just check-watchman; else echo skip-watchman; fi",
            0,
            "skip-watchman",
            id="Check: watchman guarded",
            marks=pytest.mark.check,
        ),
    ],
)
def test_check_commands_sandbox(docker_image, name, script, expect_rc, expect_out):
    # given / when
    result = run_in_sandbox(docker_image, script)
    # then
    assert result.returncode == expect_rc, (
        f"{name}: rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    if expect_out:
        assert expect_out in result.stdout


@pytest.mark.check
def test_doctor_sandbox(docker_image):
    result = run_in_sandbox(docker_image, "just doctor")
    assert result.returncode == 0, (
        f"doctor failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Doctor summary:" in result.stdout


# The add-* recipes all share the same early guard:
#   if the dump file is missing or empty, exit 1 with "missing or empty".
# These tests cover that guard without needing gcloud/brew/pnpm in the
# sandbox: the guard fires before any tool is invoked.
@pytest.mark.parametrize(
    "recipe, filename",
    [
        pytest.param("add-brew", "Brewfile", id="add-brew guards empty Brewfile"),
        pytest.param("add-gcloud", "gcloud", id="add-gcloud guards empty dump"),
    ],
)
@pytest.mark.check
def test_add_recipes_guard_empty_dump(docker_image, recipe, filename):
    # given: a synthetic host dir 'testhost' holding an empty manifest. We only
    # ADD dump/testhost/ (never truncate the tracked dump/<host>/ manifests) so
    # CI's bind-mounted checkout is never corrupted for later tests (ADR 0030),
    # and we remove it again afterwards for the same reason — CI mounts one
    # checkout for the whole job, so what a test adds, a test must take away.
    # when: the recipe restores from that host (DOTFILES_HOST=testhost)
    # then: it exits 1 with a clear "missing or empty" message
    script = (
        f"mkdir -p dump/testhost && : > dump/testhost/{filename} ; "
        f"rc=0 && DOTFILES_HOST=testhost just {recipe} || rc=$? ; "
        # rmdir, not a recursive delete: it must fail loudly rather than erase
        # anything the recipe was not supposed to leave in there.
        f"rm -f dump/testhost/{filename} ; rmdir dump/testhost ; "
        "exit $rc"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == 1, (
        f"{recipe}: expected rc=1 for empty dump/testhost/{filename}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "missing or empty" in result.stdout, (
        f"{recipe}: expected 'missing or empty' in stdout\nstdout:\n{result.stdout}"
    )


# Per-host dump host-alias resolution (ADR 0030). These exercise the recipe
# wiring and scripts/dump_host.sh. All `.host`-writing / layout-mutating cases
# run against an isolated DOTFILES_DUMP_DIR tempdir so they never touch the real
# tracked dump/ or the real dump/.host — keeping CI's bind-mounted checkout
# clean and the tests order-independent.
@pytest.mark.check
def test_dump_fails_without_host_alias(docker_image):
    """`just dump` must fail loud when no host alias is resolvable (no
    DOTFILES_HOST, no dump/.host) BEFORE touching brew/gcloud: you declare
    which host you are before recording it (ADR 0030)."""
    # Point the resolver at an empty tempdir: no .host, no host dirs.
    script = 'DOTFILES_HOST= DOTFILES_DUMP_DIR="$(mktemp -d)" just dump'
    result = run_in_sandbox(docker_image, script)
    assert result.returncode != 0, (
        f"dump should fail-loud without a host alias\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "host alias" in (result.stdout + result.stderr)


@pytest.mark.check
def test_set_host_writes_and_validates(docker_image):
    """`just set-host` records a valid alias and rejects an invalid slug
    (ADR 0030). Isolated via DOTFILES_DUMP_DIR so the real dump/.host is
    untouched."""
    ok = run_in_sandbox(
        docker_image,
        'd="$(mktemp -d)"; DOTFILES_DUMP_DIR="$d" just set-host macmini '
        '&& cat "$d/.host"',
    )
    assert ok.returncode == 0, f"set-host valid failed:\n{ok.stdout}\n{ok.stderr}"
    assert "macmini" in ok.stdout

    bad = run_in_sandbox(
        docker_image,
        'DOTFILES_DUMP_DIR="$(mktemp -d)" just set-host "bad host"',
    )
    assert bad.returncode != 0
    assert "invalid" in (bad.stdout + bad.stderr)


@pytest.mark.check
def test_dump_host_helper_resolves_restore(docker_image):
    """scripts/dump_host.sh resolve-restore: a lone host dir auto-resolves,
    multiple require an explicit pick, and an unknown alias is rejected
    (ADR 0030). Fully isolated in a tempdir."""
    script = textwrap.dedent(
        """
        d="$(mktemp -d)"
        mkdir -p "$d/only"
        printf 'single=%s\\n' \
          "$(DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-restore)"
        mkdir -p "$d/second"
        if DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-restore >/dev/null 2>&1; then
          echo "multi=UNEXPECTED_OK"
        else
          echo "multi=rejected"
        fi
        if DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-restore nope >/dev/null 2>&1; then
          echo "missing=UNEXPECTED_OK"
        else
          echo "missing=rejected"
        fi
        """
    ).strip()
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == 0, (
        f"helper probe failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "single=only" in result.stdout
    assert "multi=rejected" in result.stdout
    assert "missing=rejected" in result.stdout


@pytest.mark.check
def test_set_host_rejects_shell_metachars(docker_image):
    """just parameter quoting (ADR 0030): a metacharacter alias must be passed
    as a single quoted arg and rejected by the validator, never executed as a
    shell command. Regression for the {{quote(alias)}} boundary."""
    marker = "/tmp/dump_host_injection_marker"
    script = textwrap.dedent(
        f"""
        d="$(mktemp -d)"
        rm -f {marker}
        if DOTFILES_DUMP_DIR="$d" just set-host 'x"; touch {marker}; #'; then
          echo "outcome=UNEXPECTED_OK"
        else
          echo "outcome=rejected"
        fi
        test -e {marker} && echo "side_effect=INJECTED" || echo "side_effect=none"
        """
    ).strip()
    result = run_in_sandbox(docker_image, script)
    assert "outcome=rejected" in result.stdout, result.stdout
    assert "side_effect=none" in result.stdout, result.stdout
    assert "INJECTED" not in result.stdout


@pytest.mark.check
def test_dump_host_rejects_unsafe_host(docker_image):
    """scripts/dump_host.sh hardening (ADR 0030): a multi-line hand-edited
    dump/.host is rejected (not silently truncated to line 1), and a symlinked
    dump/<host> is refused so brew bundle cannot read outside the tree."""
    script = textwrap.dedent(
        """
        d="$(mktemp -d)"
        printf 'macbook\\nmalicious\\n' > "$d/.host"
        if DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-dump >/dev/null 2>&1; then
          echo "multiline=UNEXPECTED_OK"
        else
          echo "multiline=rejected"
        fi
        rm -f "$d/.host"
        mkdir -p "$d/real"
        ln -s "$d/real" "$d/linked"
        if DOTFILES_HOST= DOTFILES_DUMP_DIR="$d" bash scripts/dump_host.sh resolve-restore linked >/dev/null 2>&1; then
          echo "symlink=UNEXPECTED_OK"
        else
          echo "symlink=rejected"
        fi
        """
    ).strip()
    result = run_in_sandbox(docker_image, script)
    assert "multiline=rejected" in result.stdout, result.stdout
    assert "symlink=rejected" in result.stdout, result.stdout
    assert "UNEXPECTED_OK" not in result.stdout


# =============================================================================
# Format / Lint Recipe Tests
# =============================================================================
#
# `just fmt` / `just lint` chain `uv run --frozen --only-group lint ruff` (Python), `mise x -- shellcheck`
# (lint only), and `mise x -- prettier` (both). The sandbox image ships mise,
# and shellcheck is listed in mise.toml, so shellcheck runs for real here.
#
# Prettier is intentionally NOT in mise.toml (the team relies on host install
# via brew/asdf), so we override `mise x -- prettier ...` with a no-op shim.
# We do this by injecting a wrapper named `mise` earlier on PATH that:
#   - intercepts the literal pattern `x -- prettier ...` and exits 0,
#   - delegates everything else to the real mise (apt-installed at /usr/bin/mise).

# mise's tools (incl. shellcheck) are pre-installed in the sandbox image
# (Dockerfile runs `mise trust && mise install` at build time). We only need
# to override prettier — which is intentionally NOT in mise.toml — with a
# no-op shim so `just fmt`/`just lint` finish cleanly without prettier.
# Shellcheck runs for real via the pre-installed mise tool.
#
# Each one-shot container starts with an empty mise cache for the
# workspace tools, so `mise x -- shellcheck` (and friends) need the
# network to resolve "latest" against the aqua-registry. We do NOT
# set MISE_OFFLINE=1 here — GitHub Actions runners get an
# authenticated 5000/hr token via the dev container's environment,
# and the post-create.sh's `mise install` already populates the
# cache for the dev container itself. In one-shot inner containers,
# accept the ~5s warm-up.
_MISE_PRETTIER_STUB = (
    "mkdir -p /tmp/stubs && "
    "printf '%s\\n' "
    "'#!/bin/sh' "
    '\'if [ "$1" = x ] && [ "$2" = -- ] && [ "$3" = prettier ]; then exit 0; fi\' '
    "'exec /usr/bin/mise \"$@\"' "
    "> /tmp/stubs/mise && chmod +x /tmp/stubs/mise && "
    "export PATH=/tmp/stubs:$PATH && "
)

# Backwards-compat alias used by older tests; same semantics now.
_MISE_STUB = _MISE_PRETTIER_STUB

# The sandbox image excludes .git via .dockerignore, so `git ls-files` would
# fatal. Initialize a repo and stage everything so `git ls-files` returns the
# tracked file list. Empty `git ls-files` output makes grep exit 1 (no match),
# which would then break the pipeline under `set -e`.
#
# Submodule paths are intentionally NOT staged: in a real checkout, `git
# ls-files` omits files inside submodules (each submodule is a pointer in
# the parent repo). Without this, our throwaway `git init` would include
# every submodule's .sh / file and cause shellcheck/prettier/ruff/... to
# scan third-party code the recipes are designed to skip. We derive the
# exclusion list dynamically from .gitmodules so nested submodules
# (e.g. tools/tmux/plugins/tmux-resurrect) are covered too.
# SAFETY: the git writes below (including the `.git/info/exclude` overwrite) are
# only safe on a disposable tree, so `_mount_mode` guarantees one: locally a
# throwaway snapshot of just the tracked files (no host .git — see
# _snapshot_tracked_worktree), in CI the runner checkout it declares disposable,
# and a refusal in every other case. They can never reach a real repo. We
# init a normal repo at /root/dotfiles/.git, which `prek install` /
# `just install-hooks` need (they wire hooks into .git/hooks).
_GIT_INIT = (
    "cd /root/dotfiles && "
    "git init -q && "
    "git config user.email t@e && git config user.name t && "
    "git config --file .gitmodules --get-regexp path 2>/dev/null "
    "| awk '{print $2\"/\"}' > .git/info/exclude && "
    "git add -A 2>/dev/null && "
)


@pytest.mark.check
def test_just_lint_passes_on_clean_tree(docker_image):
    """`just lint` returns 0 on the as-shipped repo (ruff finds no violations)."""
    result = run_in_sandbox(docker_image, _MISE_STUB + _GIT_INIT + "just lint")
    assert result.returncode == 0, (
        f"just lint failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Python (ruff check" in result.stdout
    assert "lint done" in result.stdout


@pytest.mark.check
def test_just_fmt_passes_on_clean_tree(docker_image):
    """`just fmt` returns 0 on the as-shipped repo (ruff format applies cleanly)."""
    result = run_in_sandbox(docker_image, _MISE_STUB + _GIT_INIT + "just fmt")
    assert result.returncode == 0, (
        f"just fmt failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Python (ruff format)" in result.stdout
    assert "fmt done" in result.stdout


@pytest.mark.check
def test_just_check_passes_on_clean_tree(docker_image):
    """`just check` is the strict gate (no writes). Must pass on as-shipped tree."""
    result = run_in_sandbox(docker_image, _MISE_STUB + _GIT_INIT + "just check")
    assert result.returncode == 0, (
        f"just check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "All checks passed" in result.stdout


@pytest.mark.check
def test_just_install_hooks_wires_prek_into_git(docker_image):
    """`just install-hooks` runs `prek install` and writes a git pre-commit hook.

    The hook it writes is removed again: in CI the mounted `.git` is the real
    checkout's, and nothing else in the suite wants a pre-commit hook there.
    Only the one file prek creates is removed, never `.git/hooks` itself.
    """
    script = (
        _GIT_INIT
        + "rc=0 && { just install-hooks && "
        + "[ -f .git/hooks/pre-commit ] && echo 'pre-commit hook present' ; } "
        + "|| rc=$? ; "
        + "rm -f .git/hooks/pre-commit ; "
        + "exit $rc"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode == 0, (
        f"install-hooks failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "pre-commit hook present" in result.stdout


@pytest.mark.check
def test_just_lint_detects_ruff_violation(docker_image):
    """`just lint` exits non-zero when a Python file has a ruff violation
    that ruff cannot auto-fix.

    Uses F821 (undefined name), which is in ruff's default rule set and has
    no auto-fix — so even with `--fix` the lint step fails.

    The plant is removed again before the script exits; see the note above
    `_planted` below for why that is not optional in CI. Left behind, this one
    file made every later `just check` in the job die at ruff instead of
    reaching the leg it was testing.
    """
    script = (
        _MISE_STUB
        + _GIT_INIT
        + "printf 'def f():\\n    return undefined_name\\n' > bad_lint.py ; "
        + "rc=0 && just lint || rc=$? ; "
        + "rm -f bad_lint.py ; "
        + "exit $rc"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode != 0, (
        "just lint should fail on F821 violation\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "F821" in result.stdout or "F821" in result.stderr


# `just check` passing on a clean tree says the gate runs; it does not say the
# gate would notice anything. These two plant a violation and require a
# non-zero exit, so a leg that is dropped from the recipe fails a test instead
# of quietly widening what we ship. They were written against a justfile with
# the matching leg deleted and they failed there first; with the leg present
# they pass.
#
# One leg each from the two kinds of discovery the recipe uses, because the two
# disagree about untracked files and both behaviours are load-bearing:
# markdownlint is fed from `git ls-files`, so it sees tracked files only, while
# check_storage_bounds.py globs the filesystem and sees a sink that was never
# added.
#
# Both clean up the file they plant, which matters only in CI: there
# run_in_sandbox bind-mounts the (disposable) runner checkout itself
# instead of a per-call snapshot, so a planted violation left behind would
# travel to every later test in the job and fail the clean-tree checks. The
# `|| rc=$?` is what makes that reachable -- the harness runs under `set -e`,
# so a bare `just check` on a failing gate would exit before any cleanup.


def _planted(setup: str, cleanup: str) -> str:
    """Run `just check` with a violation planted, then undo it and re-raise.

    Keeps the gate's own exit status as the script's, so the assertions below
    read the gate and not the cleanup.
    """
    return (
        _MISE_STUB
        + _GIT_INIT
        + setup
        + "rc=0 && just check || rc=$? ; "
        + cleanup
        + "exit $rc"
    )


@pytest.mark.check
def test_just_check_detects_markdownlint_violation(docker_image):
    """`just check` exits non-zero when a TRACKED markdown file breaks a rule.

    MD047 (single trailing newline) is in markdownlint's default set and
    `.markdownlint.json` does not switch it off, so a file with no final
    newline violates exactly that one rule and nothing else.

    The `git add` is load-bearing, not tidiness: the recipe pipes
    `git ls-files '*.md'` into markdownlint, so an untracked .md is invisible
    to this leg. `docs/` is used because `.markdownlint-cli2.yaml` ignores the
    `ROOT_AGENTS_*.md` instruction sources and `templates/**` by design -- a
    violation planted there would prove nothing.
    """
    script = _planted(
        setup=(
            "printf 'Planted: this file has no trailing newline.' "
            "> docs/planted_md_violation.md && "
            "git add docs/planted_md_violation.md && "
        ),
        cleanup=(
            "git rm -q --cached docs/planted_md_violation.md ; "
            "rm -f docs/planted_md_violation.md ; "
        ),
    )
    result = run_in_sandbox(docker_image, script)
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "just check should fail on an MD047 violation in a tracked .md\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "MD047" in combined, f"expected MD047 in the output:\n{combined}"
    # The gate reached this leg rather than dying earlier for some other reason.
    # Do NOT assert on "All checks passed" here: that is ruff's and ty's own
    # per-step output, printed well before the recipe's `✅ All checks passed.`
    # banner, so it appears in a run that failed.
    assert "Markdown (markdownlint-cli2)" in result.stdout, (
        f"the gate never reached the markdownlint leg:\n{result.stdout}"
    )


@pytest.mark.check
def test_just_check_detects_unbounded_storage_sink(docker_image):
    """`just check` exits non-zero when a tofu bucket declares no bound.

    The planted bucket is deliberately correct in every other respect --
    uniform bucket-level access, enforced public-access prevention, zero
    soft-delete retention -- so the single thing it fails is the bound rule
    itself. `tests/unit/test_storage_bounds.py` owns whether that rule is
    right; this test owns whether `just check` actually runs it.

    Nothing is staged here, unlike the markdownlint leg above:
    check_storage_bounds.py globs `tofu/**/*.tf` off the filesystem, so an
    untracked sink is still caught. That asymmetry is the point of having both.
    """
    # Single-quoted for the shell below, so the HCL's double quotes need no
    # escaping; only the newlines are printf escapes.
    bucket = (
        'resource "google_storage_bucket" "planted" {\\n'
        '  name                        = "planted-no-bound"\\n'
        '  location                    = "US"\\n'
        "  uniform_bucket_level_access = true\\n"
        '  public_access_prevention    = "enforced"\\n'
        "  soft_delete_policy {\\n"
        "    retention_duration_seconds = 0\\n"
        "  }\\n"
        "}\\n"
    )
    script = _planted(
        setup=(f"mkdir -p tofu/planted && printf '{bucket}' > tofu/planted/bad.tf && "),
        # rmdir, not a recursive delete: if anything else ever lands in that
        # directory the cleanup should fail loudly rather than erase it.
        cleanup="rm -f tofu/planted/bad.tf ; rmdir tofu/planted ; ",
    )
    result = run_in_sandbox(docker_image, script)
    combined = result.stdout + result.stderr
    assert result.returncode != 0, (
        "just check should fail on a google_storage_bucket with no bound\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "check-storage-bounds: FAILED" in combined, (
        f"expected the storage-bounds gate to report a failure:\n{combined}"
    )
    assert "is unbounded" in combined, (
        f"expected the unbounded-sink violation to name the sink:\n{combined}"
    )
    # See the note in the markdownlint test: "All checks passed" is ruff's and
    # ty's own output and says nothing about the recipe's verdict.
    assert "storage bounds" in result.stdout, (
        f"the gate never reached the storage-bounds leg:\n{result.stdout}"
    )


# =============================================================================
# clean-work-env Recipe Tests
# =============================================================================


@pytest.mark.check
def test_just_clean_work_env_rejects_unknown_target(docker_image):
    """`just clean-work-env x` for x not in {a,b,c,d} fails with a clear error."""
    result = run_in_sandbox(docker_image, "just clean-work-env z")
    assert result.returncode != 0
    assert "unknown target" in result.stdout or "unknown target" in result.stderr


@pytest.mark.check
def test_just_clean_work_env_fails_when_dir_missing(docker_image):
    """`just clean-work-env a` fails if ~/.claude-work-a does not exist."""
    result = run_in_sandbox(
        docker_image,
        "rm -rf $HOME/.claude-work-a && just clean-work-env a",
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "does not exist" in combined


@pytest.mark.check
def test_just_clean_work_env_resets_managed_paths_only(docker_image):
    """`just clean-work-env a` empties CLAUDE.md and removes the managed
    directories (skills/commands/agents/plans/session-env/shell-snapshots)
    while preserving plugins/, projects/, and history files.
    """
    setup = (
        "set -eu\n"
        "d=$HOME/.claude-work-a\n"
        "mkdir -p $d/skills/foo $d/commands $d/agents $d/plans $d/session-env "
        "$d/shell-snapshots $d/plugins/keep-me $d/projects/keep-me\n"
        "echo 'KEEP THIS' > $d/CLAUDE.md\n"
        "echo 'foo skill' > $d/skills/foo/SKILL.md\n"
        "echo 'cmd' > $d/commands/c.md\n"
        "echo 'plan' > $d/plans/p.md\n"
        "echo 'plugin file' > $d/plugins/keep-me/p.json\n"
        "echo 'project file' > $d/projects/keep-me/x.json\n"
        "echo 'history' > $d/.claude.json\n"
        "just clean-work-env a\n"
        "# inspect aftermath\n"
        "[ -f $d/CLAUDE.md ] && [ ! -s $d/CLAUDE.md ] && echo 'claude_md emptied'\n"
        "[ ! -e $d/skills ] && echo 'skills removed'\n"
        "[ ! -e $d/commands ] && echo 'commands removed'\n"
        "[ ! -e $d/agents ] && echo 'agents removed'\n"
        "[ ! -e $d/plans ] && echo 'plans removed'\n"
        "[ ! -e $d/session-env ] && echo 'session-env removed'\n"
        "[ ! -e $d/shell-snapshots ] && echo 'shell-snapshots removed'\n"
        "[ -d $d/plugins/keep-me ] && echo 'plugins preserved'\n"
        "[ -d $d/projects/keep-me ] && echo 'projects preserved'\n"
        "[ -f $d/.claude.json ] && echo 'history preserved'\n"
    )
    result = run_in_sandbox(docker_image, setup)
    assert result.returncode == 0, (
        f"rc={result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    expected = [
        "claude_md emptied",
        "skills removed",
        "commands removed",
        "agents removed",
        "plans removed",
        "session-env removed",
        "shell-snapshots removed",
        "plugins preserved",
        "projects preserved",
        "history preserved",
    ]
    for line in expected:
        assert line in result.stdout, f"missing: {line}\nfull stdout:\n{result.stdout}"


# =============================================================================
# Validation Recipe Tests (semgrep rule self-tests)
# =============================================================================
#
# These exercise the rule-files-against-themselves workflow:
#   - meta-semgrep : run rules in .semgrep/rules/meta/ against the repo
#   - semgrep-test : `semgrep --test` every rule in .semgrep/rules/ (meta +
#                    python) against its co-located fixtures
#   - validate     : composite of both
#
# semgrep is installed on demand via uvx, so the first run downloads it
# (~75MB). Subsequent runs in the same container are cached.


@pytest.mark.check
def test_just_semgrep_test_passes(docker_image):
    """`just semgrep-test` validates every rule's own test annotations."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just semgrep-test",
    )
    assert result.returncode == 0, (
        f"semgrep-test failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.check
def test_just_meta_semgrep_clean_repo_passes(docker_image):
    """`just meta-semgrep` returns 0 on the as-shipped repo (no findings)."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just meta-semgrep",
    )
    assert result.returncode == 0, (
        f"meta-semgrep failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.check
def test_just_validate_runs_both_steps(docker_image):
    """`just validate` chains semgrep-test then meta-semgrep."""
    result = run_in_sandbox(
        docker_image,
        _GIT_INIT + "just validate",
    )
    assert result.returncode == 0, (
        f"validate failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# =============================================================================
# Misc Recipe Tests (default / clean-cache / clean-all / self-check / add-all)
# =============================================================================


@pytest.mark.check
def test_just_default_lists_recipes(docker_image):
    """`just` (no args) runs `default` which delegates to help (`just --list`)."""
    result = run_in_sandbox(docker_image, "just")
    assert result.returncode == 0, (
        f"just default failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # The list output should mention at least one known recipe.
    assert "sync-agents" in result.stdout


@pytest.mark.check
def test_just_clean_cache_idempotent_on_missing_dirs(docker_image):
    """`just clean-cache` succeeds even when target cache dirs do not exist."""
    # Fresh container has none of these, so this exercises the "rm -vrf" on
    # missing paths. rc must still be 0.
    result = run_in_sandbox(docker_image, "just clean-cache")
    assert result.returncode == 0, (
        f"clean-cache failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Remove zsh caches" in result.stdout


@pytest.mark.check
def test_just_clean_all_runs_clean_then_clean_cache(docker_image):
    """`just clean-all` is a composite of `clean` + `clean-cache`. Both run."""
    result = run_in_sandbox(docker_image, "just clean-all")
    assert result.returncode == 0, (
        f"clean-all failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Each child recipe prints a distinctive header.
    assert "Remove dotfiles" in result.stdout
    assert "Remove zsh caches" in result.stdout


@pytest.mark.check
def test_just_self_check_succeeds(docker_image):
    """`just self-check` runs doctor + validate-path-duplicates with summary."""
    result = run_in_sandbox(docker_image, "just self-check")
    assert result.returncode == 0, (
        f"self-check failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "Self-check summary:" in result.stdout


@pytest.mark.check
def test_just_add_all_fails_when_dumps_empty(docker_image):
    """`just add-all` is a composite. With empty per-host manifests it must
    fail at the first add-* guard (rc!=0, "missing or empty"), not silently
    succeed. Uses a synthetic dump/testhost/ (ADR 0030), removed again so the
    bind-mounted CI checkout is as clean after the test as before it."""
    script = (
        "mkdir -p dump/testhost && : > dump/testhost/Brewfile "
        "&& : > dump/testhost/gcloud ; "
        "rc=0 && DOTFILES_HOST=testhost just add-all || rc=$? ; "
        "rm -f dump/testhost/Brewfile dump/testhost/gcloud ; "
        "rmdir dump/testhost ; "
        "exit $rc"
    )
    result = run_in_sandbox(docker_image, script)
    assert result.returncode != 0
    assert "missing or empty" in result.stdout


@pytest.mark.check
def test_just_install_runs_mise_install(docker_image):
    """`just install` invokes `mise install` end-to-end and provisions the
    tools listed in mise.toml.

    Inner containers can't reuse MISE_OFFLINE=1 because their cache
    is empty; let mise resolve "latest" online against an
    authenticated GitHub token (CI runs are scoped to 5000/hr).
    """
    result = run_in_sandbox(
        docker_image,
        "mise trust >/dev/null 2>&1; just install",
    )
    assert result.returncode == 0, (
        f"just install failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "mise install" in combined


@pytest.mark.deploy
def test_deploy_provisions_global_mise(docker_image):
    """`just deploy` provisions the host-global mise toolchain.

    The recipe runs `mise -C / install` (cwd=/ so only the global
    config resolves, never a HOME-level project config). We stub
    `mise` to record argv and no-op the install, then assert the
    HOME-independent `-C / install` wiring fired and the symlink
    deploy still happened.
    """
    result = run_in_sandbox(
        docker_image,
        _MISE_RECORD_STUB + "rm -f /tmp/mise-calls.log ~/.zshrc && just deploy && "
        "grep -q -- '-C / install' /tmp/mise-calls.log && "
        "test -L ~/.zshrc",
    )
    assert result.returncode == 0, (
        f"deploy global-mise provisioning wiring failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.deploy
def test_deploy_mise_install_is_global_scoped(docker_image):
    """Guard the `-C /` scope choice: the deploy provisioning command
    must resolve ONLY the global config, never a HOME-level project
    config (`~/mise.toml` / `~/.tool-versions`).

    Plant a sentinel `~/mise.toml`; from cwd=$HOME mise sees it (HOME
    is in scope), but from cwd=/ it must not (HOME is not an ancestor
    of /), while the global config still loads. This locks the
    assumption behind `mise -C / install` so a future "simplification"
    back to `-C "$HOME"` (which would leak HOME-local configs) is
    caught.
    """
    result = run_in_sandbox(
        docker_image,
        'printf \'[tools]\\n"npm:cowsay" = "latest"\\n\' > ~/mise.toml && '
        "mise trust ~/mise.toml >/dev/null 2>&1; "
        # cwd=$HOME sees the planted config (sanity that planting worked):
        'mise -C "$HOME" config 2>&1 | grep -q cowsay && '
        # cwd=/ must NOT see it, yet must still load the global config:
        "! mise -C / config 2>&1 | grep -q cowsay && "
        "mise -C / config 2>&1 | grep -qw uv",
    )
    assert result.returncode == 0, (
        f"global-scope guard failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# ---------------------------------------------------------------------------
# The dev container uses Microsoft's official Debian 13 (trixie) base,
# with native glibc and a Podman client. The old Alpine/musl compatibility
# assertions were retired with the base-image migration. Current lifecycle
# and configuration tests cover the Podman client/server requirements and
# outside-engine transport; native glibc needs no compatibility shim.
# ---------------------------------------------------------------------------


@pytest.mark.check
def test_install_sh_has_executable_bit_in_git_index():
    """Anything that clones this repo and execs install.sh directly —
    rather than running 'bash install.sh' — depends on the execute bit.
    If install.sh in the git index has mode 100644 instead of 100755,
    the exec fails with:

      error: script "install.sh" does not have execute permissions

    and the install silently degrades to nothing. Local fs mode is
    irrelevant — what matters is the *index mode*, because that is
    what `git clone` reproduces for whoever does the exec.

    Check it the way they do, with `git ls-files -s`."""
    import subprocess

    repo_root = Path(__file__).resolve().parents[1]
    out = subprocess.run(
        ["git", "ls-files", "-s", "install.sh"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
        errors="replace",
    )
    # Output format: "<mode> <hash> <stage>\t<path>"
    mode = out.stdout.split()[0]
    assert mode == "100755", (
        f"install.sh git index mode is {mode}, expected 100755.\n"
        "Run: git update-index --chmod=+x install.sh && commit\n"
        "Otherwise a direct exec of the script fails after a clone."
    )


# =============================================================================
# Host-pollution isolation guards (番人)
# =============================================================================
#
# These pin the invariant that produced real host damage earlier (a staged
# `/private/*` secret, a truncated `dump/*`, host `.git/hooks` writes): the
# sandbox must NEVER bind-mount the real repo locally. It must instead mount a
# throwaway copy of ONLY the git-tracked first-party files, and tear it down.
# In CI the runner checkout is itself ephemeral, so the host path is bound
# directly. No Docker is needed to exercise this — we inspect the mount source
# and the snapshot contents, so the guard runs everywhere `just test` runs.


def test_snapshot_excludes_git_untracked_and_submodule_gitlinks(tmp_path):
    """`_snapshot_tracked_worktree` copies only git-tracked first-party files.

    The real `.git`, untracked secrets, and submodule gitlinks must never reach
    the throwaway sandbox checkout.
    """
    # given: a repo with a tracked file, an untracked secret, and a gitlink
    repo = tmp_path / "repo"
    repo.mkdir()

    def _git(*args):
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    _git("init", "-q")
    _git("config", "user.email", "t@e")
    _git("config", "user.name", "t")
    (repo / "tracked.txt").write_text("first-party\n", encoding="utf-8")
    (repo / "private").mkdir()
    (repo / "private" / "secret.key").write_text(
        "SECRET\n", encoding="utf-8"
    )  # untracked
    _git("add", "tracked.txt")
    _git("commit", "-qm", "init")
    # a submodule pointer (gitlink) staged with no checked-out file on disk
    _git(
        "update-index",
        "--add",
        "--cacheinfo",
        "160000,1234567890123456789012345678901234567890,sub",
    )

    # when
    snapshot = _snapshot_tracked_worktree(str(repo))

    # then
    try:
        assert (Path(snapshot) / "tracked.txt").is_file()
        assert not (Path(snapshot) / ".git").exists()
        assert not (Path(snapshot) / "private" / "secret.key").exists()
        assert not (Path(snapshot) / "sub").exists()
    finally:
        shutil.rmtree(snapshot, ignore_errors=True)


def test_run_in_sandbox_local_mounts_snapshot_not_host(monkeypatch, tmp_path):
    """Locally (no LOCAL_WORKSPACE_FOLDER) the sandbox mounts a throwaway
    git-tracked snapshot, never the host repo, and removes it afterwards."""
    # given: not in CI; the snapshot helper returns a dir we can track
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    monkeypatch.setenv(
        "DOTFILES_DEVCONTAINER_MANIFEST", str(tmp_path / "local-test-run.json")
    )
    monkeypatch.delenv("LOCAL_WORKSPACE_FOLDER", raising=False)
    monkeypatch.setenv(
        "DOTFILES_PODMAN_ENGINE_SOCKET", "/run/user/123/podman/podman.sock"
    )
    monkeypatch.setattr(
        sys.modules[__name__],
        "_selected_engine_identity",
        lambda: {
            "hostname": "test",
            "graph_root": "/test",
            "socket": "/run/test",
            "endpoint": "native-local",
        },
    )
    fake_snapshot = tempfile.mkdtemp(prefix="dotfiles-sandbox-test-")
    monkeypatch.setattr(
        sys.modules[__name__],
        "_snapshot_tracked_worktree",
        lambda _src: fake_snapshot,
    )
    captured = {}

    def _fake_run(cmd, **kwargs):
        if cmd[:2] == ["podman", "create"]:
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "b" * 64, "")
        if cmd[:3] == ["podman", "container", "inspect"]:
            run_id = captured["cmd"][captured["cmd"].index("--label") + 1].split(
                "=", 1
            )[1]
            return subprocess.CompletedProcess(
                cmd,
                0,
                json.dumps(
                    [{"Id": "b" * 64, "Config": {"Labels": {RUN_LABEL: run_id}}}]
                ),
                "",
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sys.modules[__name__], "_run", _fake_run)

    # when
    run_in_sandbox("img", "echo hi")

    # then: the bind mount SOURCE (left of ':') is the snapshot, not the host
    # repo. Check the source only — the target is always '/root/dotfiles', which
    # equals ROOT inside the dev container, so scanning the whole arg is wrong.
    cmd = captured["cmd"]
    mount_arg = cmd[cmd.index("-v") + 1]
    mount_source = mount_arg.removesuffix(":/root/dotfiles")
    assert mount_source == fake_snapshot
    assert mount_source != str(ROOT)
    # ...and the snapshot is torn down once the run completes
    assert not Path(fake_snapshot).exists()


def test_run_in_sandbox_ci_binds_host_path(monkeypatch, tmp_path):
    """In CI (LOCAL_WORKSPACE_FOLDER set plus the disposable-checkout
    declaration) the sandbox binds the host path directly and must NOT take the
    local snapshot branch. Without the declaration it refuses instead — see
    tests/unit/test_sandbox_mount_fence.py."""
    # given: CI-style env points at a host workspace path it declares disposable
    monkeypatch.setattr(sys.modules[__name__], "ROOT", tmp_path)
    monkeypatch.setenv(
        "DOTFILES_DEVCONTAINER_MANIFEST", str(tmp_path / "ci-test-run.json")
    )
    monkeypatch.setenv("LOCAL_WORKSPACE_FOLDER", "/work/ci-checkout")
    monkeypatch.setenv(
        "DOTFILES_PODMAN_ENGINE_SOCKET", "/run/user/123/podman/podman.sock"
    )
    monkeypatch.setenv(DISPOSABLE_CHECKOUT_ENV, "1")

    monkeypatch.setattr(
        sys.modules[__name__],
        "_selected_engine_identity",
        lambda: {
            "hostname": "test",
            "graph_root": "/test",
            "socket": "/run/test",
            "endpoint": "native-local",
        },
    )

    def _boom(_src):
        raise AssertionError("must not snapshot in CI mode")

    monkeypatch.setattr(sys.modules[__name__], "_snapshot_tracked_worktree", _boom)
    captured = {}

    def _fake_run(cmd, **kwargs):
        if cmd[:2] == ["podman", "create"]:
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, "b" * 64, "")
        if cmd[:3] == ["podman", "container", "inspect"]:
            run_id = captured["cmd"][captured["cmd"].index("--label") + 1].split(
                "=", 1
            )[1]
            return subprocess.CompletedProcess(
                cmd,
                0,
                json.dumps(
                    [{"Id": "b" * 64, "Config": {"Labels": {RUN_LABEL: run_id}}}]
                ),
                "",
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sys.modules[__name__], "_run", _fake_run)

    # when
    run_in_sandbox("img", "echo hi")

    # then
    cmd = captured["cmd"]
    mount_arg = cmd[cmd.index("-v") + 1]
    assert mount_arg == "/work/ci-checkout:/root/dotfiles"


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--cleanup-manifest":
        raise SystemExit("usage: test_just_sandbox.py --cleanup-manifest PATH")
    os.environ["DOTFILES_DEVCONTAINER_MANIFEST"] = sys.argv[2]
    cleanup_devcontainer_manifest(Path(sys.argv[2]))
