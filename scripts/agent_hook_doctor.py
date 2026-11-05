#!/usr/bin/env python3
"""Agent-hook wiring and runtime evidence, for doctor only; always exits 0.

gather() reads registrations and runs bounded inspections. report() decides
the doctor lines from plain values, without accessing homes or programs.
"""

import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from threading import Thread
from typing import BinaryIO

import claude_homes
import doctor_lines
import sync_agents
from doctor_lines import Line

try:
    import pwd
except ImportError:  # Windows has no passwd database or shell probes.
    pwd = None

ROOT = Path(__file__).resolve().parents[1]
PROGRAM_TIMEOUT = 30
SHELL_TIMEOUT = 10
CHECK_TIMEOUT = 300
OUTPUT_LIMIT = 65536
PIPE_GRACE = 1


@dataclass(frozen=True)
class Outcome:
    exit_code: int | None = 0
    stdout: str = ""
    stderr: str = ""
    reason: str | None = None
    timed_out: bool = False
    stdout_bytes: int = 0

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.reason is None and not self.timed_out


@dataclass(frozen=True)
class Render:
    outcome: Outcome
    fragment: dict = field(default_factory=dict)
    losses: tuple[dict, ...] = ()


@dataclass(frozen=True)
class Binary:
    path: str
    release: str | None
    render: Render | None = None
    problem: str | None = None


@dataclass(frozen=True)
class Home:
    name: str
    harness: str
    scripts: bool = False
    managed: Mapping[str, list[dict]] = field(default_factory=dict)
    binaries: tuple[Binary, ...] = ()
    guard: bool = False
    problem: str | None = None


@dataclass(frozen=True)
class Release:
    path: str
    outcome: Outcome
    checked: bool = False


@dataclass(frozen=True)
class LogSummary:
    days: int
    lines: int
    unreadable: int
    errors: Mapping[str, int]
    mismatches: Mapping[str, int]


@dataclass(frozen=True)
class Log:
    binary: str
    outcome: Outcome
    summary: LogSummary | None = None


@dataclass(frozen=True)
class ShellChoice:
    route: str
    executable: str | None
    kind: str
    reason: str


@dataclass(frozen=True)
class Shell:
    choice: ShellChoice
    argv: tuple[str, ...]
    outcome: Outcome
    token: str

    @property
    def clean(self) -> bool:
        return self.outcome.ok and self.outcome.stdout == self.token


@dataclass(frozen=True)
class Facts:
    homes: tuple[Home, ...] = ()
    releases: tuple[Release, ...] = ()
    logs: tuple[Log, ...] = ()
    tools: frozenset[str] = frozenset({"uv", "gofmt"})
    shells: tuple[Shell, ...] = ()
    system: str = "linux"


SHELL_FALLBACKS = {
    "zsh": ("/bin/zsh",),
    "bash": ("/bin/bash", "/usr/bin/bash"),
    "sh": ("/bin/sh",),
    "pwsh": ("/usr/local/bin/pwsh",),
    "powershell": (),
    "cmd": (),
}
POSIX_SHELLS = {"zsh", "bash", "sh", "dash", "ksh"}


def shell_kind(path: str) -> str:
    name = Path(path).name
    while name not in SHELL_FALLBACKS and Path(name).stem != name:
        name = Path(name).stem
    if name in {"pwsh", "powershell"}:
        return "powershell"
    return name if name in POSIX_SHELLS or name in {"cmd", "fish"} else "other"


def derive_session_shell(
    login_shell: str | None,
    system: str,
    executables: Mapping[str, str],
    files: frozenset[str],
) -> ShellChoice:
    """Codex 0.166 shell_detect.rs, POSIX: passwd, PATH, fixed fallbacks.

    All discovery is passed in. dash/ksh/fish are not recognised session
    types, although dash and ksh can read the launcher's sh syntax.
    """
    login_kind = shell_kind(login_shell or "")
    recognised = {"zsh", "bash", "sh", "powershell", "cmd"}

    def find(kind: str) -> str | None:
        if login_kind == kind and login_shell in files:
            return login_shell
        names = ("pwsh", "powershell") if kind == "powershell" else (kind,)
        for name in names:
            if name in executables:
                return executables[name]
            for path in SHELL_FALLBACKS[name]:
                if path in files:
                    return path
        return None

    if login_kind in recognised and (executable := find(login_kind)):
        return ShellChoice(
            "session",
            executable,
            login_kind,
            f"login shell {Path(login_shell or '').name}",
        )
    fallback = ("zsh", "bash") if system == "darwin" else ("bash", "zsh")
    if not login_shell:
        reason = "login shell unavailable"
    elif login_kind in recognised:
        reason = f"login shell {Path(login_shell).name} not found"
    else:
        reason = f"login shell {Path(login_shell).name} is not one Codex runs"
    for kind in fallback:
        if executable := find(kind):
            return ShellChoice(
                "session", executable, kind, f"{reason}; it falls back to {kind}"
            )
    if "/bin/sh" in files:
        return ShellChoice(
            "session", "/bin/sh", "sh", f"{reason}; it falls back to fixed /bin/sh"
        )
    return ShellChoice(
        "session", None, "none", f"{reason}; no shell found (fixed /bin/sh missing)"
    )


