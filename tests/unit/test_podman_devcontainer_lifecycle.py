"""Hermetic process-boundary proofs of the required devcontainer lifecycle."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
IMAGE_ID = "sha256:" + "a" * 64
CONTAINER_ID = "b" * 64


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "podman_lifecycle_under_test", ROOT / "tests/test_just_sandbox.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / "repo"
    snapshot = repo / "snapshot"
    (snapshot / ".devcontainer").mkdir(parents=True)
    shutil.copyfile(
        ROOT / ".devcontainer/devcontainer.json",
        snapshot / ".devcontainer/devcontainer.json",
    )
    monkeypatch.setattr(module, "ROOT", repo)
    monkeypatch.setattr(module, "_snapshot_tracked_worktree", lambda src: str(snapshot))
    monkeypatch.setattr(module.shutil, "which", lambda executable: executable)
    monkeypatch.delenv("LOCAL_WORKSPACE_FOLDER", raising=False)
    monkeypatch.delenv("DOTFILES_DEVCONTAINER_MANIFEST", raising=False)
    monkeypatch.delenv("CONTAINER_HOST", raising=False)
    monkeypatch.setenv(
        "DOTFILES_PODMAN_ENGINE_SOCKET", "/run/user/123/podman/podman.sock"
    )
    state: dict[str, Any] = {
        "calls": [],
        "failure": None,
        "containers": [],
        "foreign": False,
    }

    def journal_file():
        return (
            Path(os.environ["DOTFILES_DEVCONTAINER_MANIFEST"])
            if os.environ.get("DOTFILES_DEVCONTAINER_MANIFEST")
            else module.ROOT / ".pi/tasks" / f"devcontainer-{state['run_id']}.json"
        )

    def run(cmd, **kwargs):
        state["calls"].append((cmd, kwargs))
        output = ""
        rc = 0
        if cmd[:2] == ["podman", "info"]:
            output = json.dumps(
                {
                    "host": {
                        "hostname": state.get("hostname", "selected"),
                        "remoteSocket": {
                            "path": "unix:///run/user/123/podman/podman.sock"
                        },
                        "serviceIsRemote": False,
                    },
                    "store": {"graphRoot": "/selected/storage"},
                }
            )
        elif cmd[:2] == ["podman", "version"]:
            output = json.dumps(
                {"Client": {"Version": "6.1.4"}, "Server": {"Version": "5.6.2"}}
            )
        elif cmd[:3] == ["podman", "image", "exists"]:
            rc = (
                125
                if state["failure"] == "lookup"
                else (0 if state.get("tag_created") else 1)
            )
        elif cmd[:2] == ["devcontainer", "build"]:
            filename = os.environ.get("DOTFILES_DEVCONTAINER_MANIFEST")
            journal_path = (
                Path(filename)
                if filename
                else module.ROOT
                / ".pi/tasks"
                / f"devcontainer-{cmd[-1].rsplit(':', 1)[1]}.json"
            )
            prepared = json.loads(journal_path.read_text(encoding="utf-8"))["runs"][-1]
            assert prepared["image_id"] is None and prepared["complete"] is False
            assert prepared["build_state"] == "running"
            assert prepared["snapshot_path"] == str(snapshot)
            state["tag"] = cmd[-1]
            state["run_id"] = cmd[-1].rsplit(":", 1)[1]
            state["tag_created"] = state["failure"] not in {
                "build",
                "build-interrupt-no-tag",
            }
            if state["failure"] in {"build-interrupt", "build-interrupt-no-tag"}:
                raise KeyboardInterrupt
            if error := state.get("build_exception"):
                raise error
            if "build_tag_created" in state:
                state["tag_created"] = state["build_tag_created"]
            rc = state.get(
                "build_returncode",
                1 if state["failure"] in {"build", "build-tag"} else 0,
            )
        elif cmd[:3] == ["podman", "image", "inspect"]:
            output = json.dumps(
                [
                    {
                        "Id": state.get("image_id", IMAGE_ID),
                        "RepoTags": [state["tag"], "foreign:keep"],
                        "Config": {
                            "Labels": {
                                "devcontainer.metadata": state.get(
                                    "metadata",
                                    json.dumps(
                                        [
                                            {
                                                "containerEnv": {
                                                    module.RUN_NONCE_ENV: state.get(
                                                        "run_id"
                                                    )
                                                }
                                            }
                                        ]
                                    ),
                                )
                            }
                        },
                    }
                ]
            )
        elif cmd[:2] == ["devcontainer", "up"]:
            prepared = json.loads(journal_file().read_text(encoding="utf-8"))["runs"][
                -1
            ]
            assert prepared["up_state"] == "pending" and not prepared["container_ids"]
            state["run_id"] = cmd[-1].split("=", 1)[1]
            state["containers"] = [CONTAINER_ID]
            output = json.dumps({"containerId": CONTAINER_ID})
            rc = 1 if state["failure"] == "up" else 0
        elif cmd[:3] == ["podman", "container", "exists"]:
            rc = (
                125
                if state.get("container_query_failed")
                else (1 if state.get("container_missing") else 0)
            )
        elif cmd[:3] == ["podman", "container", "inspect"]:
            label = "foreign" if state["foreign"] else state["run_id"]
            output = json.dumps(
                [
                    {
                        "Id": state.get("container_inspected_id", CONTAINER_ID),
                        "Image": state.get("container_image", IMAGE_ID),
                        "Config": {"Labels": {module.RUN_LABEL: label}},
                    }
                ]
            )
        elif cmd[:2] == ["devcontainer", "exec"]:
            prepared = json.loads(journal_file().read_text(encoding="utf-8"))["runs"][
                -1
            ]
            assert (
                prepared["exec_state"] == "pending"
                and prepared["up_state"] == "completed"
            )
            assert prepared["container_ids"] == [CONTAINER_ID]
            if state["failure"] == "interrupt":
                raise KeyboardInterrupt
            output = f"DOTFILES_SANDBOX_EXEC_COMPLETE={state['run_id']}\n"
        elif cmd[:2] == ["podman", "create"]:
            state["run_id"] = cmd[cmd.index("--label") + 1].split("=", 1)[1]
            prepared = json.loads(journal_file().read_text(encoding="utf-8"))["runs"][
                -1
            ]
            assert (
                prepared["create_state"] == "pending" and not prepared["container_ids"]
            )
            state["containers"] = [CONTAINER_ID]
            output = CONTAINER_ID
        elif cmd[:2] == ["podman", "start"]:
            assert cmd == ["podman", "start", "--attach", CONTAINER_ID]
            prepared = json.loads(journal_file().read_text(encoding="utf-8"))["runs"][
                -1
            ]
            assert prepared["create_state"] == "completed" and prepared[
                "container_ids"
            ] == [CONTAINER_ID]
            if error := state.get("start_exception"):
                raise error
            rc = state.get("start_returncode", 0)
            output = "controlled application stdout"
        elif cmd[:2] == ["podman", "untag"]:
            journal_path = os.environ.get(
                "DOTFILES_DEVCONTAINER_MANIFEST"
            ) or state.get("journal_path")
            if journal_path:
                saved = json.loads(Path(journal_path).read_text(encoding="utf-8"))[
                    "runs"
                ][-1]
                assert saved["image_id"] == IMAGE_ID and saved["complete"] is False
            assert cmd == ["podman", "untag", IMAGE_ID, state["tag"]]
            state["tag_created"] = False
        elif cmd[:2] == ["podman", "rm"]:
            state["containers"] = []
            state["container_missing"] = True
        elif cmd[:2] == ["podman", "ps"]:
            assert cmd[-1].startswith("label=" + module.RUN_LABEL + "=")
            output = "\n".join(state.get("discovered", state["containers"]))
        elif cmd[-1] == ".devcontainer/require-podman-socket.sh" and state.get(
            "initializer_refused"
        ):
            rc = 1
        if cmd[:2] == ["devcontainer", "build"]:
            output = state.get("build_stdout", output)
        return subprocess.CompletedProcess(
            cmd, rc, output, state.get("build_stderr", "injected") if rc else ""
        )

    monkeypatch.setattr(module.subprocess, "run", run)
    return module, snapshot, state


def _diagnostic_chain(error):
    messages = []
    while error is not None:
        messages.append(f"{type(error).__name__}: {error}")
        error = error.__cause__ or error.__context__
    return "\n".join(messages)


@pytest.mark.parametrize("returncode", [1, 125, -15, 130, 137, 143])
@pytest.mark.parametrize("tag_created", [False, True])
def test_any_nonzero_build_keeps_durable_unknown_context_and_original_diagnostics(
    runtime, tmp_path, monkeypatch, returncode, tag_created
):
    module, snapshot, state = runtime
    path = tmp_path / "transport.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    state.update(
        build_returncode=returncode,
        build_tag_created=tag_created,
        build_stdout="controlled build output",
        build_stderr="connection reset by peer",
    )
    with pytest.raises(RuntimeError) as error, module.devcontainer_session():
        pytest.fail("nonzero client receipt must not yield")
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is False
    assert saved["build_state"] == "interrupted"
    assert saved["snapshot_path"] == str(snapshot)
    assert snapshot.exists()
    assert saved["image_id"] == (IMAGE_ID if tag_created else None)
    diagnostics = _diagnostic_chain(error.value)
    assert f"build failed ({returncode})" in diagnostics
    assert "controlled build output" in diagnostics
    assert "connection reset by peer" in diagnostics
    assert not any(
        cmd[:2] in (["devcontainer", "up"], ["podman", "untag"], ["podman", "rm"])
        for cmd, _ in state["calls"]
    )
    # A subsequent cleanup attempt cannot bless unknown completion.
    with pytest.raises(RuntimeError, match="completion unknown"):
        module.cleanup_devcontainer_manifest(path)
    assert snapshot.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["runs"][0]["complete"] is False


@pytest.mark.parametrize(
    "exception", [KeyboardInterrupt("signal"), OSError("transport")]
)
def test_build_exception_retains_context_and_chained_original(
    runtime, tmp_path, monkeypatch, exception
):
    module, snapshot, state = runtime
    path = tmp_path / "exception.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    state["build_exception"] = exception
    with pytest.raises(RuntimeError) as error, module.devcontainer_session():
        pytest.fail("exceptional build must not yield")
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is False and snapshot.exists()
    assert saved["snapshot_path"] == str(snapshot)
    assert str(exception) in _diagnostic_chain(error.value)


@pytest.mark.parametrize(
    "failure", ["foreign-container", "changed-engine", "tag-lookup"]
)
def test_cleanup_failure_retains_context_for_completed_build(
    runtime, tmp_path, monkeypatch, failure
):
    module, snapshot, state = runtime
    path = tmp_path / "cleanup.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    with pytest.raises(RuntimeError), module.devcontainer_session():
        if failure == "foreign-container":
            state["foreign"] = True
        elif failure == "changed-engine":
            state["hostname"] = "another-engine"
        else:
            state["failure"] = "lookup"
    assert snapshot.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is False and saved["snapshot_path"] == str(snapshot)


@pytest.mark.parametrize("failure_point", ["unknown", "complete"])
def test_journal_replace_failure_never_removes_context(
    runtime, tmp_path, monkeypatch, failure_point
):
    module, snapshot, state = runtime
    path = tmp_path / "write-failure.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    replace = Path.replace

    def fail_replace(source, target):
        pending = json.loads(source.read_text(encoding="utf-8"))["runs"][-1]
        if (failure_point == "complete" and pending["complete"]) or (
            failure_point == "unknown"
            and pending["build_state"] in {"failed", "interrupted"}
        ):
            raise OSError("controlled atomic journal failure")
        return replace(source, target)

    monkeypatch.setattr(Path, "replace", fail_replace)
    if failure_point == "unknown":
        state.update(
            build_returncode=125,
            build_stdout="original stdout",
            build_stderr="original stderr",
        )
    with pytest.raises(OSError) as error, module.devcontainer_session():
        pass
    assert snapshot.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is False and saved["snapshot_path"] == str(snapshot)
    if failure_point == "unknown":
        diagnostics = _diagnostic_chain(error.value)
        assert "build failed (125)" in diagnostics
        assert "original stdout" in diagnostics and "original stderr" in diagnostics


def test_default_journal_is_durable_unique_and_reports_actionable_path(runtime, capsys):
    module, snapshot, state = runtime
    # No manifest environment setting: each actual session must still persist.
    for index in range(2):
        with module.devcontainer_session() as receipt:
            path = module.ROOT / ".pi/tasks" / f"devcontainer-{receipt['run_id']}.json"
            saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
            assert (
                saved["snapshot_path"] == str(snapshot) and saved["complete"] is False
            )
            assert str(path) in capsys.readouterr().err
        assert not snapshot.exists()
        assert (
            json.loads(path.read_text(encoding="utf-8"))["runs"][0]["complete"] is True
        )
        if index == 0:
            (snapshot / ".devcontainer").mkdir(parents=True)
            shutil.copyfile(
                ROOT / ".devcontainer/devcontainer.json",
                snapshot / ".devcontainer/devcontainer.json",
            )
    journals = list((module.ROOT / ".pi/tasks").glob("devcontainer-*.json"))
    assert len(journals) == 2 and journals[0] != journals[1]
    assert not any("rmi" in cmd or "prune" in cmd for cmd, _ in state["calls"])


def test_unknown_build_without_manifest_env_retains_default_journal_and_snapshot(
    runtime, capsys
):
    module, snapshot, state = runtime
    state.update(build_returncode=125, build_tag_created=False)
    with (
        pytest.raises(RuntimeError, match="completion unknown"),
        module.devcontainer_session(),
    ):
        pytest.fail("transport failure must not yield")
    path = module.ROOT / ".pi/tasks" / f"devcontainer-{state['run_id']}.json"
    assert str(path) in capsys.readouterr().err
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["snapshot_path"] == str(snapshot)
    assert saved["build_state"] == "interrupted" and saved["complete"] is False
    assert snapshot.exists()


def test_bare_owned_context_without_checked_creation_remains_incomplete(runtime):
    module, snapshot, _ = runtime
    run_id = "a" * 32
    path = module.ROOT / ".pi/tasks" / f"devcontainer-{run_id}.json"
    with (
        pytest.raises(RuntimeError, match="completion unknown"),
        module.owned_container_run(run_id),
    ):
        saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
        assert saved["snapshot_path"] is None and saved["complete"] is False
    assert json.loads(path.read_text(encoding="utf-8"))["runs"][0]["complete"] is False
    assert snapshot.exists()  # container-only cleanup never owns this directory


def test_tracked_only_snapshot_is_a_sibling_outside_real_git_ancestry(
    tmp_path, monkeypatch
):
    spec = importlib.util.spec_from_file_location(
        "podman_snapshot_under_test", ROOT / "tests/test_just_sandbox.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    repo = tmp_path / "operator-repo"
    repo.mkdir()
    subprocess.run(
        ["git", "-C", str(repo), "init", "-q"], check=True, capture_output=True
    )
    (repo / "tracked.txt").write_text("tracked", encoding="utf-8")
    (repo / "secret.key").write_text("must not enter snapshot", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "tracked.txt"], check=True, capture_output=True
    )
    monkeypatch.setattr(module, "ROOT", repo)
    snapshot = Path(module._snapshot_tracked_worktree(str(repo)))
    assert snapshot.parent == repo.parent
    assert (snapshot / "tracked.txt").read_text(encoding="utf-8") == "tracked"
    assert not (snapshot / "secret.key").exists()
    assert not (snapshot / ".git").exists()
    module._assert_snapshot_has_no_git_ancestry(snapshot)
    shutil.rmtree(snapshot)


def test_fresh_build_actual_up_exec_and_exact_owned_cleanup(runtime):
    module, snapshot, state = runtime
    foreign = snapshot.parent / "foreign-context"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("unowned", encoding="utf-8")
    with module.devcontainer_session() as receipt:
        assert receipt["image_id"] == IMAGE_ID
        config = json.loads(
            (snapshot / ".devcontainer/devcontainer.json").read_text(encoding="utf-8")
        )
        assert f"--label={module.RUN_LABEL}={receipt['run_id']}" in config["runArgs"]
        assert config["containerEnv"][module.RUN_NONCE_ENV] == receipt["run_id"]
        assert config["workspaceMount"].startswith(f"source={snapshot},")
        calls = [cmd for cmd, _ in state["calls"]]
        build, up, execute = [cmd for cmd in calls if cmd[0] == "devcontainer"]
        assert build[1] == "build" and up[1] == "up" and execute[1] == "exec"
        for cmd in (build, up, execute):
            assert cmd[cmd.index("--docker-path") + 1] == "podman"
            assert cmd[cmd.index("--docker-compose-path") + 1] == "podman-compose"
        assert "podman run --rm --network none --label" in execute[-1]
        assert (
            "--mount-workspace-git-root=false" in up
            and "--mount-git-worktree-common-dir=false" in up
        )
        assert (
            "--mount-workspace-git-root=false" in execute
            and "--mount-git-worktree-common-dir=false" in execute
        )
        assert not any(flag.startswith("--mount-") for flag in build)
    assert not snapshot.exists()
    assert (foreign / "keep.txt").read_text(encoding="utf-8") == "unowned"
    commands = [cmd for cmd, _ in state["calls"]]
    assert ["podman", "rm", "-f", CONTAINER_ID] in commands
    assert ["podman", "untag", IMAGE_ID, state["tag"]] in commands
    assert not any("rmi" in cmd or "prune" in cmd for cmd in commands)


@pytest.mark.parametrize("failure", ["lookup", "build", "up", "interrupt"])
def test_failures_never_reuse_latest_and_cleanup_partial_startup(runtime, failure):
    module, snapshot, state = runtime
    state["failure"] = failure
    error = RuntimeError
    with pytest.raises(error), module.devcontainer_session():
        pytest.fail("failed lifecycle must not yield")
    commands = [cmd for cmd, _ in state["calls"]]
    assert not any("latest" in str(cmd) for cmd in commands)
    if failure in ("up", "interrupt"):
        assert ["podman", "rm", "-f", CONTAINER_ID] not in commands
    if failure == "build":
        assert not any(cmd[:2] == ["devcontainer", "up"] for cmd in commands)
        assert not any("untag" in cmd for cmd in commands)
    if failure != "lookup":
        assert (
            snapshot.exists()
        )  # nonzero/exceptional creation cannot prove termination


def test_enclosing_real_git_checkout_is_refused_before_build(runtime):
    module, _, state = runtime
    (module.ROOT / ".git").mkdir()
    with (
        pytest.raises(RuntimeError, match="enclosing Git worktree"),
        module.devcontainer_session(),
    ):
        pytest.fail("real Git ancestry must never reach CLI build")
    assert not any(cmd[0] == "devcontainer" for cmd, _ in state["calls"])


def test_nested_lifecycle_refuses_unmapped_sibling_snapshot(runtime, monkeypatch):
    module, _, state = runtime
    monkeypatch.setenv("LOCAL_WORKSPACE_FOLDER", "/engine/disposable")
    monkeypatch.setenv(module.DISPOSABLE_CHECKOUT_ENV, "1")
    with (
        pytest.raises(RuntimeError, match="sibling snapshot"),
        module.devcontainer_session(),
    ):
        pytest.fail("an explicit mapping of ROOT does not map its siblings")
    assert not any(cmd[0] == "devcontainer" for cmd, _ in state["calls"])


def test_cleanup_rejects_foreign_label_without_deleting(runtime):
    module, _, state = runtime
    state.update(run_id="ours", containers=[CONTAINER_ID], foreign=True)
    with pytest.raises(RuntimeError, match="unowned"):
        module._cleanup_run_containers("ours")
    assert not any(cmd[:2] == ["podman", "rm"] for cmd, _ in state["calls"])


def test_nested_snapshot_uses_explicit_engine_path_and_disposable_fence(
    runtime, monkeypatch
):
    module, snapshot, _ = runtime
    monkeypatch.setenv("LOCAL_WORKSPACE_FOLDER", "/engine/disposable")
    with pytest.raises(RuntimeError, match="refusing"):
        module._engine_snapshot_path(snapshot)
    monkeypatch.setenv(module.DISPOSABLE_CHECKOUT_ENV, "1")
    assert module._engine_snapshot_path(snapshot) == "/engine/disposable/snapshot"


def test_untag_preserves_reused_image_id_foreign_aliases_and_new_references(runtime):
    module, _, state = runtime
    # No build: this ID predates the run. Inspect returns a foreign keep alias,
    # and a new foreign container reference appears before cleanup.
    state.update(
        tag="localhost/run:ours", tag_created=True, containers=["foreign-reference"]
    )
    module._untag_run_image(state["tag"], IMAGE_ID)
    assert state["containers"] == ["foreign-reference"]
    commands = [cmd for cmd, _ in state["calls"]]
    assert commands[-1] == ["podman", "untag", IMAGE_ID, state["tag"]]
    assert not any(cmd[:2] in (["podman", "rmi"], ["podman", "rm"]) for cmd in commands)


def test_changed_tag_never_untags_another_image(runtime):
    module, _, state = runtime
    state["tag"] = "localhost/run:ours"
    state["tag_created"] = True
    with pytest.raises(RuntimeError, match="tag changed"):
        module._untag_run_image(state["tag"], "sha256:different")
    assert not any("untag" in cmd for cmd, _ in state["calls"])


def test_prepared_journal_and_observed_ids_are_atomic_and_recoverable(
    runtime, monkeypatch, tmp_path
):
    module, _, state = runtime
    path = tmp_path / "journal.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    with module.devcontainer_session() as receipt:
        journal = json.loads(path.read_text(encoding="utf-8"))
        record = journal["runs"][0]
        assert record["complete"] is False
        assert record["run_id"] == receipt["run_id"]
        assert record["image_id"] == IMAGE_ID
        assert record["build_state"] == "succeeded"
        assert record["container_ids"] == [CONTAINER_ID]
        assert not path.with_suffix(".json.tmp").exists()
    journal = json.loads(path.read_text(encoding="utf-8"))
    assert journal["runs"][0]["complete"] is True
    # Repeated always-step cleanup of a completed run performs no engine calls.
    state["calls"].clear()
    module.cleanup_devcontainer_manifest(path)
    assert state["calls"] == []


def test_prepared_unknown_tag_cannot_be_declared_complete_without_query(
    runtime, tmp_path
):
    module, _, state = runtime
    run_id = "e" * 32
    record = {
        "run_id": run_id,
        "tag": f"localhost/dotfiles-sandbox:{run_id}",
        "tag_was_absent": True,
        "image_id": None,
        "container_ids": [],
        "engine": module._selected_engine_identity(),
        "complete": False,
        "build_state": "running",
        "snapshot_path": str(tmp_path / "retained-context"),
        "up_state": "not-started",
        "exec_state": "not-started",
        "create_state": "not-started",
    }
    path = tmp_path / "recovery.json"
    path.write_text(json.dumps({"version": 4, "runs": [record]}), encoding="utf-8")
    state["calls"].clear()
    with pytest.raises(RuntimeError, match="completion"):
        module.cleanup_devcontainer_manifest(path)
    assert json.loads(path.read_text(encoding="utf-8"))["runs"][0]["complete"] is False
    assert any(cmd[:3] == ["podman", "image", "exists"] for cmd, _ in state["calls"])


def test_changed_selected_engine_retains_all_resources(runtime, monkeypatch, tmp_path):
    module, _, state = runtime
    run_id = "c" * 32
    record = {
        "run_id": run_id,
        "tag": None,
        "tag_was_absent": False,
        "image_id": None,
        "container_ids": [],
        "engine": module._selected_engine_identity(),
        "complete": False,
        "build_state": "not-started",
        "snapshot_path": None,
        "up_state": "not-started",
        "exec_state": "not-started",
        "create_state": "not-started",
    }
    path = tmp_path / "journal.json"
    path.write_text(json.dumps({"version": 4, "runs": [record]}), encoding="utf-8")
    state["hostname"] = "other-engine"
    with pytest.raises(RuntimeError, match="selected engine changed"):
        module.cleanup_devcontainer_manifest(path)
    assert not any(cmd[:2] == ["podman", "rm"] for cmd, _ in state["calls"])


@pytest.mark.parametrize(
    "mutation",
    ["duplicate-run", "boolean-version", "extra-root-key", "non-object-root"],
)
def test_malformed_journal_envelope_is_rejected_before_engine_access(
    runtime, tmp_path, mutation
):
    module, _, state = runtime
    record = {
        "run_id": "d" * 32,
        "tag": None,
        "tag_was_absent": False,
        "image_id": None,
        "container_ids": [],
        "engine": {
            "hostname": "selected",
            "graph_root": "/selected/storage",
            "socket": "unix:///run/user/123/podman/podman.sock",
            "endpoint": "native-local",
        },
        "complete": False,
        "build_state": "not-started",
        "snapshot_path": None,
        "up_state": "not-started",
        "exec_state": "not-started",
        "create_state": "not-started",
    }
    journal: Any = {"version": 4, "runs": [record]}
    if mutation == "duplicate-run":
        journal["runs"].append(record)
    elif mutation == "boolean-version":
        journal["version"] = True
    elif mutation == "extra-root-key":
        journal["unexpected"] = "invalid"
    else:
        journal = []
    path = tmp_path / "bad-envelope.json"
    path.write_text(json.dumps(journal), encoding="utf-8")
    with pytest.raises(RuntimeError, match="journal"):
        module.cleanup_devcontainer_manifest(path)
    assert state["calls"] == []


def _recovery_record(
    module, state, tmp_path, build_state="succeeded", image_id=None, container_ids=None
):
    run_id = "f" * 32
    record = {
        "run_id": run_id,
        "tag": f"localhost/dotfiles-sandbox:{run_id}",
        "tag_was_absent": True,
        "image_id": image_id,
        "container_ids": container_ids or [],
        "engine": module._selected_engine_identity(),
        "complete": False,
        "build_state": build_state,
        "snapshot_path": str(tmp_path / "retained-context"),
        "up_state": "not-started",
        "exec_state": "not-started",
        "create_state": "not-started",
    }
    state.update(tag=record["tag"], run_id=run_id)
    path = tmp_path / "recovery.json"
    state["journal_path"] = str(path)
    path.write_text(json.dumps({"version": 4, "runs": [record]}), encoding="utf-8")
    state["calls"].clear()
    return path, record


def test_successful_build_recovers_nonce_proven_tag_and_persists_cleanup_without_env(
    runtime, tmp_path
):
    module, _, state = runtime
    path, _ = _recovery_record(module, state, tmp_path, "succeeded")
    state["tag_created"] = True
    module.cleanup_devcontainer_manifest(path)
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["image_id"] == IMAGE_ID and saved["complete"] is True
    assert ["podman", "untag", IMAGE_ID, state["tag"]] in [
        cmd for cmd, _ in state["calls"]
    ]


@pytest.mark.parametrize("build_state", ["running", "interrupted"])
@pytest.mark.parametrize("tag_created", [False, True])
def test_unknown_build_always_retains_incomplete_even_with_owned_nonce(
    runtime, tmp_path, build_state, tag_created
):
    module, _, state = runtime
    path, _ = _recovery_record(module, state, tmp_path, build_state)
    state["tag_created"] = tag_created
    for _ in range(2):  # retry never launders the recovered ID into completion
        with pytest.raises(RuntimeError, match="completion unknown/interrupted"):
            module.cleanup_devcontainer_manifest(path)
        saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
        assert saved["complete"] is False
        assert saved["image_id"] == (IMAGE_ID if tag_created else None)
    assert not any(
        cmd[:2] in (["podman", "untag"], ["podman", "rm"]) for cmd, _ in state["calls"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-nonce",
        "foreign-nonce",
        "malformed-metadata",
        "short-id",
        "changed-tag",
        "lookup-error",
    ],
)
def test_unproven_or_changed_recovery_retains_image_and_incomplete(
    runtime, tmp_path, mutation
):
    module, _, state = runtime
    path, _ = _recovery_record(
        module,
        state,
        tmp_path,
        image_id=IMAGE_ID if mutation == "changed-tag" else None,
    )
    state["tag_created"] = True
    if mutation == "missing-nonce":
        state["metadata"] = "[]"
    elif mutation == "foreign-nonce":
        state["metadata"] = json.dumps(
            [{"containerEnv": {module.RUN_NONCE_ENV: "foreign"}}]
        )
    elif mutation == "malformed-metadata":
        state["metadata"] = "not-json"
    elif mutation in {"short-id", "changed-tag"}:
        state["image_id"] = "short" if mutation == "short-id" else "sha256:" + "d" * 64
    else:
        state["failure"] = "lookup"
    with pytest.raises(RuntimeError):
        module.cleanup_devcontainer_manifest(path)
    assert json.loads(path.read_text(encoding="utf-8"))["runs"][0]["complete"] is False
    assert not any(
        cmd[:2] in (["podman", "untag"], ["podman", "rm"]) for cmd, _ in state["calls"]
    )


@pytest.mark.parametrize("build_state", ["not-started", "succeeded"])
def test_absent_tag_requires_known_accounted_terminal_state(
    runtime, tmp_path, build_state
):
    module, _, state = runtime
    path, _ = _recovery_record(module, state, tmp_path, build_state)
    if build_state == "succeeded":
        with pytest.raises(RuntimeError, match="unaccounted"):
            module.cleanup_devcontainer_manifest(path)
    else:
        module.cleanup_devcontainer_manifest(path)
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is (build_state != "succeeded")
    assert any(cmd[:3] == ["podman", "image", "exists"] for cmd, _ in state["calls"])


def test_nonzero_build_after_tag_creation_recovers_id_but_retains_unknown_context(
    runtime, tmp_path, monkeypatch
):
    module, snapshot, state = runtime
    path = tmp_path / "failed-build.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    state["failure"] = "build-tag"
    with (
        pytest.raises(RuntimeError, match="completion unknown"),
        module.devcontainer_session(),
    ):
        pytest.fail("failed build must not yield")
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert (
        saved["build_state"] == "interrupted"
        and saved["image_id"] == IMAGE_ID
        and saved["complete"] is False
    )
    assert snapshot.exists() and saved["snapshot_path"] == str(snapshot)
    assert not any(cmd[:2] == ["podman", "untag"] for cmd, _ in state["calls"])
    assert not any(cmd[:2] == ["devcontainer", "up"] for cmd, _ in state["calls"])


@pytest.mark.parametrize("returncode", [-15, 130, 137, 143])
def test_signalled_build_result_is_unknown_not_an_accounted_failure(
    runtime, tmp_path, monkeypatch, returncode
):
    module, _, state = runtime
    path = tmp_path / "signalled.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    state["build_returncode"] = returncode
    with (
        pytest.raises(RuntimeError, match="completion unknown/interrupted"),
        module.devcontainer_session(),
    ):
        pytest.fail("signalled build must not yield")
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["build_state"] == "interrupted" and saved["complete"] is False
    assert saved["image_id"] == IMAGE_ID
    assert not any(cmd[:2] == ["podman", "untag"] for cmd, _ in state["calls"])


@pytest.mark.parametrize("failure", ["build-interrupt", "build-interrupt-no-tag"])
def test_interrupted_build_before_id_persistence_stays_recoverable_not_complete(
    runtime, tmp_path, monkeypatch, failure
):
    module, _, state = runtime
    path = tmp_path / "interrupted.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    state["failure"] = failure
    with (
        pytest.raises(RuntimeError, match="completion unknown/interrupted"),
        module.devcontainer_session(),
    ):
        pytest.fail("interrupted build must not yield")
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["build_state"] == "interrupted" and saved["complete"] is False
    assert saved["image_id"] == (IMAGE_ID if failure == "build-interrupt" else None)
    assert not any(
        cmd[:2] in (["devcontainer", "up"], ["podman", "untag"])
        for cmd, _ in state["calls"]
    )


@pytest.mark.parametrize(
    "mutation",
    ["changed-label", "changed-id", "changed-image", "query-error", "not-found"],
)
def test_recorded_container_not_in_label_discovery_is_reinspected(
    runtime, tmp_path, mutation
):
    module, _, state = runtime
    path, _ = _recovery_record(
        module, state, tmp_path, "succeeded", IMAGE_ID, [CONTAINER_ID]
    )
    state["discovered"] = []
    if mutation == "changed-label":
        state["foreign"] = True
    elif mutation == "changed-id":
        state["container_inspected_id"] = "a" * 64
    elif mutation == "changed-image":
        state["container_image"] = "d" * 64
    elif mutation == "query-error":
        state["container_query_failed"] = True
    else:
        state["container_missing"] = True
    if mutation == "not-found":
        module.cleanup_devcontainer_manifest(path)
    else:
        with pytest.raises(RuntimeError):
            module.cleanup_devcontainer_manifest(path)
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is (mutation == "not-found")
    commands = [cmd for cmd, _ in state["calls"]]
    assert ["podman", "container", "exists", CONTAINER_ID] in commands
    assert not any(cmd[:2] == ["podman", "rm"] for cmd in commands)


@pytest.mark.parametrize(
    "mutation",
    ["invalid-state", "duplicate-container", "unknown-complete", "bad-second-record"],
)
def test_entire_strict_build_journal_is_validated_before_engine_access(
    runtime, tmp_path, mutation
):
    module, _, state = runtime
    path, record = _recovery_record(module, state, tmp_path)
    journal = {"version": 4, "runs": [record]}
    if mutation == "invalid-state":
        record["build_state"] = []
    elif mutation == "duplicate-container":
        record.update(image_id=IMAGE_ID, container_ids=[CONTAINER_ID, CONTAINER_ID])
    elif mutation == "unknown-complete":
        record.update(build_state="running", complete=True)
    else:
        journal["runs"].append({})
    path.write_text(json.dumps(journal), encoding="utf-8")
    with pytest.raises(RuntimeError):
        module.cleanup_devcontainer_manifest(path)
    assert state["calls"] == []


@pytest.mark.parametrize("complete", [False, True])
def test_legacy_failed_journals_are_rejected_without_adopting_terminal_state(
    runtime, tmp_path, complete
):
    module, _, state = runtime
    path, record = _recovery_record(module, state, tmp_path)
    record.update(build_state="failed", complete=complete)
    record.pop("snapshot_path")
    path.write_text(json.dumps({"version": 2, "runs": [record]}), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="version"):
        module.cleanup_devcontainer_manifest(path)
    assert state["calls"] == [] and path.read_bytes() == before


@pytest.mark.parametrize("build_state", ["not-started", "succeeded", "interrupted"])
def test_recovery_journal_snapshot_path_is_never_deletion_authority(
    runtime, tmp_path, build_state
):
    module, snapshot, state = runtime
    victim = tmp_path / "foreign-context"
    victim.mkdir()
    sentinel = victim / "keep.txt"
    sentinel.write_text("unowned", encoding="utf-8")
    path, record = _recovery_record(module, state, tmp_path, build_state)
    record["snapshot_path"] = str(victim)
    path.write_text(json.dumps({"version": 4, "runs": [record]}), encoding="utf-8")
    if build_state == "succeeded":
        state["tag_created"] = True
    if build_state == "interrupted":
        with pytest.raises(RuntimeError, match="completion unknown"):
            module.cleanup_devcontainer_manifest(path)
    else:
        module.cleanup_devcontainer_manifest(path)
    assert sentinel.read_text(encoding="utf-8") == "unowned"
    assert snapshot.exists()
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is (build_state != "interrupted")


@pytest.mark.parametrize("snapshot_path", [False, 42, [], "", "bad\u0000path", None])
def test_invalid_snapshot_diagnostic_path_is_rejected_before_engine_access(
    runtime, tmp_path, snapshot_path
):
    module, _, state = runtime
    path, record = _recovery_record(module, state, tmp_path)
    record["snapshot_path"] = snapshot_path
    path.write_text(json.dumps({"version": 4, "runs": [record]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="snapshot"):
        module.cleanup_devcontainer_manifest(path)
    assert state["calls"] == []


def test_new_schema_cannot_bless_failed_state(runtime, tmp_path):
    module, _, state = runtime
    path, record = _recovery_record(module, state, tmp_path)
    record["build_state"] = "failed"
    path.write_text(json.dumps({"version": 4, "runs": [record]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="completion state"):
        module.cleanup_devcontainer_manifest(path)
    assert state["calls"] == []


def test_initializer_refusal_precedes_any_devcontainer_resource_call(runtime):
    module, _, state = runtime
    state["initializer_refused"] = True
    with pytest.raises(RuntimeError), module.devcontainer_session():
        pytest.fail("refused initializer must not yield")
    assert not any(cmd[0] == "devcontainer" for cmd, _ in state["calls"])
    assert not any(
        cmd[:3] == ["podman", "image", "exists"] for cmd, _ in state["calls"]
    )


@pytest.mark.parametrize("bad_record", [{}, {"run_id": 42}, None])
def test_partial_or_malformed_journal_never_contacts_engine(
    runtime, tmp_path, bad_record
):
    module, _, state = runtime
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"version": 4, "runs": [bad_record]}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="invalid"):
        module.cleanup_devcontainer_manifest(path)
    assert state["calls"] == []


@pytest.mark.parametrize("operation", ["up", "exec"])
@pytest.mark.parametrize(
    "failure", [1, 125, -15, 130, 137, 143, "exception", "signal", "missing", "invalid"]
)
def test_resource_operation_unknown_retains_context_despite_empty_discovery(
    runtime, tmp_path, monkeypatch, operation, failure
):
    module, snapshot, state = runtime
    path = tmp_path / "operation.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    original = module._run

    def process(cmd, **kwargs):
        if cmd[:2] == ["devcontainer", operation]:
            if failure == "exception":
                raise OSError("controlled transport loss")
            if failure == "signal":
                raise KeyboardInterrupt("controlled signal")
            if isinstance(failure, int):
                return subprocess.CompletedProcess(
                    cmd, failure, "original output", "transport error"
                )
            output = (
                ""
                if failure == "missing"
                else (
                    '{"containerId":"short"}'
                    if operation == "up"
                    else "foreign receipt"
                )
            )
            return subprocess.CompletedProcess(cmd, 0, output, "")
        return original(cmd, **kwargs)

    monkeypatch.setattr(module, "_run", process)
    with pytest.raises(RuntimeError) as error, module.devcontainer_session():
        pytest.fail("unproven resource operation must not yield")
    diagnostics = _diagnostic_chain(error.value)
    if isinstance(failure, int):
        assert f"failed ({failure})" in diagnostics
        assert "original output" in diagnostics and "transport error" in diagnostics
    elif failure == "exception":
        assert "controlled transport loss" in diagnostics
    elif failure == "signal":
        assert "controlled signal" in diagnostics
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["build_state"] == "succeeded" and saved["image_id"] == IMAGE_ID
    assert saved[f"{operation}_state"] == "unknown"
    assert saved["complete"] is False and snapshot.exists()
    state["discovered"] = []
    with pytest.raises(RuntimeError, match="completion unknown"):
        module.cleanup_devcontainer_manifest(path)
    assert json.loads(path.read_text(encoding="utf-8"))["runs"][0]["complete"] is False
    assert not any(
        cmd[:2] in (["podman", "rm"], ["podman", "untag"]) for cmd, _ in state["calls"]
    )


@pytest.mark.parametrize("mutation", ["label", "id", "image"])
def test_up_ownership_must_be_checked_before_operation_completion(
    runtime, tmp_path, monkeypatch, mutation
):
    module, snapshot, state = runtime
    path = tmp_path / "bad-up.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    if mutation == "label":
        state["foreign"] = True
    elif mutation == "id":
        state["container_inspected_id"] = "d" * 64
    else:
        state["container_image"] = "d" * 64
    with pytest.raises(RuntimeError), module.devcontainer_session():
        pytest.fail("foreign up receipt must not yield")
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["up_state"] == "unknown" and saved["container_ids"] == []
    assert saved["complete"] is False and snapshot.exists()


@pytest.fixture
def sync_caller(runtime, monkeypatch):
    module, _snapshot, _state = runtime
    monkeypatch.setitem(sys.modules, "test_just_sandbox", module)
    spec = importlib.util.spec_from_file_location(
        "sync_resource_under_test", ROOT / "tests/test_sync_agents.py"
    )
    assert spec and spec.loader
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    monkeypatch.setattr(sync, "ROOT", module.ROOT)
    monkeypatch.setattr(sync, "_copy_tracked_into", lambda *args: None)
    return sync


@pytest.mark.parametrize("consumer", ["saved", "sandbox", "sync"])
@pytest.mark.parametrize(
    "failure", ["nonzero", "exception", "missing", "invalid", "foreign"]
)
def test_actual_oneshot_create_ambiguity_cannot_be_cleared_by_empty_lookup(
    runtime, sync_caller, tmp_path, monkeypatch, consumer, failure
):
    module, snapshot, state = runtime
    path = tmp_path / "oneshot.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    original = module._run

    def process(cmd, **kwargs):
        if cmd[:2] in (["podman", "run"], ["podman", "create"]):
            state["run_id"] = cmd[cmd.index("--label") + 1].split("=", 1)[1]
            state["foreign"] = failure == "foreign"
            if failure == "exception":
                raise OSError("controlled create transport loss")
            return subprocess.CompletedProcess(
                cmd,
                125 if failure == "nonzero" else 0,
                CONTAINER_ID
                if failure == "foreign"
                else ("short" if failure == "invalid" else ""),
                "transport error",
            )
        return original(cmd, **kwargs)

    monkeypatch.setattr(module, "_run", process)
    monkeypatch.setattr(sync_caller, "_run", process)
    monkeypatch.setattr(sync_caller, "_SANDBOX_REPO", str(snapshot))
    with pytest.raises(RuntimeError):
        if consumer == "saved":
            module.run_saved_image(IMAGE_ID, "true")
        elif consumer == "sandbox":
            module.run_in_sandbox(IMAGE_ID, "true")
        else:
            sync_caller._run_in_container(IMAGE_ID, "true", check=False)
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["create_state"] == "unknown" and saved["complete"] is False
    assert snapshot.exists()
    with pytest.raises(RuntimeError, match="completion unknown"):
        module.cleanup_devcontainer_manifest(path)
    assert not any(cmd[:2] == ["podman", "start"] for cmd, _ in state["calls"])


@pytest.mark.parametrize("consumer", ["sandbox", "sync"])
@pytest.mark.parametrize("failure", ["query", "remove", "persist", "create"])
def test_oneshot_captured_snapshot_retained_on_unacknowledged_cleanup(
    runtime, sync_caller, tmp_path, monkeypatch, consumer, failure
):
    module, snapshot, state = runtime
    path = tmp_path / "retained.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    original = module._run
    replace = Path.replace

    def persist(source, target):
        if (
            failure == "persist"
            and json.loads(source.read_text(encoding="utf-8"))["runs"][-1]["complete"]
        ):
            raise OSError("controlled persist failure")
        return replace(source, target)

    def process(cmd, **kwargs):
        if cmd[:2] in (["podman", "run"], ["podman", "create"]):
            state["run_id"] = cmd[cmd.index("--label") + 1].split("=", 1)[1]
            return subprocess.CompletedProcess(
                cmd,
                125 if failure == "create" else 0,
                "" if failure == "create" else CONTAINER_ID,
                "",
            )
        if cmd[:2] == ["podman", "ps"] and failure == "query":
            return subprocess.CompletedProcess(cmd, 125, "", "query failure")
        if cmd[:2] == ["podman", "rm"] and failure == "remove":
            return subprocess.CompletedProcess(cmd, 125, "", "remove failure")
        return original(cmd, **kwargs)

    monkeypatch.setattr(module, "_run", process)
    monkeypatch.setattr(sync_caller, "_run", process)
    monkeypatch.setattr(Path, "replace", persist)
    fixture = None
    if consumer == "sync":
        monkeypatch.setattr(
            sync_caller.tempfile, "mkdtemp", lambda **kwargs: str(snapshot)
        )
        fixture = sync_caller.sandbox_repo.__wrapped__()
        next(fixture)
    with pytest.raises((RuntimeError, OSError)):
        if consumer == "sandbox":
            module.run_in_sandbox(IMAGE_ID, "true")
        else:
            sync_caller._run_in_container(IMAGE_ID, "true", check=False)
    if fixture:
        with pytest.raises(StopIteration):
            next(fixture)
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is False
    assert snapshot.exists()


@pytest.mark.parametrize("consumer", ["saved", "sandbox", "sync"])
@pytest.mark.parametrize("returncode", [0, 1, 42, 125, -15, 130, 137, 143])
def test_checked_oneshot_preserves_application_status_and_exact_cleanup(
    runtime, sync_caller, tmp_path, monkeypatch, consumer, returncode
):
    module, snapshot, state = runtime
    path = tmp_path / "application.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    state["start_returncode"] = returncode
    fixture = None
    if consumer == "saved":
        result = module.run_saved_image(IMAGE_ID, "exit 42", offline=True)
    elif consumer == "sandbox":
        result = module.run_in_sandbox(IMAGE_ID, "exit 42")
    else:
        monkeypatch.setattr(
            sync_caller.tempfile, "mkdtemp", lambda **kwargs: str(snapshot)
        )
        fixture = sync_caller.sandbox_repo.__wrapped__()
        next(fixture)
        result = sync_caller._run_in_container(IMAGE_ID, "exit 42", check=False)
    assert result.returncode == returncode
    assert result.stdout == "controlled application stdout"
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["create_state"] == "completed" and saved["complete"] is True
    assert saved["container_ids"] == [CONTAINER_ID]
    assert ["podman", "rm", "-f", CONTAINER_ID] in [cmd for cmd, _ in state["calls"]]
    creates = [cmd for cmd, _ in state["calls"] if cmd[:2] == ["podman", "create"]]
    assert len(creates) == 1 and "--rm" in creates[0]
    if consumer == "saved":
        assert creates[0][creates[0].index("--network") + 1] == "none"
        assert snapshot.exists()  # this caller never owned a snapshot
    elif consumer == "sandbox":
        assert not snapshot.exists()
    else:
        assert snapshot.exists()  # shared fixture survives until all test calls finish
        assert fixture is not None
        with pytest.raises(StopIteration):
            next(fixture)
        assert not snapshot.exists()


def test_sync_check_true_preserves_intentional_application_failure(
    runtime, sync_caller, monkeypatch
):
    module, snapshot, state = runtime
    monkeypatch.setattr(sync_caller, "_SANDBOX_REPO", str(snapshot))
    state["start_returncode"] = 42
    with pytest.raises(pytest.fail.Exception, match="exit code 42"):
        sync_caller._run_in_container(IMAGE_ID, "exit 42")
    path = module.ROOT / ".pi/tasks" / f"devcontainer-{state['run_id']}.json"
    assert json.loads(path.read_text(encoding="utf-8"))["runs"][0]["complete"] is True
    assert not sync_caller._SANDBOX_PENDING_RUNS


@pytest.mark.parametrize(
    "exception", [OSError("start transport"), KeyboardInterrupt("start signal")]
)
def test_start_exception_does_not_erase_known_creation_or_skip_exact_cleanup(
    runtime, exception
):
    module, snapshot, state = runtime
    state["start_exception"] = exception
    with pytest.raises(type(exception)):
        module.run_saved_image(IMAGE_ID, "true")
    path = module.ROOT / ".pi/tasks" / f"devcontainer-{state['run_id']}.json"
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["create_state"] == "completed" and saved["complete"] is True
    assert ["podman", "rm", "-f", CONTAINER_ID] in [cmd for cmd, _ in state["calls"]]
    assert snapshot.exists()


def test_known_lifecycle_body_failure_is_not_unknown_creation(runtime):
    module, snapshot, state = runtime
    with (
        pytest.raises(AssertionError, match="controlled body"),
        module.devcontainer_session(),
    ):
        raise AssertionError("controlled body")
    path = module.ROOT / ".pi/tasks" / f"devcontainer-{state['run_id']}.json"
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["up_state"] == saved["exec_state"] == "completed"
    assert saved["complete"] is True and not snapshot.exists()


@pytest.mark.parametrize("consumer", ["saved", "sandbox", "sync"])
@pytest.mark.parametrize("acknowledgment", ["not-found", "rm-success", "identity-only"])
def test_failed_start_requires_exact_removal_ack_not_identity_alone(
    runtime, sync_caller, tmp_path, monkeypatch, consumer, acknowledgment
):
    module, snapshot, state = runtime
    path = tmp_path / "start-ack.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    monkeypatch.setattr(sync_caller, "_SANDBOX_REPO", str(snapshot))
    state["start_returncode"] = 125
    original = module._run

    def process(cmd, **kwargs):
        if cmd[:2] == ["podman", "rm"] and acknowledgment != "rm-success":
            state["container_missing"] = acknowledgment == "not-found"
            return subprocess.CompletedProcess(cmd, 125, "", "ambiguous rm")
        return original(cmd, **kwargs)

    monkeypatch.setattr(module, "_run", process)

    def invoke():
        if consumer == "saved":
            return module.run_saved_image(IMAGE_ID, "true")
        if consumer == "sandbox":
            return module.run_in_sandbox(IMAGE_ID, "true")
        return sync_caller._run_in_container(IMAGE_ID, "true", check=False)

    if acknowledgment == "identity-only":
        with pytest.raises(RuntimeError, match="removal unacknowledged"):
            invoke()
        assert snapshot.exists()
    else:
        assert invoke().returncode == 125
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["create_state"] == "completed"
    assert saved["complete"] is (acknowledgment != "identity-only")


@pytest.mark.parametrize("operation", ["up", "exec", "create"])
@pytest.mark.parametrize(
    "status", ["pending", "unknown", "invalid", "missing", "unknown-complete"]
)
def test_strict_operation_recovery_cannot_bless_unknown_or_missing_evidence(
    runtime, tmp_path, operation, status
):
    module, snapshot, state = runtime
    path, record = _recovery_record(
        module, state, tmp_path, image_id=IMAGE_ID, container_ids=[CONTAINER_ID]
    )
    if operation == "create":
        record.update(
            tag=None, tag_was_absent=False, image_id=None, build_state="not-started"
        )
    elif operation == "exec":
        record["up_state"] = "completed"
    if status == "missing":
        record.pop(f"{operation}_state")
    else:
        record[f"{operation}_state"] = (
            "unknown" if status == "unknown-complete" else status
        )
    if status == "unknown-complete":
        record["complete"] = True
    path.write_text(json.dumps({"version": 4, "runs": [record]}), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(RuntimeError):
        module.cleanup_devcontainer_manifest(path)
    assert path.read_bytes() == before and snapshot.exists()
    if status in {"missing", "invalid", "unknown-complete"}:
        assert state["calls"] == []
    assert not any(
        cmd[:2] in (["podman", "rm"], ["podman", "untag"]) for cmd, _ in state["calls"]
    )


@pytest.mark.parametrize("legacy_complete", [False, True])
def test_version3_without_operation_receipts_is_rejected_before_engine_access(
    runtime, tmp_path, legacy_complete
):
    module, _, state = runtime
    path, record = _recovery_record(module, state, tmp_path)
    for key in ("up_state", "exec_state", "create_state"):
        record.pop(key)
    record["complete"] = legacy_complete
    path.write_text(json.dumps({"version": 3, "runs": [record]}), encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(RuntimeError, match="version"):
        module.cleanup_devcontainer_manifest(path)
    assert path.read_bytes() == before and state["calls"] == []


@pytest.mark.parametrize("consumer", ["sandbox", "sync"])
def test_oneshot_only_deletes_creator_captured_context_after_durable_ack(
    runtime, sync_caller, tmp_path, monkeypatch, consumer
):
    module, snapshot, _state = runtime
    victim = tmp_path / "foreign"
    victim.mkdir()
    (victim / "sentinel").write_text("keep", encoding="utf-8")
    original = module._journal_record
    snapshots_at_ack = []

    def diagnostic_only(record, path=None):
        record["snapshot_path"] = str(victim)
        if record["complete"]:
            snapshots_at_ack.append(snapshot.exists())
        original(record, path)

    monkeypatch.setattr(module, "_journal_record", diagnostic_only)
    fixture = None
    if consumer == "sandbox":
        module.run_in_sandbox(IMAGE_ID, "true")
    else:
        monkeypatch.setattr(
            sync_caller.tempfile, "mkdtemp", lambda **kwargs: str(snapshot)
        )
        fixture = sync_caller.sandbox_repo.__wrapped__()
        next(fixture)
        sync_caller._run_in_container(IMAGE_ID, "true", check=False)
        with pytest.raises(StopIteration):
            next(fixture)
    assert snapshots_at_ack == [True]
    assert not snapshot.exists()
    assert (victim / "sentinel").read_text(encoding="utf-8") == "keep"


def test_sync_fixture_remembers_earlier_incomplete_run_after_later_success(
    runtime, sync_caller, tmp_path, monkeypatch
):
    module, snapshot, _state = runtime
    monkeypatch.setattr(sync_caller.tempfile, "mkdtemp", lambda **kwargs: str(snapshot))
    fixture = sync_caller.sandbox_repo.__wrapped__()
    next(fixture)
    original = module._run

    def process(cmd, **kwargs):
        if cmd[:2] == ["podman", "create"]:
            return subprocess.CompletedProcess(cmd, 125, "", "create lost")
        return original(cmd, **kwargs)

    monkeypatch.setattr(module, "_run", process)
    with pytest.raises(RuntimeError, match="completion unknown"):
        sync_caller._run_in_container(IMAGE_ID, "true", check=False)
    monkeypatch.setattr(module, "_run", original)
    assert sync_caller._run_in_container(IMAGE_ID, "true").returncode == 0
    with pytest.raises(StopIteration):
        next(fixture)
    assert snapshot.exists()
    journals = list((module.ROOT / ".pi/tasks").glob("*.json"))
    assert sorted(
        json.loads(path.read_text(encoding="utf-8"))["runs"][0]["complete"]
        for path in journals
    ) == [False, True]


@pytest.mark.parametrize("operation", ["up", "exec", "create"])
@pytest.mark.parametrize(
    "failure_point", ["intent", "ownership", "completion", "unknown"]
)
def test_operation_journal_write_failure_retains_context_and_blocks_later_calls(
    runtime, tmp_path, monkeypatch, operation, failure_point
):
    module, snapshot, state = runtime
    path = tmp_path / "write-operation.json"
    monkeypatch.setenv("DOTFILES_DEVCONTAINER_MANIFEST", str(path))
    replace = Path.replace
    original = module._run

    def persist(source, target):
        pending = json.loads(source.read_text(encoding="utf-8"))["runs"][-1]
        status = pending[f"{operation}_state"]
        if (
            (
                failure_point == "intent"
                and status == "pending"
                and (operation != "create" or not pending["container_ids"])
            )
            or (
                failure_point == "ownership"
                and operation != "exec"
                and status == "pending"
                and pending["container_ids"]
            )
            or (
                failure_point == "ownership"
                and operation == "exec"
                and status == "completed"
            )
            or (failure_point == "completion" and status == "completed")
            or (failure_point == "unknown" and status == "unknown")
        ):
            raise OSError("controlled operation journal failure")
        return replace(source, target)

    def process(cmd, **kwargs):
        if failure_point == "unknown" and cmd[:2] == (
            ["podman", "create"]
            if operation == "create"
            else ["devcontainer", operation]
        ):
            return subprocess.CompletedProcess(
                cmd, 125, "original receipt error", "transport"
            )
        return original(cmd, **kwargs)

    monkeypatch.setattr(Path, "replace", persist)
    monkeypatch.setattr(module, "_run", process)
    with pytest.raises((RuntimeError, OSError)):
        if operation == "create":
            module.run_in_sandbox(IMAGE_ID, "true")
        else:
            with module.devcontainer_session():
                pytest.fail("unpersisted operation must not yield")
    saved = json.loads(path.read_text(encoding="utf-8"))["runs"][0]
    assert saved["complete"] is False and snapshot.exists()
    assert saved["snapshot_path"] == str(snapshot)
    assert not any(
        cmd[:2] in (["podman", "rm"], ["podman", "untag"], ["podman", "start"])
        for cmd, _ in state["calls"]
    )
    if failure_point == "intent":
        assert not any(
            cmd[:2]
            == (
                ["podman", "create"]
                if operation == "create"
                else ["devcontainer", operation]
            )
            for cmd, _ in state["calls"]
        )


@pytest.mark.parametrize(
    "journal", [{"version": 3, "runs": []}, {"version": 4, "runs": [{}]}]
)
def test_cleanup_cli_keeps_nonzero_eof_status_for_invalid_manifest(tmp_path, journal):
    manifest = tmp_path / "invalid.json"
    manifest.write_text(json.dumps(journal), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tests/test_just_sandbox.py"),
            "--cleanup-manifest",
            str(manifest),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode != 0
    assert "RuntimeError" in result.stderr
    assert json.loads(manifest.read_text(encoding="utf-8")) == journal


@pytest.mark.parametrize("colon_path", [False, True])
def test_hermetic_mount_callers_preserve_ambient_journal(
    tmp_path, monkeypatch, colon_path
):
    """The actual callers preserve outer journals and colon-bearing source paths."""
    manifest = tmp_path / "ambient.json"
    original = b'{"version": 4, "runs": []}\n'
    manifest.write_bytes(original)
    report = tmp_path / "two-callers.xml"
    names = {
        "test_run_in_sandbox_local_mounts_snapshot_not_host",
        "test_run_in_sandbox_ci_binds_host_path",
    }
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k must_not_deselect_the_callers")
    # Windows drive paths already contain a colon; do not create an illegal name.
    name = "drive:temp" if colon_path and os.name != "nt" else "child-temp"
    child_temp = tmp_path / name
    child_temp.mkdir()
    env = dict(
        os.environ,
        DOTFILES_DEVCONTAINER_MANIFEST=str(manifest),
        TMPDIR=str(child_temp),
        TEMP=str(child_temp),
        TMP=str(child_temp),
    )
    env.pop("PYTEST_ADDOPTS", None)
    env.pop("PYTEST_CURRENT_TEST", None)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-o",
            "addopts=",
            f"--junitxml={report}",
            *[f"tests/test_just_sandbox.py::{name}" for name in sorted(names)],
        ],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    cases = ET.parse(report).getroot().findall(".//testcase")
    assert len(cases) == 2
    assert {case.attrib["name"] for case in cases} == names
    assert all(
        case.find(tag) is None
        for case in cases
        for tag in ("failure", "error", "skipped")
    )
    assert manifest.read_bytes() == original
