"""The kernel check is advisory: its findings never change doctor's exit code.

`scripts/doctor.sh` wires kernel-doctor the way it wires ca-doctor — accept a
consistent run, and treat a crash, an empty result or an inconsistent protocol
as unverified rather than clean. It differs in one deliberate way (ADR-0065):
this repository ships no Linux kernel, so nothing the kernel checker reports is
the repository's to fix. Its findings are added to `warn` and never to `err`.

That matters because `just doctor` exits non-zero on any ERR, and two callers
assert exit 0: `just self-check` and `test_doctor_sandbox`. Without this, an
unpatched kernel on a development host — something only the operator can fix,
and only outside this repository — would turn the repo's own gates red.
"""

import re
import sys
from pathlib import Path

import pytest
from _bash_hook import run_bash

ROOT = Path(__file__).resolve().parents[2]
# doctor.sh runs `kernel-doctor.exe` under Git Bash (uname MINGW*/MSYS*/CYGWIN*),
# and run_bash always picks Git Bash on native Windows. Git Bash runs a shebang
# script even when its name ends in .exe, so the fake only needs that name.
KERNEL_DOCTOR_NAME = "kernel-doctor.exe" if sys.platform == "win32" else "kernel-doctor"


def _run(tmp_path: Path, output: str | None, rc: int = 0) -> tuple[str, int]:
    text = (ROOT / "scripts" / "doctor.sh").read_text(encoding="utf-8")
    helpers = re.search(r"(?ms)^log_ok\(\).*?^has\(\).*?$", text)
    block = re.search(r"(?ms)^# Linux kernel CVE evidence:.*?(?=^# AI tooling:)", text)
    assert helpers and block, "doctor must wire the kernel CVE check cross-platform"
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    if output is not None:
        binary = tmp_path / "output" / "kernel-doctor" / KERNEL_DOCTOR_NAME
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
    return result.stdout + result.stderr, result.returncode


def test_missing_checker_is_not_a_clean_scan(tmp_path: Path) -> None:
    out, rc = _run(tmp_path, None)
    assert "WARN kernel-build" in out
    assert "just kernel-doctor-build" in out
    assert "counts 0 1 0" in out
    assert rc == 0


@pytest.mark.parametrize(
    ("output", "rc", "counts"),
    [
        ("OK   kernel-scope - 6.6.159", 0, "1 0 0"),
        ("OK   a - b\nWARN c - d", 1, "1 1 0"),
        ("WARN kernel-version-x - unverified-vendor", 1, "0 1 0"),
    ],
)
def test_findings_are_counted(
    tmp_path: Path, output: str, rc: int, counts: str
) -> None:
    out, _ = _run(tmp_path, output, rc)
    assert "counts " + counts in out
    assert "WARN kernel-check" not in out


@pytest.mark.parametrize(
    ("output", "rc"),
    [
        ("", 0),
        ("bad protocol", 0),
        ("OK   a - b", 139),
        ("OK   a - b", 2),
        ("WARN a - b", 0),
        # An ERR must not be accepted, even though the tool never emits one.
        ("ERR  a - b", 2),
        ("OK   a - b\nERR  c - d", 2),
    ],
)
def test_inconsistent_results_are_unverified_and_never_fatal(
    tmp_path: Path, output: str, rc: int
) -> None:
    """A stray ERR is downgraded to a WARN -- this is the ADR-0065 contract.

    The kernel is not this repository's to fix, so no kernel finding may reach
    doctor's `err` count or make `just doctor` exit non-zero; `just self-check`
    and test_doctor_sandbox both assert exit 0.
    """
    out, code = _run(tmp_path, output, rc)
    assert "WARN kernel-check" in out
    assert "counts 0 1 0" in out
    assert "ERR" not in out
    assert code == 0


def test_an_err_never_reaches_doctors_error_count(tmp_path: Path) -> None:
    """Even a checker that crashes with a bare ERR line stays advisory."""
    out, code = _run(tmp_path, "ERR  kernel-coverage - something is badly wrong", 2)
    assert "counts 0 1 0" in out, out
    assert " 0 0 1" not in out, out
    assert code == 0