def derive_login_shell(
    shell: str | None, executables: Mapping[str, str], files: frozenset[str]
) -> ShellChoice:
    if shell == "":
        return ShellChoice("$SHELL -lc", None, "none", "SHELL is empty")
    path = "/bin/sh" if shell is None else shell
    executable = path if path in files else executables.get(path)
    return ShellChoice(
        "$SHELL -lc",
        executable,
        shell_kind(path) if executable else "none",
        f"SHELL={path}" if shell is not None else "SHELL unset; /bin/sh -lc",
    )


def probe_argv(choice: ShellChoice, token: str) -> tuple[str, ...]:
    if choice.executable is None:
        return ()
    if choice.kind == "powershell":
        command = f"$l = [Console]::In.ReadLine(); if ($l -ceq '{token}') {{ [Console]::Out.Write('{token}') }} else {{ [Console]::Out.Write('{token}:stdin') }}"
    elif choice.kind in POSIX_SHELLS:
        command = f'IFS= read -r line; if [ "$line" = {token} ]; then printf %s {token}; else printf %s {token}:stdin; fi'
    elif choice.kind == "fish":
        # fish cannot parse sh's `if`, yet runs today's script hooks.
        command = f'read -l line; if test "$line" = {token}; printf %s {token}; else; printf %s {token}:stdin; end'
    else:
        # A shell whose syntax doctor does not know: the token alone, with
        # stdin unchecked (3d never wires Codex under it).
        command = f"printf %s {token}"
    if choice.route != "session":
        flags = ("-lc",)
    elif choice.kind == "powershell":
        flags = ("-NoProfile", "-Command")
    elif choice.kind == "cmd":
        flags = ("/c",)
    else:
        flags = ("-c",)
    return choice.executable, *flags, command


def _shell_lines(shell: Shell, *, wired: bool, guard: bool) -> list[Line]:
    choice = shell.choice
    prefix = f"{choice.route}: {choice.executable} ({choice.kind})"
    if choice.executable is None:
        return [
            (
                "WARN",
                "agent-hook-codex-shell",
                f"{choice.route}: no shell found; {choice.reason}",
            )
        ]
    lines: list[Line] = [
        ("INFO", "agent-hook-codex-shell", f"{prefix}: {choice.reason}")
    ]
    if choice.kind not in POSIX_SHELLS:
        lines.append(
            (
                "WARN" if wired else "INFO",
                "agent-hook-codex-shell",
                f"{prefix} cannot read the agent-hook sh launcher; 3d will not wire Codex under it",
            )
        )
    outcome = shell.outcome
    if outcome.exit_code is None and not outcome.timed_out:
        lines.append(
            _inspection("Codex", f"{choice.route} {choice.executable}", outcome)
        )
    if shell.clean:
        return lines
    if outcome.timed_out:
        detail = "timed out"
    elif outcome.exit_code != 0:
        detail = outcome.reason or f"exits {outcome.exit_code}"
    elif not outcome.stdout:
        detail = "exits 0 before the command runs"
    elif outcome.stdout.endswith(shell.token + ":stdin"):
        detail = "a startup file reads stdin, so each hook loses its input"
    elif outcome.stdout.endswith(shell.token):
        count = outcome.stdout_bytes - len(shell.token.encode("utf-8"))
        detail = f"{count} bytes come before every hook's answer"
    else:
        detail = f"stdout is not the probe token ({outcome.stdout_bytes} bytes); command execution unverified"
    lines.append(
        (
            "WARN" if guard else "INFO",
            "agent-hook-codex-shell",
            f"{prefix}: {detail}; guards can fail open",
        )
    )
    return lines


