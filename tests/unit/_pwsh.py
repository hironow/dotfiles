"""Which PowerShell a test runs, and what that PowerShell says it is."""

from __future__ import annotations

import shutil
import subprocess


def resolve_pwsh(environ, which=shutil.which):
    """The PowerShell the replays run: PODMAN_GC_TEST_PWSH, else pwsh on PATH.

    An override that is not an executable stops the run; it never turns the
    PowerShell cases into skips.
    """
    override = environ.get("PODMAN_GC_TEST_PWSH")
    if override is None:
        return which("pwsh")
    found = which(override)
    if found is None:
        raise RuntimeError(f"PODMAN_GC_TEST_PWSH={override!r} is not an executable")
    return found


def powershell_identity(pwsh):
    """Version and edition, from the runtime itself."""
    proc = subprocess.run(
        [
            pwsh,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "'{0} {1}' -f $PSVersionTable.PSVersion, $PSVersionTable.PSEdition",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0 and not proc.stderr, (pwsh, proc.stdout, proc.stderr)
    return proc.stdout.strip()
