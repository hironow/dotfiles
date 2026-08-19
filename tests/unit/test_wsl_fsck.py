"""wsl_fsck.sh — WSL ext4-corruption diagnosis + repair runbook (ADR 0035).

Born from a live incident (2026-08-19): the WSL Ubuntu distro failed to boot
with "An error occurred mounting the distribution disk, it was mounted
read-only as a fallback" — dmesg showed `EXT4-fs error … bad block bitmap
checksum` and the kernel remounted `/` read-only, after which WSL papered over
it with a tmpfs overlay. The distro LOOKS half-alive, so the fault needs a
named diagnosis and an exact, safe repair runbook.

Like wsl_compact.sh, the script is ADVISORY: the repair needs `wsl --shutdown`
(runner offline) plus an elevated `wsl --mount`, and misidentifying the device
or fsck-ing a mounted filesystem destroys data. The script therefore only
diagnoses and prints the runbook; a human executes it with eyes on the output.

Static text assertions, matching tests/unit/test_runner_gc.py.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
FSCK = SCRIPTS / "wsl_fsck.sh"
DOCTOR = SCRIPTS / "doctor.sh"


def _text() -> str:
    return FSCK.read_text(encoding="utf-8")


def test_fsck_stays_advisory() -> None:
    """Repair kills the runner and rewrites the filesystem; never self-apply."""
    text = _text()
    assert "--shutdown" in text, "the runbook must document the shutdown."
    assert not re.search(r"^\s*[^#]*wsl\.exe --shutdown", text, re.M), (
        "wsl_fsck.sh must not execute `wsl --shutdown` itself."
    )
    for line in text.splitlines():
        if "wsl.exe" in line:
            assert not re.search(r"e2fsck -f", line), (
                "wsl_fsck.sh must not run e2fsck itself — a misidentified "
                "device or a still-mounted filesystem turns the repair into "
                f"the disaster: {line!r}"
            )


def test_fsck_uses_the_shared_vhdx_resolver() -> None:
    text = _text()
    assert "wsl_vhdx_path" in text and "wsl_vhdx_lib.sh" in text, (
        "wsl_fsck.sh must resolve the vhdx via wsl_vhdx_lib.sh, not a directory walk."
    )
    assert "head -1" not in text


def test_detection_is_mount_state_not_dmesg() -> None:
    """dmesg is VM-global, volatile across shutdown, and root-gated.

    The read-only fallback is authoritatively visible in the mount table: `/`
    on overlay/tmpfs, or mounted ro. dmesg may corroborate but must not be the
    primary signal.
    """
    text = _text()
    assert "findmnt" in text, (
        "detect the fallback from the root mount state (findmnt), not dmesg."
    )
    assert re.search(r"overlay", text), "an overlay root IS the fallback."


def test_wsl_invocations_disable_msys_conversion_and_pin_the_distro() -> None:
    """MSYS rewrites `/`-args before wsl.exe sees them, and a bare wsl.exe
    call boots the DEFAULT distro — which may be the corrupted one."""
    # join backslash-continuations so a guard on the first physical line counts
    text = re.sub(r"\\\n\s*", " ", _text())
    for line in text.splitlines():
        if (
            re.search(r"^\s*[^#]*\bwsl\.exe\b", line)
            and "--" not in line.split("wsl.exe")[0]
        ):
            assert "MSYS_NO_PATHCONV" in line or "MSYS2_ARG_CONV_EXCL" in line, (
                f"wsl.exe call without path-conversion guard: {line!r}"
            )
            assert re.search(r"-d\s", line) or "--list" in line or "-l" in line, (
                f"wsl.exe call must pin a distro with -d (or be a --list): {line!r}"
            )


def test_wsl_list_output_is_denulled() -> None:
    """wsl.exe -l prints UTF-16LE + CRLF; without stripping NULs every distro
    name is mangled and never matches."""
    text = _text()
    for line in text.splitlines():
        if re.search(r"wsl\.exe\s+(-l|--list)", line):
            assert re.search(r"tr -d '\\+0", line.replace('"', "'")) or "\\0" in line, (
                f"wsl.exe list output must strip NUL bytes: {line!r}"
            )


def test_helper_selection_excludes_docker_and_wsl1() -> None:
    """docker-desktop distros are not general-purpose, and WSL1 distros have
    no VM block-device access, so neither can host the e2fsck."""
    text = _text()
    assert "docker-desktop" in text, "exclude docker-desktop distros."
    assert re.search(r"-l\s+-v|--list\s+--verbose", text), (
        "helper candidates must come from `wsl -l -v` so WSL1 distros can be "
        "filtered by the VERSION column."
    )


def test_runbook_covers_the_dangerous_steps() -> None:
    """The runbook IS the product; each step below prevents a lived or
    reviewed failure mode."""
    text = _text()
    # Own the VM with the helper BEFORE mounting: a bare `wsl --mount` with no
    # VM running boots the DEFAULT distro — possibly the corrupted target.
    assert text.index("-e true") < text.index("--vhd --bare"), (
        "start the helper (-e true) before the bare attach — a bare wsl call "
        "with no VM running boots the DEFAULT distro."
    )
    assert "--bare" in text, "attach without auto-mounting."
    assert "lsblk" in text, (
        "identify the device by lsblk set-difference (before/after the "
        "attach), never by guessing sdX."
    )
    assert "/proc/mounts" in text or "findmnt" in text, (
        "prove the device is unmounted before fsck."
    )
    assert "e2fsck -fn" in text and "e2fsck -fy" in text, (
        "dry-run (-fn) first, then repair (-fy) as an informed decision."
    )
    assert "--unmount" in text, "ALWAYS unmount — a stuck attach blocks WSL."
    assert "--export" in text, (
        "when no WSL2 helper exists or e2fsck fails, export/import is the "
        "fallback; the no-helper branch must not dead-end."
    )


def test_doctor_advises_wsl_fsck_without_booting_wsl() -> None:
    """doctor must surface the read-only fallback on already-running distros
    only — starting WSL as a diagnostic side effect is not acceptable."""
    text = DOCTOR.read_text(encoding="utf-8")
    assert "wsl-fsck" in text, "doctor must point at `just wsl-fsck`."
    assert "--running" in text, (
        "doctor may only inspect distros that are already running."
    )


def test_ro_detection_ignores_errors_remount_ro() -> None:
    """A HEALTHY root reads `ext4 rw,relatime,…,errors=remount-ro,…` — naive
    substring/glob matching on 'ro' flags every healthy distro as corrupted.

    The mount state must be judged on the FIRST option (rw/ro), never by
    searching the whole option string.
    """
    for path in (FSCK, DOCTOR):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"ext4\*ro", text) and not re.search(
            r"ext4.*\*ro,?\*", text
        ), (
            f"{path.name}: glob '*ro*' also matches 'errors=remount-ro'; "
            "judge the leading rw/ro option instead."
        )
