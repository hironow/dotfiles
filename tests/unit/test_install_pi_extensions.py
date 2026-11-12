"""Pi package setup preserves existing user settings and user-owned extensions."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/install_pi_extensions.py"
spec = importlib.util.spec_from_file_location("install_pi_extensions", SCRIPT)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture(autouse=True)
def _fake_package_git_verification(monkeypatch: pytest.MonkeyPatch) -> None:
    # This file fakes Pi installation. Real git integrity cases live in
    # test_egm_integration.py, without this fixture.
    monkeypatch.setattr(installer, "verify_egm", lambda _root: None)


def _no_ollama_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the Ollama bootstrap: it would add one more subprocess call."""
    monkeypatch.setattr(installer, "host_policy", lambda: None)
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
    assert install.call_count == 10  # Nine missing declarations + npm reconciliation.
    assert all(call.args[0][0] == "pi" for call in install.call_args_list)
    extension = agent / "extensions/jev-sonnet-fallback.ts"
    assert extension.read_text(encoding="utf-8") == installer.EXTENSION.read_text(
        encoding="utf-8"
    )
    installer.install(agent, symlinks=False)
    assert extension.is_file()


def test_egm_only_install_is_scoped_and_preserves_the_selected_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    path = agent / "settings.json"
    settings = {"theme": "dark", "npmCommand": ["bun"], "packages": ["npm:personal"]}
    path.write_text(json.dumps(settings), encoding="utf-8")
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer, "verify_egm", lambda _root: None, raising=False)
    monkeypatch.setattr(
        installer, "_ensure_ollama", lambda _sources: pytest.fail("unrelated bootstrap")
    )
    installer.install(agent, symlinks=False, egm_only=True)
    assert [call.args[0] for call in run.call_args_list] == [
        ["pi", "install", installer.EGM_SOURCE]
    ]
    assert run.call_args.kwargs["env"]["PI_CODING_AGENT_DIR"] == str(agent.resolve())
    assert (
        json.loads(path.read_text(encoding="utf-8"))
        == settings | installer.TELEMETRY_OFF
    )
    assert not (agent / "extensions").exists()
    assert sorted(p.name for p in (agent / "agents").iterdir()) == ["egm-reviewer.md"]
    assert (agent / "docs/agents/egm.md").is_file()
    assert (agent / "docs/agents/egm.md").as_posix() in (agent / "AGENTS.md").read_text(
        encoding="utf-8"
    )


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


def test_a_configured_missing_egm_is_reinstalled_without_global_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    settings = {"packages": [installer.EGM_SOURCE]}
    (agent / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    installer.install(agent, egm_only=True)
    assert [call.args[0] for call in run.call_args_list] == [
        ["pi", "install", installer.EGM_SOURCE]
    ]
    # A healthy configured git package must not trigger the npm recovery path.
    (agent / installer.EGM_RELATIVE).mkdir(parents=True)
    run.reset_mock()
    installer.install(agent, egm_only=True)
    assert run.call_count == 0


def test_general_npm_recovery_cannot_change_egm_after_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    sources = json.loads(installer.MANIFEST.read_text(encoding="utf-8"))
    (agent / "settings.json").write_text(
        json.dumps({"packages": sources}), encoding="utf-8"
    )
    (agent / installer.EGM_RELATIVE).mkdir(parents=True)
    state = {"approved": True}

    def verify(_root: Path) -> None:
        if not state["approved"]:
            raise RuntimeError("recovery moved EGM off its approved revision")

    def run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        if args == ["pi", "update", "--extensions"]:
            state["approved"] = False
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(installer, "verify_egm", verify)
    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer, "_ensure_ollama", lambda _sources: None)
    with pytest.raises(RuntimeError, match="recovery moved EGM"):
        installer.install(agent, symlinks=False)
    assert not (agent / "docs/agents/egm.md").exists()


