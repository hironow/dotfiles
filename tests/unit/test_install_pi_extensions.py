"""Pi package setup preserves existing user settings and user-owned extensions."""

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/install_pi_extensions.py"
spec = importlib.util.spec_from_file_location("install_pi_extensions", SCRIPT)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_deploy_keeps_existing_packages_and_places_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    settings = {"theme": "dark", "packages": ["npm:pi-goal-x", "npm:personal-plugin"]}
    (agent / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    install = Mock()
    monkeypatch.setattr(installer.subprocess, "run", install)
    installer.install(agent, symlinks=False)
    assert json.loads((agent / "settings.json").read_text(encoding="utf-8")) == settings
    assert install.call_count == 10  # Nine missing declarations + one reconciliation.
    assert all(call.args[0][0] == "pi" for call in install.call_args_list)
    extension = agent / "extensions/jev-sonnet-fallback.ts"
    assert extension.read_text(encoding="utf-8") == installer.EXTENSION.read_text(
        encoding="utf-8"
    )
    installer.install(agent, symlinks=False)
    assert extension.is_file()


def test_windows_copy_updates_only_managed_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    installer.install(agent, symlinks=False)
    extension = agent / "extensions/jev-sonnet-fallback.ts"
    assert extension.is_file() and not extension.is_symlink()
    extension.write_text(
        "// dotfiles-managed: jev-sonnet-fallback\nold version", encoding="utf-8"
    )
    installer.install(agent, symlinks=False)
    assert extension.read_text(encoding="utf-8") == installer.EXTENSION.read_text(
        encoding="utf-8"
    )


def test_deploy_refuses_user_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    (agent / "extensions").mkdir(parents=True)
    (agent / "extensions/jev-sonnet-fallback.ts").write_text(
        "user extension", encoding="utf-8"
    )
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    with pytest.raises(RuntimeError, match="refusing to replace user extension"):
        installer.install(agent, symlinks=False)


AGENT_NAMES = ("codex-jev.md", "codex-jev-writer.md")


@pytest.mark.skipif(os.name == "nt", reason="native Windows symlinks need privileges")
def test_codex_agents_are_linked_into_the_user_agent_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    installer.install(agent, symlinks=True)
    for name in AGENT_NAMES:
        link = agent / "agents" / name
        assert link.is_symlink() and link.resolve() == installer.AGENTS_DIR / name
    installer.install(agent, symlinks=True)  # idempotent
    assert all((agent / "agents" / name).is_symlink() for name in AGENT_NAMES)


def test_codex_agents_are_skipped_where_symlinks_and_sh_are_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    installer.install(agent, symlinks=False)
    assert not (agent / "agents").exists()


@pytest.mark.skipif(os.name == "nt", reason="native Windows symlinks need privileges")
def test_a_user_owned_agent_of_the_same_name_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    (agent / "agents").mkdir(parents=True)
    (agent / "agents/codex-jev.md").write_text("mine", encoding="utf-8")
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    with pytest.raises(RuntimeError, match="refusing to replace user agent"):
        installer.install(agent, symlinks=True)
    assert (agent / "agents/codex-jev.md").read_text(encoding="utf-8") == "mine"


def test_the_agent_definitions_call_the_runner_with_the_right_sandbox() -> None:
    for name, sandbox in (
        ("codex-jev.md", "read-only"),
        ("codex-jev-writer.md", "workspace-write"),
    ):
        text = (installer.AGENTS_DIR / name).read_text(encoding="utf-8")
        assert "type: external-cli" in text and "promptDelivery: stdin" in text
        assert f'jev_codex_exec.py" --sandbox {sandbox}' in text
        assert f"name: {name.removesuffix('.md')}" in text
