"""Behavioural + static checks for the `validate-path-windows` justfile
recipe and its wiring into `doctor`.

Why this exists
---------------
On WSL2 the user's policy is "stay inside WSL; do not depend on Windows".
In practice the Windows `PATH` leaks into WSL (`appendWindowsPath=true` is
the WSL default), so dozens of `/mnt/<drive>/...` directories end up on
`$PATH` as silent fallbacks. Today the WSL-native tools win by ordering,
but a single reorder would fall through to a Windows binary — which under
interop-off WSL either fails to exec or misbehaves. We want `just doctor`
to surface this contamination mechanically instead of relying on memory.

`validate-path-windows` mirrors the sibling `validate-path-duplicates`:
it scans `${VALIDATE_PATH:-$PATH}` (the `VALIDATE_PATH` override is the
test injection point), prints offending entries, and exits 2 on findings
so `doctor` can render it as a WARN.

These tests run host-side with no Docker (part of `tests/unit/`, gated by
`just ci` and `unit-test.yaml`), so they honour the WSL-only constraint.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
JUSTFILE = ROOT / "justfile"


@pytest.fixture
def just_binary() -> str:
    just = shutil.which("just")
    if just is None:
        pytest.skip("just not on PATH")
    return just


def _run_validator(
    just_binary: str, validate_path: str
) -> subprocess.CompletedProcess[str]:
    """Invoke the real repo recipe with a crafted PATH to scan.

    `PATH` here only lets `just`/bash/coreutils resolve; the scanned value
    is injected via `VALIDATE_PATH` (never touching the real `$PATH`).
    """
    env = {
        "PATH": f"{os.path.dirname(just_binary)}:/usr/bin:/bin:/usr/local/bin",
        "HOME": os.environ.get("HOME", "/root"),
        "VALIDATE_PATH": validate_path,
    }
    return subprocess.run(
        [just_binary, "-f", str(JUSTFILE), "validate-path-windows"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_flags_windows_drive_leak(just_binary: str) -> None:
    """A `/mnt/<drive>/...` entry is Windows contamination -> exit 2 and
    the offending path is surfaced."""
    result = _run_validator(just_binary, "/usr/bin:/mnt/c/Windows/System32:/bin")
    combined = result.stdout + result.stderr
    assert result.returncode == 2, (
        f"expected exit 2 on Windows leak, got {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "/mnt/c/Windows/System32" in combined, (
        f"expected the offending entry in output; got:\n{combined}"
    )


def test_clean_path_passes(just_binary: str) -> None:
    """A PATH with no `/mnt/<drive>` entries is clean -> exit 0."""
    result = _run_validator(just_binary, "/usr/bin:/bin:/usr/local/bin")
    assert result.returncode == 0, (
        f"expected exit 0 on clean PATH, got {result.returncode}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_mnt_wsl_is_not_windows(just_binary: str) -> None:
    """`/mnt/wsl/...` is a WSL-internal mount, NOT a Windows drive. It must
    not be flagged (guards against a false positive that would cry wolf)."""
    result = _run_validator(just_binary, "/usr/bin:/mnt/wsl/some/tool:/bin")
    assert result.returncode == 0, (
        f"/mnt/wsl must not be flagged as Windows contamination; "
        f"got exit {result.returncode}.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_doctor_wires_in_windows_check() -> None:
    """`doctor` must invoke the validator so contamination actually shows up
    in its summary — the recipe existing but unwired would be a silent gap."""
    text = JUSTFILE.read_text()
    assert "\nvalidate-path-windows:" in text, (
        "recipe validate-path-windows not defined"
    )
    assert "just validate-path-windows" in text, (
        "doctor does not call `just validate-path-windows`; contamination "
        "would never surface in `just doctor`."
    )
