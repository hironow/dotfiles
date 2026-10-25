"""Exercise WSL clipboard provisioning without invoking any host package manager."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from _bash_hook import bash_path, resolve_bash

ROOT = Path(__file__).resolve().parents[2]


def _step() -> str:
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    match = re.search(
        r"^step_wsl_clipboard\(\) \{\n.*?^\}\n", text, re.MULTILINE | re.DOTALL
    )
    assert match, "missing WSL clipboard install step"
    return match.group(0)


def _stub(path: Path, name: str, body: str) -> None:
    target = path / name
    target.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8", newline="\n")
    target.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _stub(bin_dir, "uname", 'echo "6.6.87.2-microsoft-standard-WSL2"')
    _stub(bin_dir, "id", "echo 0")
    _stub(
        bin_dir,
        "apt-get",
        'echo "$*" >> "$HOME/apt.log"; if [ "$1" = install ]; then printf "#!/bin/sh\\nexit 0\\n" > "$HOME/bin/wl-copy"; cp "$HOME/bin/wl-copy" "$HOME/bin/wl-paste"; chmod +x "$HOME/bin/wl-copy" "$HOME/bin/wl-paste"; fi',
    )
    # Keep the subprocess PATH hermetic, but allow the apt stub to create tools.
    for name in ("cp", "chmod"):
        _stub(bin_dir, name, f'/usr/bin/{name} "$@"')
    return tmp_path


def _run(
    sandbox: Path, os_name: str = "linux", repeat: int = 1
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    return subprocess.run(
        [
            resolve_bash(),
            "-c",
            'set -eu\nexport PATH="$PWD/bin" HOME="$PWD"\n'
            + _step()
            + f"\nDOTFILES_OS={os_name}\n"
            + "step_wsl_clipboard\n" * repeat,
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=sandbox,
        timeout=15,
    )


def test_root_installs_and_repeat_is_noop(sandbox: Path) -> None:
    result = _run(sandbox, repeat=2)
    assert result.returncode == 0, result.stderr
    assert (sandbox / "apt.log").read_text(encoding="utf-8").splitlines() == [
        "update",
        "install -y --no-install-recommends wl-clipboard",
    ]
    assert "already installed" in result.stdout


@pytest.mark.parametrize("os_name", ["mac", "windows"])
def test_other_os_skips(sandbox: Path, os_name: str) -> None:
    assert _run(sandbox, os_name).returncode == 0
    assert not (sandbox / "apt.log").exists()


def test_non_wsl_linux_skips(sandbox: Path) -> None:
    _stub(sandbox / "bin", "uname", "echo 6.8.0-generic")
    assert _run(sandbox).returncode == 0
    assert not (sandbox / "apt.log").exists()


@pytest.mark.parametrize("present", ["wl-copy", "wl-paste", "both"])
def test_partial_tools_install_but_complete_pair_skips(
    sandbox: Path, present: str
) -> None:
    for name in ("wl-copy", "wl-paste"):
        if present in (name, "both"):
            _stub(sandbox / "bin", name, "exit 0")
    result = _run(sandbox)
    assert result.returncode == 0, result.stderr
    assert (sandbox / "apt.log").exists() == (present != "both")


@pytest.mark.parametrize("sudo", ["missing", "denied", "available"])
def test_sudo_is_noninteractive(sandbox: Path, sudo: str) -> None:
    _stub(sandbox / "bin", "id", "echo 1000")
    if sudo != "missing":
        _stub(
            sandbox / "bin",
            "sudo",
            'echo "$*" >> "$HOME/sudo.log"; [ "$1" = -n ] || exit 99; shift; '
            + ("exit 1" if sudo == "denied" else '"$@"'),
        )
    result = _run(sandbox)
    assert result.returncode == 0, result.stderr
    assert (sandbox / "apt.log").exists() == (sudo == "available")
    if sudo != "available":
        assert "sudo apt-get" in result.stderr
    if sudo != "missing":
        assert all(
            line.startswith("-n ")
            for line in (sandbox / "sudo.log").read_text(encoding="utf-8").splitlines()
        )


def test_missing_apt_is_actionable(sandbox: Path) -> None:
    (sandbox / "bin/apt-get").unlink()
    result = _run(sandbox)
    assert result.returncode == 0
    assert "package manager" in result.stderr


@pytest.mark.parametrize("failed", ["update", "install", "tools"])
def test_failures_are_visible(sandbox: Path, failed: str) -> None:
    _stub(
        sandbox / "bin",
        "apt-get",
        f'echo "$*" >> "$HOME/apt.log"; [ "$1" != "{failed}" ]',
    )
    result = _run(sandbox)
    assert result.returncode == 0
    assert "WARN installation incomplete" in result.stderr
    if failed == "update":
        assert (sandbox / "apt.log").read_text(encoding="utf-8").splitlines() == [
            "update"
        ]


def test_step_is_in_normal_install_flow() -> None:
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert re.search(r"^step_wsl_clipboard$", text, re.MULTILINE)


@pytest.mark.parametrize("scenario", ["missing", "no-display", "no-socket", "non-wsl"])
def test_doctor_clipboard_runtime_warnings(sandbox: Path, scenario: str) -> None:
    doctor = (ROOT / "scripts/doctor.sh").read_text(encoding="utf-8")
    block = doctor[
        doctor.index("# WSLg clipboard tools") : doctor.index("# Rogue npm-global")
    ]
    _stub(
        sandbox / "bin",
        "uname",
        'if [ "$1" = -s ]; then echo Linux; else echo '
        + ("6.8.0-generic" if scenario == "non-wsl" else "microsoft-WSL2")
        + "; fi",
    )
    if scenario != "missing":
        for tool in ("wl-copy", "wl-paste"):
            _stub(
                sandbox / "bin",
                tool,
                'echo "clipboard must not be touched" >&2; exit 99',
            )
    env = {
        **os.environ,
        "WAYLAND_DISPLAY": "",
        "XDG_RUNTIME_DIR": "",
    }
    if scenario == "no-socket":
        env.update(WAYLAND_DISPLAY="wayland-0", XDG_RUNTIME_DIR=bash_path(sandbox))
    result = subprocess.run(
        [
            resolve_bash(),
            "-c",
            'set -eu\nexport PATH="$PWD/bin" HOME="$PWD"\nhas(){ command -v "$1" >/dev/null 2>&1; }\nlog_warn(){ printf "WARN %s %s\\n" "$1" "$2"; }\nlog_ok(){ printf "OK %s %s\\n" "$1" "$2"; }\n'
            + block,
        ],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        cwd=sandbox,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    expected = {
        "missing": "wl-copy/wl-paste missing",
        "no-display": "WAYLAND_DISPLAY/XDG_RUNTIME_DIR missing",
        "no-socket": "Wayland socket missing",
    }
    if scenario == "non-wsl":
        assert result.stdout == ""
    else:
        assert expected[scenario] in result.stdout


def test_doctor_reports_missing_tools_and_wayland_without_copying() -> None:
    doctor = (ROOT / "scripts/doctor.sh").read_text(encoding="utf-8")
    block = doctor[
        doctor.index("# WSLg clipboard tools") : doctor.index("# Rogue npm-global")
    ]
    assert "log_warn 'wsl-clipboard'" in block
    assert "log_ok 'wsl-clipboard'" in block
    assert "has wl-copy" in block and "has wl-paste" in block
    assert "WAYLAND_DISPLAY" in block and "XDG_RUNTIME_DIR" in block
    assert '[ -S "$clipboard_socket" ]' in block
    assert "UI copy not tested" in block
