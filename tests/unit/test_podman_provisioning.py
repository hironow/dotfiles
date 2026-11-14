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
    for name in (
        "git",
        "just",
        "brew",
        "sudo",
        "apt-get",
        "apt-cache",
        "dnf",
        "pacman",
    ):
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


def _apt_cache(sandbox: Path, answer: str) -> None:
    """A fake `apt-cache policy podman` that prints `answer` in the C locale.

    Outside the C locale it answers in Japanese, as apt does under ja_JP
    ("候補:" for "Candidate:"), so the installer must ask for the C locale.
    """
    # the sandbox PATH holds only its own stubs, so use the shell's printf
    _stub(
        sandbox / "bin",
        "apt-cache",
        '[ "$*" = "policy podman" ] || exit 97\n'
        'if [ "${LC_ALL:-}" != C ]; then\n'
        "  printf '%s\\n' 'podman:' '  候補:               6.1.4-1'\n"
        "  exit 0\n"
        "fi\n"
        f"printf '%s' {shlex.quote(answer)}",
    )


def _candidate(version: str) -> str:
    return f"podman:\n  Installed: (none)\n  Candidate: {version}\n"


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
        'echo "$*" >> "$HOME/package.log"; '
        'if [ "$1" = install ]; then cp "$HOME/package/podman" "$HOME/bin/podman"; fi',
    )
    # Ubuntu 24.04 offers 4.9.3: stop before installing anything, so no old
    # Podman and no runtime packages are left behind.
    _apt_cache(sandbox, _candidate("4.3.1+ds1-1ubuntu0.2"))
    result = _run(sandbox)
    assert result.returncode != 0
    assert "Podman 5+ is required" in result.stderr
    assert "apt offers 4.3.1+ds1-1ubuntu0.2" in result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "update"
    ]
    assert not (sandbox / "unexpected.log").exists()


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (_candidate("(none)"), "apt offers no Podman"),
        ("", "apt offers no Podman"),
        (_candidate("garbage"), "cannot read apt's Podman candidate"),
        (None, "cannot read apt's Podman candidate"),
    ],
)
def test_an_unreadable_or_missing_apt_candidate_installs_nothing(
    sandbox: Path, answer: str | None, reason: str
) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 0")
    _stub(sandbox / "bin", "apt-get", 'echo "$*" >> "$HOME/package.log"')
    if answer is None:
        _stub(sandbox / "bin", "apt-cache", "exit 100")
    else:
        _apt_cache(sandbox, answer)
    result = _run(sandbox)
    assert result.returncode != 0
    assert reason in result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "update"
    ]
    assert not (sandbox / "unexpected.log").exists()


def test_an_apt_candidate_with_an_epoch_is_read_by_its_upstream_version(
    sandbox: Path,
) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 0")
    _stub(
        sandbox / "bin",
        "apt-get",
        'echo "$*" >> "$HOME/package.log"; '
        'if [ "$1" = install ]; then cp "$HOME/package/podman" "$HOME/bin/podman"; fi',
    )
    _apt_cache(sandbox, _candidate("1:5.4.2+ds1-1"))
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines()[-1] == (
        "install -y --no-install-recommends podman netavark aardvark-dns passt uidmap fuse-overlayfs nftables catatonit"
    )


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
    # reading the candidate needs no root, so it does not go through sudo
    _apt_cache(sandbox, _candidate("6.1.4+ds1-1"))
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "sudo.log").read_text(encoding="utf-8").splitlines() == [
        "-n true",
        "-n apt-get update",
        "-n apt-get install -y --no-install-recommends podman netavark aardvark-dns passt uidmap fuse-overlayfs nftables catatonit",
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


DNF_INSTALL = (
    "install -y podman netavark aardvark-dns passt shadow-utils fuse-overlayfs"
)
REPOQUERY = "-q repoquery --latest-limit 1 --queryformat %{version}\\n podman"


def _dnf(sandbox: Path, answer: str | None) -> None:
    """A fake dnf. `repoquery` must come with exactly the expected arguments
    and prints `answer` (None: it fails); `install` puts the package's
    podman on PATH. Each call is logged by name."""
    repoquery = "exit 1" if answer is None else f"printf '%s' {shlex.quote(answer)}"
    _stub(
        sandbox / "bin",
        "dnf",
        f'if [ "$*" = {shlex.quote(REPOQUERY)} ]; then\n'
        '  echo repoquery >> "$HOME/package.log"\n'
        f"  {repoquery}\n"
        f'elif [ "$*" = {shlex.quote(DNF_INSTALL)} ]; then\n'
        '  echo install >> "$HOME/package.log"\n'
        '  cp "$HOME/package/podman" "$HOME/bin/podman"\n'
        "else\n"
        '  printf "%s\\n" "$*" >> "$HOME/unexpected.log"; exit 97\n'
        "fi",
    )


def _dnf_host(sandbox: Path, answer: str | None) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 0")
    (sandbox / "bin" / "apt-get").unlink()
    _dnf(sandbox, answer)


# Measured on 2026-11-10: Fedora 45 (dnf5) prints "6.1.3\n", Rocky Linux 9.3
# "5.8.2\n\n", Rocky Linux 8.9 "4.9.4\n\n"; a package dnf does not know
# prints nothing.
@pytest.mark.parametrize("answer", ["6.1.3\n", "5.8.2\n\n", "\n5.8.2\n"])
def test_dnf_is_used_when_apt_is_unavailable(sandbox: Path, answer: str) -> None:
    _dnf_host(sandbox, answer)
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "repoquery",
        "install",
    ]
    assert not (sandbox / "unexpected.log").exists()


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("4.9.4\n\n", "dnf offers 4.9.4; Podman 5+ is required"),
        ("", "dnf offers no Podman package"),
        ("\n\n", "dnf offers no Podman package"),
        ("5.8.2\n6.1.3\n", "cannot read dnf's Podman candidate: 5.8.2"),
        ("garbage\n", "cannot read dnf's Podman candidate: garbage"),
        (None, "cannot read dnf's Podman candidate (dnf repoquery failed)"),
    ],
)
def test_an_old_missing_or_unreadable_dnf_candidate_installs_nothing(
    sandbox: Path, answer: str | None, reason: str
) -> None:
    # The RHEL 8 family offers Podman 4.9: stop before installing anything.
    _dnf_host(sandbox, answer)
    result = _run(sandbox)
    assert result.returncode != 0
    assert reason in result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "repoquery"
    ]
    assert not (sandbox / "unexpected.log").exists()


def test_dnf_reads_its_candidate_with_the_same_privilege_that_installs(
    sandbox: Path,
) -> None:
    _stub(sandbox / "bin", "uname", "echo Linux")
    _stub(sandbox / "bin", "id", "echo 1000")
    (sandbox / "bin" / "apt-get").unlink()
    _stub(
        sandbox / "bin",
        "sudo",
        'printf "%s\\n" "$*" >> "$HOME/sudo.log"; '
        '[ "$1" = -n ] || exit 97; shift; "$@"',
    )
    _stub(sandbox / "bin", "true", "exit 0")
    _dnf(sandbox, "6.1.3\n")
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "sudo.log").read_text(encoding="utf-8").splitlines() == [
        "-n true",
        "-n dnf " + REPOQUERY,
        "-n dnf " + DNF_INSTALL,
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
    _apt_cache(sandbox, _candidate("6.1.4+ds1-1"))
    result = _run(sandbox)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (sandbox / "package.log").read_text(encoding="utf-8").splitlines() == [
        "update",
        "install -y --no-install-recommends podman netavark aardvark-dns passt uidmap fuse-overlayfs nftables catatonit",
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
