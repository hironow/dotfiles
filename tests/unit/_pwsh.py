"""Which PowerShell a test runs, and what that PowerShell says it is."""

from __future__ import annotations

import shutil
import subprocess


def resolve_pwsh(environ, which=shutil.which):
    """The PowerShell the tests run: an override, else pwsh on PATH.

    DOTFILES_TEST_PWSH is the override; PODMAN_GC_TEST_PWSH, which the GC
    compatibility workflow sets, is its older name. Set DOTFILES_TEST_PWSH to
    powershell.exe to test Windows PowerShell 5.1, which runs the GC and
    `just podman-install`. An override that is not an executable stops the
    run; it never turns the PowerShell cases into skips.
    """
    for name in ("DOTFILES_TEST_PWSH", "PODMAN_GC_TEST_PWSH"):
        override = environ.get(name)
        if override is None:
            continue
        found = which(override)
        if found is None:
            raise RuntimeError(f"{name}={override!r} is not an executable")
        return found
    return which("pwsh")


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
