#!/usr/bin/env python3
"""Agent-hook wiring and runtime evidence, for doctor only; always exits 0.

gather() reads registrations and runs bounded inspections. report() decides
the doctor lines from plain values, without accessing homes or programs.
"""

import json
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path

import agent_hook_wiring
import claude_homes
import doctor_lines
import sync_agents
from agent_hook_codex_plan import codex_guards
from agent_hook_release import (
    OUTPUT_LIMIT,
    PROGRAM_TIMEOUT,
    RELEASE_FILE,
    Outcome,
    build_hookrelease,
    check_release,
    go_environment,
    run,
)
from codex_shells import (  # noqa: F401 (re-exported for doctor's callers and tests)
    POSIX_SHELLS,
    SHELL_FALLBACKS,
    SHELL_TIMEOUT,
    Shell,
    ShellChoice,
    derive_login_shell,
    derive_session_shell,
    gather_shells,
    probe_argv,
    shell_kind,
)
from doctor_lines import Line


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
    key: str = ""  # sync's target key: claude, work-a, ..., codex


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
class Facts:
    homes: tuple[Home, ...] = ()
    releases: tuple[Release, ...] = ()
    logs: tuple[Log, ...] = ()
    tools: frozenset[str] = frozenset({"uv", "gofmt"})
    shells: tuple[Shell, ...] = ()
    system: str = "linux"
    # The homes `just agent-hooks-uninstall` marked, by key, and the
    # registration changes sync left unfinished, by journal name.
    marks: frozenset[str] = frozenset()
    journals: tuple[str, ...] = ()


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


def _in_any_order(hooks: Mapping[str, list[dict]]) -> dict[str, list[dict]]:
    return {
        event: sorted(groups, key=lambda group: json.dumps(group, sort_keys=True))
        for event, groups in hooks.items()
    }


def _compared(home: Home, fragment: dict) -> tuple[object, object]:
    """What doctor compares with the render: the home's managed blocks, or,
    for Codex, only agent-hook's groups against G (codex_guards), in any
    order: its scripts stay beside them, rtk and the formatter wait for PR 5,
    and sync leaves an unchanged group where it is."""
    rendered = fragment.get("hooks", {})
    if home.harness != "codex":
        return home.managed, rendered
    binary = {
        event: groups
        for event, blocks in home.managed.items()
        if (
            groups := [
                block
                for block in blocks
                if sync_agents._is_agent_hook_group(block, codex=True)
            ]
        )
    }
    if not isinstance(rendered, dict):
        return binary, rendered
    return _in_any_order(binary), _in_any_order(codex_guards(rendered))


def _home_lines(home: Home) -> list[Line]:
    lines: list[Line] = []
    if home.problem:
        return [
            ("WARN", "agent-hook-inspect", f"{home.name}: registration: {home.problem}")
        ]
    # Codex keeps its scripts beside agent-hook's guards until PR 5 (PR 3d.2)
    mixed = home.scripts and home.binaries and home.harness != "codex"
    if mixed or len(home.binaries) > 1:
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
        difference = first_difference(*_compared(home, rendered.fragment))
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
    if not (
        facts.homes or facts.releases or facts.logs or facts.shells or facts.journals
    ):
        # No fact at all, which gather() finds only with no agent home.
        # doctor.sh reads exit 0 with no line as a run that failed.
        return [
            (
                "INFO",
                "agent-hook-wiring",
                "no Claude or Codex home found; nothing to check",
            )
        ]
    lines: list[Line] = [
        (
            "WARN",
            "agent-hook-wiring",
            (
                f"a registration change is unfinished ({journal}); "
                "run just sync-agents to finish or restore it"
            ),
        )
        for journal in facts.journals
    ]
    for home in facts.homes:
        if home.key not in facts.marks:
            continue
        if home.binaries:
            lines.append(
                (
                    "WARN",
                    "agent-hook-wiring",
                    (
                        f"{home.key}: uninstalled, yet wired; run just agent-hooks-uninstall "
                        f"{home.key} or just agent-hooks-install {home.key}"
                    ),
                )
            )
        else:
            lines.append(
                (
                    "INFO",
                    "agent-hook-wiring",
                    (
                        f"agent-hook uninstalled in {home.key}: today's scripts run; "
                        f"just agent-hooks-install {home.key} wires it again"
                    ),
                )
            )
    scripts = [
        home.name
        for home in facts.homes
        if home.scripts and not home.binaries and home.key not in facts.marks
    ]
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
    outcome = run(args, timeout=PROGRAM_TIMEOUT)
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
        elif not RELEASE_FILE.fullmatch(resolved.as_posix()):
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
        return Home(name, harness, key=agent.key)
    except (OSError, ValueError, TypeError) as exc:
        return Home(
            name, harness, problem=f"cannot read {registration}: {exc}", key=agent.key
        )
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
        key=agent.key,
    )


def _release_checks(
    paths: tuple[str, ...], env: Mapping[str, str]
) -> tuple[Release, ...]:
    if not paths:
        return ()
    selected, outcome = go_environment(env)
    if not outcome.ok:
        return tuple(Release(path, outcome) for path in paths)
    try:
        with tempfile.TemporaryDirectory(prefix="agent-hook-doctor-") as temporary:
            checker, built = build_hookrelease(Path(temporary), selected)
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
                Release(path, check_release(checker, path, selected), checked=True)
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
    outcome = run([path, "log", "--summary", "--days", "1"], timeout=PROGRAM_TIMEOUT)
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
    marks, journals = _marks_and_journals(env, homes)
    return Facts(
        tuple(homes),
        checked,
        tuple(logs),
        frozenset(tool for tool in ("uv", "gofmt") if shutil.which(tool)),
        gather_shells(system, env) if codex_home.is_dir() else (),
        system,
        marks,
        journals,
    )


def _marks_and_journals(
    env: Mapping[str, str], homes: list[Home]
) -> tuple[frozenset[str], tuple[str, ...]]:
    """The uninstall marks of these homes, and the pending journals, where
    sync keeps them (agent_hook_wiring.Roots); none without a usable root."""
    try:
        roots = agent_hook_wiring.Roots.from_env(env)
    except ValueError:
        return frozenset(), ()
    marks = frozenset(
        home.key for home in homes if home.key and roots.mark(home.key).is_file()
    )
    journals = tuple(sorted(path.name for path in roots.state.glob("switch-*.json")))
    return marks, journals


def main() -> int:
    for level, name, detail in report(gather(Path.home())):
        print(doctor_lines.fmt((level, name, " ".join(detail.splitlines()))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
