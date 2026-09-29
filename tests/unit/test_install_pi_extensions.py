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
