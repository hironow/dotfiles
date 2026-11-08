"""Codex's shell routes live in codex_shells, which imports neither doctor nor
sync, so both can use them (PR 3d.2); doctor keeps its names for its callers."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import agent_hook_doctor
import codex_shells
from agent_hook_release import Outcome

MOVED = (
    "POSIX_SHELLS",
    "SHELL_FALLBACKS",
    "SHELL_TIMEOUT",
    "Shell",
    "ShellChoice",
    "derive_login_shell",
    "derive_session_shell",
    "gather_shells",
    "probe_argv",
    "shell_kind",
)


def test_doctor_reexports_every_moved_name() -> None:
    for name in MOVED:
        assert getattr(agent_hook_doctor, name) is getattr(codex_shells, name), name


def test_codex_shells_imports_neither_sync_nor_doctor() -> None:
    source = Path(codex_shells.__file__).read_text(encoding="utf-8")
    for module in ("sync_agents", "agent_hook_doctor", "agent_hook_sync"):
        assert f"import {module}" not in source


def _shell(kind: str, *, executable: str | None = "/bin/x", clean: bool = True):
    choice = codex_shells.ShellChoice("session shell", executable, kind, "why")
    outcome = Outcome(stdout="token" if clean else "noise token")
    return codex_shells.Shell(choice, ("x",), outcome, "token")


@pytest.mark.parametrize(
    ("shells", "reason"),
    [
        ((_shell("zsh"), _shell("bash")), ""),
        ((), "no POSIX shell to check"),
        (
            (_shell("zsh"), _shell("fish")),
            "session shell /bin/x is fish, not a POSIX shell",
        ),
        (
            (_shell("none", executable=None), _shell("zsh")),
            "session shell: no shell found",
        ),
        (
            (_shell("zsh", clean=False), _shell("zsh")),
            "session shell /bin/x does not run a command cleanly (run just doctor)",
        ),
    ],
    ids=["clean", "none", "fish", "missing", "noisy"],
)
def test_the_shells_are_ready_only_when_both_are_clean_posix_shells(
    shells: tuple, reason: str
) -> None:
    assert codex_shells.unready_reason(shells) == reason
