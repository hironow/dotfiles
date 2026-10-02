#!/usr/bin/env python3
"""Re-vendor rtk's Pi extension from the installed rtk (`just rtk-pi-refresh`).

After an rtk upgrade its own Pi extension may change. The installed rtk writes
it into a throwaway PI_CODING_AGENT_DIR (`rtk init -g --agent pi`); this keeps
config/pi/extensions/rtk.ts's header, bumps the version in it, and replaces the
body below the sentinel with the new upstream file, verbatim.
"""

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from ai_tools_check import vendored_version
from install_pi_extensions import VENDORED_SENTINEL

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "config/pi/extensions/rtk.ts"


def vendored(current: str, version: str, upstream: str) -> str:
    """Functional core: the new vendored file from the old one and rtk's output."""
    header, sentinel, _old = current.partition(VENDORED_SENTINEL)
    if not sentinel:
        raise ValueError(f"{TARGET} has no '{VENDORED_SENTINEL.strip()}' line")
    header = re.sub(
        r"Vendored from rtk \d+\.\d+\.\d+", f"Vendored from rtk {version}", header
    )
    return header + sentinel + upstream


def main() -> int:
    current = TARGET.read_text(encoding="utf-8")
    version_out = subprocess.run(
        ["rtk", "--version"],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    version = re.search(r"\d+\.\d+\.\d+", version_out)
    if not version:
        raise SystemExit(f"cannot read rtk's version from {version_out!r}")
    with tempfile.TemporaryDirectory() as agent_dir:
        env = {
            **os.environ,
            "PI_CODING_AGENT_DIR": agent_dir,
            "RTK_TELEMETRY_DISABLED": "1",
        }
        subprocess.run(
            ["rtk", "init", "-g", "--agent", "pi"],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
        )
        upstream = (Path(agent_dir) / "extensions/rtk.ts").read_text(encoding="utf-8")
    TARGET.write_text(
        vendored(current, version[0], upstream), encoding="utf-8", newline="\n"
    )
    print(
        f"{TARGET.relative_to(ROOT).as_posix()}: rtk {vendored_version(current)} -> {version[0]}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
