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
    #
    # HOME first: main() reads ~/.env when that file exists, so on a host that
    # has one the fake _acl below is asked about a path this test never set up.
    # A tmp home has none, which is also the case this test means to exercise.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
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


# --- main(), pinned before its phases were split into a pure report ---------

SANDBOX_ACL = "x nn\\CodexSandboxUsers:(OI)(CI)(RX)\n"
OWNER_ACL = "x NN\\u:(F)\n"


def _main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *,
    argv: list[str],
    profile: str = SANDBOX_ACL,
    env_acl: str | None = None,
    mise: str | None = OWNER_ACL,
    grant_works: bool = True,
) -> tuple[int, list[str]]:
    home = tmp_path / "home"
    home.mkdir()
    directory = tmp_path / "mise"
    if mise is not None:
        directory.mkdir()
    if env_acl is not None:
        (home / ".env").write_text("", encoding="utf-8")
    acls = {home: profile, home / ".env": env_acl or "", directory: mise or ""}
    monkeypatch.setattr(sandbox.sys, "platform", "win32")
    monkeypatch.setenv("MISE_DATA_DIR", str(directory))
    monkeypatch.setattr(sandbox.Path, "home", lambda: home)
    monkeypatch.setattr(sandbox, "_acl", lambda path: acls[path])

    def run(args: list[str], **_: object) -> None:
        if grant_works:
            acls[directory] = SANDBOX_ACL

    monkeypatch.setattr(sandbox.subprocess, "run", run)
    code = sandbox.main(argv)
    return code, capsys.readouterr().out.splitlines()


def test_main_reports_an_exposed_env_then_repairs_mise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _main(tmp_path, monkeypatch, capsys, argv=[], env_acl=SANDBOX_ACL)
    assert code == 1
    assert [line[:30] for line in out] == [
        "WARN codex-sandbox-secrets - C",
        "OK   codex-sandbox - granted C",
        "OK   codex-sandbox - Codex's s",
        "OK   codex-sandbox-git - git i",
    ]
    assert out[1].endswith(f"read on {tmp_path / 'mise'}")


def test_main_with_check_reports_without_repairing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _main(tmp_path, monkeypatch, capsys, argv=["--check"])
    assert code == 1
    assert len(out) == 2
    assert out[0].startswith("WARN codex-sandbox - ")
    assert "just codex-sandbox-tools" in out[0]
    assert out[1].startswith("OK   codex-sandbox-git - ")


def test_main_without_the_elevated_sandbox_has_nothing_to_say_about_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _main(tmp_path, monkeypatch, capsys, argv=[], profile=OWNER_ACL)
    assert (code, out) == (
        0,
        [
            "OK   codex-sandbox - Codex's elevated sandbox is not set up; nothing to reach"
        ],
    )


def test_main_without_a_mise_dir_still_reports_the_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _main(
        tmp_path, monkeypatch, capsys, argv=[], env_acl=SANDBOX_ACL, mise=None
    )
    assert code == 1
    assert out[0].startswith("WARN codex-sandbox-secrets - ")
    assert out[1] == f"OK   codex-sandbox - no mise data dir at {tmp_path / 'mise'}"
    assert len(out) == 2


def test_main_reports_a_repair_that_did_not_take(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _main(tmp_path, monkeypatch, capsys, argv=[], grant_works=False)
    assert code == 1
    assert out[0].startswith("WARN codex-sandbox - ")
    assert out[1].startswith("OK   codex-sandbox-git - ")


# --- report(): the lines from the gathered facts, no I/O -------------------


def _names(lines: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    return [(level, name) for level, name, _detail in lines]


def test_report_names_a_repair_only_when_one_was_tried_and_took() -> None:
    lines = sandbox.report(None, "D", before="blocked", after="readable")
    assert lines[0] == (
        "OK",
        "codex-sandbox",
        f"granted {sandbox.SANDBOX_GROUP} read on D",
    )
    assert _names(lines[1:]) == [("OK", "codex-sandbox"), ("OK", "codex-sandbox-git")]
    # already readable: nothing was granted
    assert _names(sandbox.report(None, "D", before="readable", after=None)) == [
        ("OK", "codex-sandbox"),
        ("OK", "codex-sandbox-git"),
    ]


def test_report_without_a_mise_dir_still_reports_the_env_file() -> None:
    lines = sandbox.report(SANDBOX_ACL, "D", before=None, after=None)
    assert _names(lines) == [("WARN", "codex-sandbox-secrets"), ("OK", "codex-sandbox")]
    assert lines[1][2] == "no mise data dir at D"


def test_report_has_no_git_line_without_the_sandbox() -> None:
    assert _names(sandbox.report(None, "D", before="absent", after=None)) == [
        ("OK", "codex-sandbox")
    ]
