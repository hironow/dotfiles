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


def _no_ollama_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the Ollama bootstrap: it would add one more subprocess call."""
    monkeypatch.setattr(
        installer.shutil,
        "which",
        lambda name: "/usr/bin/ollama" if name == "ollama" else None,
    )


def test_deploy_keeps_existing_packages_and_places_extension(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    settings = {"theme": "dark", "packages": ["npm:pi-goal-x", "npm:personal-plugin"]}
    (agent / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    _no_ollama_bootstrap(monkeypatch)
    install = Mock()
    monkeypatch.setattr(installer.subprocess, "run", install)
    installer.install(agent, symlinks=False)
    # The personal declaration stays; only the telemetry keys are added (ADR 0058).
    assert json.loads((agent / "settings.json").read_text(encoding="utf-8")) == (
        settings | installer.TELEMETRY_OFF
    )
    assert install.call_count == 9  # Eight missing declarations + one reconciliation.
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
    _no_ollama_bootstrap(monkeypatch)
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
    _no_ollama_bootstrap(monkeypatch)
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    with pytest.raises(RuntimeError, match="refusing to replace user extension"):
        installer.install(agent, symlinks=False)


AGENT_NAMES = ("codex-jev.md", "codex-jev-writer.md")


def _install(
    agent: Path, monkeypatch: pytest.MonkeyPatch, python: str = "/py/bin/python3"
) -> None:
    _no_ollama_bootstrap(monkeypatch)
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
        assert f'args: [{json.dumps(str(script))}, "--sandbox", "{sandbox}"]' in text
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


RTK = Path(__file__).resolve().parents[2] / "config/pi/extensions/rtk.ts"


def _upstream_rtk() -> str:
    """What `rtk init -g --agent pi` writes: the vendored file below its header."""
    return installer.vendored_body(RTK.read_text(encoding="utf-8"))


def test_rtk_is_placed_next_to_jev(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    _install(agent, monkeypatch)
    placed = agent / "extensions/rtk.ts"
    assert placed.read_text(encoding="utf-8") == RTK.read_text(encoding="utf-8")
    assert (agent / "extensions/jev-sonnet-fallback.ts").is_file()


def test_a_file_rtk_init_wrote_is_taken_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    (agent / "extensions").mkdir(parents=True)
    (agent / "extensions/rtk.ts").write_text(_upstream_rtk(), encoding="utf-8")
    _install(agent, monkeypatch)
    assert (agent / "extensions/rtk.ts").read_text(encoding="utf-8") == RTK.read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize("content", ["// an older rtk.ts\n", "user edits\n"])
def test_another_rtk_file_is_kept_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, content: str
) -> None:
    agent = tmp_path / "agent"
    (agent / "extensions").mkdir(parents=True)
    existing = agent / "extensions/rtk.ts"
    existing.write_text(content, encoding="utf-8")
    with pytest.raises(RuntimeError, match=r"rtk\.ts.*not applied"):
        _install(agent, monkeypatch)
    assert existing.read_text(encoding="utf-8") == content
    # one extension that cannot be placed does not hold back the rest
    assert (agent / "extensions/jev-sonnet-fallback.ts").is_file()
    assert (agent / "agents/codex-jev.md").is_file()


def test_an_unrelated_rtk_symlink_is_kept_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    (agent / "extensions").mkdir(parents=True)
    other = tmp_path / "elsewhere.ts"
    other.write_text("other", encoding="utf-8")
    link = agent / "extensions/rtk.ts"
    try:
        link.symlink_to(other)
    except OSError:
        pytest.skip("this host cannot create symlinks")
    with pytest.raises(RuntimeError, match=r"rtk\.ts"):
        _install(agent, monkeypatch)
    assert link.resolve() == other.resolve()


def test_the_vendored_rtk_extension_only_rewrites_bash_and_fails_open() -> None:
    text = RTK.read_text(encoding="utf-8")
    assert text.startswith("// dotfiles-managed: rtk\n")
    assert "Apache License 2.0" in text.split(installer.VENDORED_SENTINEL)[0]
    body = _upstream_rtk()
    assert 'event.toolName === "bash"' in body
    assert 'process.env.RTK_DISABLED === "1"' in body
    assert "Fail open" in body


# The decision alone (installer.placement), without a filesystem
SOURCE = (
    "// dotfiles-managed: rtk\n// header\n" + installer.VENDORED_SENTINEL + "body\n"
)


@pytest.mark.parametrize(
    ("placed", "symlinks", "action"),
    [
        (installer.Placed(), True, "place"),
        (installer.Placed(link_to_source=True), True, "keep"),
        (installer.Placed(link_to_source=False), True, "refuse"),
        (installer.Placed(text=SOURCE), False, "refresh"),
        # what `rtk init` writes is the vendored body alone
        (installer.Placed(text="body\n"), True, "take-over"),
        (installer.Placed(text="body\n"), False, "take-over"),
        (installer.Placed(text="// the user's own\n"), False, "refuse"),
    ],
)
def test_placement_decides_from_what_is_there(
    placed: object, symlinks: bool, action: str
) -> None:
    assert installer.placement(SOURCE, placed, symlinks=symlinks) == action


# The retired web extension and remote-pi (ADR 0058, ADR 0059): still
# configured entries go, personal declarations and other pins stay.


@pytest.mark.parametrize(
    ("declared", "removed_source"),
    [
        ("npm:pi-web-access@0.37.0", "npm:pi-web-access"),
        ("npm:remote-pi@0.7.0", "npm:remote-pi"),
    ],
)
def test_a_still_configured_retired_package_is_removed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, declared: str, removed_source: str
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "settings.json").write_text(
        json.dumps({"packages": [declared, "npm:personal-plugin"]}),
        encoding="utf-8",
    )
    _no_ollama_bootstrap(monkeypatch)
    install = Mock()
    monkeypatch.setattr(installer.subprocess, "run", install)
    installer.install(agent, symlinks=False)
    removed = [
        call.args[0]
        for call in install.call_args_list
        if call.args[0][:2] == ["pi", "remove"]
    ]
    assert removed == [["pi", "remove", removed_source]]


@pytest.mark.parametrize(
    ("packages", "retired"),
    [
        ([], []),
        (["npm:pi-goal-x"], []),
        (["npm:pi-web-access"], ["npm:pi-web-access"]),
        (["npm:pi-web-access@0.37.0"], ["npm:pi-web-access"]),
        ([{"source": "npm:pi-web-access@1.0.0"}], ["npm:pi-web-access"]),
        (["npm:remote-pi"], ["npm:remote-pi"]),
        (["npm:remote-pi@0.7.0"], ["npm:remote-pi"]),
        (
            ["npm:pi-web-access@0.37.0", "npm:remote-pi@0.7.0", "npm:pi-goal-x"],
            ["npm:pi-web-access", "npm:remote-pi"],
        ),
    ],
)
def test_retirement_matches_bare_names_pins_and_object_forms(
    packages: list, retired: list[str]
) -> None:
    assert installer.retired_configured(packages) == retired


# Pi's own metrics, off in settings.json on every machine (ADR 0058).


def test_telemetry_is_written_last_over_a_pi_rewrite_and_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    settings = {"theme": "dark", "enableAnalytics": True, "packages": []}
    path = agent / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    _no_ollama_bootstrap(monkeypatch)
    monkeypatch.setattr(
        installer.subprocess, "run", Mock(side_effect=lambda *a, **k: None)
    )
    installer.install(agent, symlinks=False)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written == settings | installer.TELEMETRY_OFF
    before = path.read_text(encoding="utf-8")
    installer.install(agent, symlinks=False)
    assert path.read_text(encoding="utf-8") == before  # no rewrite when already off


@pytest.mark.parametrize(
    ("settings", "edits"),
    [
        ({}, dict(installer.TELEMETRY_OFF)),
        (dict(installer.TELEMETRY_OFF), {}),
        (
            {"enableInstallTelemetry": True, "enableAnalytics": False},
            {"enableInstallTelemetry": False},
        ),
    ],
)
def test_telemetry_edits_are_only_the_keys_that_differ(
    settings: dict, edits: dict
) -> None:
    assert installer.telemetry_edits(settings) == edits


# The Ollama bootstrap for the web-search extension (ADR 0058), per
# https://ollama.com/download.


@pytest.mark.parametrize(
    ("sources", "ollama", "reachable", "missing"),
    [
        ([], None, False, False),  # not declared: never bootstrap
        (["npm:@ollama/pi-web-search"], "/usr/bin/ollama", False, False),
        # a server already answering on localhost:11434 serves the extension
        (["npm:@ollama/pi-web-search"], None, True, False),
        (["npm:@ollama/pi-web-search"], None, False, True),
    ],
)
def test_ollama_is_bootstrapped_only_when_declared_and_unserved(
    sources: list, ollama: str | None, reachable: bool, missing: bool
) -> None:
    assert installer.ollama_missing(sources, ollama, reachable) is missing


@pytest.mark.parametrize(
    ("system", "wsl", "ollama", "reachable", "owns"),
    [
        # Windows alone installs as usual
        ("win32", None, None, False, False),
        ("win32", "Ubuntu", "/usr/bin/ollama.exe", False, False),
        # mirrored mode: the Windows-side server answers from WSL
        ("win32", "Ubuntu", None, True, False),
        # the coexistence machine: one Ollama, on the WSL side
        ("win32", "Ubuntu", None, False, True),
        # WSL and other platforms are never told to skip
        ("linux", "Ubuntu", None, False, False),
        ("darwin", None, None, False, False),
    ],
)
def test_a_windows_wsl_machine_keeps_its_one_ollama_on_the_wsl_side(
    system: str, wsl: str | None, ollama: str | None, reachable: bool, owns: bool
) -> None:
    assert installer.wsl_owns_ollama(system, wsl, ollama, reachable) is owns


@pytest.mark.parametrize(
    ("platform", "command"),
    [
        (
            "darwin",
            ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
        ),
        (
            "linux",
            ["sh", "-c", "curl -fsSL https://ollama.com/install.sh | sh"],
        ),
        (
            "win32",
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "irm https://ollama.com/install.ps1 | iex",
            ],
        ),
        ("sunos", None),
    ],
)
def test_the_installer_is_ollamas_own_download_page_command(
    platform: str, command: list[str] | None
) -> None:
    assert installer.ollama_command(platform) == command


def test_a_missing_ollama_is_installed_and_a_failure_only_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "settings.json").write_text(json.dumps({"packages": []}), encoding="utf-8")
    # Ollama missing (binary and loopback), and the installer fails: the
    # placement still completes.
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    monkeypatch.setattr(installer, "_ollama_reachable", lambda: False)
    monkeypatch.setattr(installer.sys, "platform", "linux")
    failed = Mock(returncode=1)
    monkeypatch.setattr(installer.subprocess, "run", Mock(return_value=failed))
    installer.install(agent, symlinks=False)
    assert (agent / "extensions/jev-sonnet-fallback.ts").is_file()
    out = capsys.readouterr()
    assert "Installing Ollama" in out.out
    assert "WARN: Ollama install failed" in out.err


def test_a_windows_wsl_machine_installs_no_second_ollama(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "settings.json").write_text(json.dumps({"packages": []}), encoding="utf-8")
    monkeypatch.setattr(installer.shutil, "which", lambda name: None)
    monkeypatch.setattr(installer, "_ollama_reachable", lambda: False)
    monkeypatch.setattr(installer, "_wsl_distro", lambda: "Ubuntu")
    monkeypatch.setattr(installer.sys, "platform", "win32")
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    installer.install(agent, symlinks=False)
    # only the pi package commands ran: no second Ollama was installed
    assert not any(
        "ollama.com" in " ".join(str(part) for part in call.args[0])
        for call in run.call_args_list
    )
    assert (agent / "extensions/jev-sonnet-fallback.ts").is_file()
    out = capsys.readouterr()
    assert "one Ollama lives on the WSL side (Ubuntu)" in out.out
    assert "install it from WSL" in out.out
