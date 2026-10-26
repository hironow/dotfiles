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


def _run(tmp_path: Path, output: str | None, rc: int = 0) -> str:
    text = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    helpers = re.search(r"(?ms)^log_ok\(\).*?^has\(\).*?$", text)
    block = re.search(r"(?ms)^# CA health and incidents:.*?(?=^# AI tooling:)", text)
    assert helpers and block, "doctor must wire the CA incident check cross-platform"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    if output is not None:
        binary = tmp_path / "output" / "ca-doctor" / CA_DOCTOR_NAME
        binary.parent.mkdir(parents=True)
        binary.write_text(
            "#!/bin/sh\n"
            + "printf '%s\\n' '"
            + output.replace("'", "'\"'\"'")
            + "'\n"
            + f"exit {rc}\n",
            encoding="utf-8",
            newline="\n",
        )
        binary.chmod(0o755)
    harness = scripts / "doctor.sh"
    harness.write_text(
        helpers[0]
        + "\nok=0; warn=0; err=0\n"
        + block[0]
        + '\necho "counts $ok $warn $err"\n',
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
