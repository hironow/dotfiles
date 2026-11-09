"""Podman devcontainer/Cursor transport contract; no engine calls."""

import importlib.util
import json
import os
import re
import shlex
import shutil
from pathlib import Path

import pytest
from _bash_hook import bash_path, run_bash

ROOT = Path(__file__).resolve().parents[2]


def config():
    text = (ROOT / ".devcontainer/devcontainer.json").read_text(encoding="utf-8")
    return json.loads(re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE))


def test_official_trixie_and_only_docker_feature_lock_removed():
    current = config()
    assert current["image"] == "mcr.microsoft.com/devcontainers/base:trixie"
    assert (
        "ghcr.io/devcontainers/features/docker-outside-of-docker:1"
        not in current["features"]
    )
    lock = json.loads(
        (ROOT / ".devcontainer/devcontainer-lock.json").read_text(encoding="utf-8")
    )
    assert set(lock["features"]) == {
        key for key in current["features"] if not key.startswith("./")
    }
    assert current["remoteUser"] == current["containerUser"] == "root"
    assert (
        current["containerEnv"]["MISE_TRUSTED_CONFIG_PATHS"]
        == "/root/dotfiles:/root/sandbox/dotfiles-fresh"
    )


def test_engine_socket_is_explicit_and_not_host_forwarding():
    current = config()
    assert current["mounts"] == [
        "source=${localEnv:DOTFILES_PODMAN_ENGINE_SOCKET},target=/run/dotfiles-podman/podman.sock,type=bind"
    ]
    assert (
        current["containerEnv"]["CONTAINER_HOST"]
        == "unix:///run/dotfiles-podman/podman.sock"
    )
    assert current["containerEnv"]["PODMAN_COMPOSE_PROVIDER"] == "podman-compose"
    # Application-scoped host selection cannot come from remote customizations.
    assert (
        "dev.containers.dockerPath"
        not in current["customizations"]["vscode"]["settings"]
    )
    assert "require-podman-socket.sh" in current["initializeCommand"]


def test_ide_engine_selection_requires_host_application_user_setting():
    instructions = (ROOT / ".devcontainer/README.md").read_text(encoding="utf-8")
    assert "host application User setting" in instructions
    assert "before **Reopen in Container**" in instructions
    examples = re.findall(r"```json\n(.*?)\n```", instructions, re.DOTALL)
    assert any(
        json.loads(example).get("dev.containers.dockerPath") == "podman"
        for example in examples
    )
    assert "cannot select the host engine" in instructions
    assert "does not enforce or verify" in instructions


def test_feature_installs_native_podman_without_changing_generated_versions():
    body = (ROOT / ".devcontainer/features/dotfiles-tools/install.sh").read_text(
        encoding="utf-8"
    )
    assert "podman uidmap" in body
    assert "podman --version" in body
    assert "Podman >=5" in body


def test_cursor_never_sets_up_docker_or_world_writable_sockets():
    install = (ROOT / ".cursor/install.sh").read_text(encoding="utf-8")
    start = (ROOT / ".cursor/start.sh").read_text(encoding="utf-8")
    for forbidden in (
        "docker.io",
        "dockerd",
        "daemon.json",
        "chmod 666",
        "usermod -aG docker",
    ):
        assert forbidden not in install + start
    assert "--podman-only" in install
    assert "fuse-overlayfs" in install
    assert "podman.socket" in start
    assert "sudo podman" not in start


