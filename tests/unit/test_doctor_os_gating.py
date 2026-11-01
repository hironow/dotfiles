"""doctor prints a check only on the OS it is about.

A check that cannot apply to this host (the WSL `/mnt` PATH leak on macOS, the
Windows/WSL Ollama policy on Linux) adds a line the operator can do nothing
with. The block under test is cut out of scripts/doctor.sh, and `uname`, `just`
and `uv` are replaced with shell functions, so every host shape runs on any OS
(functions also work under Git Bash on native Windows, where a fake executable
on PATH would not reliably shadow uname.exe).
"""

import re
from pathlib import Path

import pytest
from _bash_hook import run_bash

ROOT = Path(__file__).resolve().parents[2]
WSL = ("Linux", "6.6.87.2-microsoft-standard-WSL2")


def _harness(tmp_path: Path, block_re: str, fakes: str) -> str:
    text = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    helpers = re.search(r"(?ms)^log_ok\(\).*?^has\(\).*?$", text)
    block = re.search(block_re, text)
    assert helpers and block, f"doctor.sh no longer has the block {block_re!r}"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    harness = scripts / "doctor.sh"
    harness.write_text(
        helpers[0]
        + "\nok=0; warn=0; err=0; info=0\n"
        + fakes
        + "\n"
        + block[0]
        + '\necho "counts $ok $warn $err"\n',
        encoding="utf-8",
        newline="\n",
    )
    result = run_bash(
        harness, cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _uname(system: str, release: str) -> str:
    return (
        'uname(){ case "$1" in -s) echo \''
        + system
        + "' ;; -r) echo '"
        + release
        + "' ;; esac; }\n"
    )


PATH_WINDOWS = r"(?ms)^# Windows PATH contamination.*?(?=^# zsh is the supported)"


@pytest.mark.parametrize(
    ("host", "shown"),
    [
        (WSL, True),
        (("Linux", "6.8.0-45-generic"), False),
        (("Darwin", "25.2.0"), False),
        (("MINGW64_NT-10.0-26100", "3.6.4"), False),
    ],
)
def test_the_windows_path_leak_check_runs_only_in_wsl(
    tmp_path: Path, host: tuple[str, str], shown: bool
) -> None:
    out = _harness(tmp_path, PATH_WINDOWS, _uname(*host) + "just(){ return 0; }\n")
    assert ("OK   PATH-windows" in out) is shown
    assert ("counts 1 0 0" if shown else "counts 0 0 0") in out


OLLAMA = r"(?ms)^# Canonical Ollama ownership.*?(?=^echo \"Doctor summary)"


def _uv(output: str, rc: int) -> str:
    quoted = output.replace("'", "'\"'\"'")
    printer = f"printf '%s\\n' '{quoted}'; " if output else ""
    return "uv(){ " + printer + f"return {rc}; }}\n"


def test_a_silent_not_applicable_exit_prints_nothing(tmp_path: Path) -> None:
    out = _harness(tmp_path, OLLAMA, _uv("", 3))
    assert "ollama" not in out
    assert "counts 0 0 0" in out


def test_uv_noise_on_stderr_does_not_break_the_silent_exit(tmp_path: Path) -> None:
    """The contract covers the checker's stdout. `uv run` itself writes warnings
    to stderr (seen live: `VIRTUAL_ENV=... does not match the project
    environment path`), and they are not the checker speaking."""
    noisy = "uv(){ echo 'warning: VIRTUAL_ENV does not match' >&2; return 3; }\n"
    out = _harness(tmp_path, OLLAMA, noisy)
    assert "ollama" not in out
    assert "counts 0 0 0" in out


@pytest.mark.parametrize(
    "output",
    [
        "OK   ollama-policy - Windows/WSL singleton policy not applicable on this host",
        "something unexpected",
    ],
)
def test_output_with_the_not_applicable_exit_is_inconsistent(
    tmp_path: Path, output: str
) -> None:
    """Nothing printed with exit 3 is counted: the run contradicts itself."""
    out = _harness(tmp_path, OLLAMA, _uv(output, 3))
    assert "WARN ollama-inspection" in out
    assert "counts 0 1 0" in out


@pytest.mark.parametrize(
    ("output", "rc", "counts", "unavailable"),
    [
        ("", 1, "0 1 0", True),
        ("", 0, "0 1 0", True),
        ("OK   ollama-owner - one backend", 0, "1 0 0", False),
        ("ERR  ollama-owner - two backends", 1, "0 0 1", False),
    ],
)
def test_an_applicable_host_is_read_as_before(
    tmp_path: Path, output: str, rc: int, counts: str, unavailable: bool
) -> None:
    out = _harness(tmp_path, OLLAMA, _uv(output, rc))
    assert "counts " + counts in out
    assert ("WARN ollama-inspection" in out) is unavailable
