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
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# Named here, not imported, so the behavioural tests below fail on real
# behaviour (the sandbox reaching docker with the real repo) rather than on a
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
    sandbox: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI keeps today's behaviour: the host checkout is bind-mounted as is."""
    # given
    monkeypatch.setenv("LOCAL_WORKSPACE_FOLDER", "/work/ci-checkout")
    monkeypatch.setenv(DISPOSABLE_CHECKOUT_ENV, "1")
    captured: dict[str, list[str]] = {}

    def _fake_run(cmd: list[str] | str, **kwargs: object) -> object:
        assert isinstance(cmd, list)
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(sandbox, "_run", _fake_run)

    def _boom(_src: str) -> str:
        raise AssertionError("must not snapshot when CI binds the checkout")

    monkeypatch.setattr(sandbox, "_snapshot_tracked_worktree", _boom)

    # when
    sandbox.run_in_sandbox("img", "echo hi")

    # then
    cmd = captured["cmd"]
    assert cmd[cmd.index("-v") + 1] == "/work/ci-checkout:/root/dotfiles"


def test_ci_workflow_declares_the_disposable_checkout() -> None:
    """The fence is fail-closed, so CI must declare its checkout disposable.

    Without this line in the workflow's `env:` block, every sandbox test in CI
    refuses instead of binding the runner checkout.
    """
    workflow = _WORKFLOW.read_text(encoding="utf-8")
    assert f"{DISPOSABLE_CHECKOUT_ENV}=1" in workflow