def test_missing_engine_is_required_failure_not_skip(monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "podman_sandbox_config_test", ROOT / "tests/test_just_sandbox.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "_docker_available", lambda: False)
    # Existing fixture must fail, not turn a required runtime into a skip.
    with pytest.raises(pytest.fail.Exception):
        next(module.docker_image.__wrapped__())


@pytest.fixture
def selected_engine(tmp_path, monkeypatch):
    binary = tmp_path / "bin"
    binary.mkdir()
    jq = shutil.which("jq")
    assert jq, "canonical jq is required for hermetic initializer tests"
    (binary / "jq").write_text(
        "#!/bin/sh\nexec " + shlex.quote(bash_path(Path(jq))) + ' "$@"\n',
        encoding="utf-8",
    )
    (binary / "podman").write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$*" >> "$FAKE_CALLS"\n'
        'case "$1" in\n'
        ' --version) printf "podman version %s\\n" "$FAKE_CLIENT" ;;\n'
        ' info) [ "$FAKE_INFO" != failed ] || exit 125\n'
        ' [ "$FAKE_INFO" != malformed ] || { echo "not json"; exit 0; }\n'
        ' printf \'{"version":{"Version":"%s"},"host":{"remoteSocket":{"path":"%s"}}}\\n\' "$FAKE_SERVER" "$FAKE_SOCKET" ;;\n'
        " *) exit 99 ;;\nesac\n",
        encoding="utf-8",
    )
    for script in binary.iterdir():
        script.chmod(0o755)
    monkeypatch.setenv("PATH", bash_path(binary))
    monkeypatch.setenv("FAKE_CALLS", bash_path(tmp_path / "calls"))
    monkeypatch.setenv("FAKE_CLIENT", "6.1.4")
    monkeypatch.setenv("FAKE_SERVER", "5.6.2")
    monkeypatch.setenv("FAKE_SOCKET", "unix:///run/user/456/podman/podman.sock")
    monkeypatch.setenv("FAKE_INFO", "valid")
    monkeypatch.setenv(
        "DOTFILES_PODMAN_ENGINE_SOCKET", "/run/user/456/podman/podman.sock"
    )
    return binary


@pytest.mark.parametrize(
    "mutation",
    [
        "mismatch",
        "forwarded",
        "old-client",
        "old-server",
        "malformed",
        "failed",
        "missing-podman",
        "missing-jq",
        "missing-version",
        "missing-socket",
    ],
)
def test_initializer_rejects_unverified_selected_engine(
    selected_engine, tmp_path, monkeypatch, mutation
):
    changes = {
        "mismatch": ("DOTFILES_PODMAN_ENGINE_SOCKET", "/run/podman/podman.sock"),
        "forwarded": ("FAKE_SOCKET", "/var/folders/forwarded.sock"),
        "old-client": ("FAKE_CLIENT", "4.9.0"),
        "old-server": ("FAKE_SERVER", "4.9.0"),
        "malformed": ("FAKE_INFO", "malformed"),
        "failed": ("FAKE_INFO", "failed"),
        "missing-version": ("FAKE_SERVER", ""),
        "missing-socket": ("FAKE_SOCKET", ""),
    }
    if mutation in changes:
        monkeypatch.setenv(*changes[mutation])
    else:
        (selected_engine / mutation.removeprefix("missing-")).unlink()
    result = run_bash(
        ROOT / ".devcontainer/require-podman-socket.sh",
        cwd=tmp_path,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode != 0, f"initializer accepted {mutation}"
    assert result.stderr
    calls = tmp_path / "calls"
    if calls.exists():
        assert set(calls.read_text(encoding="utf-8").splitlines()) <= {
            "--version",
            "info --format json",
        }


@pytest.mark.parametrize("reported_prefix", ["", "unix://"])
@pytest.mark.parametrize(
    "socket, valid",
    [
        ("", False),
        ("unix:///run/user/123/podman/podman.sock", False),
        ("/var/folders/forwarded-api.sock", False),
        ("/run/user/456/podman/podman.sock", True),
        ("/run/podman/podman.sock", True),
    ],
)
@pytest.mark.usefixtures("selected_engine")
def test_initialize_requires_raw_selected_engine_socket_without_probing_host(
    tmp_path, socket, valid, reported_prefix
):
    reported = reported_prefix + socket if valid else "/run/user/456/podman/podman.sock"
    result = run_bash(
        ROOT / ".devcontainer/require-podman-socket.sh",
        cwd=tmp_path,
        env=dict(
            os.environ, DOTFILES_PODMAN_ENGINE_SOCKET=socket, FAKE_SOCKET=reported
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert (result.returncode == 0) is valid
    if not valid:
        assert "DOTFILES_PODMAN_ENGINE_SOCKET" in result.stderr