def first_difference(actual: object, expected: object, path: str = "") -> str | None:
    """The first differing event/block/field, with JSON object order ignored."""
    if isinstance(actual, Mapping) and isinstance(expected, Mapping):
        for key in dict.fromkeys([*expected, *actual]):
            location = f"{path}.{key}" if path else str(key)
            if key not in actual or key not in expected:
                return location
            difference = first_difference(actual[key], expected[key], location)
            if difference:
                return difference
        return None
    if isinstance(actual, list) and isinstance(expected, list):
        for index in range(max(len(actual), len(expected))):
            location = f"{path}[{index}]"
            if index >= len(actual) or index >= len(expected):
                return location
            difference = first_difference(actual[index], expected[index], location)
            if difference:
                return difference
        return None
    return path if type(actual) is not type(expected) or actual != expected else None


def _inspection(subject: str, call: str, outcome: Outcome) -> Line:
    reason = outcome.reason or (
        "timed out" if outcome.timed_out else f"exits {outcome.exit_code}"
    )
    return "WARN", "agent-hook-inspect", f"{subject}: {call}: {reason}"


def _home_lines(home: Home) -> list[Line]:
    lines: list[Line] = []
    if home.problem:
        return [
            ("WARN", "agent-hook-inspect", f"{home.name}: registration: {home.problem}")
        ]
    if (home.scripts and home.binaries) or len(home.binaries) > 1:
        lines.append(
            (
                "WARN",
                "agent-hook-wiring",
                f"{home.name}: mixed scripts/binary or multiple binary paths; just sync-agents resolves it",
            )
        )
    elif not home.scripts and not home.binaries:
        lines.append(
            (
                "INFO",
                "agent-hook-wiring",
                f"no dotfiles hook registered in {home.name} (not new with agent-hook)",
            )
        )
    for binary in home.binaries:
        if binary.problem or binary.release is None:
            lines.append(
                (
                    "WARN",
                    "agent-hook-binary",
                    f"{home.name}: {binary.path}: {binary.problem or 'no release'}",
                )
            )
        rendered = binary.render
        if rendered is None:
            continue
        if not rendered.outcome.ok:
            lines.append(
                _inspection(home.name, f"{binary.path} render", rendered.outcome)
            )
            continue
        difference = first_difference(home.managed, rendered.fragment.get("hooks", {}))
        if difference:
            lines.append(
                (
                    "WARN",
                    "agent-hook-registered",
                    f"{home.name}: managed blocks differ from render at {difference}; run just sync-agents",
                )
            )
        for loss in rendered.losses:
            lines.append(
                (
                    "INFO",
                    "agent-hook-loss",
                    f"{home.name}: {loss.get('level', '')} {loss.get('tool', '')}: {loss.get('reason', '')}",
                )
            )
    return lines


def _log_lines(log: Log, homes: tuple[str, ...]) -> list[Line]:
    if not log.outcome.ok or log.summary is None:
        subject = f"{' / '.join(homes)}: {log.binary}" if homes else log.binary
        return [_inspection(subject, "log --summary --days 1", log.outcome)]
    summary = log.summary
    actionable = {"shim.broken", "hook.failed", "hook.timeout", "answer.failed"}
    warning = any(count > 0 for count in summary.mismatches.values()) or any(
        summary.errors.get(code, 0) > 0 for code in actionable
    )
    lines: list[Line] = [
        (
            "WARN" if warning else "INFO",
            "agent-hook-log",
            f"last {summary.days} UTC day: {summary.lines} lines; errors={json.dumps(dict(summary.errors), sort_keys=True)}; mismatches={json.dumps(dict(summary.mismatches), sort_keys=True)}; agent-hook log shows the lines",
        )
    ]
    if summary.unreadable:
        lines.append(
            (
                "INFO",
                "agent-hook-log",
                f"{summary.unreadable} unreadable log lines skipped",
            )
        )
    return lines


