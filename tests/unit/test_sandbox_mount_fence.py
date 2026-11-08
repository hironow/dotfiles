"""The sandbox must never git-init the operator's real checkout.

`tests/test_just_sandbox.py` prefixes nearly every sandbox script with
`_GIT_INIT`, which runs `git init`, OVERWRITES `.git/info/exclude` and
`git add -A` in whatever `run_in_sandbox` mounted at /root/dotfiles. That is
only safe on a disposable copy.

`LOCAL_WORKSPACE_FOLDER` alone does not prove the mount source is disposable:
`.devcontainer/devcontainer.json` exports it inside the dev container as well,
so `just test` run from a dev container on a developer machine would point it
at the real working repo and clobber its `.git/info/exclude` (which carries the
`skills/` glob) plus stage the whole tree. These tests pin the fence that stops
that, and they need no Docker.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# Named here, not imported, so the behavioural tests below fail on real
# behaviour (the sandbox reaching the engine with the real repo) rather than on a
# missing attribute. `test_module_and_fence_agree_on_the_env_name` pins the two
# spellings together.
DISPOSABLE_CHECKOUT_ENV = "DOTFILES_SANDBOX_DISPOSABLE_CHECKOUT"

ROOT = Path(__file__).resolve().parents[2]
_SANDBOX_TESTS = ROOT / "tests" / "test_just_sandbox.py"
_WORKFLOW = ROOT / ".github" / "workflows" / "test-just.yaml"


def _load_sandbox_module() -> Any:
    """Import tests/test_just_sandbox.py as a plain module.

    Loaded under its own name so pytest's own collection of that file (during
    `just test`) is untouched. Module level is imports plus string constants,
    so this is cheap and has no side effects.
    """
    spec = importlib.util.spec_from_file_location(
        "just_sandbox_under_test", _SANDBOX_TESTS
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def sandbox() -> Any:
    return _load_sandbox_module()


def test_module_and_fence_agree_on_the_env_name(sandbox: Any) -> None:
    """The sandbox module, the CI workflow and these tests share one spelling."""
    assert sandbox.DISPOSABLE_CHECKOUT_ENV == DISPOSABLE_CHECKOUT_ENV


def test_no_local_workspace_folder_means_snapshot(sandbox: Any) -> None:
    """A plain host run has no LOCAL_WORKSPACE_FOLDER: mount a snapshot."""
    assert sandbox._mount_mode({}) == "snapshot"


def test_ci_declaring_a_disposable_checkout_may_bind(sandbox: Any) -> None:
    """CI's checkout is thrown away after the job, so binding it is fine."""
    env = {
        "LOCAL_WORKSPACE_FOLDER": "/home/runner/work/dotfiles/dotfiles",
        DISPOSABLE_CHECKOUT_ENV: "1",
    }
    assert sandbox._mount_mode(env) == "bind"


def test_dev_container_on_a_real_checkout_is_refused(sandbox: Any) -> None:
    """LOCAL_WORKSPACE_FOLDER without CI's declaration = a real working repo."""
    env = {"LOCAL_WORKSPACE_FOLDER": "/home/dev/dotfiles"}
    with pytest.raises(RuntimeError) as excinfo:
        sandbox._mount_mode(env)
    message = str(excinfo.value)
    assert "/home/dev/dotfiles" in message
    assert DISPOSABLE_CHECKOUT_ENV in message


def test_unset_or_falsey_declaration_is_refused(sandbox: Any) -> None:
    """Only an exact "1" counts; a typo must fail loudly, not bind."""
    for value in ("", "0", "false", "true", "yes"):
        env = {
            "LOCAL_WORKSPACE_FOLDER": "/home/dev/dotfiles",
            DISPOSABLE_CHECKOUT_ENV: value,
        }
        with pytest.raises(RuntimeError):
            sandbox._mount_mode(env)


def test_run_in_sandbox_refuses_before_reaching_docker(
    sandbox: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal happens before any container touches the real checkout."""
    # given: a dev container pointed at the operator's own repo
    monkeypatch.setenv("LOCAL_WORKSPACE_FOLDER", "/home/dev/dotfiles")
    monkeypatch.delenv(DISPOSABLE_CHECKOUT_ENV, raising=False)

    def _no_docker(cmd: list[str] | str, **kwargs: object) -> object:
        raise AssertionError(f"must not run anything: {cmd!r}")

    monkeypatch.setattr(sandbox, "_run", _no_docker)
    monkeypatch.setattr(sandbox, "_snapshot_tracked_worktree", _no_docker)

    # when / then
    with pytest.raises(RuntimeError):
        sandbox.run_in_sandbox("img", "echo hi")


def test_run_in_sandbox_binds_the_declared_ci_checkout(
    sandbox: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CI keeps today's behaviour: the host checkout is bind-mounted as is."""
    # given
    monkeypatch.setattr(sandbox, "ROOT", tmp_path)
    monkeypatch.setenv("LOCAL_WORKSPACE_FOLDER", "/work/ci-checkout")
    monkeypatch.setenv(
        "DOTFILES_PODMAN_ENGINE_SOCKET", "/run/user/123/podman/podman.sock"
    )
    monkeypatch.setenv(DISPOSABLE_CHECKOUT_ENV, "1")
    captured: dict[str, list[str]] = {}

    def _fake_run(cmd: list[str] | str, **kwargs: object) -> object:
        assert isinstance(cmd, list)
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
                    [
                        {
                            "Id": "b" * 64,
                            "Config": {"Labels": {sandbox.RUN_LABEL: run_id}},
                        }
                    ]
                ),
                "",
            )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sandbox, "_run", _fake_run)
    monkeypatch.setattr(
        sandbox,
        "_selected_engine_identity",
        lambda: {
            "hostname": "test",
            "graph_root": "/test",
            "socket": "/run/test",
            "endpoint": "native-local",
        },
    )

    def _boom(_src: str) -> str:
        raise AssertionError("must not snapshot when CI binds the checkout")

    monkeypatch.setattr(sandbox, "_snapshot_tracked_worktree", _boom)

    # when
    sandbox.run_in_sandbox("img", "echo hi")

    # then
    cmd = captured["cmd"]
    assert cmd[cmd.index("-v") + 1] == "/work/ci-checkout:/root/dotfiles"


