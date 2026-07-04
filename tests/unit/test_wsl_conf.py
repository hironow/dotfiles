"""The repo ships a recommended `/etc/wsl.conf` and a `just wsl-conf`
advisor, so bare-WSL provisioning of the interop/systemd settings is
discoverable instead of tribal knowledge.

WSL machine provisioning needs `appendWindowsPath=false` (keep the Windows
PATH from shadowing WSL-native tools — see `just validate-path-windows`) and
`systemd=true` (native docker / service manager). `/etc/wsl.conf` is root-
owned and its reload needs a Windows-side `wsl --shutdown`, so the recipe is
an advisor (preview + sudo steps), not a self-applying mutation.

Static assertions, host-side (tests/unit/), so they run in `just ci`.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "config" / "wsl" / "wsl.conf"
JUSTFILE = ROOT / "justfile"


def test_template_exists_and_hardens() -> None:
    assert TEMPLATE.is_file(), "config/wsl/wsl.conf template is missing"
    text = TEMPLATE.read_text()
    assert re.search(r"^\s*appendWindowsPath\s*=\s*false", text, re.MULTILINE), (
        "wsl.conf template must set appendWindowsPath=false (no Windows PATH leak)."
    )
    assert re.search(r"^\s*systemd\s*=\s*true", text, re.MULTILINE), (
        "wsl.conf template must set systemd=true (native docker / service manager)."
    )


def test_justfile_wires_wsl_conf() -> None:
    text = JUSTFILE.read_text()
    assert re.search(r"^wsl-conf:", text, re.MULTILINE), (
        "justfile must define a `wsl-conf` recipe that surfaces the template."
    )
    assert "config/wsl/wsl.conf" in text, (
        "the wsl-conf recipe must reference the config/wsl/wsl.conf template."
    )