def report(facts: Facts) -> list[Line]:
    if not (facts.homes or facts.releases or facts.logs or facts.shells):
        # No fact at all, which gather() finds only with no agent home.
        # doctor.sh reads exit 0 with no line as a run that failed.
        return [
            (
                "INFO",
                "agent-hook-wiring",
                "no Claude or Codex home found; nothing to check",
            )
        ]
    lines: list[Line] = []
    scripts = [home.name for home in facts.homes if home.scripts and not home.binaries]
    if scripts:
        names = (
            " and ".join(scripts)
            if len(scripts) < 3
            else ", ".join(scripts[:-1]) + ", and " + scripts[-1]
        )
        lines.append(
            ("INFO", "agent-hook-wiring", f"not wired: today's scripts run in {names}")
        )
    for home in facts.homes:
        lines.extend(_home_lines(home))
    for release in facts.releases:
        outcome = release.outcome
        checked = release.checked and not outcome.timed_out
        if checked and outcome.ok:
            lines.append(
                (
                    "OK",
                    "agent-hook-fresh",
                    f"release {release.path} is what this checkout builds",
                )
            )
        elif checked and outcome.exit_code == 1:
            lines.append(
                (
                    "WARN",
                    "agent-hook-fresh",
                    f"release {release.path} is not what this checkout builds ({outcome.stderr.strip()}); run just sync-agents",
                )
            )
        elif checked and outcome.exit_code == 3:
            lines.append(
                (
                    "WARN",
                    "agent-hook-fresh",
                    f"release {release.path} differs from the build its release ID names ({outcome.stderr.strip()}); sync never replaces a release in place: remove {Path(release.path).parent} and run just sync-agents",
                )
            )
        else:
            reason = (
                release.outcome.reason
                or release.outcome.stderr.strip()
                or f"exits {release.outcome.exit_code}"
            )
            lines.append(
                (
                    "INFO",
                    "agent-hook-fresh",
                    f"release {release.path}: cannot check here: {reason}",
                )
            )
    if any(home.binaries for home in facts.homes):
        for tool, suffix in (("uv", ".py"), ("gofmt", ".go")):
            if tool not in facts.tools:
                lines.append(
                    (
                        "INFO",
                        "agent-hook-tools",
                        f"{tool} missing on PATH: the formatter leaves {suffix} files as they are",
                    )
                )
        for log in facts.logs:
            homes = tuple(
                home.name
                for home in facts.homes
                if any(binary.path == log.binary for binary in home.binaries)
            )
            lines.extend(_log_lines(log, homes))
    if facts.system != "windows":
        codex = [home for home in facts.homes if home.harness == "codex"]
        for shell in facts.shells:
            lines.extend(
                _shell_lines(
                    shell,
                    wired=any(home.binaries for home in codex),
                    guard=any(home.guard for home in codex),
                )
            )
    return lines


# ---- Imperative shell ----


def _run(
    args: tuple[str, ...] | list[str],
    *,
    timeout: float,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    input: bytes | None = None,
) -> Outcome:
    """Run a call with a deadline, and keep what doctor reads of it.

    It keeps the exit code, the first OUTPUT_LIMIT bytes of stdout and of
    stderr, and stdout's whole size. On POSIX the call leads a session of its
    own. Past the deadline (the call, or a pipe it left open, still running)
    its whole process group is killed. On Windows only the call is killed
    (job objects are the Windows host's item B3). A process outside the group
    that still holds a pipe is not waited for past PIPE_GRACE.
    """
    try:
        child = subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL if input is None else subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name != "nt",
        )
    except FileNotFoundError:
        return Outcome(None, reason=f"missing: {args[0]}")
    except (OSError, ValueError) as exc:
        return Outcome(None, reason=f"cannot start: {exc}")
    stdout = bytearray()
    stderr_output = bytearray()
    stdout_bytes = 0

    def drain(stream: BinaryIO, kept: bytearray, count_stdout: bool) -> None:
        nonlocal stdout_bytes
        with stream:
            # One read of the pipe at a time: a buffered read waits for 8 KiB
            # or EOF, and a pipe held from outside the group gives neither.
            while chunk := os.read(stream.fileno(), 8192):
                if count_stdout:
                    stdout_bytes += len(chunk)
                kept.extend(chunk[: max(0, OUTPUT_LIMIT - len(kept))])

    def feed(stream: BinaryIO, payload: bytes) -> None:
        try:
            with stream:
                stream.write(payload)
        except OSError:
            pass  # The call can exit, or close stdin, before it reads.

    assert child.stdout is not None and child.stderr is not None
    # Daemon threads: a pipe held from outside the group must not keep
    # doctor from exiting.
    pipes = [
        Thread(target=drain, args=(child.stdout, stdout, True), daemon=True),
        Thread(target=drain, args=(child.stderr, stderr_output, False), daemon=True),
    ]
    if input is not None:
        assert child.stdin is not None
        pipes.append(Thread(target=feed, args=(child.stdin, input), daemon=True))
    deadline = time.monotonic() + timeout
    for pipe in pipes:
        pipe.start()
    # The pipes first, then the call: the call is reaped only once it is
    # done, so a group kill never comes after the reap. The group's ID is the
    # call's pid, and a reap frees that pid for another process to take.
    for pipe in pipes:
        pipe.join(timeout=max(0, deadline - time.monotonic()))
    timed_out = any(pipe.is_alive() for pipe in pipes)
    if not timed_out:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
    if timed_out:
        if os.name == "nt":
            child.kill()
        else:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # Every process of the group had already exited.
    child.wait()
    grace = time.monotonic() + PIPE_GRACE  # one grace for all the pipes
    for pipe in pipes:
        pipe.join(timeout=max(0, grace - time.monotonic()))
    stderr = bytes(stderr_output).decode("utf-8", errors="replace")
    reason = (
        f"timed out after {timeout:g} s"
        if timed_out
        else None
        if child.returncode == 0
        else f"exits {child.returncode}"
        + (f": {stderr.strip()}" if stderr.strip() else "")
    )
    return Outcome(
        None if timed_out else child.returncode,
        bytes(stdout).decode("utf-8", errors="replace"),
        stderr,
        reason,
        timed_out=timed_out,
        stdout_bytes=stdout_bytes,
    )


