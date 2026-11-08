"""Exercise the scoped installer CLI with hermetic native package boundaries."""

import os
import shlex
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from _bash_hook import bash_path, run_bash

ROOT = Path(__file__).resolve().parents[2]


def _stub(directory: Path, name: str, body: str) -> None:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path: Path) -> Iterator[Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (tmp_path / "checkout").mkdir()
    (tmp_path / "package").mkdir()
    _stub(
        tmp_path / "package",
        "podman",
        'echo "$*" >> "$HOME/podman.log"; '
        '[ "$*" = --version ] || exit 97; echo "podman version 6.1.4"',
    )
    _stub(bin_dir, "uname", "echo Darwin")
    for name in ("git", "just", "brew", "sudo", "apt-get", "dnf", "pacman"):
        _stub(bin_dir, name, f'echo "{name} $*" >> "$HOME/unexpected.log"; exit 98')
    executable = shutil.which("cp")
    assert executable is not None, "fixture needs cp on PATH"
    _stub(bin_dir, "cp", f'exec {shlex.quote(bash_path(Path(executable)))} "$@"')
    yield tmp_path
    log = tmp_path / "podman.log"
    if log.exists():
        assert all(
            line == "--version" for line in log.read_text(encoding="utf-8").splitlines()
        ), "installer must never initialize, start, upgrade or probe a machine"


def _run(sandbox: Path, *args: str, scoped: bool = True):
    env = os.environ.copy()
    for name in ("BASH_ENV", "ENV"):
        env.pop(name, None)
    env.update(
        HOME=bash_path(sandbox),
        PATH=bash_path(sandbox / "bin"),
        DOTPATH=bash_path(sandbox / "checkout"),
        INSTALL_SKIP_HOMEBREW="1",
        INSTALL_SKIP_GCLOUD="1",
        INSTALL_SKIP_ADD_UPDATE="1",
    )
    return run_bash(
        ROOT / "install.sh",
        *(["--podman-only"] if scoped else []),
        *args,
        cwd=sandbox,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX just dispatch; native PS switch is tested separately"
)
def test_podman_install_recipe_uses_the_scoped_native_installer(sandbox: Path) -> None:
    just = shutil.which("just")
    bash = shutil.which("bash")
    assert just and bash, "just and bash are required to verify the setup entry point"
    _stub(sandbox / "bin", "bash", f'exec {shlex.quote(bash)} "$@"')
    _stub(
        sandbox / "bin",
        "podman",
        'echo "$*" >> "$HOME/podman.log"; '
        '[ "$*" = --version ] || exit 97; echo "podman version 5.6.2"',
    )
    env = os.environ.copy()
    for name in ("BASH_ENV", "ENV"):
        env.pop(name, None)
    env.update(
        HOME=str(sandbox),
        PATH=str(sandbox / "bin"),
        DOTPATH=str(sandbox / "checkout"),
    )
    result = subprocess.run(
        [just, "--justfile", str(ROOT / "justfile"), "podman-install"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (sandbox / "unexpected.log").exists()
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        "--version"
    ]


@pytest.mark.parametrize("sudo", ["missing", "denied"])
def test_linux_refuses_to_prompt_or_change_packages_without_privilege(
    sandbox: Path, sudo: str
) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 1000")
    if sudo == "missing":
        (sandbox / "bin" / "sudo").unlink()
    else:
        _stub(sandbox / "bin", "sudo", '[ "$*" = "-n true" ] || exit 97; exit 1')
    result = _run(sandbox)
    assert result.returncode != 0
    assert "noninteractive sudo" in result.stderr
    assert not (sandbox / "unexpected.log").exists()


@pytest.mark.parametrize("installed", [False, True])
def test_old_native_packages_do_not_bypass_minimum_or_fall_back(
    sandbox: Path, installed: bool
) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 0")
    _stub(sandbox / "package", "podman", 'echo "podman version 4.3.1"')
    if installed:
        _stub(sandbox / "bin", "podman", 'echo "podman version 4.3.1"')
    _stub(
        sandbox / "bin",
        "apt-get",
        'if [ "$1" = install ]; then cp "$HOME/package/podman" "$HOME/bin/podman"; fi',
    )
    result = _run(sandbox)
    assert result.returncode != 0
    assert "Podman 5+ is required" in result.stderr
    assert not (sandbox / "unexpected.log").exists()


@pytest.mark.parametrize("behavior", ["failure", "no_cli", "old_cli"])
def test_native_package_success_alone_is_not_success(
    sandbox: Path, behavior: str
) -> None:
    if behavior == "old_cli":
        _stub(sandbox / "package", "podman", 'echo "podman version 4.3.1"')
    body = {
        "failure": "exit 42",
        "no_cli": "exit 0",
        "old_cli": 'cp "$HOME/package/podman" "$HOME/bin/podman"',
    }[behavior]
    _stub(sandbox / "bin", "brew", body)
    result = _run(sandbox)
    assert result.returncode != 0
    assert not (sandbox / "unexpected.log").exists()


@pytest.mark.parametrize("version", ["", "not-a-version", "podman version bad"])
def test_malformed_cli_version_fails_without_package_changes(
    sandbox: Path, version: str
) -> None:
    _stub(sandbox / "bin", "podman", f"echo {shlex.quote(version)}")
    result = _run(sandbox)
    assert result.returncode != 0
    assert "cannot parse Podman CLI version" in result.stderr
    assert not (sandbox / "unexpected.log").exists()


def test_extra_scoped_arguments_fail_before_any_mutation(sandbox: Path) -> None:
    result = _run(sandbox, "--unexpected")
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert not (sandbox / "unexpected.log").exists()


def test_mac_without_homebrew_has_no_download_fallback(sandbox: Path) -> None:
    (sandbox / "bin" / "brew").unlink()
    result = _run(sandbox)
    assert result.returncode != 0
    assert "Homebrew is required" in result.stderr
    assert not (sandbox / "unexpected.log").exists()


def test_unsupported_linux_package_manager_fails_closed(sandbox: Path) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 0")
    for name in ("apt-get", "dnf", "pacman"):
        (sandbox / "bin" / name).unlink()
    result = _run(sandbox)
    assert result.returncode != 0
    assert "no supported native package manager" in result.stderr
    assert not (sandbox / "unexpected.log").exists()


def test_unreadable_cli_version_fails_with_actionable_error(sandbox: Path) -> None:
    _stub(sandbox / "bin", "podman", "exit 7")
    result = _run(sandbox)
    assert result.returncode != 0
    assert "cannot read Podman CLI version" in result.stderr
    assert not (sandbox / "unexpected.log").exists()


def test_normal_mac_setup_also_provisions_the_required_cli(sandbox: Path) -> None:
    for name in ("git", "just", "mise", "sheldon", "corepack", "find", "head"):
        _stub(sandbox / "bin", name, "exit 0")
    _stub(
        sandbox / "bin",
        "brew",
        '[ "$*" = "install podman" ] || exit 97; '
        'cp "$HOME/package/podman" "$HOME/bin/podman"',
    )
    result = _run(sandbox, scoped=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "bin" / "podman").is_file(), result.stdout
    assert not (sandbox / "unexpected.log").exists()


def test_windows_posix_mode_directs_to_native_bootstrap(sandbox: Path) -> None:
    _stub(sandbox / "bin", "uname", "echo MINGW64_NT-10.0")
    result = _run(sandbox)
    assert result.returncode != 0
    assert "bootstrap.ps1 -PodmanOnly" in result.stderr
    assert not (sandbox / "unexpected.log").exists()


def test_linux_elevates_only_package_commands_without_a_prompt(sandbox: Path) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 1000")
    _stub(
        sandbox / "bin",
        "sudo",
        'echo "$*" >> "$HOME/sudo.log"; [ "$1" = -n ] || exit 97; shift; "$@"',
    )
    _stub(sandbox / "bin", "true", "exit 0")
    _stub(
        sandbox / "bin",
        "apt-get",
        'echo "$*" >> "$HOME/package.log"; '
        'if [ "$1" = install ]; then '
        'cp "$HOME/package/podman" "$HOME/bin/podman"; fi',
    )
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "sudo.log").read_text(encoding="utf-8").splitlines() == [
        "-n true",
        "-n apt-get update",
        "-n apt-get install -y --no-install-recommends podman netavark aardvark-dns passt uidmap fuse-overlayfs",
    ]
    assert not (sandbox / "unexpected.log").exists()


def test_pacman_is_used_when_apt_and_dnf_are_unavailable(sandbox: Path) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 0")
    for name in ("apt-get", "dnf"):
        (sandbox / "bin" / name).unlink()
    _stub(
        sandbox / "bin",
        "pacman",
        'echo "$*" >> "$HOME/package.log"; '
        'cp "$HOME/package/podman" "$HOME/bin/podman"',
    )
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "-S --needed --noconfirm podman netavark aardvark-dns passt shadow fuse-overlayfs"
    ]
    assert not (sandbox / "unexpected.log").exists()


