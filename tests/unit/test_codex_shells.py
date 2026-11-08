"""Codex's shell routes live in codex_shells, which imports neither doctor nor
sync, so both can use them (PR 3d.2); doctor keeps its names for its callers."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import agent_hook_doctor
import codex_shells

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