def test_pi_context_preserves_user_text_and_refreshes_only_its_block(
    tmp_path: Path,
) -> None:
    guide = tmp_path / "docs/agents/egm.md"
    original = "# Personal instructions\nKeep my choices.\n"
    first = installer.egm_context(original, guide)
    assert first.startswith(original)
    assert installer.egm_context(first, guide) == first
    decorated = first + "\nAdditional user instructions.\n"
    moved = tmp_path / "moved guide.md"
    refreshed = installer.egm_context(decorated, moved)
    assert refreshed.startswith(original)
    assert refreshed.endswith("\nAdditional user instructions.\n")
    assert moved.as_posix() in refreshed and guide.as_posix() not in refreshed


@pytest.mark.parametrize(
    "text",
    [
        installer.EGM_START,
        installer.EGM_END,
        installer.EGM_END + installer.EGM_START,
        installer.EGM_START * 2 + installer.EGM_END,
    ],
)
def test_malformed_context_is_refused_without_writes(tmp_path: Path, text: str) -> None:
    context = tmp_path / "AGENTS.md"
    context.write_text(text, encoding="utf-8")
    with pytest.raises(RuntimeError, match="malformed EGM"):
        installer._place_egm_guide(tmp_path)
    assert context.read_text(encoding="utf-8") == text
    assert not (tmp_path / "docs/agents/egm.md").exists()


def test_pi_uses_the_effective_context_file_and_keeps_user_guides(
    tmp_path: Path,
) -> None:
    override = tmp_path / "AGENTS.override.md"
    override.write_text("User override\n", encoding="utf-8")
    installer._place_egm_guide(tmp_path)
    assert override.read_text(encoding="utf-8").startswith("User override\n")
    assert installer.EGM_START in override.read_text(encoding="utf-8")
    assert not (tmp_path / "AGENTS.md").exists()
    guide = tmp_path / "docs/agents/egm.md"
    guide.write_text("User guide\n", encoding="utf-8")
    before = override.read_bytes()
    with pytest.raises(RuntimeError, match="user EGM guide"):
        installer._place_egm_guide(tmp_path)
    assert guide.read_text(encoding="utf-8") == "User guide\n"
    assert override.read_bytes() == before


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


# The retired web extension, remote-pi (ADR 0058, ADR 0059), pi-memory and
# pi-observational-memory: still
# configured entries go, personal declarations and other pins stay.


