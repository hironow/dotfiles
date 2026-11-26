"""The native Windows runner SERVICE must be repo-managed, like the WSL leg.

Found live (2026-08-20): service `actions.runner.example-org.gpu-win` sat
Stopped + StartType=Disabled for an unknown stretch — GitHub showed the
runner offline and nothing on the host said so. The install/restart helpers
lived as ad-hoc scripts inside the runner directory (unversioned, host
hard-coded), so every machine reinvents them and none of the status tooling
knows the service exists.

History that shapes the requirements (see memory/ADR 0035 context):
- The service runs as **LocalSystem**, whose PATH is the *Machine* PATH.
  This box needed three Machine PATH appends (scoop shims, .bun\\bin, mise
  shims) before jobs could find their tools — the "PATH onion". The installer
  must verify those entries and point at scripts/restore_machine_path.ps1,
  not silently install a runner whose jobs die on `command not found`.
- PowerShell 5.1 reads a BOM-less UTF-8 script as ANSI, so the ps1 payloads
  must stay ASCII-only to survive a cp932 console.
- Service creation needs Administrator; the repo convention is UAC
  self-elevation (Start-Process -Verb RunAs, exit with the child's code),
  as in scripts/restore_machine_path.ps1.

Static text assertions, matching tests/unit/test_runner_gc.py.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
SVC = SCRIPTS / "install_runner_svc_win.ps1"


RESTART = SCRIPTS / "restart_runner_svc_win.ps1"


def test_installer_exists() -> None:
    assert SVC.is_file(), "scripts/install_runner_svc_win.ps1 is missing"
    assert RESTART.is_file(), "scripts/restart_runner_svc_win.ps1 is missing"
    # ASCII-only is covered by the glob test in test_runner_gc.py.
