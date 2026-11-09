"""`just ca-os-bundle-apply` hands both hashes of the candidate run to ca-doctor.

`ca-doctor os-bundle --apply` replaces macOS's /private/etc/ssl/cert.pem only
when the input's and the candidate's SHA-256 are the ones the candidate run
printed (docs/runbook/ca-doctor.md). `just --dry-run` prints each recipe's
commands without running them, so no sudo and no build run here. The recipes
are macOS's.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = [
    pytest.mark.skipif(shutil.which("just") is None, reason="just is not installed"),
    pytest.mark.skipif(sys.platform != "darwin", reason="the recipes are macOS's"),
]


def _dry_run(*args: str) -> str:
    result = subprocess.run(
        ["just", "--dry-run", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stderr


def test_apply_passes_each_hash_to_its_flag() -> None:
    input_sha, candidate_sha = "a" * 64, "b" * 64
    commands = _dry_run("ca-os-bundle-apply", input_sha, candidate_sha)
    assert (
        "sudo output/ca-doctor/ca-doctor os-bundle --source tools/ca-doctor" in commands
    )
    assert f"--expect-sha256 {input_sha}" in commands
    assert f"--expect-out-sha256 {candidate_sha}" in commands
    assert "--in /private/etc/ssl/cert.pem --apply" in commands
    assert '--backup "/private/etc/ssl/cert.pem.dotfiles-backup-' in commands


def test_candidate_writes_beside_the_bundle_and_never_applies() -> None:
    commands = _dry_run("ca-os-bundle-candidate")
    assert (
        "--in /private/etc/ssl/cert.pem --out output/ca-os-bundle/cert.pem" in commands
    )
    assert "--apply" not in commands
    assert "sudo" not in commands