@pytest.mark.parametrize(
    ("declared", "removed_source"),
    [
        ("npm:pi-web-access@0.37.0", "npm:pi-web-access"),
        ("npm:remote-pi@0.7.0", "npm:remote-pi"),
        ("npm:pi-memory@0.4.2", "npm:pi-memory"),
        ("npm:pi-observational-memory@3.1.4", "npm:pi-observational-memory"),
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
        (["npm:pi-memory"], ["npm:pi-memory"]),
        (["npm:pi-observational-memory"], ["npm:pi-observational-memory"]),
        # A name that only starts with a retired one is not retired.
        (["npm:pi-memory-extra"], []),
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


def test_no_retired_package_is_declared() -> None:
    # A declared retired package would be removed and reinstalled on every run.
    declared = json.loads(installer.MANIFEST.read_text(encoding="utf-8"))
    assert installer.retired_configured(declared) == []


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
        ("win32", None),
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
    monkeypatch.setattr(installer, "host_policy", lambda: None)
    failed = Mock(returncode=1)
    monkeypatch.setattr(installer.subprocess, "run", Mock(return_value=failed))
    installer.install(agent, symlinks=False)
    assert (agent / "extensions/jev-sonnet-fallback.ts").is_file()
    out = capsys.readouterr()
    assert "Installing Ollama" in out.out
    assert "WARN: Ollama install failed" in out.err


@pytest.mark.parametrize("policy", ["windows-full", "wsl-client"])
@pytest.mark.parametrize("present", [True, False])
def test_coexistence_policy_precedes_binary_and_health_shortcuts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    policy: str,
    present: bool,
) -> None:
    monkeypatch.setattr(installer, "host_policy", lambda: policy)
    monkeypatch.setattr(
        installer.shutil, "which", lambda name: "/wrong/ollama" if present else None
    )
    monkeypatch.setattr(installer, "_ollama_reachable", lambda: present)
    run = Mock(return_value=Mock(returncode=1))
    monkeypatch.setattr(installer.subprocess, "run", run)
    installer._ensure_ollama([installer.OLLAMA_PACKAGE])
    command = run.call_args.args[0]
    assert command[-1] == "--setup"
    assert command[-2].endswith("ollama_host.py")
    assert "ollama.com" not in " ".join(command)
    assert run.call_count == 1  # No Linux/standalone fallback after failed setup.
    assert "policy/bridge setup incomplete" in capsys.readouterr().err


@pytest.mark.parametrize(
    "failure", [OSError("launch unavailable"), subprocess.TimeoutExpired("setup", 90)]
)
def test_policy_setup_failure_cannot_suppress_extension_placement(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture, failure: Exception
) -> None:
    monkeypatch.setattr(installer, "host_policy", lambda: "wsl-client")
    monkeypatch.setattr(installer.subprocess, "run", Mock(side_effect=failure))
    installer._ensure_ollama([installer.OLLAMA_PACKAGE])
    assert "policy/bridge setup incomplete" in capsys.readouterr().err


# An extension dotfiles placed whose source is gone (retired or renamed) is
# removed on the next install, so retiring one in the repo retires it on every
# machine. Only our own placements go: a symlink to the source path of its own
# name, or a copy whose first line is our marker for its own name
# (`// dotfiles-managed: <name>`). A user's file, a user's copy of one of ours
# under another name, and a symlink pointing anywhere else stay.


def test_every_extension_source_names_itself_in_its_marker() -> None:
    # Retirement recognizes our copies by this line, so every source must carry it.
    for source in installer.EXTENSIONS_DIR.glob("*.ts"):
        first = source.read_text(encoding="utf-8").splitlines()[0]
        assert first == f"{installer.EXTENSION_MARKER}{source.stem}", source


def test_a_retired_extension_we_placed_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    extensions = agent / "extensions"
    extensions.mkdir(parents=True)
    (extensions / "retired-link.ts").symlink_to(
        installer.EXTENSIONS_DIR / "retired-link.ts"
    )
    (extensions / "retired-copy.ts").write_text(
        "// dotfiles-managed: retired-copy\nold body\n", encoding="utf-8"
    )
    _no_ollama_bootstrap(monkeypatch)
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    installer.install(agent, symlinks=True)
    assert not (extensions / "retired-link.ts").is_symlink()
    assert not (extensions / "retired-copy.ts").exists()
    assert (extensions / "jev-sonnet-fallback.ts").is_symlink()


def test_files_that_are_not_ours_are_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    extensions = agent / "extensions"
    extensions.mkdir(parents=True)
    user = extensions / "mine.ts"
    user.write_text("export default function () {}\n", encoding="utf-8")
    renamed_copy = extensions / "my-rtk.ts"
    renamed_copy.write_text("// dotfiles-managed: rtk\nmy edits\n", encoding="utf-8")
    not_utf8 = extensions / "legacy.ts"
    not_utf8.write_bytes("// \u65e5\u672c\n".encode("cp932"))
    elsewhere = extensions / "elsewhere.ts"
    elsewhere.symlink_to(tmp_path / "somewhere-else.ts")
    # A link to itself: resolving it raises on Python 3.12 and not on 3.13+.
    loop = extensions / "loop.ts"
    loop.symlink_to(loop)
    _no_ollama_bootstrap(monkeypatch)
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    installer.install(agent, symlinks=True)
    assert user.read_text(encoding="utf-8") == "export default function () {}\n"
    assert renamed_copy.read_text(encoding="utf-8") == (
        "// dotfiles-managed: rtk\nmy edits\n"
    )
    assert not_utf8.exists()
    assert elsewhere.is_symlink()
    assert loop.is_symlink()


@pytest.mark.parametrize(
    ("stored", "target"),
    [
        ("\\\\?\\D:\\a\\x.ts", "D:\\a\\x.ts"),
        ("\\\\?\\UNC\\server\\share\\x.ts", "\\\\server\\share\\x.ts"),
        ("D:\\a\\x.ts", "D:\\a\\x.ts"),
        ("/home/u/x.ts", "/home/u/x.ts"),
    ],
)
def test_a_windows_link_target_drops_its_extended_length_prefix(
    stored: str, target: str
) -> None:
    # On Windows, readlink returns the NT form: \\?\D:\... or \\?\UNC\server\...
    assert installer.drop_extended_length_prefix(stored) == target


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX follows alias before '..'; Win32 folds '..' as text, so there "
    "the link does point at our path",
)
def test_a_user_link_that_only_spells_our_path_is_kept(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # sources/alias/../gone.ts reads like sources/gone.ts, but alias points
    # elsewhere, so it resolves outside. Only the exact path we link to counts.
    sources = tmp_path / "sources"
    sources.mkdir()
    outside = tmp_path / "outside/subdir"
    outside.mkdir(parents=True)
    (sources / "alias").symlink_to(outside)
    monkeypatch.setattr(installer, "EXTENSIONS_DIR", sources)
    extensions = tmp_path / "agent/extensions"
    extensions.mkdir(parents=True)
    link = extensions / "gone.ts"
    link.symlink_to(sources / "alias" / ".." / "gone.ts")
    assert installer._retire_extensions(tmp_path / "agent") == []
    assert link.is_symlink()


def test_a_leftover_that_cannot_be_checked_is_kept_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # It may be a user's file: keep it, finish the rest, and report it at the end.
    agent = tmp_path / "agent"
    extensions = agent / "extensions"
    extensions.mkdir(parents=True)
    locked = extensions / "locked.ts"
    locked.write_text("// dotfiles-managed: locked\n", encoding="utf-8")
    retired = extensions / "retired-copy.ts"
    retired.write_text("// dotfiles-managed: retired-copy\n", encoding="utf-8")
    real_leftover = installer._leftover

    def leftover(destination: Path) -> object:
        if destination.name == "locked.ts":
            raise PermissionError(13, "Permission denied", str(destination))
        return real_leftover(destination)

    monkeypatch.setattr(installer, "_leftover", leftover)
    _no_ollama_bootstrap(monkeypatch)
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    with pytest.raises(RuntimeError, match=r"locked\.ts"):
        installer.install(agent, symlinks=True)
    assert locked.exists()
    assert not retired.exists()
    assert (agent / "agents/codex-jev.md").exists()  # later steps still ran


def test_an_egm_only_install_retires_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    extensions = agent / "extensions"
    extensions.mkdir(parents=True)
    copy = extensions / "retired-copy.ts"
    copy.write_text("// dotfiles-managed: retired-copy\n", encoding="utf-8")
    monkeypatch.setattr(installer.subprocess, "run", Mock())
    monkeypatch.setattr(installer, "_place_egm_guide", lambda _agent: None)
    installer.install(agent, symlinks=True, egm_only=True)
    assert copy.exists()


@pytest.mark.parametrize(
    ("placed", "retired"),
    [
        (installer.Placed(link_to_source=True), True),
        (installer.Placed(link_to_source=False), False),
        (installer.Placed(text="// dotfiles-managed: gone\nx"), True),
        (installer.Placed(text="// dotfiles-managed: gone\r\nx"), True),
        (installer.Placed(text="// dotfiles-managed: other\nx"), False),
        (installer.Placed(text="// dotfiles-managed: gone-not\nx"), False),
        (installer.Placed(text="user file\n"), False),
        (installer.Placed(text=""), False),
        (installer.Placed(), False),
    ],
)
def test_retirement_decides_from_what_is_there(placed: object, retired: bool) -> None:
    assert installer.retired_extension(placed, "gone") is retired


@pytest.mark.parametrize(
    ("source", "name"),
    [
        ("npm:pi-goal-x", "pi-goal-x"),
        ("npm:pi-goal-x@1.2.3", "pi-goal-x"),
        ("npm:@ollama/pi-web-search", "@ollama/pi-web-search"),
        ("npm:@ollama/pi-web-search@0.4.0", "@ollama/pi-web-search"),
        ("git:github.com/google/elephant-goldfish-model@v0.1.0", None),
    ],
)
def test_npm_name_drops_the_pin_and_keeps_the_scope(
    source: str, name: str | None
) -> None:
    assert installer.npm_name(source) == name


def test_a_pinned_web_search_package_still_needs_ollama() -> None:
    pinned = [f"{installer.OLLAMA_PACKAGE}@0.4.0"]
    assert installer.ollama_missing(pinned, None, reachable=False)


@pytest.mark.parametrize(
    ("configured", "declared"),
    [
        ("npm:pi-goal-x", "npm:pi-goal-x@1.2.3"),  # pin
        ("npm:pi-goal-x@1.2.3", "npm:pi-goal-x@1.3.0"),  # move the pin
        ("npm:pi-goal-x@1.2.3", "npm:pi-goal-x"),  # unpin
        ("npm:@scope/pkg", "npm:@scope/pkg@2.0.0"),
    ],
)
def test_a_changed_pin_replaces_the_configured_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, configured: str, declared: str
) -> None:
    agent = tmp_path / "agent"
    agent.mkdir()
    (agent / "settings.json").write_text(
        json.dumps({"packages": [configured]}), encoding="utf-8"
    )
    manifest = tmp_path / "pi-packages.json"
    manifest.write_text(json.dumps([declared]), encoding="utf-8")
    monkeypatch.setattr(installer, "MANIFEST", manifest)
    _no_ollama_bootstrap(monkeypatch)
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    installer.install(agent, symlinks=False)
    calls = [call.args[0] for call in run.call_args_list]
    assert calls[:2] == [["pi", "remove", configured], ["pi", "install", declared]]


