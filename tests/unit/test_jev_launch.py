"""Opt-in Jev launcher: typed answers, host validation, and subscription order."""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock
from typing import cast

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))  # jev_launch imports its sibling core
SCRIPT = SCRIPTS / "jev_launch.py"
spec = importlib.util.spec_from_file_location("jev_launch", SCRIPT)
assert spec is not None and spec.loader is not None
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


HARD = (
    b'{"answers":{"difficulty":{"type":"score","score":1.9,"confidence":0.9},'
    b'"strict_structure":{"type":"noul","noul":0.1}}}'
)


def test_jev_selects_high_without_exposing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    def reply(request: urllib.request.Request, timeout: int) -> io.BytesIO:
        assert timeout == 5
        assert isinstance(request.data, bytes)
        assert "secret" not in request.data.decode("utf-8")
        assert request.get_header("Authorization") == "Bearer secret"
        return io.BytesIO(HARD)

    monkeypatch.setattr(launcher.urllib.request, "urlopen", reply)
    assert launcher.choose_effort("fix a complex bug", "secret") == "high"


@pytest.mark.parametrize(
    "answer",
    [b'{"answers":{"difficulty":{"type":"choice"}}}', b'{"answers":{}}', b"[]"],
)
def test_unusable_answer_falls_back(
    monkeypatch: pytest.MonkeyPatch, answer: bytes
) -> None:
    monkeypatch.setattr(
        launcher.urllib.request, "urlopen", lambda *_args, **_kwargs: io.BytesIO(answer)
    )
    assert launcher.choose_effort("task", "secret") == "medium"


