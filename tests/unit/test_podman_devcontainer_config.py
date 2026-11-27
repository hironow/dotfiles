"""Podman devcontainer/Cursor transport contract; no engine calls."""

import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest
from _bash_hook import bash_path, run_bash

ROOT = Path(__file__).resolve().parents[2]


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


# ADR-0093 D4: the Cursor environment must stay rootless: a user socket, a
# pinned mise key, no docker group, no socket open to everyone. Held by runs
# of the real scripts with recording fakes.
CURSOR = ROOT / ".cursor"
PINNED_FPR = "24853EC9F655CE80B48E6C3A8B81C9D17413A06D"


def _fakes(directory: Path, bodies: dict[str, str]) -> None:
    directory.mkdir(exist_ok=True)
    for name, body in bodies.items():
        (directory / name).write_text(
            "#!/bin/sh\n" + body + "\n", encoding="utf-8", newline="\n"
        )
        (directory / name).chmod(0o755)


def run_cursor_start(
    tmp_path: Path,
    script: Path,
    *,
    uid: str = "1000",
    socket: str | None = None,
    systemctl_rc: int = 0,
) -> tuple[subprocess.CompletedProcess[str], str]:
    run = tmp_path / "run"
    run.mkdir()
    log = tmp_path / "calls"
    log.touch()
    fake = tmp_path / "fake-bin"
    _fakes(
        fake,
        {
            "id": f'[ "$1" = -u ] && echo {uid}',
            "podman": 'printf "podman %s umask=%s\\n" "$*" "$(umask)" >> "$FIXTURE_LOG"\n'
            'case "$1" in info) echo "unix://$FIXTURE_SOCKET" ;; version) echo "5.4.0 5.4.0" ;; esac',
            "systemctl": 'printf "systemctl %s\\n" "$*" >> "$FIXTURE_LOG"\nexit "$FIXTURE_SYSTEMCTL_RC"',
            "sudo": 'printf "sudo %s\\n" "$*" >> "$FIXTURE_LOG"\nexit 97',
            "chmod": 'printf "chmod %s\\n" "$*" >> "$FIXTURE_LOG"',
        },
    )
    done = subprocess.run(
        [_bash(), str(script)],
        env={
            "PATH": f"{fake}:/usr/bin:/bin",
            "HOME": str(tmp_path),
            "XDG_RUNTIME_DIR": str(run),
            "FIXTURE_LOG": str(log),
            "FIXTURE_SOCKET": socket or f"{run}/podman/podman.sock",
            "FIXTURE_SYSTEMCTL_RC": str(systemctl_rc),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=60,
    )
    # The fallback service starts in the background; wait for its line.
    for _ in range(50):
        if systemctl_rc == 0 or "system service" in log.read_text(encoding="utf-8"):
            break
        time.sleep(0.1)
    return done, log.read_text(encoding="utf-8")


def _bash() -> str:
    bash = shutil.which("bash")
    if bash is None or sys.platform == "win32":
        pytest.skip("runs the Linux scripts with POSIX fakes")
    return bash


def check_start_refuses_root(tmp_path: Path, script: Path) -> None:
    done, calls = run_cursor_start(tmp_path, script, uid="0")
    assert done.returncode == 1 and "non-root" in done.stderr, done.stderr
    assert "systemctl" not in calls and "system service" not in calls, calls


def check_start_refuses_an_unexpected_socket(tmp_path: Path, script: Path) -> None:
    done, calls = run_cursor_start(
        tmp_path, script, socket=str(tmp_path / "elsewhere.sock")
    )
    assert done.returncode == 1 and "refusing unexpected user socket" in done.stderr, (
        done.stderr
    )
    assert "systemctl" not in calls, calls


def check_start_uses_the_user_socket(tmp_path: Path, script: Path) -> None:
    done, calls = run_cursor_start(tmp_path, script)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "systemctl --user start podman.socket\n" in calls, calls
    assert "sudo " not in calls and "chmod " not in calls, calls


def check_the_fallback_service_is_private(tmp_path: Path, script: Path) -> None:
    done, calls = run_cursor_start(tmp_path, script, systemctl_rc=1)
    assert done.returncode == 0, done.stdout + done.stderr
    socket = tmp_path / "run" / "podman" / "podman.sock"
    assert f"podman system service --time=0 unix://{socket} umask=0077" in calls, calls
    assert "sudo " not in calls and "chmod " not in calls, calls


def test_cursor_start_refuses_root(tmp_path: Path) -> None:
    check_start_refuses_root(tmp_path, CURSOR / "start.sh")


def test_cursor_start_refuses_an_unexpected_socket(tmp_path: Path) -> None:
    check_start_refuses_an_unexpected_socket(tmp_path, CURSOR / "start.sh")


def test_cursor_start_uses_the_user_socket(tmp_path: Path) -> None:
    check_start_uses_the_user_socket(tmp_path, CURSOR / "start.sh")


def test_cursor_start_fallback_keeps_the_socket_private(tmp_path: Path) -> None:
    check_the_fallback_service_is_private(tmp_path, CURSOR / "start.sh")


def run_cursor_install(
    tmp_path: Path, script: Path, *, fingerprint: str
) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run a copy of .cursor/install.sh in a temp repo: a stub install.sh,
    the real mise config and skills_lock.py, and fakes for every command
    that reaches past the temp folder."""
    bash = _bash()
    if not Path("/dev/fuse").is_char_device():
        pytest.skip("the script requires /dev/fuse, which this host lacks")
    if any(Path(d, "mise").exists() for d in ("/usr/bin", "/bin")):
        pytest.skip("a mise in /usr/bin or /bin would skip the fingerprint check")
    repo = tmp_path / "repo"
    (repo / ".cursor").mkdir(parents=True)
    shutil.copy(script, repo / ".cursor" / "install.sh")
    for rel in ("config/mise/config.toml", "scripts/skills_lock.py"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / rel, repo / rel)
    (repo / "emulator").mkdir()
    log = tmp_path / "calls"
    log.touch()
    (repo / "install.sh").write_text(
        f'printf "install.sh %s\\n" "$*" >> "{log}"\n', encoding="utf-8"
    )
    fake = tmp_path / "fake-bin"
    mise = 'printf "mise %s\\n" "$*" >> "$FIXTURE_LOG"\ncase "$*" in "--version") echo 2026.10.17 ;; "-C / where "*) echo "$FIXTURE_TOOLS/$4" ;; esac'
    _fakes(
        fake,
        {
            "sudo": 'printf "sudo %s\\n" "$*" >> "$FIXTURE_LOG"\ncat > /dev/null\n'
            'case "$*" in *"apt-get install"*" mise") '
            f"printf '#!/bin/sh\\n%s\\n' '{mise}' > \"$FIXTURE_BIN/mise\"; /bin/chmod 755 \"$FIXTURE_BIN/mise\" ;; esac",
            "curl": 'printf "curl %s\\n" "$*" >> "$FIXTURE_LOG"\n'
            'while [ "$#" -gt 0 ]; do [ "$1" = -o ] && echo KEY > "$2"; shift; done',
            "gpg": 'case "$*" in *--list-keys*) echo "fpr:::::::::$FIXTURE_FPR:" ;; esac',
            "chmod": 'printf "chmod %s\\n" "$*" >> "$FIXTURE_LOG"',
            "usermod": 'printf "usermod %s\\n" "$*" >> "$FIXTURE_LOG"',
        },
    )
    home = tmp_path / "home"
    home.mkdir()
    temp = tmp_path / "tmp"
    temp.mkdir()
    done = subprocess.run(
        [bash, str(repo / ".cursor" / "install.sh")],
        env={
            "PATH": f"{fake}:/usr/bin:/bin",
            "HOME": str(home),
            "TMPDIR": str(temp),
            "FIXTURE_LOG": str(log),
            "FIXTURE_BIN": str(fake),
            "FIXTURE_FPR": fingerprint,
            "FIXTURE_TOOLS": str(tmp_path / "tools"),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        check=False,
        timeout=120,
    )
    return done, log.read_text(encoding="utf-8")


def check_install_stops_on_a_foreign_key(tmp_path: Path, script: Path) -> None:
    done, calls = run_cursor_install(tmp_path, script, fingerprint="0" * 40)
    assert done.returncode == 1 and "fingerprint mismatch" in done.stderr, done.stderr
    assert (
        "sources.list.d/mise.list" not in calls
        and "--no-install-recommends mise" not in calls
    ), calls


def check_install_trusts_the_pinned_key_and_stays_rootless(
    tmp_path: Path, script: Path
) -> None:
    done, calls = run_cursor_install(tmp_path, script, fingerprint=PINNED_FPR)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "sudo tee /etc/apt/sources.list.d/mise.list" in calls, calls
    assert "sudo apt-get install -y --no-install-recommends mise" in calls, calls
    for forbidden in ("usermod", "docker", "chmod 666", "daemon.json", "sudo podman"):
        assert forbidden not in calls, (forbidden, calls)


def test_cursor_install_stops_on_a_foreign_mise_key(tmp_path: Path) -> None:
    check_install_stops_on_a_foreign_key(tmp_path, CURSOR / "install.sh")


def test_cursor_install_trusts_the_pinned_key_and_stays_rootless(
    tmp_path: Path,
) -> None:
    check_install_trusts_the_pinned_key_and_stays_rootless(
        tmp_path, CURSOR / "install.sh"
    )