def _blocks(doc: object) -> dict[str, list[dict]]:
    if not isinstance(doc, dict) or not isinstance(doc.get("hooks"), dict):
        raise TypeError("expected an object with hooks")
    hooks = doc["hooks"]
    for blocks in hooks.values():
        if not isinstance(blocks, list):
            raise TypeError("expected event blocks")
        for block in blocks:
            if not isinstance(block, dict) or not isinstance(block.get("hooks"), list):
                raise TypeError("expected block hooks")
            if any(
                not isinstance(hook, dict)
                or not isinstance(hook.get("command", ""), str)
                for hook in block["hooks"]
            ):
                raise ValueError("expected hook objects with command strings")
    return hooks


def _render(path: str, harness: str, system: str) -> Render:
    args = [path, "render", "--harness", harness, "--os", system]
    if harness == "codex":
        args.extend(["--shell", "sh"])
    args.extend(["--binary", path])
    outcome = _run(args, timeout=PROGRAM_TIMEOUT)
    if not outcome.ok:
        return Render(outcome)
    if outcome.stdout_bytes > OUTPUT_LIMIT:
        return Render(replace(outcome, reason=f"output exceeds {OUTPUT_LIMIT} bytes"))
    try:
        fragment = json.loads(outcome.stdout)
        _blocks(fragment)
        losses = tuple(json.loads(line) for line in outcome.stderr.splitlines())
        if any(
            not isinstance(loss, dict)
            or any(
                not isinstance(loss.get(key), str)
                for key in ("level", "tool", "reason")
            )
            for loss in losses
        ):
            raise ValueError("expected loss objects")
    except (ValueError, TypeError) as exc:
        return Render(replace(outcome, reason=f"output does not parse: {exc}"))
    return Render(outcome, fragment, losses)


def _binary(path: str, harness: str, system: str) -> Binary:
    release = None
    problem = None
    try:
        resolved = Path(path).resolve(strict=True)
        if not resolved.is_file():
            return Binary(path, None, problem="no release: not a file")
        elif (
            not sync_agents.POSIX_RELEASE.fullmatch(resolved.as_posix())
            or resolved.parent.parent.name != "releases"
        ):
            problem = "no release: path does not resolve to releases/<id>/agent-hook"
        else:
            release = str(resolved)
    except FileNotFoundError:
        return Binary(path, None, problem="missing")
    except (OSError, RuntimeError) as exc:
        return Binary(path, None, problem=f"no release: {exc}")
    return Binary(path, release, _render(path, harness, system), problem)


def _registered_path(hook: dict, *, codex: bool) -> str | None:
    if not sync_agents._runs_agent_hook_release(hook, codex=codex):
        return None
    if not codex:
        return hook["command"]
    for launcher in sync_agents.AGENT_HOOK_LAUNCHERS:
        if match := launcher.start.match(hook["command"]):
            path = match[1]
            return (
                path.replace(launcher.escaped_quote, "'")
                if launcher.escaped_quote
                else path
            )
    return None


