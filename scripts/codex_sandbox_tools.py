#!/usr/bin/env python3
"""Let Codex's Windows sandbox run the tools mise installs, rtk above all.

Codex's elevated Windows sandbox runs commands as separate users and reaches
the profile through inheritable CodexSandboxUsers:(RX) entries it sets on the
profile's top directories (codex-rs windows-sandbox-rs setup). A directory that
does not inherit keeps those users out. %LOCALAPPDATA%\\mise was one, so every
mise tool was "access denied" in the sandbox and each command the rtk hook
rewrote to `rtk ...` failed. Turning its inheritance back on gives it the same
entries as its siblings and nothing more; `icacls <dir> /inheritance:r` undoes it.

Usage: codex_sandbox_tools.py [--check]   (--check reports without changing)
Prints a doctor-style OK/WARN line; exit 1 while the sandbox cannot run mise
tools. Windows only: elsewhere Codex's sandbox reads the whole disk.
"""

from collections.abc import Sequence
import os
from pathlib import Path
import subprocess
import sys

SANDBOX_GROUP = "CodexSandboxUsers"


# ---- Functional core ----


def state(parent_acl: str, acl: str) -> str:
    """'absent' (no elevated sandbox), 'readable' or 'blocked', from icacls output."""
    if SANDBOX_GROUP not in parent_acl:
        return "absent"
    return "readable" if SANDBOX_GROUP in acl else "blocked"


def message(current: str, directory: str) -> tuple[str, str]:
    if current == "blocked":
        return (
            "WARN",
            f"{directory} does not inherit the {SANDBOX_GROUP} read access, so rtk and "
            "every mise tool fail inside Codex's sandbox: just codex-sandbox-tools",
        )
    if current == "absent":
        return ("OK", "Codex's elevated sandbox is not set up; nothing to reach")
    return ("OK", "Codex's sandbox can run mise tools")


# ---- Imperative shell ----


def _acl(path: Path) -> str:
    return subprocess.run(
        ["icacls", str(path)],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    ).stdout


def main(argv: Sequence[str]) -> int:
    if sys.platform != "win32":
        return 0
    directory = Path(
        os.environ.get("MISE_DATA_DIR") or Path(os.environ["LOCALAPPDATA"]) / "mise"
    )
    if not directory.is_dir():
        print(f"OK   codex-sandbox - no mise data dir at {directory}")
        return 0
    current = state(_acl(directory.parent), _acl(directory))
    if current == "blocked" and "--check" not in argv:
        subprocess.run(
            ["icacls", str(directory), "/inheritance:e", "/Q"],
            capture_output=True,
            check=False,
        )
        current = state(_acl(directory.parent), _acl(directory))
        if current == "readable":
            print(f"OK   codex-sandbox - {directory} inherits again")
    level, detail = message(current, str(directory))
    print(f"{level:<4} codex-sandbox - {detail}")
    return 1 if current == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
