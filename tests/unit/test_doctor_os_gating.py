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


def _harness(
    tmp_path: Path,
    block_re: str,
    fakes: str,
    rewrite: tuple[str, str] | None = None,
) -> str:
    """``rewrite`` replaces a literal in the block (e.g. a host path with one
    under ``tmp_path``) and fails if the block no longer contains it."""
    text = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    helpers = re.search(r"(?ms)^log_ok\(\).*?^has\(\).*?$", text)
    found = re.search(block_re, text)
    # doctor runs under its own `set` line; a block that only works without it
    # would end the real doctor at that line.
    options = re.search(r"^set -[a-z]+(?: -o [a-z]+)*$", text, re.MULTILINE)
    assert helpers and found, f"doctor.sh no longer has the block {block_re!r}"
    assert options, "doctor.sh lost its set line"
    block = found[0]
    if rewrite:
        assert rewrite[0] in block, f"the block no longer has {rewrite[0]!r}"
        block = block.replace(*rewrite)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    harness = scripts / "doctor.sh"
    harness.write_text(
        options[0]
        + "\n"
        + helpers[0]
        + "\nok=0; warn=0; err=0; info=0\n"
        + fakes
        + "\n"
        + block
        + '\necho "counts $ok $warn $err $info"\n',
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


PNPM = r"(?ms)^# pnpm comes per repo from corepack.*?^fi$"
WITH_PNPM = "pnpm(){ echo '10.20.0'; }\n"
WITHOUT_PNPM = (
    'has(){ [ "$1" = pnpm ] && return 1; command -v "$1" >/dev/null 2>&1; }\n'
)


@pytest.mark.parametrize(
    ("host", "fake", "line", "counts"),
    [
        (("Darwin", "25.2.0"), WITH_PNPM, "OK   pnpm - 10.20.0", "1 0 0 0"),
        (("Darwin", "25.2.0"), WITHOUT_PNPM, "WARN pnpm - missing", "0 1 0 0"),
        (("Linux", "6.8.0-45-generic"), WITH_PNPM, "OK   pnpm", "1 0 0 0"),
        (("Linux", "6.8.0-45-generic"), WITHOUT_PNPM, "WARN pnpm - missing", "0 1 0 0"),
        (WSL, WITH_PNPM, "OK   pnpm", "1 0 0 0"),
        (WSL, WITHOUT_PNPM, "WARN pnpm - missing", "0 1 0 0"),
        (("MINGW64_NT-10.0-26100", "3.6.4"), WITH_PNPM, None, "0 0 0 0"),
        (("MINGW64_NT-10.0-26100", "3.6.4"), WITHOUT_PNPM, None, "0 0 0 0"),
    ],
)
def test_pnpm_is_checked_only_off_native_windows(
    tmp_path: Path, host: tuple[str, str], fake: str, line: str | None, counts: str
) -> None:
    """Native Windows does not use pnpm (ADR 0070); elsewhere corepack still
    supplies it per repo (ADR 0017), so a missing pnpm stays a WARN."""
    out = _harness(tmp_path, PNPM, _uname(*host) + fake)
    if line is None:
        assert "pnpm" not in out
    else:
        assert line in out
    assert "counts " + counts in out


BREW = r"(?ms)^# Homebrew is used on macOS.*?^fi$"
WITH_BREW = "brew(){ echo 'Homebrew 9.9.9'; }\n"
WITHOUT_BREW = (
    'has(){ [ "$1" = brew ] && return 1; command -v "$1" >/dev/null 2>&1; }\n'
)


@pytest.mark.parametrize(
    ("host", "fake", "line", "counts"),
    [
        (("Darwin", "25.2.0"), WITH_BREW, "OK   brew - Homebrew 9.9.9", "1 0 0 0"),
        (("Darwin", "25.2.0"), WITHOUT_BREW, "WARN brew - missing", "0 1 0 0"),
        (("Linux", "6.8.0-45-generic"), WITH_BREW, "OK   brew", "1 0 0 0"),
        (
            ("Linux", "6.8.0-45-generic"),
            WITHOUT_BREW,
            "INFO brew - not installed (optional on Linux",
            "0 0 0 1",
        ),
        (WSL, WITHOUT_BREW, "INFO brew - not installed", "0 0 0 1"),
        (("MINGW64_NT-10.0-26100", "3.6.4"), WITH_BREW, None, "0 0 0 0"),
        (("MINGW64_NT-10.0-26100", "3.6.4"), WITHOUT_BREW, None, "0 0 0 0"),
    ],
)
def test_brew_is_required_only_on_macos(
    tmp_path: Path, host: tuple[str, str], fake: str, line: str | None, counts: str
) -> None:
    """The justfile treats Homebrew as optional on Linux (WSL and mise-managed
    hosts have none) and never uses it on native Windows."""
    out = _harness(tmp_path, BREW, _uname(*host) + fake)
    if line is None:
        assert "brew" not in out
    else:
        assert line in out
    assert "counts " + counts in out


# The macOS check that Homebrew holds no Docker package: `just dump` records
# whatever Homebrew has, and the Brewfile policy test (ADR 0067) then fails
# on main. doctor names the packages and the command that removes them.
BREW_DOCKER = r"(?ms)^# Homebrew must hold no Docker package.*?^fi$"


def _brew_lists(formulae: str, casks: str) -> str:
    return (
        'brew(){ case "$*" in '
        f"'list --formula -1') printf '{formulae}' ;; "
        f"'list --cask -1') printf '{casks}' ;; "
        "esac; }\n"
    )


@pytest.mark.parametrize(
    ("host", "fake", "line", "counts"),
    [
        (
            ("Darwin", "25.2.0"),
            _brew_lists("jq\ndocker\ndocker-compose\n", "orbstack\nghostty\n"),
            "WARN brew-docker - Homebrew has docker docker-compose orbstack",
            "0 1 0 0",
        ),
        (
            ("Darwin", "25.2.0"),
            _brew_lists("jq\npodman\n", "ghostty\n"),
            "OK   brew-docker - no Docker packages in Homebrew",
            "1 0 0 0",
        ),
        (
            ("Darwin", "25.2.0"),
            _brew_lists("jq\n", "docker-desktop\n"),
            "WARN brew-docker - Homebrew has docker-desktop",
            "0 1 0 0",
        ),
        (
            # An unchecked list must not read as clean (ADR 0066 Decision 2).
            ("Darwin", "25.2.0"),
            "brew(){ return 1; }\n",
            "WARN brew-docker - cannot list Homebrew packages",
            "0 1 0 0",
        ),
        (("Darwin", "25.2.0"), WITHOUT_BREW, None, "0 0 0 0"),
        (("Linux", "6.8.0-45-generic"), _brew_lists("docker\n", ""), None, "0 0 0 0"),
        (
            ("MINGW64_NT-10.0-26100", "3.6.4"),
            _brew_lists("docker\n", ""),
            None,
            "0 0 0 0",
        ),
    ],
)
def test_macos_doctor_names_docker_packages_homebrew_still_holds(
    tmp_path: Path, host: tuple[str, str], fake: str, line: str | None, counts: str
) -> None:
    out = _harness(tmp_path, BREW_DOCKER, _uname(*host) + fake)
    if line is None:
        assert "brew-docker" not in out
    else:
        assert line in out
    if line and line.startswith("WARN brew-docker - Homebrew has "):
        # The advice removes exactly the packages the line names.
        names = line.removeprefix("WARN brew-docker - Homebrew has ")
        assert f"brew uninstall {names}\n" in out
    assert "counts " + counts in out


def test_doctor_and_the_brewfile_test_forbid_the_same_packages() -> None:
    doctor = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    found = re.search(r"^_brew_docker='([^']+)'$", doctor, re.MULTILINE)
    assert found, "doctor.sh lost its Docker package list"
    policy = (ROOT / "tests/unit/test_cli_release_age_policy.py").read_text(
        encoding="utf-8"
    )
    block = policy.split("assert not packages & {", 1)[1].split("}", 1)[0]
    assert set(found[1].split()) == set(re.findall(r'"([^"]+)"', block))


# gcloud lives on Windows when the host is WSL (owner, 2026-11-13): WSL shows
# the Windows copy as a fact (INFO), and every other host still WARNs when
# gcloud is missing. The Windows drives are mounted under /mnt; the test
# plants them under tmp_path instead.
GCLOUD = r"(?ms)^# gcloud lives on Windows.*?^fi$"
TO_TMP = ("/mnt/", "./mnt/")
WITHOUT_GCLOUD = (
    'has(){ [ "$1" = gcloud ] && return 1; command -v "$1" >/dev/null 2>&1; }\n'
)
CLOUD_SDK = "Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd"
PER_USER = "mnt/c/Users/someone/AppData/Local/" + CLOUD_SDK
ALL_USERS = "mnt/c/Program Files (x86)/" + CLOUD_SDK


def _plant(tmp_path: Path, *paths: str) -> None:
    for path in paths:
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("", encoding="utf-8")


@pytest.mark.parametrize(
    ("planted", "line"),
    [
        ((PER_USER,), "INFO gcloud - not in WSL; Windows has ./" + PER_USER),
        ((ALL_USERS,), "INFO gcloud - not in WSL; Windows has ./" + ALL_USERS),
        # The per-user copy is the one named when both exist.
        ((ALL_USERS, PER_USER), "INFO gcloud - not in WSL; Windows has ./" + PER_USER),
    ],
)
def test_wsl_shows_the_windows_gcloud_as_a_fact(
    tmp_path: Path, planted: tuple[str, ...], line: str
) -> None:
    _plant(tmp_path, *planted)
    out = _harness(tmp_path, GCLOUD, _uname(*WSL) + WITHOUT_GCLOUD, TO_TMP)
    assert line + " (gcloud is used from Windows)" in out
    assert "counts 0 0 0 1" in out


def test_wsl_without_any_gcloud_still_warns(tmp_path: Path) -> None:
    (tmp_path / "mnt" / "c" / "Users" / "someone").mkdir(parents=True)
    out = _harness(tmp_path, GCLOUD, _uname(*WSL) + WITHOUT_GCLOUD, TO_TMP)
    assert "WARN gcloud - missing" in out
    assert "counts 0 1 0 0" in out


@pytest.mark.parametrize(
    "host",
    [
        ("Linux", "6.8.0-45-generic"),
        ("Darwin", "25.2.0"),
        ("MINGW64_NT-10.0-26100", "3.6.4"),
    ],
)
def test_only_wsl_looks_for_a_windows_gcloud(
    tmp_path: Path, host: tuple[str, str]
) -> None:
    _plant(tmp_path, PER_USER)
    out = _harness(tmp_path, GCLOUD, _uname(*host) + WITHOUT_GCLOUD, TO_TMP)
    assert "WARN gcloud - missing" in out
    assert "counts 0 1 0 0" in out


def test_a_gcloud_on_path_is_ok_everywhere(tmp_path: Path) -> None:
    _plant(tmp_path, PER_USER)
    fake = "has(){ return 0; }\ngcloud(){ echo 'Google Cloud SDK 999.0.0'; }\n"
    out = _harness(tmp_path, GCLOUD, _uname(*WSL) + fake, TO_TMP)
    assert "OK   gcloud - Google Cloud SDK 999.0.0" in out
    assert "counts 1 0 0 0" in out
