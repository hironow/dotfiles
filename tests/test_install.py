"""Required installer acceptance; never build from the operator's raw checkout."""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_LABEL = "io.dotfiles.test-run"


def _native(
    args: list[str], environment: dict[str, str], *, timeout: int = 30
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["podman", *args],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )


def accept_installer(source: Path, output: Path) -> dict:
    """Build only an owned tracked snapshot, retaining uncertain build evidence."""
    environment = os.environ.copy()
    client = _native(["--version"], environment)
    version = re.fullmatch(
        r"podman version ([0-9]+)\.[0-9]+\.[0-9]+(?:[-+][^\s]+)?", client.stdout.strip()
    )
    if client.returncode or not version or int(version[1]) < 5:
        raise RuntimeError("Podman client >=5 is required; provision it separately")
    info = _native(["info", "--format", "json"], environment)
    try:
        metadata = json.loads(info.stdout)
        engine = metadata["version"]["Version"]
        version = (
            re.fullmatch(r"([0-9]+)\.[0-9]+\.[0-9]+(?:[-+][^\s]+)?", engine)
            if isinstance(engine, str)
            else None
        )
        if info.returncode or not version or int(version[1]) < 5:
            raise ValueError("unsupported engine")
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Podman engine >=5 is required; activate it separately"
        ) from error
    try:
        host = metadata["host"]
        fields = (
            host["hostname"],
            host["remoteSocket"]["path"],
            metadata["store"]["graphRoot"],
        )
        if type(host["serviceIsRemote"]) is not bool or not all(
            isinstance(value, str)
            and value
            and not any(ord(char) < 32 for char in value)
            for value in fields
        ):
            raise ValueError("invalid selected engine identity")
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Podman selected-engine identity unavailable; refusing creation"
        ) from error
    helper_path = ROOT / "tests/test_just_sandbox.py"
    spec = importlib.util.spec_from_file_location(
        f"installer_snapshot_{uuid.uuid4().hex}", helper_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Reviewed Podman snapshot helper is not integrated")
    helper = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = helper
    spec.loader.exec_module(helper)
    if not all(
        callable(getattr(helper, name, None))
        for name in ("_open_tracked_file", "_snapshot_tracked_worktree")
    ):
        raise RuntimeError("Reviewed Podman snapshot helper is not integrated")
    # Capability guard above prevents accidental use of the old unsafe helper;
    # it is not a substitute for independent review of the integrated source.
    endpoint = environment.get("CONTAINER_HOST")
    if not endpoint and host["serviceIsRemote"]:
        connection_query = _native(
            ["system", "connection", "list", "--format", "json"], environment
        )
        if connection_query.returncode:
            raise RuntimeError("Selected installer connection unavailable")
        connections = json.loads(connection_query.stdout)
        name = environment.get("CONTAINER_CONNECTION")
        selected = (
            [item for item in connections if item.get("Name") == name]
            if name
            else [item for item in connections if item.get("Default") is True]
        )
        if (
            len(selected) != 1
            or not isinstance(selected[0].get("URI"), str)
            or not selected[0]["URI"]
        ):
            raise RuntimeError("Selected installer connection missing/ambiguous")
        endpoint = selected[0]["URI"]
    identity = {
        "hostname": host["hostname"],
        "graph_root": metadata["store"]["graphRoot"],
        "socket": host["remoteSocket"]["path"],
        "endpoint": endpoint or "native-local",
    }
    context = Path(helper._snapshot_tracked_worktree(str(source)))
    try:
        record = _build_prepared_snapshot(context, output, environment, identity)
    except BaseException as error:
        raise RuntimeError(
            f"Installer acceptance incomplete; retained owned context {context}"
        ) from error
    if record.get("complete") is not True:
        raise RuntimeError(
            f"Installer cleanup not acknowledged; retained context {context}"
        )
    shutil.rmtree(context)  # only this process-owned context, after persisted cleanup
    return record


def _save_record(record: dict, path: Path) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=path.name + ".",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(record, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _full_image_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:sha256:)?[0-9a-f]{64}", value
    ):
        raise RuntimeError("Invalid immutable installer image ID; retaining resources")
    return value.removeprefix("sha256:")


def _assert_engine(identity: dict, environment: dict[str, str]) -> None:
    result = _native(["info", "--format", "json"], environment)
    try:
        info = json.loads(result.stdout)
        host = info["host"]
        if type(host["serviceIsRemote"]) is not bool:
            raise ValueError("malformed selected engine transport metadata")
        version = re.fullmatch(
            r"([0-9]+)\.[0-9]+\.[0-9]+(?:[-+][^\s]+)?", info["version"]["Version"]
        )
        endpoint = environment.get("CONTAINER_HOST")
        if not endpoint and host["serviceIsRemote"]:
            connections = _native(
                ["system", "connection", "list", "--format", "json"], environment
            )
            if connections.returncode:
                raise ValueError("connection query failed")
            name = environment.get("CONTAINER_CONNECTION")
            selected = (
                [
                    item
                    for item in json.loads(connections.stdout)
                    if item.get("Name") == name
                ]
                if name
                else [
                    item
                    for item in json.loads(connections.stdout)
                    if item.get("Default") is True
                ]
            )
            if len(selected) != 1:
                raise ValueError("ambiguous selected connection")
            endpoint = selected[0]["URI"]
        current = {
            "hostname": host["hostname"],
            "graph_root": info["store"]["graphRoot"],
            "socket": host["remoteSocket"]["path"],
            "endpoint": endpoint or "native-local",
        }
        if (
            result.returncode
            or not version
            or int(version[1]) < 5
            or current != identity
        ):
            raise ValueError("selected engine changed")
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Selected installer engine identity changed/unavailable; retaining resources"
        ) from error


