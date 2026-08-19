"""The repo ships a recommended Windows-side `%USERPROFILE%\\.wslconfig`
template and a `just wslconfig` advisor, mirroring config/wsl/wsl.conf +
`just wsl-conf` for the distro side.

What belongs in the template is shaped by live findings on the trade box
(2026-08-20):

- `autoMemoryReclaim=gradual` is safe to share.
- `sparseVhd=true` is deliberately ABSENT: Microsoft disabled sparse
  conversion over data-corruption risk (`wsl --manage --set-sparse` demands
  `--allow-unsafe`). A vhdx that is already sparse keeps working and fstrim
  returns space without this key — shipping it would spread the risk to
  every new machine.
- `vmIdleTimeout` is deliberately ABSENT: tested live, it does not govern
  distro lifetime (the keepalive task in wsl_autostart.ps1 does).
- Machine limits (`[wsl2] memory=`, `processors=`) stay local.

`.wslconfig` reload needs `wsl --shutdown`, which takes the self-hosted
runner offline — so the recipe is an advisor (diff + apply steps), never a
self-applying mutation.

Static assertions, host-side (tests/unit/), so they run in `just ci`.
"""

from __future__ import annotations

import re
from pathlib import Path

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
        "sparseVhd must not ship in the template: Microsoft disabled sparse "
        "conversion over data-corruption risk; an already-sparse vhdx works "
        "without it."
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
