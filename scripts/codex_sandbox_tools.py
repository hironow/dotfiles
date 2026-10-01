#!/usr/bin/env python3
"""Let Codex's Windows sandbox run the tools mise installs, rtk above all.

Codex's elevated Windows sandbox runs commands as separate users and reaches
the profile through inheritable CodexSandboxUsers:(RX) entries it sets on the
profile's top directories (codex-rs windows-sandbox-rs setup). A directory that
does not inherit keeps those users out. %LOCALAPPDATA%\\mise was one, so every
mise tool was "access denied" in the sandbox and each command the rtk hook
rewrote to `rtk ...` failed. The fix grants that group read and execute on the
mise dir and nothing more (turning inheritance back on would also import any
other inheritable entry of the parent); `icacls <dir> /remove:g
CodexSandboxUsers` undoes it.

The same entries reach files directly under the profile, so a secret kept in
~/.env is readable in the sandbox; Codex skips ~/.config, where the Jev key
lives. That is reported, never changed: Codex grants the entry again when it
sets its sandbox up, so only moving the secret lasts.

Usage: codex_sandbox_tools.py [--check]   (--check reports without changing)
Prints doctor-style OK/WARN lines; exit 1 on a WARN. Windows only: elsewhere
Codex's sandbox reads the whole disk.
"""

from collections.abc import Sequence
import os
from pathlib import Path
import subprocess
import sys

SANDBOX_GROUP = "CodexSandboxUsers"


# ---- Functional core ----


def state(profile_acl: str, acl: str) -> str:
    """'absent' (no elevated sandbox), 'readable' or 'blocked', from icacls output.

    Codex grants the sandbox group read on the profile itself when it sets the
    sandbox up, so the profile tells whether it exists, wherever mise lives."""
    if SANDBOX_GROUP not in profile_acl:
        return "absent"
    return "readable" if SANDBOX_GROUP in acl else "blocked"


def message(current: str, directory: str) -> tuple[str, str]:
    if current == "blocked":
        return (
            "WARN",
            f"{directory} lacks the {SANDBOX_GROUP} read access, so rtk and "
            "every mise tool fail inside Codex's sandbox: just codex-sandbox-tools",
        )
    if current == "absent":
        return ("OK", "Codex's elevated sandbox is not set up; nothing to reach")
    return ("OK", "Codex's sandbox can run mise tools")


def fix_command(directory: str) -> list[str]:
    """Read and execute for the sandbox group, inherited below, and nothing else."""
    return ["icacls", directory, "/grant", f"{SANDBOX_GROUP}:(OI)(CI)(RX)", "/Q"]


def secrets_message(env_acl: str) -> tuple[str, str]:
    """From the icacls output for ~/.env."""
    if SANDBOX_GROUP in env_acl:
        return (
            "WARN",
            "Codex's sandbox can read ~/.env, and Codex grants that again on setup: "
            "move its secrets under ~/.config (which it skips) and delete ~/.env",
        )
    return ("OK", "~/.env is not readable in Codex's sandbox")


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
    exposed = False
    env_file = Path.home() / ".env"
    if env_file.is_file():
        level, detail = secrets_message(_acl(env_file))
        exposed = level == "WARN"
        print(f"{level:<4} codex-sandbox-secrets - {detail}")
    if not directory.is_dir():
        print(f"OK   codex-sandbox - no mise data dir at {directory}")
        return 1 if exposed else 0
    current = state(_acl(Path.home()), _acl(directory))
    if current == "blocked" and "--check" not in argv:
        subprocess.run(fix_command(str(directory)), capture_output=True, check=False)
        current = state(_acl(Path.home()), _acl(directory))
        if current == "readable":
            print(f"OK   codex-sandbox - granted {SANDBOX_GROUP} read on {directory}")
    level, detail = message(current, str(directory))
    print(f"{level:<4} codex-sandbox - {detail}")
    return 1 if current == "blocked" or exposed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
