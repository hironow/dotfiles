"""The CA checker is optional to launch but cannot silently pass on failure."""

import re
import sys
from pathlib import Path

import pytest
from _bash_hook import run_bash

ROOT = Path(__file__).resolve().parents[2]
# doctor.sh runs `ca-doctor.exe` under Git Bash (uname MINGW*/MSYS*/CYGWIN*), and
# run_bash always picks Git Bash on native Windows. Git Bash runs a shebang
# script even when its name ends in .exe, so the fake only needs that name.
CA_DOCTOR_NAME = "ca-doctor.exe" if sys.platform == "win32" else "ca-doctor"


def _run(
    tmp_path: Path, output: str | None, rc: int = 0, body: str | None = None
) -> str:
    text = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    helpers = re.search(r"(?ms)^log_ok\(\).*?^has\(\).*?$", text)
    # Stop at the CA block's own end marker, not at the next section: the
    # kernel block sits in between and would otherwise be executed here too,
    # adding its own `WARN kernel-build` to every count this file asserts.
    block = re.search(
        r"(?ms)^# CA health and incidents:.*?(?=^# --- end CA health and incidents ---)",
        text,
    )
    assert helpers and block, "doctor must wire the CA incident check cross-platform"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    if body is None and output is not None:
        body = (
            "printf '%s\\n' '" + output.replace("'", "'\"'\"'") + "'\n" + f"exit {rc}\n"
        )
    if body is not None:
        binary = tmp_path / "output" / "ca-doctor" / CA_DOCTOR_NAME
        binary.parent.mkdir(parents=True)
        binary.write_text("#!/bin/sh\n" + body, encoding="utf-8", newline="\n")
        binary.chmod(0o755)
    harness = scripts / "doctor.sh"
    harness.write_text(
        helpers[0]
        + "\nok=0; warn=0; err=0; info=0\n"
        + block[0]
        + '\necho "counts $ok $warn $err"\necho "info $info"\n',
        encoding="utf-8",
        newline="\n",
    )
    result = run_bash(
        harness,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_missing_checker_is_not_a_clean_scan(tmp_path: Path) -> None:
    out = _run(tmp_path, None)
    assert "WARN ca-build" in out
    assert "just ca-doctor-build" in out
    assert "counts 0 1 0" in out


@pytest.mark.parametrize(
    ("output", "rc", "counts"),
    [
        ("OK   ca-version-go - fixed", 0, "1 0 0"),
        ("WARN ca-live - unavailable", 1, "0 1 0"),
        ("ERR  ca-live - accepted", 2, "0 0 1"),
        ("OK   ca-version-go - fixed\nERR  ca-node - old", 2, "1 0 1"),
    ],
)
def test_checker_findings_are_counted(
    tmp_path: Path, output: str, rc: int, counts: str
) -> None:
    out = _run(tmp_path, output, rc)
    assert "counts " + counts in out
    assert "WARN ca-check" not in out


@pytest.mark.parametrize(
    ("output", "rc"),
    [
        ("", 0),
        ("bad protocol", 0),
        ("OK   ca-version-go - fixed", 139),
        ("OK   ca-version-go - fixed", 2),
        ("ERR  ca-live - accepted", 0),
    ],
)
def test_crash_empty_or_inconsistent_results_are_unverified(
    tmp_path: Path, output: str, rc: int
) -> None:
    out = _run(tmp_path, output, rc)
    assert "WARN ca-check" in out
    assert "counts 0 1 0" in out


def test_info_lines_are_shown_but_counted_apart(tmp_path: Path) -> None:
    out = _run(tmp_path, "OK   ca-build - fresh\nINFO ca-coverage - scope", 0)
    assert "INFO ca-coverage - scope" in out
    assert "counts 1 0 0" in out
    assert "info 1" in out


def test_info_alone_is_not_a_clean_scan(tmp_path: Path) -> None:
    """An exit 0 with no OK line verified nothing, whatever INFO it printed."""
    out = _run(tmp_path, "INFO ca-coverage - scope", 0)
    assert "WARN ca-check" in out
    assert "counts 0 1 0" in out
    assert "info 0" in out


# The binary from before --summary rejects the flag before its freshness check,
# with exactly this line and exit 2 (tools/ca-doctor/main.go). That is a stale
# build, not a security finding: doctor must ask for a rebuild, not count an ERR.
OLD_BINARY = (
    'case " $* " in *" --summary "*)\n'
    "  printf '%s\\n' 'ERR  ca-arguments - usage: ca-doctor --source <tools/ca-doctor> [--offline]'\n"
    "  exit 2 ;;\n"
    "esac\n"
    "printf '%s\\n' 'OK   ca-build - fresh'\n"
)


def test_a_binary_without_summary_asks_for_a_rebuild(tmp_path: Path) -> None:
    out = _run(tmp_path, None, body=OLD_BINARY)
    assert "WARN ca-build" in out
    assert "just ca-doctor-build" in out
    assert "counts 0 1 0" in out
    assert "ERR  ca-arguments" not in out


def test_doctor_asks_for_the_summary(tmp_path: Path) -> None:
    new_binary = (
        'case " $* " in *" --summary "*)\n'
        "  printf '%s\\n' 'OK   ca-build - summary'\n"
        "  exit 0 ;;\n"
        "esac\n"
        "printf '%s\\n' 'OK   ca-build - full'\n"
    )
    out = _run(tmp_path, None, body=new_binary)
    assert "OK   ca-build - summary" in out
    assert "counts 1 0 0" in out


def test_a_real_security_error_is_still_counted(tmp_path: Path) -> None:
    out = _run(tmp_path, "ERR  ca-live-x-python - accepted chains: a", 2)
    assert "counts 0 0 1" in out
    assert "WARN ca-build" not in out
