"""Installer acceptance at its native-process and filesystem boundaries."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "installer_acceptance", ROOT / "tests/test_install.py"
)
assert SPEC and SPEC.loader
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


@pytest.mark.parametrize(
    "mode",
    [
        "ok",
        "client_error",
        "bad_marker",
        "wrong_id",
        "foreign_label",
        "malformed_tags",
        "malformed_remote",
        "cleanup_lookup_error",
        "untag_failure",
        "engine_change",
        "build_timeout",
        "final_save_error",
    ],
)
def test_prepared_snapshot_requires_fresh_evidence_then_untags_only_owned_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    context = tmp_path / "owned-context"
    (context / "tests/docker").mkdir(parents=True)
    (context / "tests/docker/InstallTest.Dockerfile").write_text(
        "FROM scratch\n", encoding="utf-8"
    )
    identity = {
        "hostname": "controlled",
        "graph_root": "/controlled/storage",
        "socket": "unix:///run/user/501/podman/podman.sock",
        "endpoint": "native-local",
    }
    environment = {}
    if mode == "malformed_remote":
        environment["CONTAINER_HOST"] = "unix:///controlled/client.sock"
        identity["endpoint"] = environment["CONTAINER_HOST"]
    image = "a" * 64
    state = {"built": False, "tag": "", "run": ""}
    calls = []

    def process(command, **kwargs):
        calls.append(command)
        result = subprocess.CompletedProcess(command, 0, "", "")
        args = command[1:]
        if args == ["info", "--format", "json"]:
            result.stdout = json.dumps(
                {
                    "version": {"Version": "5.6.2"},
                    "host": {
                        "hostname": "different-engine"
                        if state["built"] and mode == "engine_change"
                        else identity["hostname"],
                        "serviceIsRemote": "false"
                        if state["built"] and mode == "malformed_remote"
                        else False,
                        "remoteSocket": {"path": identity["socket"]},
                    },
                    "store": {"graphRoot": identity["graph_root"]},
                }
            )
        elif args[:2] == ["image", "exists"]:
            result.returncode = (
                125
                if state["built"] and mode == "cleanup_lookup_error"
                else 0
                if state["built"]
                else 1
            )
        elif args[0] == "build":
            state["tag"] = args[args.index("-t") + 1]
            state["run"] = state["tag"].split(":")[-1]
            assert (
                args[args.index("--build-arg") + 1]
                == f"DOTFILES_INSTALL_ACCEPTANCE_RUN={state['run']}"
            )
            assert (
                args[args.index("--label") + 1]
                == f"{acceptance.RUN_LABEL}={state['run']}"
            )
            assert args[-1] == str(context)
            assert args[args.index("-f") + 1] == str(
                context / "tests/docker/InstallTest.Dockerfile"
            )
            Path(args[args.index("--iidfile") + 1]).write_text(
                "sha256:" + image + "\n", encoding="utf-8"
            )
            result.stdout = (
                "\n".join(
                    f"DOTFILES_INSTALL_{marker}:{state['run']}"
                    for marker in ("PASS1", "PASS2", "TRIPWIRE")
                )
                + "\n"
            )
            state["built"] = True
            if mode == "client_error":
                result.returncode = 1
            if mode == "bad_marker":
                result.stdout = "stale or cached run evidence\n"
            if mode == "build_timeout":
                raise subprocess.TimeoutExpired(command, 1800)
        elif args[:2] == ["image", "inspect"]:
            result.stdout = json.dumps(
                [
                    {
                        "Id": "b" * 64 if mode == "wrong_id" else image,
                        "RepoTags": state["tag"]
                        if mode == "malformed_tags"
                        else [state["tag"], "localhost/foreign:keep"],
                        "Config": {
                            "Labels": {
                                acceptance.RUN_LABEL: "foreign-run"
                                if mode == "foreign_label"
                                else state["run"]
                            }
                        },
                    }
                ]
            )
        elif args[0] == "untag":
            assert args == ["untag", image, state["tag"]]
            if mode == "untag_failure":
                result.returncode = 125
            else:
                state["built"] = False
        else:
            raise AssertionError(command)
        return result

    monkeypatch.setattr(subprocess, "run", process)
    if mode == "final_save_error":
        original_replace = Path.replace

        def replace(path, target):
            if json.loads(path.read_text(encoding="utf-8")).get("complete") is True:
                raise OSError("controlled completion persistence failure")
            return original_replace(path, target)

        monkeypatch.setattr(Path, "replace", replace)
    if mode != "ok":
        with pytest.raises(RuntimeError):
            acceptance._build_prepared_snapshot(
                context, tmp_path / "records", environment, identity
            )
        saved = json.loads(
            (tmp_path / "records" / state["run"] / "journal.json").read_text(
                encoding="utf-8"
            )
        )
        assert saved["complete"] is False
        assert context.exists()
        assert all(
            not set(command).intersection({"rmi", "prune", "--force"})
            for command in calls
        )
        assert not any(command[1] == "untag" for command in calls) or mode in {
            "untag_failure",
            "final_save_error",
        }
        return
    record = acceptance._build_prepared_snapshot(
        context, tmp_path / "records", environment, identity
    )
    assert record.get("complete") is True
    persisted = json.loads(
        (tmp_path / "records" / record["run_id"] / "journal.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted == record
    assert record["image_id"] == image
    assert len([command for command in calls if command[1] == "untag"]) == 1
    assert all(
        not set(command).intersection({"rmi", "prune", "--force"}) for command in calls
    )


def test_source_entrypoint_refuses_unintegrated_snapshot_helper_before_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "library"
    (library / "tests").mkdir(parents=True)
    (library / "tests/test_just_sandbox.py").write_text(
        'def _snapshot_tracked_worktree(source):\n    raise AssertionError("unsafe helper must never run")\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(acceptance, "ROOT", library)
    calls = []
    metadata = {
        "version": {"Version": "5.6.2"},
        "host": {
            "hostname": "controlled",
            "serviceIsRemote": False,
            "remoteSocket": {"path": "unix:///run/user/501/podman/podman.sock"},
        },
        "store": {"graphRoot": "/controlled/storage"},
    }

    def process(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "podman version 6.1.4\n"
            if command[-1] == "--version"
            else json.dumps(metadata),
            "",
        )

    monkeypatch.setattr(subprocess, "run", process)
    with pytest.raises(RuntimeError, match="snapshot helper is not integrated"):
        acceptance.accept_installer(tmp_path, tmp_path / "records")
    assert calls == [["podman", "--version"], ["podman", "info", "--format", "json"]]
    assert not (tmp_path / "records").exists()


@pytest.mark.parametrize("invalid", ["hostname", "socket", "graph_root", "remote"])
def test_invalid_selected_identity_is_rejected_before_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    # Decode external JSON before injecting intentionally invalid field types.
    metadata = json.loads(
        '{"version":{"Version":"5.6.2"},'
        '"host":{"hostname":"controlled","serviceIsRemote":false,'
        '"remoteSocket":{"path":"unix:///run/user/501/podman/podman.sock"}},'
        '"store":{"graphRoot":"/controlled/storage"}}'
    )
    if invalid == "hostname":
        metadata["host"]["hostname"] = ""
    elif invalid == "socket":
        metadata["host"]["remoteSocket"]["path"] = None
    elif invalid == "graph_root":
        metadata["store"]["graphRoot"] = None
    else:
        metadata["host"]["serviceIsRemote"] = "false"

    def process(command, **kwargs):
        content = (
            "podman version 6.1.4\n"
            if command[-1] == "--version"
            else json.dumps(metadata)
        )
        return subprocess.CompletedProcess(command, 0, content, "")

    monkeypatch.setattr(subprocess, "run", process)
    with pytest.raises(RuntimeError, match="selected-engine identity"):
        acceptance.accept_installer(tmp_path, tmp_path / "output")
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("server", ["4.9.0", "invalid", None])
def test_bad_engine_is_rejected_before_any_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, server: str | None
) -> None:
    calls = []

    def process(command, **kwargs):
        calls.append(command)
        content = (
            "podman version 6.1.4\n"
            if command == ["podman", "--version"]
            else json.dumps({"version": {"Version": server}})
        )
        return subprocess.CompletedProcess(command, 0, content, "")

    monkeypatch.setattr(subprocess, "run", process)
    with pytest.raises(RuntimeError, match=r"Podman engine >=5"):
        acceptance.accept_installer(tmp_path, tmp_path / "output")
    assert calls == [["podman", "--version"], ["podman", "info", "--format", "json"]]
    assert not (tmp_path / "output").exists()


def test_old_client_is_rejected_before_any_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []

    def process(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "podman version 4.9.0\n", "")

    monkeypatch.setattr(subprocess, "run", process)
    with pytest.raises(RuntimeError, match=r"Podman client >=5"):
        acceptance.accept_installer(tmp_path, tmp_path / "output")
    assert calls == [["podman", "--version"]]
    assert not (tmp_path / "output").exists()
