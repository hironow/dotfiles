"""Claude wiring through sync, in isolated homes and data/state directories."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

if os.name == "nt":
    pytest.skip("transaction tests require POSIX", allow_module_level=True)

import agent_hook_plan as plan
import agent_hook_release as release
import agent_hook_sync as hooks
import agent_hook_wiring as wiring
import sync_agents as sync

ROOT = Path(__file__).resolve().parents[2]
CORPUS = [
    json.loads(line)
    for line in (ROOT / "tools/agent-hooks/internal/rendercorpus/render.jsonl")
    .read_text(encoding="utf-8")
    .splitlines()
]
CLAUDE_RENDER = next(
    case
    for case in CORPUS
    if case["case"] == "render/claude/darwin/default/stable/plain"
)


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for variable, name in (
        ("HOME", "home"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_DATA_HOME", "data"),
    ):
        monkeypatch.setenv(variable, str(tmp_path / name))


class FakeSource:
    def __init__(self, roots: wiring.Roots, *, available: bool = True) -> None:
        self.roots = roots
        self.available = available
        self.id = "1111111111111111"
        self.calls: list[str] = []
        self.selftest_ok = True
        self.template_version = 1
        self.render_owned = True

    def evidence(self) -> plan.ReleaseEvidence:
        path = self.roots.data / "releases" / self.id / "agent-hook"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"#!/bin/sh\nexit 0\n")
            path.chmod(0o700)
        return plan.ReleaseEvidence(
            path.resolve(), self.id, sha256(path.read_bytes()).hexdigest()
        )

    def prepare(self, roots: wiring.Roots) -> hooks.ReleaseOffer:
        self.calls.append("prepare")
        return hooks.ReleaseOffer(
            self.evidence() if self.available else None,
            "" if self.available else "missing Go",
        )

    def preview(self, roots: wiring.Roots) -> hooks.ReleaseOffer:
        self.calls.append("preview")
        path = roots.data / "releases" / self.id / "agent-hook"
        if path.is_file():
            return hooks.ReleaseOffer(
                plan.ReleaseEvidence(
                    path.resolve(), self.id, sha256(path.read_bytes()).hexdigest()
                ),
                "verification unknown until sync",
            )
        return hooks.ReleaseOffer(None, "unknown: release is not built")

    def render(
        self, evidence: plan.ReleaseEvidence, link: Path, system: str
    ) -> release.Outcome:
        self.calls.append("render")
        fragment = json.loads(CLAUDE_RENDER["stdout"])
        for blocks in fragment["hooks"].values():
            for block in blocks:
                for handler in block["hooks"]:
                    handler["command"] = str(link) if self.render_owned else "unowned"
                    handler["timeout"] = 30 + self.template_version - 1
        return release.Outcome(stdout=json.dumps(fragment))

    def selftest(self, link: Path) -> release.Outcome:
        self.calls.append("selftest")
        return (
            release.Outcome()
            if self.selftest_ok
            else release.Outcome(1, reason="selftest failed")
        )


class RecordingDisk(hooks.PosixDisk):
    def __init__(self) -> None:
        self.renames: list[Path] = []
        self.before_rename: Callable[[Path], None] = lambda _: None

    def rename(self, source: Path, target: Path) -> None:
        self.before_rename(target)
        self.renames.append(target)
        super().rename(source, target)


@pytest.fixture
def workspace(
    tmp_path: Path,
) -> tuple[Path, sync.AgentTarget, wiring.Roots, FakeSource]:
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "ROOT_AGENTS.md").write_text("base\n", encoding="utf-8")
    (dotfiles / ".claude").mkdir()
    fragment = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/check.sh"',
                        }
                    ],
                }
            ]
        }
    }
    (dotfiles / sync.HOOK_SETTINGS_FRAGMENT).write_text(
        json.dumps(fragment), encoding="utf-8"
    )
    agent = sync.AgentTarget(
        tmp_path / "home/.claude",
        "Claude",
        key="claude",
        receives_hooks=True,
        main_file="AGENTS.md",
    )
    roots = wiring.Roots.from_env(os.environ)
    return dotfiles, agent, roots, FakeSource(roots)


def open_session(
    workspace: tuple,
    *,
    operation: str = "sync",
    disk: hooks.PosixDisk | None = None,
    steps: wiring.Steps | None = None,
):
    dotfiles, agent, roots, source = workspace
    return hooks.open_session(
        operation,
        [sync.hook_home(dotfiles, agent, roots, "Darwin")],
        roots,
        source,
        disk=disk or RecordingDisk(),
        steps=steps or wiring.NoSteps(),
        validate=lambda: sync.validate_hook_layers(dotfiles, [agent], "Darwin"),
    )


def test_first_wiring_then_noop_and_release_only_update(workspace: tuple) -> None:
    _, agent, roots, source = workspace
    disk = RecordingDisk()
    with open_session(workspace, disk=disk) as session:
        assert session.plans["claude"].plan.action == "register"
        assert session.apply_home("claude").status == "committed"
    settings = agent.directory / "settings.json"
    before = settings.read_bytes(), settings.stat().st_mtime_ns
    assert roots.link("claude").resolve() == source.evidence().path
    assert disk.renames.count(settings) == 1
    with open_session(workspace, disk=disk) as session:
        assert not session.changed
        assert session.apply_home("claude").status == "committed"
    assert (settings.read_bytes(), settings.stat().st_mtime_ns) == before
    source.id = "2222222222222222"
    with open_session(workspace, disk=disk) as session:
        assert session.plans["claude"].plan.action == "link"
        assert session.apply_home("claude").status == "committed"
    assert (settings.read_bytes(), settings.stat().st_mtime_ns) == before
    assert roots.link("claude").resolve().parent.name == source.id
    assert source.calls.count("prepare") == 3


def test_state_is_written_before_the_single_combined_settings_write(
    workspace: tuple,
) -> None:
    dotfiles, agent, _, _ = workspace
    (dotfiles / sync.SHARED_SETTINGS_FRAGMENT).write_text(
        json.dumps({"env": {"A": "1"}, "retired": {"once": {"missing": [False]}}}),
        encoding="utf-8",
    )
    disk = RecordingDisk()
    with open_session(workspace, disk=disk) as session:
        assert session.apply_home("claude").status == "committed"
    settings, state = (
        agent.directory / "settings.json",
        agent.directory / sync.SETTINGS_STATE_FILE,
    )
    assert disk.renames.count(settings) == 1
    assert disk.renames.index(state) < disk.renames.index(settings)
    assert json.loads(settings.read_bytes())["env"] == {"A": "1"}
    assert json.loads(state.read_bytes())["retired"] == ["once"]


def test_sync_mode_does_not_early_return_before_first_wiring(
    workspace: tuple, capsys: pytest.CaptureFixture[str]
) -> None:
    dotfiles, agent, roots, source = workspace
    agent.directory.mkdir(parents=True)
    (agent.directory / "AGENTS.md").write_text("base\n", encoding="utf-8")
    sync._merge_hook_settings(dotfiles, agent)
    sync.sync_mode(
        dotfiles,
        auto_yes=True,
        agents=[agent],
        hook_source=source,
        env=dict(os.environ),
        system="Darwin",
    )
    assert roots.link("claude").resolve() == source.evidence().path
    assert "wired (1111111111111111)" in capsys.readouterr().out


@pytest.mark.parametrize("layer", ["shared", "os", "profile", "local", "retired"])
def test_hooks_in_any_settings_layer_stop_before_home_or_release_writes(
    workspace: tuple, layer: str
) -> None:
    dotfiles, agent, _, source = workspace
    path = {
        "shared": dotfiles / sync.SHARED_SETTINGS_FRAGMENT,
        "os": dotfiles / ".claude/settings.shared.macos.json",
        "profile": dotfiles / ".claude/settings.profiles/claude.json",
        "local": agent.directory / sync.MACHINE_LOCAL_SETTINGS,
        "retired": dotfiles / sync.SHARED_SETTINGS_FRAGMENT,
    }[layer]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"retired": {"x": {"hooks": [{}]}}}
            if layer == "retired"
            else {"settings": {"hooks": {}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as stopped:
        sync.sync_mode(
            dotfiles,
            auto_yes=True,
            agents=[agent],
            hook_source=source,
            env=dict(os.environ),
            system="Darwin",
        )
    assert stopped.value.code == 1
    assert source.calls == []
    assert not (agent.directory / "AGENTS.md").exists()
    assert not (agent.directory / "settings.json").exists()


def test_native_windows_keeps_scripts_without_calling_the_source(
    workspace: tuple, capsys: pytest.CaptureFixture[str]
) -> None:
    dotfiles, agent, roots, source = workspace
    sync.sync_mode(
        dotfiles,
        auto_yes=True,
        agents=[agent],
        hook_source=source,
        env=dict(os.environ),
        system="Windows",
    )
    assert source.calls == []
    assert not roots.link("claude").exists()
    assert "native Windows" in capsys.readouterr().out
    command = json.loads((agent.directory / "settings.json").read_bytes())["hooks"][
        "PreToolUse"
    ][0]["hooks"][0]["command"]
    assert command.startswith('sh "')


def test_real_release_source_reports_missing_go_without_running_anything(
    tmp_path: Path,
) -> None:
    env = {**os.environ, "PATH": ""}
    source = hooks.GoReleaseSource(env)
    offer = source.prepare(wiring.Roots.from_env(env))
    assert offer.release is None and "Go" in offer.reason


def test_real_release_source_bounds_every_program_and_uses_supplied_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = wiring.Roots.from_env(os.environ)
    binary = roots.data / "releases/1234567890abcdef/agent-hook"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        f"#!{sys.executable}\nimport json, sys\nfragment = json.loads({CLAUDE_RENDER['stdout']!r})\nif sys.argv[1] == 'render':\n for blocks in fragment['hooks'].values():\n  for block in blocks:\n   for hook in block['hooks']: hook['command'] = sys.argv[-1]\n print(json.dumps(fragment))\n",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    checker_text = f"#!{sys.executable}\nimport sys\nif sys.argv[1] == 'build': print({str(binary)!r})\nelif sys.argv[1] == 'id': print('1234567890abcdef')\n"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    go = bin_dir / "go"
    go.write_text(
        f"#!{sys.executable}\nfrom pathlib import Path\nimport sys\npath = Path(sys.argv[sys.argv.index('-o') + 1])\npath.write_text({checker_text!r}, encoding='utf-8')\npath.chmod(0o700)\n",
        encoding="utf-8",
    )
    go.chmod(0o700)
    env = {**os.environ, "PATH": str(bin_dir)}
    calls: list[tuple[list[str], float, dict]] = []
    original_run = release.run

    def record(args, *, timeout, **kwargs):
        calls.append((list(args), timeout, kwargs))
        return original_run(args, timeout=timeout, **kwargs)

    monkeypatch.setattr(release, "run", record)
    source = hooks.GoReleaseSource(env)
    offer = source.prepare(roots)
    assert offer.release is not None, offer.reason
    assert offer.release.path == binary.resolve()
    assert offer.release.sha256 == sha256(binary.read_bytes()).hexdigest()
    assert [timeout for _, timeout, _ in calls] == [300, 300, 30, 300]
    assert all(call[2]["env"]["HOME"] == env["HOME"] for call in calls)
    rendered = source.render(offer.release, roots.link("claude"), "Darwin")
    assert rendered.ok and source.selftest(binary).ok
    assert [call[1] for call in calls[-2:]] == [30, 30]
    assert all(call[2]["cwd"] == release.MODULE for call in calls)


def test_user_edit_after_planning_is_preserved_by_one_replan(workspace: tuple) -> None:
    _, agent, _, source = workspace
    with open_session(workspace) as session:
        agent.directory.mkdir(parents=True)
        (agent.directory / "settings.json").write_bytes(b'{"editor":"kept"}')
        assert session.apply_home("claude").status == "committed"
    assert (
        json.loads((agent.directory / "settings.json").read_bytes())["editor"] == "kept"
    )
    assert source.calls.count("prepare") == 1
    assert source.calls.count("render") == 2


def test_a_second_edit_stops_without_writing_the_home(workspace: tuple) -> None:
    _, agent, _, _ = workspace
    settings_path = agent.directory / "settings.json"

    class ChangingDisk(RecordingDisk):
        reads = 0

        def read_bytes(self, path: Path) -> bytes:
            raw = super().read_bytes(path)
            if path == settings_path:
                self.reads += 1
                if raw == b'{"editor":1}' and self.reads == 2:
                    path.write_bytes(b'{"editor":2}')
            return raw

    disk = ChangingDisk()
    with open_session(workspace, disk=disk) as session:
        agent.directory.mkdir(parents=True)
        settings_path.write_bytes(b'{"editor":1}')
        result = session.apply_home("claude")
    assert result.status == "stopped" and "changed while sync ran" in result.reason
    assert settings_path.read_bytes() == b'{"editor":2}'
    assert disk.renames == []


class FakeProcesses:
    def __init__(self, running: bool = False) -> None:
        self.is_running = running
        self.calls = 0

    def running(self) -> bool:
        self.calls += 1
        return self.is_running


def configuration(workspace: tuple) -> hooks.HookConfiguration:
    dotfiles, agent, _, source = workspace
    return sync.hook_configuration(
        dotfiles,
        env=dict(os.environ),
        source=source,
        all_agents=[agent],
        system="Darwin",
        processes=FakeProcesses(),
    )


def test_uninstall_twice_sync_scripts_then_install_preserves_user_hooks(
    workspace: tuple,
) -> None:
    _, agent, roots, source = workspace
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    path = agent.directory / "settings.json"
    current = json.loads(path.read_bytes())
    user = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "user-command"}],
    }
    other = {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": str(roots.link("work-a")),
                "args": ["claude", "pre"],
            }
        ],
    }
    direct = {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": str(source.evidence().path),
                "args": ["claude", "pre"],
            }
        ],
    }
    current["hooks"]["PreToolUse"].extend([user, other, direct])
    current["private-key"] = "kept"
    path.write_text(json.dumps(current), encoding="utf-8")
    config = configuration(workspace)
    source.available = False
    calls_before = source.calls.count("prepare")
    assert hooks.run_command(config, "uninstall", ["p"]) == 0
    assert roots.mark("claude").is_file()
    first = path.read_bytes(), path.stat().st_mtime_ns
    assert hooks.run_command(config, "uninstall", ["p"]) == 0
    assert (path.read_bytes(), path.stat().st_mtime_ns) == first
    assert source.calls.count("prepare") == calls_before
    assert roots.link("claude").is_symlink()
    assert source.evidence().path.is_file()
    with open_session(workspace) as session:
        assert session.plans["claude"].plan.action == "uninstalled"
        assert session.apply_home("claude").status == "committed"
    assert hooks.run_command(config, "install", ["p"]) == 1
    assert roots.mark("claude").is_file()
    source.available = True
    assert hooks.run_command(config, "install", ["p"]) == 0
    assert not roots.mark("claude").exists()
    after = json.loads(path.read_bytes())
    assert after["private-key"] == "kept"
    assert all(block in after["hooks"]["PreToolUse"] for block in (user, direct))
    # A block that runs another home's stable link is sync's by its one rule
    # (as doctor and the scripts' merge read it), so this home's replaces it.
    assert other not in after["hooks"]["PreToolUse"]


@pytest.mark.parametrize("name", ["x", "codex", "g", "gemini", "no-such-target"])
def test_cli_refuses_non_claude_targets_before_taking_the_lock(
    workspace: tuple, name: str
) -> None:
    config = configuration(workspace)
    assert hooks.run_command(config, "install", [name]) != 0
    assert not config.roots.lock.exists()
    assert not config.roots.data.exists()


def test_gc_preserves_links_and_unowned_release_commands_and_args(
    workspace: tuple,
) -> None:
    _, agent, roots, source = workspace
    first = source.evidence()
    source.id = "2222222222222222"
    second = source.evidence()
    source.id = "3333333333333333"
    third = source.evidence()
    source.id = "4444444444444444"
    unused = source.evidence()
    wiring.switch_link(RecordingDisk(), roots.data, "unknown-key", first.path)
    agent.directory.mkdir(parents=True)
    registration = {
        "hooks": {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f"'{second.path}' run",
                            "args": [str(third.path)],
                            "async": True,
                        }
                    ]
                }
            ]
        }
    }
    (agent.directory / "settings.json").write_text(
        json.dumps(registration), encoding="utf-8"
    )
    config = configuration(workspace)
    assert hooks.run_command(config, "gc", []) == 0
    assert unused.path.is_file()
    assert hooks.run_command(config, "gc", [], delete=True) == 0
    assert not unused.path.parent.exists()
    assert all(item.path.is_file() for item in (first, second, third))
    assert source.calls == []


def test_preview_uses_only_id_and_existing_releases_and_writes_nothing(
    workspace: tuple, capsys: pytest.CaptureFixture[str]
) -> None:
    dotfiles, agent, roots, source = workspace
    disk = RecordingDisk()
    sync.preview_mode(
        dotfiles,
        agents=[agent],
        hook_source=source,
        env=dict(os.environ),
        system="Darwin",
        hook_disk=disk,
    )
    assert source.calls == ["preview"]
    assert disk.renames == []
    assert not roots.lock.exists()
    assert not roots.data.exists()
    assert not agent.directory.exists()
    assert "unknown" in capsys.readouterr().out


def test_gc_rechecks_a_link_that_moves_after_listing(workspace: tuple) -> None:
    _, _, roots, source = workspace
    first = source.evidence()
    source.id = "2222222222222222"
    keep = source.evidence()
    wiring.switch_link(RecordingDisk(), roots.data, "claude", first.path)

    class MovingDisk(RecordingDisk):
        reads = 0

        def entries(self, path: Path) -> list[Path]:
            if path == roots.data / "current":
                self.reads += 1
                if self.reads == 2:
                    wiring.switch_link(RecordingDisk(), roots.data, "claude", keep.path)
            return super().entries(path)

    assert (
        hooks.run_command(
            configuration(workspace), "gc", [], delete=True, disk=MovingDisk()
        )
        == 0
    )
    assert keep.path.is_file()


def test_gc_reads_every_release_named_by_a_journal(workspace: tuple) -> None:
    _, agent, roots, source = workspace
    evidence = []
    for number in range(1, 6):
        source.id = f"{number:016x}"
        evidence.append(source.evidence())
    agent.directory.mkdir(parents=True)
    old_settings = json.dumps(
        {
            "hooks": {
                "PreToolUse": [
                    {
                        "hooks": [
                            {
                                "command": str(evidence[2].path),
                                "args": [str(evidence[3].path)],
                            }
                        ]
                    }
                ]
            }
        }
    ).encode()
    new_settings = json.dumps(
        {"hooks": {"PreToolUse": [{"hooks": [{"command": str(evidence[4].path)}]}]}}
    ).encode()
    journal = wiring.Journal(
        "claude",
        "register",
        "link",
        wiring.Release(evidence[0].path, evidence[0].id, evidence[0].sha256),
        wiring.LinkChange(
            roots.link("claude"), str(evidence[1].path), str(evidence[0].path)
        ),
        wiring.FileChange(
            agent.directory / "settings.json", old_settings, new_settings
        ),
        None,
    )
    wiring.write_journal(RecordingDisk(), roots.journal("claude"), journal)
    found = hooks.release_references(roots, RecordingDisk(), [])
    assert found == {item.path for item in evidence}


def test_gc_delete_refuses_a_running_codex(workspace: tuple) -> None:
    config = replace(configuration(workspace), processes=FakeProcesses(True))
    unused = workspace[3].evidence()
    assert hooks.run_command(config, "gc", [], delete=True) == 1
    assert unused.path.is_file()


def test_install_with_equal_registration_moves_only_the_mark(workspace: tuple) -> None:
    _, agent, roots, _ = workspace
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    mark = roots.mark("claude")
    mark.parent.mkdir(parents=True)
    mark.write_bytes(b"")
    settings = agent.directory / "settings.json"
    before = settings.read_bytes(), settings.stat().st_mtime_ns
    disk = RecordingDisk()
    with open_session(workspace, operation="install", disk=disk) as session:
        assert session.plans["claude"].plan.settings is plan.UNCHANGED
        assert session.apply_home("claude").status == "committed"
    assert (settings.read_bytes(), settings.stat().st_mtime_ns) == before
    assert settings not in disk.renames
    assert roots.link("claude") not in disk.renames
    assert not mark.exists()


@pytest.mark.parametrize("foreign_hooks", [False, True])
def test_a_journaled_change_abandons_without_replanning_after_file_edit(
    workspace: tuple, foreign_hooks: bool
) -> None:
    _, agent, roots, source = workspace
    foreign = b'{"hooks":{"editor":[]}}' if foreign_hooks else b'{"editor":"keep"}'

    class EditingSteps:
        def before(self, key: str, stage: str) -> None:
            if stage == "file":
                (agent.directory / "settings.json").write_bytes(foreign)

    with open_session(workspace, steps=EditingSteps()) as session:
        result = session.apply_home("claude")
    assert result.status == "abandoned"
    assert (agent.directory / "settings.json").read_bytes() == foreign
    assert source.calls.count("render") == 1
    assert roots.link("claude").is_symlink()
    assert not roots.journal("claude").exists()


@pytest.mark.parametrize("selftest_ok", [False, True])
def test_other_settings_edits_survive_verify_and_restore(
    workspace: tuple, selftest_ok: bool
) -> None:
    dotfiles, agent, roots, source = workspace
    agent.directory.mkdir(parents=True)
    settings = agent.directory / "settings.json"
    settings.write_bytes(b'{"hooks":{"user":[]},"old":1}')
    (dotfiles / sync.SHARED_SETTINGS_FRAGMENT).write_text(
        json.dumps({"env": {"NEW": "yes"}, "retired": {"once": {"absent": [True]}}}),
        encoding="utf-8",
    )
    source.selftest_ok = selftest_ok

    class EditingSteps:
        def before(self, key: str, stage: str) -> None:
            if stage == "verify":
                current = json.loads(settings.read_bytes())
                current["editor"] = "kept"
                settings.write_text(json.dumps(current), encoding="utf-8")

    with open_session(workspace, steps=EditingSteps()) as session:
        result = session.apply_home("claude")
    assert result.status == ("committed" if selftest_ok else "restored")
    current = json.loads(settings.read_bytes())
    assert current["editor"] == "kept" and current["env"] == {"NEW": "yes"}
    assert json.loads((agent.directory / sync.SETTINGS_STATE_FILE).read_bytes())[
        "retired"
    ] == ["once"]
    assert not roots.journal("claude").exists()


def test_a_hooks_edit_stops_with_the_journal_kept(workspace: tuple) -> None:
    _, agent, roots, _ = workspace

    class EditingSteps:
        def before(self, key: str, stage: str) -> None:
            if stage == "verify":
                (agent.directory / "settings.json").write_bytes(
                    b'{"hooks":{"editor":[]}}'
                )

    with open_session(workspace, steps=EditingSteps()) as session:
        result = session.apply_home("claude")
    assert result.status == "stopped" and "file.hooks" in result.reason
    assert roots.journal("claude").is_file()


def test_state_only_sync_records_absent_migrations_and_preserves_a_later_value(
    workspace: tuple,
) -> None:
    dotfiles, agent, _, _ = workspace
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    settings = agent.directory / "settings.json"
    before = settings.read_bytes(), settings.stat().st_mtime_ns
    (dotfiles / sync.SHARED_SETTINGS_FRAGMENT).write_text(
        json.dumps({"retired": {"once": {"old": [False]}}}), encoding="utf-8"
    )
    disk = RecordingDisk()
    with open_session(workspace, disk=disk) as session:
        assert session.changed and session.plans["claude"].plan.action == "nothing"
        assert session.apply_home("claude").status == "committed"
    assert (settings.read_bytes(), settings.stat().st_mtime_ns) == before
    assert disk.renames == [agent.directory / sync.SETTINGS_STATE_FILE]
    current = json.loads(settings.read_bytes())
    current["old"] = False
    settings.write_text(json.dumps(current), encoding="utf-8")
    with open_session(workspace) as session:
        assert not session.changed
        assert session.apply_home("claude").status == "committed"
    assert json.loads(settings.read_bytes())["old"] is False


def test_keep_preserves_the_entire_file_when_no_release_is_available(
    workspace: tuple,
) -> None:
    _, agent, _, source = workspace
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    settings = agent.directory / "settings.json"
    current = json.loads(settings.read_bytes())
    user = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": "user-after-owned"}],
    }
    current["hooks"]["PreToolUse"].append(user)
    settings.write_text(json.dumps(current, separators=(",", ":")), encoding="utf-8")
    before = settings.read_bytes(), settings.stat().st_mtime_ns
    source.available = False
    disk = RecordingDisk()
    with open_session(workspace, disk=disk) as session:
        assert session.plans["claude"].plan.action == "keep"
        assert not session.changed
        assert session.apply_home("claude").status == "committed"
    assert (settings.read_bytes(), settings.stat().st_mtime_ns) == before
    assert disk.renames == []


def test_changed_template_registers_again_without_moving_the_link(
    workspace: tuple,
) -> None:
    _, agent, roots, source = workspace
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    source.template_version = 2
    disk = RecordingDisk()
    with open_session(workspace, disk=disk) as session:
        assert session.plans["claude"].plan.action == "register"
        assert session.apply_home("claude").status == "committed"
    assert roots.link("claude") not in disk.renames
    assert disk.renames.count(agent.directory / "settings.json") == 1


def test_a_moved_link_is_planned_again_from_its_new_target(workspace: tuple) -> None:
    _, _, roots, source = workspace
    source.id = "2222222222222222"
    other = source.evidence()
    source.id = "1111111111111111"
    with open_session(workspace) as session:
        wiring.switch_link(RecordingDisk(), roots.data, "claude", other.path)
        result = session.apply_home("claude")
        assert session.plans["claude"].facts.target == str(other.path)
    assert result.status == "committed"
    assert roots.link("claude").resolve() == source.evidence().path
    assert source.calls.count("prepare") == 1


def test_uninstall_and_install_do_not_apply_shared_settings_or_retirements(
    workspace: tuple,
) -> None:
    dotfiles, agent, _, _ = workspace
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    state = agent.directory / sync.SETTINGS_STATE_FILE
    state.write_bytes(b'{ "retired":[], "private":true }')
    settings = agent.directory / "settings.json"
    current = json.loads(settings.read_bytes())
    current.update({"env": {"PRIVATE": "yes"}, "old": False, "language": "ja"})
    settings.write_text(json.dumps(current), encoding="utf-8")
    (dotfiles / sync.SHARED_SETTINGS_FRAGMENT).write_text(
        json.dumps(
            {
                "env": {"REPLACED": "no"},
                "settings": {"language": "en"},
                "retired": {"once": {"old": [False]}},
            }
        ),
        encoding="utf-8",
    )
    before = {key: value for key, value in current.items() if key != "hooks"}
    state_before = state.read_bytes(), state.stat().st_mtime_ns
    for operation in ("uninstall", "install"):
        assert hooks.run_command(configuration(workspace), operation, ["p"]) == 0
        assert {
            key: value
            for key, value in json.loads(settings.read_bytes()).items()
            if key != "hooks"
        } == before
        assert (state.read_bytes(), state.stat().st_mtime_ns) == state_before


def test_third_party_hook_files_and_blocks_survive_the_full_cycle(
    workspace: tuple,
) -> None:
    _, agent, _, _ = workspace
    (agent.directory / "hooks").mkdir(parents=True)
    script = agent.directory / "hooks/herdr.py"
    script.write_text("# installed by herdr\n", encoding="utf-8")
    block = {
        "matcher": "Bash",
        "hooks": [{"type": "command", "command": f'python "{script}"'}],
    }
    settings = agent.directory / "settings.json"
    settings.write_text(
        json.dumps({"hooks": {"PreToolUse": [block]}}), encoding="utf-8"
    )
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    for operation in ("uninstall", "install"):
        assert hooks.run_command(configuration(workspace), operation, ["p"]) == 0
        assert block in json.loads(settings.read_bytes())["hooks"]["PreToolUse"]
        assert script.read_text(encoding="utf-8") == "# installed by herdr\n"


def test_crashed_change_is_recovered_before_preparing_a_release_and_the_sessions_link_stays(
    workspace: tuple,
) -> None:
    _, agent, roots, source = workspace
    settings = agent.directory / "settings.json"
    session_command = agent.directory.parent / "session-command"

    class CrashDisk(RecordingDisk):
        def fsync_directory(self, path: Path) -> None:
            super().fsync_directory(path)
            if path == agent.directory and settings.exists():
                command = json.loads(settings.read_bytes())["hooks"]["PreToolUse"][0][
                    "hooks"
                ][0]["command"]
                session_command.write_text(command, encoding="utf-8")
                os._exit(0)

    child = os.fork()
    if child == 0:
        try:
            with open_session(workspace, disk=CrashDisk()) as session:
                session.apply_home("claude")
        finally:
            os._exit(91)
    _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0
    assert wiring.read_journal(RecordingDisk(), roots.journal("claude")).stage == "file"
    source.available = False
    with open_session(workspace) as session:
        assert session.recovered
        assert (
            source.calls[0] == "prepare"
        )  # No selftest is needed while restoring stage=file.
    assert not settings.exists()
    command = session_command.read_text(encoding="utf-8")
    assert release.run(
        [command, "claude", "pre", "--hook", "rtk"], env=dict(os.environ), timeout=2
    ).ok
    assert roots.link("claude").is_symlink()


def test_recovery_stop_prevents_release_preparation_and_gc_deletion(
    workspace: tuple,
) -> None:
    config = configuration(workspace)
    unused = workspace[3].evidence()
    config.roots.state.mkdir(parents=True)
    journal = config.roots.journal("claude")
    journal.write_bytes(b"{")
    assert hooks.run_command(config, "gc", [], delete=True) == 1
    assert unused.path.is_file() and journal.read_bytes() == b"{"
    assert workspace[3].calls == []


def test_two_entries_use_the_same_lock_before_preparing_a_release(
    workspace: tuple,
) -> None:
    with open_session(workspace):
        child = os.fork()
        if child == 0:
            try:
                with (
                    pytest.raises(wiring.LockBusy),
                    hooks.open_session(
                        "uninstall", [], workspace[2], workspace[3], wait_limit=0.03
                    ),
                ):
                    os._exit(92)
                os._exit(0)
            finally:
                os._exit(93)
        _, status = os.waitpid(child, 0)
    assert os.waitstatus_to_exitcode(status) == 0


def test_gc_reads_codex_registrations_independently_of_ownership(
    workspace: tuple,
) -> None:
    dotfiles, agent, _, source = workspace
    direct = source.evidence()
    codex = sync.AgentTarget(
        agent.directory.parent / ".codex",
        "Codex",
        key="codex",
        receives_codex_hooks=True,
    )
    codex.directory.mkdir(parents=True)
    (codex.directory / "hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "hooks": [
                                {
                                    "command": f"'{direct.path}' codex pre",
                                    "commandWindows": "user-owned",
                                }
                            ]
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    config = sync.hook_configuration(
        dotfiles,
        env=dict(os.environ),
        source=source,
        all_agents=[agent, codex],
        system="Darwin",
        processes=FakeProcesses(),
    )
    assert hooks.run_command(config, "gc", [], delete=True) == 0
    assert direct.path.is_file()


def test_unowned_render_falls_back_to_scripts_and_keeps_a_previously_wired_home(
    workspace: tuple,
) -> None:
    _, agent, roots, source = workspace
    source.render_owned = False
    with open_session(workspace) as session:
        assert session.plans["claude"].plan.action == "scripts"
        assert session.apply_home("claude").status == "committed"
    assert not roots.link("claude").exists()
    source.render_owned = True
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    before = (agent.directory / "settings.json").read_bytes()
    source.render_owned = False
    with open_session(workspace) as session:
        assert session.plans["claude"].plan.action == "keep"
        assert session.apply_home("claude").status == "committed"
    assert (agent.directory / "settings.json").read_bytes() == before


def test_preview_of_an_existing_release_still_does_not_lock_or_write(
    workspace: tuple, capsys: pytest.CaptureFixture[str]
) -> None:
    dotfiles, agent, roots, source = workspace
    source.evidence()
    disk = RecordingDisk()
    sync.preview_mode(
        dotfiles,
        agents=[agent],
        hook_source=source,
        env=dict(os.environ),
        system="Darwin",
        hook_disk=disk,
    )
    assert source.calls == ["preview", "render"]
    assert not roots.lock.exists() and not agent.directory.exists()
    assert disk.renames == []
    assert "unknown" in capsys.readouterr().out


def test_cli_parser_passes_only_explicit_scratch_configuration(
    workspace: tuple,
) -> None:
    config = configuration(workspace)
    assert hooks.main(["uninstall", "p"], configure=lambda _: config) == 0
    assert config.roots.mark("claude").exists()


@pytest.mark.parametrize(
    "exit_code,expected", [(0, True), (1, False), (2, None), (None, None)]
)
def test_pgrep_port_distinguishes_no_process_from_a_failed_query(
    workspace: tuple,
    monkeypatch: pytest.MonkeyPatch,
    exit_code: int | None,
    expected: bool | None,
) -> None:
    calls = []

    def fake_query(args, *, timeout, env):
        calls.append((args, timeout, env["HOME"]))
        return release.Outcome(
            exit_code, reason="query failed" if exit_code is None else None
        )

    monkeypatch.setattr(release, "run", fake_query)
    processes = hooks.PgrepCodex(dict(os.environ))
    if expected is None:
        with pytest.raises(hooks.SyncStopped):
            processes.running()
    else:
        assert processes.running() is expected
    assert calls == [(["pgrep", "-x", "codex"], 30, os.environ["HOME"])]


def test_the_real_command_entry_uninstalls_only_in_explicit_scratch_homes(
    workspace: tuple,
) -> None:
    dotfiles, _, roots, _ = workspace
    outcome = release.run(
        [
            sys.executable,
            str(ROOT / "scripts/agent_hook_sync.py"),
            "uninstall",
            "p",
            "--dotfiles",
            str(dotfiles),
        ],
        env=dict(os.environ),
        cwd=ROOT,
        timeout=5,
    )
    assert outcome.ok, outcome.reason or outcome.stderr
    assert roots.mark("claude").is_file()
    assert not roots.link("claude").exists()


def test_a_home_that_stops_lets_the_others_sync_then_the_run_fails(
    workspace: tuple, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dotfiles, agent, roots, source = workspace
    work = sync.AgentTarget(
        tmp_path / "home/.claude-work-a",
        "Claude work-a",
        key="work-a",
        receives_hooks=True,
        main_file="AGENTS.md",
    )
    # given work-a uninstalled, yet wired (the state that stops), and claude
    # not yet wired, listed after it
    with open_session(workspace) as session:
        assert session.apply_home("claude").status == "committed"
    wired = (agent.directory / "settings.json").read_bytes()
    work.directory.mkdir(parents=True)
    (work.directory / "settings.json").write_bytes(
        wired.replace(b"/current/claude/", b"/current/work-a/")
    )
    roots.mark("work-a").parent.mkdir(parents=True, exist_ok=True)
    roots.mark("work-a").write_bytes(b"")
    (agent.directory / "settings.json").unlink()
    # when sync runs both
    with pytest.raises(SystemExit) as exit_info:
        sync.sync_mode(
            dotfiles,
            auto_yes=True,
            agents=[work, agent],
            hook_source=source,
            env=dict(os.environ),
            system="Darwin",
        )
    # then claude is wired anyway, work-a is left as it was, and the run fails
    out = capsys.readouterr().out
    assert exit_info.value.code == 1
    assert "agent-hook: work-a stopped: uninstalled, yet wired" in out
    assert "agent-hook: claude wired (1111111111111111)" in out
    assert (agent.directory / "settings.json").is_file()
    assert (work.directory / "settings.json").read_bytes() == wired.replace(
        b"/current/claude/", b"/current/work-a/"
    )