def _owned_image(tag: str, run_id: str, environment: dict[str, str]) -> str:
    result = _native(["image", "inspect", tag], environment)
    try:
        values = json.loads(result.stdout)
        if result.returncode or not isinstance(values, list) or len(values) != 1:
            raise ValueError("image inspect failed")
        image = values[0]
        if (
            not isinstance(image["RepoTags"], list)
            or not all(isinstance(value, str) for value in image["RepoTags"])
            or not isinstance(image["Config"]["Labels"], dict)
            or image["Config"]["Labels"].get(RUN_LABEL) != run_id
            or tag not in image["RepoTags"]
        ):
            raise ValueError("image tag/label is not owned")
        return _full_image_id(image["Id"])
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(
            "Installer image ownership unavailable; retaining resources"
        ) from error


def _build_prepared_snapshot(
    context: Path, output: Path, environment: dict[str, str], identity: dict
) -> dict:
    """Protocol component: caller supplies its owned, validated tracked snapshot."""
    context = context.absolute()
    dockerfile = context / "tests/docker/InstallTest.Dockerfile"
    if (
        not dockerfile.is_file()
        or dockerfile.is_symlink()
        or output.resolve().is_relative_to(context.resolve())
    ):
        raise RuntimeError(
            "Installer requires a validated snapshot and external journal directory"
        )
    run_id = uuid.uuid4().hex
    tag = f"localhost/dotfiles-install-test:{run_id}"
    _assert_engine(identity, environment)
    absent = _native(["image", "exists", tag], environment)
    if absent.returncode != 1:
        raise RuntimeError("Installer tag absence is unproven; refusing creation")
    directory = output / run_id
    directory.mkdir(parents=True, exist_ok=False)
    journal = directory / "journal.json"
    iid = directory / "image.id"
    record = {
        "version": 1,
        "run_id": run_id,
        "tag": tag,
        "tag_was_absent": True,
        "engine": identity,
        "snapshot_path": str(context),
        "image_id": None,
        "build_state": "prepared",
        "complete": False,
    }
    _save_record(record, journal)
    record["build_state"] = "running"
    _save_record(record, journal)
    print(f"Installer acceptance journal: {journal}", flush=True)
    try:
        build = _native(
            [
                "build",
                "--iidfile",
                str(iid),
                "--build-arg",
                f"DOTFILES_INSTALL_ACCEPTANCE_RUN={run_id}",
                "--label",
                f"{RUN_LABEL}={run_id}",
                "-t",
                tag,
                "-f",
                str(dockerfile),
                str(context),
            ],
            environment,
            timeout=1800,
        )
        (directory / "build.stdout").write_text(build.stdout, encoding="utf-8")
        (directory / "build.stderr").write_text(build.stderr, encoding="utf-8")
        if build.returncode:
            raise RuntimeError(
                f"Installer client exited {build.returncode}; remote completion unknown"
            )
        lines = (build.stdout + "\n" + build.stderr).splitlines()
        if not all(
            lines.count(f"DOTFILES_INSTALL_{marker}:{run_id}") == 1
            for marker in ("PASS1", "PASS2", "TRIPWIRE")
        ):
            raise RuntimeError("Fresh installer passes/tripwire execution not proven")
        image_id = _full_image_id(
            iid.read_text(encoding="utf-8").removesuffix("\n").removesuffix("\r")
        )
        if _owned_image(tag, run_id, environment) != image_id:
            raise RuntimeError("Installer iidfile differs from owned tag identity")
        record.update(image_id=image_id, build_state="succeeded")
        _save_record(record, journal)
    except BaseException as error:
        record.update(build_state="unknown", error=str(error))
        _save_record(record, journal)
        raise RuntimeError(
            f"Installer build completion/evidence unresolved; retained context {context}; journal {journal}"
        ) from error
    try:
        _assert_engine(identity, environment)
        exists = _native(["image", "exists", tag], environment)
        if exists.returncode == 0:
            if _owned_image(tag, run_id, environment) != record["image_id"]:
                raise RuntimeError("Installer tag identity changed before cleanup")
            _assert_engine(identity, environment)
            removed = _native(["untag", image_id, tag], environment)
            if removed.returncode:
                raise RuntimeError("Owned installer alias removal refused")
        elif exists.returncode != 1:
            raise RuntimeError("Installer tag lookup failed during cleanup")
        record["complete"] = True
        _save_record(record, journal)
    except BaseException as error:
        record["complete"] = False
        record["error"] = str(error)
        _save_record(record, journal)
        raise RuntimeError(
            f"Installer cleanup incomplete; retained context {context}; journal {journal}"
        ) from error
    return record


def test_installer_acceptance() -> None:
    accept_installer(ROOT, ROOT / ".pi/tasks/install-acceptance")