def _has_guard(hook: dict) -> bool:
    command = hook.get("command", "")
    args = hook.get("args", [])
    if not isinstance(args, list):
        args = []
    invocation = command + " " + " ".join(str(arg) for arg in args)
    return bool(
        re.search(
            r"(?:^|\s)--hook\s+(?:command|files|secrets)-guard(?:\s|$)", invocation
        )
    ) or any(
        name in command
        for name in (
            "block-prohibited-files",
            "block-prohibited-commands",
            "block-secrets",
        )
    )


def _home(path: Path, agent: sync_agents.AgentTarget, system: str) -> Home:
    codex = agent.receives_codex_hooks
    name, harness = ("Codex", "codex") if codex else (path.name, "claude")
    registration = path / ("hooks.json" if codex else "settings.json")
    try:
        doc = json.loads(registration.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise TypeError("expected a registration object")
        hooks = _blocks(doc) if "hooks" in doc else {}
    except FileNotFoundError:
        return Home(name, harness)
    except (OSError, ValueError, TypeError) as exc:
        return Home(name, harness, problem=f"cannot read {registration}: {exc}")
    target = replace(agent, directory=path)
    managed = {
        event: owned
        for event, blocks in hooks.items()
        if (
            owned := [
                block
                for block in blocks
                if sync_agents._is_managed_hook_block(block, target)
            ]
        )
    }
    paths: dict[str, None] = {}
    scripts = guard = False
    for event, blocks in managed.items():
        for block in blocks:
            for hook in block["hooks"]:
                binary = _registered_path(hook, codex=codex)
                if binary:
                    paths[binary] = None
                else:
                    scripts = True
                guard = guard or (event == "PreToolUse" and _has_guard(hook))
    return Home(
        name,
        harness,
        scripts,
        managed,
        tuple(_binary(binary, harness, system) for binary in paths),
        guard,
    )


def _go_environment(env: Mapping[str, str]) -> tuple[dict[str, str], Outcome]:
    module = ROOT / "tools/agent-hooks"
    selected = dict(env)
    mise = shutil.which("mise", path=env.get("PATH", ""))
    if mise:
        outcome = _run(
            [mise, "which", "go"], cwd=module, env=env, timeout=PROGRAM_TIMEOUT
        )
        if not outcome.ok:
            return selected, replace(outcome, reason=f"mise which go: {outcome.reason}")
        go = outcome.stdout.strip()
        if not go or not Path(go).is_file() or not os.access(go, os.X_OK):
            return selected, Outcome(None, reason="mise which go: missing executable")
        selected["PATH"] = str(Path(go).parent) + os.pathsep + env.get("PATH", "")
    elif not shutil.which("go", path=env.get("PATH", "")):
        return selected, Outcome(None, reason="missing Go on PATH")
    return selected, Outcome()


def _release_checks(
    paths: tuple[str, ...], env: Mapping[str, str]
) -> tuple[Release, ...]:
    if not paths:
        return ()
    selected, outcome = _go_environment(env)
    if not outcome.ok:
        return tuple(Release(path, outcome) for path in paths)
    module = ROOT / "tools/agent-hooks"
    try:
        with tempfile.TemporaryDirectory(prefix="agent-hook-doctor-") as temporary:
            checker = str(Path(temporary) / "hookrelease")
            built = _run(
                ["go", "build", "-o", checker, "./cmd/hookrelease"],
                cwd=module,
                env=selected,
                timeout=CHECK_TIMEOUT,
            )
            if not built.ok:
                return tuple(
                    Release(
                        path,
                        replace(
                            built,
                            reason=f"build hookrelease: {built.reason}",
                        ),
                    )
                    for path in paths
                )
            return tuple(
                Release(
                    path,
                    _run(
                        [checker, "check", path],
                        cwd=module,
                        env=selected,
                        timeout=CHECK_TIMEOUT,
                    ),
                    checked=True,
                )
                for path in paths
            )
    except OSError as exc:
        return tuple(
            Release(path, Outcome(None, reason=f"cannot build hookrelease: {exc}"))
            for path in paths
        )


ERROR_CODES = {
    "input.unreadable",
    "shim.broken",
    "hook.failed",
    "hook.timeout",
    "rewrite.dropped",
    "tool.failed",
    "answer.failed",
    "usage",
    "other",
}
MISMATCHES = {"envelope", "input", "mapping", "unchecked", "other"}


def _counts(value: object, allowed: set[str]) -> bool:
    return isinstance(value, dict) and all(
        key in allowed and type(count) is int and count >= 0
        for key, count in value.items()
    )


def _log(path: str) -> Log:
    outcome = _run([path, "log", "--summary", "--days", "1"], timeout=PROGRAM_TIMEOUT)
    if not outcome.ok:
        return Log(path, outcome)
    if outcome.stdout_bytes > OUTPUT_LIMIT:
        return Log(
            path, replace(outcome, reason=f"output exceeds {OUTPUT_LIMIT} bytes")
        )
    try:
        doc = json.loads(outcome.stdout)
        if not isinstance(doc, dict) or set(doc) != {
            "days",
            "lines",
            "unreadable",
            "errors",
            "mismatches",
        }:
            raise ValueError("expected a summary object")
        if (
            any(
                type(doc[key]) is not int or doc[key] < 0
                for key in ("days", "lines", "unreadable")
            )
            or doc["days"] != 1
        ):
            raise ValueError("expected one day and nonnegative counts")
        if not _counts(doc["errors"], ERROR_CODES) or not _counts(
            doc["mismatches"], MISMATCHES
        ):
            raise ValueError("unknown codes or invalid counts")
    except (ValueError, TypeError) as exc:
        return Log(path, replace(outcome, reason=f"output does not parse: {exc}"))
    return Log(path, outcome, LogSummary(**doc))


def _login_shell() -> str | None:
    if pwd is None:
        return None
    try:
        return pwd.getpwuid(os.getuid()).pw_shell
    except (KeyError, OSError):
        return None


def gather_shells(system: str, env: Mapping[str, str]) -> tuple[Shell, ...]:
    if system == "windows":
        return ()
    login = _login_shell()
    names = {*SHELL_FALLBACKS, env.get("SHELL", "")}
    executables = {
        name: found
        for name in names
        if name and (found := shutil.which(name, path=env.get("PATH", "")))
    }
    candidates = {path for paths in SHELL_FALLBACKS.values() for path in paths}
    candidates.update(path for path in (login, env.get("SHELL")) if path)
    files = frozenset(path for path in candidates if Path(path).is_file())
    choices = (
        derive_session_shell(login, system, executables, files),
        derive_login_shell(env.get("SHELL"), executables, files),
    )
    probes = []
    for choice in choices:
        token = "agent-hook-probe-" + secrets.token_hex(8)
        argv = probe_argv(choice, token)
        outcome = (
            _run(
                argv,
                env=env,
                timeout=SHELL_TIMEOUT,
                input=(token + "\n").encode("utf-8"),
            )
            if argv
            else Outcome(None, reason="missing shell")
        )
        probes.append(Shell(choice, argv, outcome, token))
    return tuple(probes)


def gather(home: Path) -> Facts:
    system = "windows" if os.name == "nt" else sys.platform
    env = dict(os.environ)
    claude = {
        agent.directory.name: agent
        for agent in sync_agents.AGENTS
        if agent.receives_hooks
    }
    homes = [
        _home(path, claude[path.name], system) for path in claude_homes.existing(home)
    ]
    codex = next(agent for agent in sync_agents.AGENTS if agent.receives_codex_hooks)
    codex_home = Path(env.get("CODEX_HOME") or home / ".codex")
    if codex_home.is_dir():
        homes.append(_home(codex_home, codex, system))
    binaries = tuple(
        dict.fromkeys(
            binary.path
            for found in homes
            for binary in found.binaries
            if binary.render is not None
        )
    )
    releases = tuple(
        dict.fromkeys(
            binary.release
            for found in homes
            for binary in found.binaries
            if binary.release
        )
    )
    checked = _release_checks(releases, env)
    logs = []
    for path in binaries:
        log = _log(path)
        logs.append(log)
        if log.outcome.ok:
            break
    return Facts(
        tuple(homes),
        checked,
        tuple(logs),
        frozenset(tool for tool in ("uv", "gofmt") if shutil.which(tool)),
        gather_shells(system, env) if codex_home.is_dir() else (),
        system,
    )


def main() -> int:
    for level, name, detail in report(gather(Path.home())):
        print(doctor_lines.fmt((level, name, " ".join(detail.splitlines()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