def test_private_home_env_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip(
            "Windows uses process env; POSIX ownership/mode checks do not apply"
        )
    secret = tmp_path / ".env"
    secret.write_text("TYPESAFE_API_KEY=secret\n", encoding="utf-8")
    monkeypatch.setattr(launcher.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_AI_API_KEY", raising=False)
    secret.chmod(0o644)
    assert launcher.jev_key() is None
    secret.chmod(0o600)
    assert launcher.jev_key() == "secret"


def test_home_env_key_needs_a_private_file_on_every_platform(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # given a key in ~/.env and no key in the environment
    (tmp_path / ".env").write_text("TYPESAFE_API_KEY=secret\n", encoding="utf-8")
    monkeypatch.setattr(launcher.Path, "home", lambda: tmp_path)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.delenv("TYPESAFE_AI_API_KEY", raising=False)

    # when the file is not private, then the key is refused with a hint
    monkeypatch.setattr(launcher, "env_file_is_private", lambda _path: False)
    assert launcher.jev_key() is None
    assert "~/.env" in capsys.readouterr().err

    # when it is private, then the key is read (Windows included)
    monkeypatch.setattr(launcher, "env_file_is_private", lambda _path: True)
    assert launcher.jev_key() == "secret"


def _my_sid() -> str:
    """The current user's SID (CSV output, so it is locale-independent)."""
    row = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    ).stdout
    return row.strip().split(",")[-1].strip('"')


def _icacls(*args: str) -> None:
    subprocess.run(["icacls", *args], check=True, capture_output=True)


@pytest.mark.skipif(sys.platform != "win32", reason="reads a real Windows ACL")
def test_windows_acl_check_on_a_real_file(tmp_path: Path) -> None:
    # given a file made private the way the runbook says (a temp dir may grant
    # other accounts access, so its inherited ACL is not assumed)
    secret = tmp_path / ".env"
    secret.write_text("TYPESAFE_API_KEY=secret\n", encoding="utf-8")
    _icacls(str(secret), "/inheritance:r", "/grant:r", f"*{_my_sid()}:(F)")
    assert launcher.env_file_is_private(secret) is True

    # when Everyone (by SID, so the check is locale-independent) may read it
    _icacls(str(secret), "/grant", "*S-1-1-0:(R)")

    # then it is no longer private
    assert launcher.env_file_is_private(secret) is False


@pytest.mark.skipif(sys.platform != "win32", reason="reads a real Windows ACL")
def test_windows_acl_check_accepts_a_file_with_only_inherited_entries(
    tmp_path: Path,
) -> None:
    # given a folder shaped like a default profile home (the user, SYSTEM and
    # Administrators, inherited by new files)
    home = tmp_path / "home"
    home.mkdir()
    grants = [f"*{sid}:(OI)(CI)(F)" for sid in (_my_sid(), "S-1-5-18", "S-1-5-32-544")]
    _icacls(
        str(home), "/inheritance:r", *[g for sid in grants for g in ("/grant:r", sid)]
    )

    # when ~/.env is created there with no ACL of its own
    secret = home / ".env"
    secret.write_text("TYPESAFE_API_KEY=secret\n", encoding="utf-8")

    # then its inherited ACL is accepted as private without any repair
    assert launcher.env_file_is_private(secret) is True


def test_network_error_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(launcher.urllib.request, "urlopen", fail)
    assert launcher.choose_effort("task", "secret") == "medium"


def test_pi_route_prefers_ready_subscription(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setenv("TYPESAFE_API_KEY", "secret")

    def check(args: list[str], **kwargs: object) -> Mock:
        seen.append(args[-1])
        assert "TYPESAFE_API_KEY" not in cast("dict[str, str]", kwargs["env"])
        return Mock(
            returncode=0, stdout="ready" if args[-1] == "cursor" else "not_ready"
        )

    monkeypatch.setattr(launcher.subprocess, "run", check)
    assert launcher.pi_route() == "cursor/claude-sonnet-5-5"
    assert seen == ["github-copilot", "cursor"]


def test_pi_route_uses_metered_only_after_subscriptions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def check(args: list[str], **_kwargs: object) -> Mock:
        seen.append(args[-1])
        return Mock(
            returncode=0, stdout="ready" if args[-1] == "openrouter" else "not_ready"
        )

    monkeypatch.setattr(launcher.subprocess, "run", check)
    assert launcher.pi_route() == "openrouter/anthropic/claude-sonnet-5.5"
    assert seen == ["github-copilot", "cursor", "openrouter"]


def test_pi_without_ready_provider_exits_with_a_message_not_a_traceback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(launcher.sys, "argv", ["jev_launch.py", "pi", "hello"])
    monkeypatch.setattr(launcher, "jev_key", lambda: None)
    monkeypatch.setattr(
        launcher.subprocess,
        "run",
        lambda args, **_kwargs: Mock(returncode=0, stdout="not_ready"),
    )
    monkeypatch.setattr(
        launcher.os,
        "execvpe",
        lambda *_args: pytest.fail("Pi must not start without a ready provider"),
    )
    with pytest.raises(SystemExit) as exited:
        launcher.main()
    assert exited.value.code == (
        "Jev: no authenticated Pi Sonnet 5.5 provider (run pi /login)"
    )


def _launch(
    monkeypatch: pytest.MonkeyPatch, host: str
) -> tuple[list[str], dict[str, str]]:
    """Run main() with the effects stubbed; return what would be executed."""
    seen: dict[str, tuple[list[str], dict[str, str]]] = {}
    monkeypatch.setattr(launcher.sys, "argv", ["jev_launch.py", host, "hello"])
    monkeypatch.setattr(launcher, "jev_key", lambda: "secret")
    monkeypatch.setattr(launcher, "choose_effort", lambda *_args: "high")
    monkeypatch.setattr(launcher, "extension_installed", lambda: True)
    monkeypatch.setattr(
        launcher, "pi_route", lambda: "github-copilot/claude-sonnet-5.5"
    )

    def child(argv: list[str], **kwargs: object) -> Mock:
        seen["run"] = (argv, cast("dict[str, str]", kwargs["env"]))
        return Mock(returncode=0)

    monkeypatch.setattr(launcher.subprocess, "run", child)
    monkeypatch.setattr(
        launcher.os,
        "execvpe",
        lambda _file, argv, env: seen.update(run=(argv, env)),
    )
    try:
        launcher.main()
    except SystemExit:
        pass
    return seen["run"]


def test_main_wires_key_effort_route_and_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv, env = _launch(monkeypatch, "pi")
    assert Path(argv[0]).stem == "pi"
    assert argv[1:5] == [
        "--model",
        "github-copilot/claude-sonnet-5.5",
        "--thinking",
        "high",
    ]
    assert env["JEV_KEY_HANDOFF"] == "secret" and "TYPESAFE_API_KEY" not in env
    argv, env = _launch(monkeypatch, "claude")
    assert Path(argv[0]).stem == "claude"
    assert argv[1:5] == ["--model", launcher.SONNET, "--effort", "high"]
    assert "JEV_KEY_HANDOFF" not in env


def test_claude_gets_the_worker_hook_and_agents_but_pi_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argv, _ = _launch(monkeypatch, "claude")
    settings = json.loads(argv[argv.index("--settings") + 1])
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert "jev_claude_hook.py" in command
    assert Path(sys.executable).as_posix() in command
    assert set(json.loads(argv[argv.index("--agents") + 1])) == {
        "worker-medium",
        "worker-high",
    }
    argv, _ = _launch(monkeypatch, "pi")
    assert "--settings" not in argv and "--agents" not in argv


@pytest.mark.parametrize("installed", [True, False])
def test_extension_is_detected_in_the_pi_agent_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, installed: bool
) -> None:
    (tmp_path / "extensions").mkdir()
    if installed:
        (tmp_path / "extensions/jev-sonnet-fallback.ts").write_text(
            "x", encoding="utf-8"
        )
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path))
    assert launcher.extension_installed() is installed


def _hook_shell() -> str:
    """The bash Claude Code runs hook commands with: Git Bash on Windows."""
    if sys.platform != "win32":
        return shutil.which("bash") or "bash"
    # Never a bare "bash" from a native process: System32's WSL bash wins.
    # git may be <root>/cmd/git.exe or <root>/mingw64/bin/git.exe.
    git = shutil.which("git")
    for root in Path(git).resolve().parents if git else []:
        if (root / "bin" / "bash.exe").is_file():
            return str(root / "bin" / "bash.exe")
    pytest.skip("Git for Windows bash.exe not found")


def test_the_worker_hook_command_runs_in_the_hook_shell() -> None:
    # given the command Claude Code is told to run for the worker hook
    command = launcher.hook_command()

    # when the hook shell runs it with an empty payload
    result = subprocess.run(
        [_hook_shell(), "-c", command],
        input="{}",
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        encoding="utf-8",
        errors="replace",
    )

    # then the hook itself started (it ignores the payload and exits 0)
    assert result.returncode == 0, result.stderr
