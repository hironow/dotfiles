"""The repo ships a recommended Windows-side `%USERPROFILE%\\.wslconfig`
template and a `just wslconfig` advisor, mirroring config/wsl/wsl.conf +
`just wsl-conf` for the distro side.

What belongs in the template is shaped by live findings on the trade box
(2026-08-20):

- `autoMemoryReclaim=gradual` is safe to share.
- `sparseVhd=true` is deliberately ABSENT (ADR 0035): up to WSL 3.0.1 the
  key is forced off over data corruption; from 3.0.2 (microsoft/WSL#41726)
  it makes every new vhdx sparse, still experimental. A vhdx that is already
  sparse keeps working and fstrim returns space without this key — shipping
  it would spread the experiment to every new machine.
- `vmIdleTimeout` is deliberately ABSENT: tested live, it does not govern
  distro lifetime (the keepalive task in wsl_autostart.ps1 does).
- Machine limits (`[wsl2] memory=`, `processors=`) stay local.

`.wslconfig` reload needs `wsl --shutdown`, which takes the self-hosted
runner offline — so the recipe is an advisor (diff + apply steps), never a
self-applying mutation.

Static assertions, host-side (tests/unit/), so they run in `just ci`.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from _bash_hook import bash_path, run_bash

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "config" / "wsl" / "wslconfig"
SCRIPT = ROOT / "scripts" / "wslconfig_conf.sh"


def _advise(tmp_path: Path, live: str) -> tuple[str, Path, Path]:
    """Run the advisor against a live .wslconfig in a scratch tree.

    `wsl` and `wsl.exe` are fakes that only record their arguments, so a run
    that tried to reload WSL shows in the log instead of stopping the runner.
    Returns the output, the live file and the call log.
    """
    (tmp_path / "config" / "wsl").mkdir(parents=True)
    shutil.copy(TEMPLATE, tmp_path / "config" / "wsl" / "wslconfig")
    (tmp_path / "home").mkdir()
    conf = tmp_path / "home" / ".wslconfig"
    conf.write_text(live, encoding="utf-8", newline="\n")
    calls = tmp_path / "wsl-calls.log"
    fakes = tmp_path / "fakes.sh"
    fakes.write_text(
        "uname() { echo MINGW64_NT-10.0-26300; }\n"
        "cygpath() { echo home; }\n"
        f'wsl() {{ echo "wsl $*" >> "{bash_path(calls)}"; }}\n'
        f'wsl.exe() {{ echo "wsl.exe $*" >> "{bash_path(calls)}"; }}\n',
        encoding="utf-8",
        newline="\n",
    )
    env = {**os.environ, "BASH_ENV": bash_path(fakes), "USERPROFILE": "unused"}
    proc = run_bash(
        SCRIPT,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return proc.stdout, conf, calls


def test_advisor_warns_on_the_two_live_misconfigurations(tmp_path: Path) -> None:
    """The two misconfigurations found live on the trade box (2026-08-20):
    localhostForwarding under networkingMode=mirrored is ignored and makes
    every wsl.exe call print a warning; sparseVhd turns sparse on for new
    disks in WSL 3.0.2+, which this repo does not do (ADR 0035)."""
    out, _, _ = _advise(
        tmp_path,
        "[wsl2]\nnetworkingMode=mirrored\nlocalhostForwarding=true\n"
        "[experimental]\nautoMemoryReclaim=gradual\nsparseVhd=true\n",
    )
    assert "localhostForwarding is IGNORED under networkingMode=mirrored" in out, out
    assert "sparseVhd is set" in out, out


def test_advisor_leaves_localhost_forwarding_alone_without_mirrored(
    tmp_path: Path,
) -> None:
    out, _, _ = _advise(
        tmp_path,
        "[wsl2]\nlocalhostForwarding=true\n[experimental]\nautoMemoryReclaim=gradual\n",
    )
    assert "IGNORED" not in out, out
    assert "already carries the recommended keys" in out, out


def test_advisor_never_applies_anything_itself(tmp_path: Path) -> None:
    """Reloading .wslconfig needs `wsl --shutdown`, which takes the
    self-hosted runner offline: the advisor prints the step and never runs
    it, and never writes the live file."""
    live = "[wsl2]\nnetworkingMode=mirrored\nlocalhostForwarding=true\n"
    out, conf, calls = _advise(tmp_path, live)
    assert "wsl --shutdown" in out, out
    assert conf.read_text(encoding="utf-8") == live
    assert not calls.exists(), calls.read_text(encoding="utf-8")


def test_sparsevhd_warning_states_what_the_key_does_per_wsl_version(
    tmp_path: Path,
) -> None:
    """The key is not dead: WSL 3.0.2+ (microsoft/WSL#41726) makes every NEW
    distro vhdx sparse when it is set; earlier builds forced sparse off while
    data corruption was debugged. The warning must say that, not "does nothing"."""
    (tmp_path / "config" / "wsl").mkdir(parents=True)
    shutil.copy(TEMPLATE, tmp_path / "config" / "wsl" / "wslconfig")
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / ".wslconfig").write_text(
        "[experimental]\nautoMemoryReclaim=gradual\nsparseVhd=true\n", encoding="utf-8"
    )
    fakes = tmp_path / "fakes.sh"
    fakes.write_text(
        "uname() { echo MINGW64_NT-10.0-26300; }\ncygpath() { echo home; }\n",
        encoding="utf-8",
        newline="\n",
    )
    env = {**os.environ, "BASH_ENV": bash_path(fakes), "USERPROFILE": "unused"}
    proc = run_bash(
        SCRIPT,
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    out = proc.stdout
    assert "sparseVhd" in out, out
    assert "dead key" not in out and "does nothing" not in out, out
    assert "3.0.2" in out and "41726" in out, out
    assert "ADR 0035" in out, out
