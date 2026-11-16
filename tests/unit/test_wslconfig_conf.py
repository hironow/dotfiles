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
import re
import shutil
from pathlib import Path

from _bash_hook import bash_path, run_bash

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "config" / "wsl" / "wslconfig"
SCRIPT = ROOT / "scripts" / "wslconfig_conf.sh"
JUSTFILE = ROOT / "justfile"


def test_template_exists_with_the_safe_subset() -> None:
    assert TEMPLATE.is_file(), "config/wsl/wslconfig template is missing"
    text = TEMPLATE.read_text(encoding="utf-8")
    assert re.search(r"^\s*autoMemoryReclaim\s*=\s*gradual", text, re.MULTILINE), (
        "the template must set autoMemoryReclaim=gradual."
    )


def test_template_does_not_spread_risky_or_rejected_keys() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert not re.search(r"^\s*sparseVhd\s*=", text, re.MULTILINE), (
        "sparseVhd must not ship in the template: this repo does not turn "
        "sparse on (ADR 0035); an already-sparse vhdx works without it."
    )
    assert "sparseVhd" in text, (
        "the template must explain WHY sparseVhd is absent, or the next "
        "editor re-adds it from the trade box's local file."
    )
    assert not re.search(r"^\s*vmIdleTimeout\s*=", text, re.MULTILINE), (
        "vmIdleTimeout was tested live and does not govern distro lifetime "
        "(the keepalive task does); shipping it would be cargo cult."
    )
    assert not re.search(r"^\s*memory\s*=|^\s*processors\s*=", text, re.MULTILINE), (
        "machine limits are per-host and must stay out of the shared template."
    )


def test_advisor_never_self_applies() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--shutdown" in text, (
        "the advisor must document the wsl --shutdown reload step."
    )
    # Anchored to a line-initial invocation so the printed guidance
    # (`echo "  wsl --shutdown"`) does not false-positive.
    assert not re.search(r"^\s*wsl(\.exe)?\s+--shutdown", text, re.MULTILINE), (
        "the advisor must not execute `wsl --shutdown` itself — it takes the "
        "self-hosted runner offline without asking."
    )
    assert not re.search(r"^\s*[^#]*(>|>>)\s*\"?\$\{?conf", text, re.MULTILINE), (
        "the advisor must not write the live .wslconfig; it previews and "
        "prints the apply steps only."
    )


def test_justfile_wires_wslconfig() -> None:
    text = JUSTFILE.read_text(encoding="utf-8")
    assert re.search(r"^wslconfig:", text, re.MULTILINE), (
        "justfile must define a `wslconfig` recipe that surfaces the template."
    )
    assert "config/wsl/wslconfig" in text or "wslconfig_conf.sh" in text, (
        "the wslconfig recipe must reference the template or its advisor script."
    )


def test_optional_networking_keys_ship_commented_only() -> None:
    """networkingMode=mirrored (+ dnsTunneling / autoProxy) are modern
    recommendations but environment-sensitive: mirrored needs Win11 22H2+ and
    some VPN stacks break under it. They ship as a commented-out optional
    block — documented, never active by default."""
    text = TEMPLATE.read_text(encoding="utf-8")
    for key in ("networkingMode", "dnsTunneling", "autoProxy"):
        assert key in text, f"the template must document the optional {key} key."
        assert not re.search(rf"^\s*{key}\s*=", text, re.MULTILINE), (
            f"{key} must stay commented out: it is environment-sensitive and "
            "must be an explicit local opt-in."
        )


def test_advisor_flags_live_misconfigurations() -> None:
    """The advisor must catch the two live misconfigurations found on the
    trade box (2026-08-20), not just missing recommended keys:

    - localhostForwarding=true under networkingMode=mirrored is ignored and
      makes every wsl.exe invocation print a warning.
    - sparseVhd=true turns sparse on for new disks in WSL 3.0.2+, which this
      repo does not do (ADR 0035).
    """
    text = SCRIPT.read_text(encoding="utf-8")
    assert "localhostForwarding" in text and "mirrored" in text, (
        "the advisor must warn when localhostForwarding coexists with "
        "networkingMode=mirrored (the combination is ignored + noisy)."
    )
    assert "sparseVhd" in text, (
        "the advisor must warn when the live file carries the sparseVhd key."
    )


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
