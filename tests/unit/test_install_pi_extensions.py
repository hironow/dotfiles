"""Pi package setup preserves existing user settings and user-owned extensions."""

import importlib.util
import json
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


def _install(
    agent: Path, monkeypatch: pytest.MonkeyPatch, python: str = "/py/bin/python3"
) -> None:
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    monkeypatch.setattr(installer.sys, "executable", python)
    installer.install(agent, symlinks=False)


def test_codex_agents_are_rendered_with_absolute_paths_and_no_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    _install(agent, monkeypatch)
    script = installer.ROOT / "scripts/jev_codex_exec.py"
    for name, sandbox in (
        ("codex-jev.md", "read-only"),
        ("codex-jev-writer.md", "workspace-write"),
    ):
        text = (agent / "agents" / name).read_text(encoding="utf-8")
        assert not (agent / "agents" / name).is_symlink()
        assert 'command: "/py/bin/python3"' in text
        assert f'args: ["{script}", "--sandbox", "{sandbox}"]' in text
        assert "@PYTHON@" not in text and "@SCRIPT@" not in text
        assert "sh" != text.split("command:")[1].split()[0].strip('"')
        assert "type: external-cli" in text and "promptDelivery: stdin" in text
        assert f"name: {name.removesuffix('.md')}" in text


def test_a_windows_style_interpreter_path_stays_valid_yaml(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    _install(agent, monkeypatch, python="C:\\Program Files\\Python 3.14\\python.exe")
    text = (agent / "agents/codex-jev.md").read_text(encoding="utf-8")
    line = next(
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("command:")
    )
    # A YAML double-quoted scalar is a JSON string here: it must decode to the real path.
    assert (
        json.loads(line.removeprefix("command: "))
        == "C:\\Program Files\\Python 3.14\\python.exe"
    )


def test_rendering_again_follows_a_moved_interpreter_and_is_otherwise_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    _install(agent, monkeypatch, python="/old/python3")
    _install(agent, monkeypatch, python="/new/python3")
    text = (agent / "agents/codex-jev.md").read_text(encoding="utf-8")
    assert "/new/python3" in text and "/old/python3" not in text
    before = text
    _install(agent, monkeypatch, python="/new/python3")
    assert (agent / "agents/codex-jev.md").read_text(encoding="utf-8") == before


def test_a_user_owned_agent_of_the_same_name_is_never_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    (agent / "agents").mkdir(parents=True)
    (agent / "agents/codex-jev.md").write_text("mine", encoding="utf-8")
    with pytest.raises(RuntimeError, match="refusing to replace user agent"):
        _install(agent, monkeypatch)
    assert (agent / "agents/codex-jev.md").read_text(encoding="utf-8") == "mine"