def test_dnf_is_used_when_apt_is_unavailable(sandbox: Path) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 0")
    (sandbox / "bin" / "apt-get").unlink()
    _stub(
        sandbox / "bin",
        "dnf",
        'echo "$*" >> "$HOME/package.log"; '
        'cp "$HOME/package/podman" "$HOME/bin/podman"',
    )
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "install -y podman netavark aardvark-dns passt shadow-utils fuse-overlayfs"
    ]
    assert not (sandbox / "unexpected.log").exists()


def test_missing_linux_podman_installs_runtime_and_dns_packages(sandbox: Path) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 0")
    _stub(
        sandbox / "bin",
        "apt-get",
        'echo "$*" >> "$HOME/package.log"; '
        'if [ "$1" = install ]; then '
        'cp "$HOME/package/podman" "$HOME/bin/podman"; fi',
    )
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "update",
        "install -y --no-install-recommends podman netavark aardvark-dns passt uidmap fuse-overlayfs",
    ]
    assert not (sandbox / "unexpected.log").exists()


def test_old_mac_podman_uses_native_upgrade(sandbox: Path) -> None:
    _stub(sandbox / "bin", "podman", 'echo "podman version 4.3.1"')
    _stub(
        sandbox / "bin",
        "brew",
        'echo "$*" >> "$HOME/package.log"; '
        '[ "$*" = "upgrade podman" ] || exit 97; '
        'cp "$HOME/package/podman" "$HOME/bin/podman"',
    )
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "upgrade podman"
    ]
    assert not (sandbox / "unexpected.log").exists()


def test_missing_mac_podman_is_installed_natively(sandbox: Path) -> None:
    _stub(
        sandbox / "bin",
        "brew",
        'echo "$*" >> "$HOME/package.log"; '
        '[ "$*" = "install podman" ] || exit 97; '
        'cp "$HOME/package/podman" "$HOME/bin/podman"',
    )
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "install podman"
    ]
    assert not (sandbox / "unexpected.log").exists()


@pytest.mark.parametrize("os_name", ["Darwin", "Linux", "MINGW64_NT-10.0"])
def test_installed_podman_only_checks_version_without_bootstrap(
    sandbox: Path, os_name: str
) -> None:
    _stub(sandbox / "bin", "uname", f"echo {os_name}")
    _stub(
        sandbox / "bin",
        "podman",
        'printf "%s\\n" "$*" >> "$HOME/podman.log"; '
        '[ "$*" = --version ] || exit 97; echo "podman version 5.6.2"',
    )
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not (sandbox / "unexpected.log").exists()
    assert (sandbox / "podman.log").read_text(encoding="utf-8").splitlines() == [
        "--version"
    ]
