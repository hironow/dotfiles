"""Codex's Windows sandbox can run the tools mise installs, rtk above all.

Codex's elevated Windows sandbox runs commands as separate users and reaches
the profile through inheritable CodexSandboxUsers:(RX) entries. On this host
%LOCALAPPDATA%\\mise did not inherit, so rtk was "access denied" in the sandbox
and every command the rtk hook rewrote failed. The check reads icacls output
for the mise data dir and the profile; the fix grants the sandbox group read.
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
    ("profile", "acl", "expected"),
    [
        (PARENT, PROTECTED, "blocked"),
        (PARENT, INHERITING, "readable"),
        # Codex never set up its elevated sandbox here: nothing to reach
        (NO_SANDBOX, PROTECTED, "absent"),
    ],
)
def test_the_state_comes_from_the_two_acls(
    profile: str, acl: str, expected: str
) -> None:
    assert sandbox.state(profile, acl) == expected


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
    assert "codex_sandbox_tools.py" in ai_tools_check.CHECKERS["codex"][1]


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


def test_a_relocated_mise_dir_is_still_fixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # MISE_DATA_DIR moved to a drive whose top Codex never touched: whether
    # the sandbox exists is read from the profile, not from the dir's parent
    mise = tmp_path / "tools" / "mise"
    mise.mkdir(parents=True)
    granted: list[list[str]] = []
    acls = {Path.home(): PARENT, mise.parent: NO_SANDBOX}

    def acl(path: Path) -> str:
        if path == mise:
            return INHERITING if granted else PROTECTED
        return acls[path]

    monkeypatch.setattr(sandbox.sys, "platform", "win32")
    monkeypatch.setenv("MISE_DATA_DIR", str(mise))
    monkeypatch.setattr(sandbox, "_acl", acl)
    monkeypatch.setattr(
        sandbox.subprocess, "run", lambda args, **_: granted.append(args)
    )
    assert sandbox.main([]) == 0
    assert granted == [sandbox.fix_command(str(mise))]
    assert "can run mise tools" in capsys.readouterr().out


def test_git_in_the_sandbox_is_explained_not_changed() -> None:
    # The sandbox runs as another user, so git stops at its ownership check;
    # loosening safe.directory would let sandboxed code plant a .git/config
    # that the owner's git later runs, so doctor only explains (an OK line)
    level, detail = sandbox.git_message()
    assert level == "OK"
    assert "safe.directory" in detail
    assert "without the sandbox" in detail
