"""`just wsl-compact` must tell a sparse vhdx from a non-sparse one, and say
who else can open it.

Why this exists
---------------
On 2026-11-17 `wsl --manage --move` to D: dropped the vhdx's sparse flag, yet
`just wsl-compact` printed "sparse: yes": it grepped localised `fsutil` output
for the word "sparse", which the English "This file is NOT set as sparse"
contains too. For a sparse vhdx it also printed diskpart steps, which diskpart
refuses ("must not be sparse") after the runner has already been stopped.
The same move let the volume's inherited ACL hand the vhdx (the whole distro,
runner credentials included) to every local user, and nothing said so.

The script runs against bash-function fakes loaded through BASH_ENV, proven in
force before each run (tests/unit/_bash_fakes.py). The PowerShell fact reader
is exercised for real on Windows only.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from _bash_fakes import require_bash_fakes
from _bash_hook import bash_path, resolve_bash, run_bash

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
COMPACT = SCRIPTS / "wsl_compact.sh"
VHDX_LIB = SCRIPTS / "wsl_vhdx_lib.sh"

GIB = 1024**3
USER = "S-1-5-21-1111-2222-3333-1001"
# The ACEs measured on this host's vhdx: the user, SYSTEM and Administrators
# (inherited), plus the ones WSL adds for its VM and its AppContainer.
TRUSTED_ACES = (
    "S-1-5-83-1-1023668523-1252250600-4291834010-2935368367",
    "S-1-15-3-1024-2268835264-3721307629-241982045-173645152-1490879176-104643441-2915960892-1612460704",
    "S-1-5-32-544",
    "S-1-5-18",
    USER,
)
FAKES = (
    "uname",
    "reg.exe",
    "cygpath",
    "stat",
    "du",
    "wsl.exe",
    "powershell.exe",
    "fsutil",
)
LAUNCHERS = ("wsl.exe", "powershell.exe", "reg.exe", "fsutil")

FAKE_LAYER = r"""
uname() { echo MINGW64_NT-10.0-26300; }
reg.exe() {
  case "$*" in
    *"/v DistributionName"*) printf '    DistributionName    REG_SZ    %s\r\n' "$FAKE_DISTRO" ;;
    *"/v BasePath"*) printf '    BasePath    REG_SZ    D:\\wsl\\Ubuntu\r\n' ;;
    *"/v VhdFileName"*)
      [ -n "${FAKE_VHDX_NAME:-}" ] || return 1
      printf '    VhdFileName    REG_SZ    %s\r\n' "$FAKE_VHDX_NAME" ;;
    *) printf 'HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Lxss\\{dd4a2d94}\r\n' ;;
  esac
}
cygpath() {
  case "$1" in
    -u) echo disk ;;
    -w) case "$2" in disk) echo 'D:\wsl\Ubuntu' ;; *) echo 'D:\wsl\Ubuntu\ext4.vhdx' ;; esac ;;
    *) return 1 ;;
  esac
}
stat() { echo "$FAKE_LOGICAL"; }
du() { printf '%s\t%s\n' "$FAKE_ONDISK" "$3"; }
wsl.exe() { echo "${FAKE_USED_GB}G"; }
powershell.exe() {
  [ "$FAKE_FACTS" = "FAIL" ] && return 1
  printf '%b' "$FAKE_FACTS"
}
fsutil() { : > fsutil-called; echo 'This file is NOT set as sparse'; }
"""


def facts(
    sparse: str = "0", allow: tuple[str, ...] = TRUSTED_ACES, owner: str = USER
) -> str:
    lines = [f"sparse {sparse}", f"user {USER}", f"owner {owner}"]
    lines += [f"allow {sid}" for sid in allow]
    return "\\r\\n".join(lines) + "\\r\\n"


def run_compact(
    tmp_path: Path,
    *,
    fact_lines: str,
    logical_gb: int = 227,
    ondisk_gb: int = 227,
    used_gb: int = 56,
    distro: str = "Ubuntu",
    vhdx_name: str = "",
) -> subprocess.CompletedProcess[str]:
    (tmp_path / "disk").mkdir(exist_ok=True)
    (tmp_path / "disk" / (vhdx_name or "ext4.vhdx")).write_text("", encoding="utf-8")
    layer = tmp_path / "fakes.sh"
    layer.write_text(FAKE_LAYER, encoding="utf-8", newline="\n")
    bash_dir = Path(resolve_bash()).parent
    env = {
        "PATH": ":".join(
            bash_path(p)
            for p in (
                bash_dir,
                bash_dir.parent / "usr/bin",
                Path("/usr/bin"),
                Path("/bin"),
            )
        ),
        "HOME": bash_path(tmp_path),
        "BASH_ENV": bash_path(layer),
        "FAKE_DISTRO": "Ubuntu" if distro == "Ubuntu" else distro,
        "RUNNER_GC_WSL_DISTRO": "Ubuntu",
        "FAKE_VHDX_NAME": vhdx_name,
        "FAKE_LOGICAL": str(logical_gb * GIB),
        "FAKE_ONDISK": str(ondisk_gb * GIB),
        "FAKE_USED_GB": str(used_gb),
        "FAKE_FACTS": fact_lines,
        "MSYS_NO_PATHCONV": "1",
        "MSYS2_ARG_CONV_EXCL": "*",
    }
    require_bash_fakes(tmp_path, env, FAKES, LAUNCHERS)
    return run_bash(
        COMPACT,
        cwd=tmp_path,
        companions=(VHDX_LIB,),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )


def test_non_sparse_is_reported_as_such_even_when_fsutil_speaks_english(
    tmp_path: Path,
) -> None:
    """The English "NOT set as sparse" contains "sparse"; the grep said yes."""
    proc = run_compact(tmp_path, fact_lines=facts(sparse="0"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "sparse    : no" in proc.stdout
    assert "diskpart" in proc.stdout and "compact vdisk" in proc.stdout
    assert "--compact" in proc.stdout and "not verified" in proc.stdout
    assert not (tmp_path / "fsutil-called").exists(), (
        "the verdict must not come from fsutil"
    )


def test_sparse_vhdx_gets_no_diskpart_steps(tmp_path: Path) -> None:
    proc = run_compact(tmp_path, fact_lines=facts(sparse="1"), ondisk_gb=95)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "sparse    : yes" in proc.stdout
    assert "compact vdisk" not in proc.stdout, "diskpart refuses a sparse vhdx"
    assert "refuse" in proc.stdout
    assert "--set-sparse false" in proc.stdout
    assert "~132 GB" in proc.stdout, (
        "logical minus on disk: what turning sparse off can cost"
    )


def test_unreadable_attribute_is_unknown_and_shows_no_steps(tmp_path: Path) -> None:
    proc = run_compact(tmp_path, fact_lines=facts(sparse="?"))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "sparse    : unknown" in proc.stdout
    assert "compact vdisk" not in proc.stdout
    assert "set-sparse false" not in proc.stdout


def test_powershell_failure_is_unknown_not_safe(tmp_path: Path) -> None:
    proc = run_compact(tmp_path, fact_lines="FAIL")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "sparse    : unknown" in proc.stdout
    assert "ACL       : unknown" in proc.stdout


def test_trusted_acl_is_quiet(tmp_path: Path) -> None:
    proc = run_compact(tmp_path, fact_lines=facts())
    assert "WARN" not in proc.stdout, proc.stdout
    assert "ACL       : only" in proc.stdout


@pytest.mark.parametrize(
    "extra",
    ["S-1-5-11", "S-1-5-32-545", "S-1-5-21-1111-2222-3333-1009"],
)
def test_untrusted_ace_warns_with_its_sid_and_a_folder_fix(
    tmp_path: Path, extra: str
) -> None:
    proc = run_compact(tmp_path, fact_lines=facts(allow=(*TRUSTED_ACES, extra)))
    assert "WARN" in proc.stdout
    assert extra in proc.stdout
    # The fix targets the vhdx's folder: a file-only fix returns with the next vhdx.
    assert re.search(
        r'icacls "D:\\wsl\\Ubuntu" /inheritance:r /grant:r', proc.stdout
    ), proc.stdout


def test_foreign_owner_warns(tmp_path: Path) -> None:
    proc = run_compact(tmp_path, fact_lines=facts(owner="S-1-5-21-1111-2222-3333-1009"))
    assert "WARN" in proc.stdout and "S-1-5-21-1111-2222-3333-1009" in proc.stdout


def test_acl_warning_survives_a_small_slack(tmp_path: Path) -> None:
    """The small-slack early exit must not swallow the ACL warning."""
    proc = run_compact(
        tmp_path,
        fact_lines=facts(allow=(*TRUSTED_ACES, "S-1-5-11")),
        ondisk_gb=60,
        used_gb=56,
    )
    assert "Slack is small" in proc.stdout
    assert "WARN" in proc.stdout and "S-1-5-11" in proc.stdout


def test_unreadable_acl_is_unknown(tmp_path: Path) -> None:
    proc = run_compact(
        tmp_path, fact_lines="sparse 0\\r\\nuser x\\r\\nowner ?\\r\\nallow ?\\r\\n"
    )
    assert "ACL       : unknown" in proc.stdout
    assert "ACL       : only" not in proc.stdout


def test_missing_distro_points_at_the_registry_not_get_location(tmp_path: Path) -> None:
    proc = run_compact(tmp_path, fact_lines=facts(), distro="Debian")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "--get-location" not in proc.stdout
    assert "reg query" in proc.stdout and "Lxss" in proc.stdout


def test_registry_vhdx_file_name_is_honoured(tmp_path: Path) -> None:
    proc = run_compact(tmp_path, fact_lines=facts(), vhdx_name="disk.vhdx")
    assert "No vhdx found" not in proc.stdout, proc.stdout
    assert "disk/disk.vhdx" in proc.stdout


def _untrusted(tmp_path: Path, stdin: str) -> list[str]:
    probe = tmp_path / "probe.sh"
    probe.write_text(
        ". ./wsl_vhdx_lib.sh\nwsl_vhdx_untrusted_sids\n", encoding="utf-8", newline="\n"
    )
    shutil.copy(VHDX_LIB, tmp_path / "wsl_vhdx_lib.sh")
    proc = run_bash(
        probe,
        cwd=tmp_path,
        input=stdin,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.split()


def test_untrusted_sids_allowlist(tmp_path: Path) -> None:
    base = f"user {USER}\nowner {USER}\n" + "".join(
        f"allow {s}\n" for s in TRUSTED_ACES
    )
    assert _untrusted(tmp_path, base) == []
    assert _untrusted(tmp_path, base + "allow S-1-1-0\n") == ["S-1-1-0"]
    # OWNER RIGHTS stands for the owner, not a new principal.
    assert _untrusted(tmp_path, base + "allow S-1-3-4\n") == []
    assert _untrusted(tmp_path, f"user {USER}\nowner ?\nallow ?\n") == ["?"]


@pytest.mark.skipif(
    sys.platform != "win32", reason="reads a real file's attributes and ACL"
)
def test_powershell_facts_survive_a_leaked_pwsh7_module_path(tmp_path: Path) -> None:
    folder = tmp_path / "ディスク"
    folder.mkdir()
    disk = folder / "ext4.vhdx"
    disk.write_bytes(b"\0" * 4096)
    probe = tmp_path / "facts.sh"
    probe.write_text(
        '. ./wsl_vhdx_lib.sh\nwsl_vhdx_facts "$1"\n', encoding="utf-8", newline="\n"
    )
    shutil.copy(VHDX_LIB, tmp_path / "wsl_vhdx_lib.sh")
    env = {**os.environ, "PSModulePath": "C:/nonexistent-powershell7-modules"}

    def read() -> str:
        proc = run_bash(
            probe,
            str(disk),
            cwd=tmp_path,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        return proc.stdout

    before = read()
    assert "\r" not in before
    assert "sparse 0" in before.splitlines()
    assert any(line.startswith("owner S-1-") for line in before.splitlines())
    assert any(line.startswith("allow S-1-5-18") for line in before.splitlines()), (
        before
    )
    subprocess.run(
        ["fsutil", "sparse", "setflag", str(disk)], check=True, capture_output=True
    )
    assert "sparse 1" in read().splitlines()