def test_installed_pinned_packages_are_not_reported_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    (agent / "npm/node_modules/@scope/pkg").mkdir(parents=True)
    (agent / "settings.json").write_text(
        json.dumps({"packages": ["npm:@scope/pkg@2.0.0"]}), encoding="utf-8"
    )
    manifest = tmp_path / "pi-packages.json"
    manifest.write_text(json.dumps(["npm:@scope/pkg@2.0.0"]), encoding="utf-8")
    monkeypatch.setattr(installer, "MANIFEST", manifest)
    _no_ollama_bootstrap(monkeypatch)
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    installer.install(agent, symlinks=False)
    assert run.call_count == 0  # no reinstall and no `pi update --extensions`


def test_a_new_egm_tag_replaces_a_clean_old_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    (agent / installer.EGM_RELATIVE).mkdir(parents=True)
    old = "git:github.com/google/elephant-goldfish-model@v0.0.9"
    (agent / "settings.json").write_text(
        json.dumps({"packages": [old]}), encoding="utf-8"
    )
    clean: list[Path] = []
    monkeypatch.setattr(installer, "egm_clean", clean.append)
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    installer.install(agent, egm_only=True)
    assert clean == [agent / installer.EGM_RELATIVE]
    assert [call.args[0] for call in run.call_args_list] == [
        ["pi", "remove", old],
        ["pi", "install", installer.EGM_SOURCE],
    ]


def test_a_dirty_old_egm_bundle_stops_the_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = tmp_path / "agent"
    (agent / installer.EGM_RELATIVE).mkdir(parents=True)
    old = "git:github.com/google/elephant-goldfish-model@v0.0.9"
    (agent / "settings.json").write_text(
        json.dumps({"packages": [old]}), encoding="utf-8"
    )

    def dirty(_root: Path) -> None:
        raise RuntimeError("EGM checkout has local changes")

    monkeypatch.setattr(installer, "egm_clean", dirty)
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="local changes"):
        installer.install(agent, egm_only=True)
    assert run.call_count == 0


def test_egm_required_paths_are_what_verify_checks() -> None:
    paths = installer.egm_required_paths()
    assert ".claude-plugin/plugin.json" in paths
    assert "skills/egm-review/SKILL.md" in paths
    assert len(paths) == len(set(paths))
