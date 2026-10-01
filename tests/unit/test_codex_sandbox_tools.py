"""Codex's Windows sandbox can run the tools mise installs, rtk above all.

Codex's elevated Windows sandbox runs commands as separate users and reaches
the profile through inheritable CodexSandboxUsers:(RX) entries. On this host
%LOCALAPPDATA%\\mise did not inherit, so rtk was "access denied" in the sandbox
and every command the rtk hook rewrote failed. The check reads icacls output
for the mise data dir and its parent; the fix turns inheritance back on.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import ai_tools_check  # noqa: E402
import codex_sandbox_tools as sandbox  # noqa: E402
import sync_agents  # noqa: E402

PARENT = r"""C:\Users\u\AppData\Local nn\CodexSandboxUsers:(I)(OI)(CI)(RX)
                          NT AUTHORITY\SYSTEM:(I)(OI)(CI)(F)
                          NN\u:(I)(OI)(CI)(F)
"""
PROTECTED = r"""C:\Users\u\AppData\Local\mise NT AUTHORITY\SYSTEM:(OI)(CI)(F)
                               BUILTIN\Administrators:(OI)(CI)(F)
                               NN\u:(OI)(CI)(F)
"""
INHERITING = (
    PROTECTED + "                               nn\\CodexSandboxUsers:(I)(OI)(CI)(RX)\n"
)
NO_SANDBOX = r"""C:\Users\u\AppData\Local NT AUTHORITY\SYSTEM:(I)(OI)(CI)(F)
"""


@pytest.mark.parametrize(
    ("parent", "acl", "expected"),
    [
        (PARENT, PROTECTED, "blocked"),
        (PARENT, INHERITING, "readable"),
        # Codex never set up its elevated sandbox here: nothing to reach
        (NO_SANDBOX, PROTECTED, "absent"),
    ],
)
def test_the_state_comes_from_the_two_acls(
    parent: str, acl: str, expected: str
) -> None:
    assert sandbox.state(parent, acl) == expected


def test_a_blocked_dir_warns_with_the_fix() -> None:
    level, detail = sandbox.message("blocked", r"C:\Users\u\AppData\Local\mise")
    assert level == "WARN"
    assert "just codex-sandbox-tools" in detail
    assert r"C:\Users\u\AppData\Local\mise" in detail


@pytest.mark.parametrize("state", ["readable", "absent"])
def test_other_states_are_ok(state: str) -> None:
    assert sandbox.message(state, "d")[0] == "OK"


def test_syncing_codex_fixes_it_and_doctor_checks_it() -> None:
    assert "codex_sandbox_tools.py" in [step[0] for step in sync_agents.CODEX_STEPS]
    assert "codex_sandbox_tools.py" in ai_tools_check.CODEX_CHECKS


ENV_READABLE = r"""C:\Users\u\.env nn\CodexSandboxUsers:(RX)
                 NN\u:(F)
"""


def test_a_profile_env_file_the_sandbox_can_read_warns() -> None:
    level, detail = sandbox.secrets_message(ENV_READABLE)
    assert level == "WARN"
    assert "~/.config" in detail


def test_a_private_profile_env_file_is_ok() -> None:
    assert sandbox.secrets_message(r"C:\Users\u\.env NN\u:(F)")[0] == "OK"


def test_the_fix_grants_the_sandbox_group_read_and_nothing_else() -> None:
    # Re-enabling inheritance would import every inheritable entry of the
    # parent, e.g. Users:(M) above a relocated MISE_DATA_DIR
    command = sandbox.fix_command("D:/tools/mise")
    assert command == [
        "icacls",
        "D:/tools/mise",
        "/grant",
        "CodexSandboxUsers:(OI)(CI)(RX)",
        "/Q",
    ]