@pytest.mark.parametrize(
    "link_kind", ["directory", "external", "internal", "git", "dangling"]
)
def test_snapshot_rejects_tracked_symlinks_before_copy_or_launch(
    sandbox, tmp_path, monkeypatch, link_kind
):
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "data/file").write_text("tracked", encoding="utf-8")
    (repo / "aaa-first").write_text("first", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    external = tmp_path / "external"
    external.mkdir()
    (external / "file").write_text("external sentinel", encoding="utf-8")
    target = repo / "data" if link_kind == "directory" else repo / "data/file"
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    destination = {
        "directory": external,
        "external": external / "file",
        "internal": repo / "aaa-first",
        "git": repo / ".git/config",
        "dangling": tmp_path / "absent",
    }[link_kind]
    try:
        target.symlink_to(destination, target_is_directory=link_kind == "directory")
    except OSError as error:
        pytest.skip(f"symlink privilege unavailable: {error}")
    monkeypatch.setattr(sandbox, "ROOT", repo)
    monkeypatch.delenv("LOCAL_WORKSPACE_FOLDER", raising=False)
    copied = []
    monkeypatch.setattr(
        sandbox.shutil, "copyfileobj", lambda *args: copied.append(args)
    )
    monkeypatch.setattr(sandbox, "_run", lambda *a, **k: pytest.fail("must not launch"))
    with pytest.raises(RuntimeError, match="symlink"):
        sandbox._snapshot_tracked_worktree(str(repo))
    with pytest.raises(RuntimeError, match="symlink"):
        sandbox.run_in_sandbox("unused", "true")
    assert copied == []
    assert not list(tmp_path.glob(".dotfiles-sandbox-*"))


def test_snapshot_preserves_working_and_staged_bytes_not_untracked(
    sandbox, tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    (repo / "tracked").write_text("index", encoding="utf-8")
    (repo / "staged-only").write_text("staged", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    (repo / "tracked").write_text("working", encoding="utf-8")
    (repo / ".pi").mkdir()
    (repo / ".pi/secret").write_text("excluded", encoding="utf-8")
    monkeypatch.setattr(sandbox, "ROOT", repo)
    snapshot = Path(sandbox._snapshot_tracked_worktree(str(repo)))
    try:
        assert (snapshot / "tracked").read_text(encoding="utf-8") == "working"
        assert (snapshot / "staged-only").read_text(encoding="utf-8") == "staged"
        assert not (snapshot / ".pi").exists()
        assert not (snapshot / ".git").exists()
    finally:
        shutil.rmtree(snapshot)


@pytest.mark.parametrize("substitution", ["directory", "fifo"])
def test_snapshot_rejects_nonregular_substitution(
    sandbox, tmp_path, monkeypatch, substitution
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    (repo / "file").unlink()
    if substitution == "directory":
        (repo / "file").mkdir()
    else:
        import os

        if not hasattr(os, "mkfifo"):
            pytest.skip("FIFO substitution is POSIX-only")
        os.mkfifo(repo / "file")
    monkeypatch.setattr(sandbox, "ROOT", repo)
    with pytest.raises(RuntimeError, match="nonregular"):
        sandbox._snapshot_tracked_worktree(str(repo))
    assert not list(tmp_path.glob(".dotfiles-sandbox-*"))


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "/absolute",
        ".git/config",
        "data/.GiT/config",
        "data/../file",
        "data//file",
        "C:escape",
        r"data\file",
    ],
)
def test_snapshot_validates_git_names_before_read(sandbox, tmp_path, monkeypatch, name):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(sandbox, "ROOT", repo)
    monkeypatch.setattr(
        sandbox.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            [], 0, f"100644 {'a' * 40} 0\t{name}\0".encode()
        ),
    )
    with pytest.raises(RuntimeError, match="tracked name"):
        sandbox._snapshot_tracked_worktree(str(repo))
    assert not list(tmp_path.glob(".dotfiles-sandbox-*"))


@pytest.mark.parametrize("link_root", [True, False])
def test_snapshot_rejects_source_root_or_ancestor_symlink(
    sandbox, tmp_path, monkeypatch, link_root
):
    real = tmp_path / "real"
    repo = real / "repo"
    repo.mkdir(parents=True)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(repo if link_root else real, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink privilege unavailable: {error}")
    monkeypatch.setattr(sandbox, "ROOT", repo)
    with pytest.raises(RuntimeError, match="snapshot root ancestor"):
        sandbox._snapshot_tracked_worktree(str(alias if link_root else alias / "repo"))
    assert not list(real.glob(".dotfiles-sandbox-*"))


def test_snapshot_removes_partial_copy_on_read_failure(sandbox, tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file").write_text("tracked", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    monkeypatch.setattr(sandbox, "ROOT", repo)

    def interrupted(*args):
        raise OSError("injected read failure")

    monkeypatch.setattr(sandbox.shutil, "copyfileobj", interrupted)
    with pytest.raises(OSError, match="injected read failure"):
        sandbox._snapshot_tracked_worktree(str(repo))
    assert not list(tmp_path.glob(".dotfiles-sandbox-*"))


@pytest.mark.parametrize("anchored", [True, False])
def test_snapshot_omits_vanished_and_gitlinks_with_portable_reads(
    sandbox, tmp_path, monkeypatch, anchored
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "file").write_text("working", encoding="utf-8")
    (repo / "vanished").write_text("gone", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{'a' * 40},module",
        ],
        check=True,
        capture_output=True,
    )
    (repo / "module").mkdir()
    (repo / "module/secret").write_text("excluded", encoding="utf-8")
    (repo / "vanished").unlink()
    monkeypatch.setattr(sandbox, "ROOT", repo)
    if not anchored:
        monkeypatch.setattr(sandbox.os, "supports_dir_fd", set())
    snapshot = Path(sandbox._snapshot_tracked_worktree(str(repo)))
    try:
        assert (snapshot / "file").read_text(encoding="utf-8") == "working"
        assert not (snapshot / "vanished").exists()
        assert not (snapshot / "module").exists()
    finally:
        shutil.rmtree(snapshot)


def test_ci_workflow_declares_the_disposable_checkout() -> None:
    """The fence is fail-closed, so CI must declare its checkout disposable.

    Without this line in the workflow's `env:` block, every sandbox test in CI
    refuses instead of binding the runner checkout.
    """
    workflow = _WORKFLOW.read_text(encoding="utf-8")
    assert f"{DISPOSABLE_CHECKOUT_ENV}=1" in workflow


def test_actual_sync_copy_rejects_internal_untracked_ancestor_before_copy(
    sandbox, tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "test_just_sandbox", sandbox)
    spec = importlib.util.spec_from_file_location(
        "sync_copy_under_test", ROOT / "tests/test_sync_agents.py"
    )
    assert spec and spec.loader
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    repo = tmp_path / "repo"
    (repo / "nested").mkdir(parents=True)
    (repo / "nested/file").write_text("tracked", encoding="utf-8")
    (repo / "aaa").write_text("first", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    (repo / "untracked").mkdir()
    sentinel = repo / "untracked/file"
    sentinel.write_text("INTERNAL UNTRACKED SENTINEL", encoding="utf-8")
    shutil.rmtree(repo / "nested")
    (repo / "nested").symlink_to(repo / "untracked", target_is_directory=True)
    destination = tmp_path / "copy"
    destination.mkdir()
    with pytest.raises(RuntimeError, match="symlink"):
        sync._copy_tracked_into(str(repo), str(destination))
    assert list(destination.iterdir()) == []
    assert sentinel.read_text(encoding="utf-8") == "INTERNAL UNTRACKED SENTINEL"


def test_actual_sync_copy_preserves_working_bytes_and_omits_untracked_gitlinks(
    sandbox, tmp_path, monkeypatch
):
    monkeypatch.setitem(sys.modules, "test_just_sandbox", sandbox)
    spec = importlib.util.spec_from_file_location(
        "sync_copy_positive", ROOT / "tests/test_sync_agents.py"
    )
    assert spec and spec.loader
    sync = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sync)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "working").write_text("index", encoding="utf-8")
    (repo / "vanished").write_text("gone", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "add", "."], check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "update-index",
            "--add",
            "--cacheinfo",
            f"160000,{'a' * 40},module",
        ],
        check=True,
        capture_output=True,
    )
    (repo / "working").write_text("current bytes", encoding="utf-8")
    (repo / "vanished").unlink()
    (repo / "module").mkdir()
    (repo / "module/untracked").write_text("secret", encoding="utf-8")
    (repo / "secret").write_text("secret", encoding="utf-8")
    destination = tmp_path / "copy"
    destination.mkdir()
    sync._copy_tracked_into(str(repo), str(destination))
    assert [path.name for path in destination.iterdir()] == ["working"]
    assert (destination / "working").read_text(encoding="utf-8") == "current bytes"
