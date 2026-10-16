#!/usr/bin/env python3
"""Install the Claude Code plugins every Claude home shares.

j-cc hands Codex work to `codex:codex-rescue`, which exists only with the Codex
plugin; the rest of the set is what the operator's homes use (ADR 0056). The
plugins are declared in dump/harness/claude-plugins.json, each marketplace
pinned to a tag except claude-plugins-official (no tags) and this repo's own
marketplace (a `./` path), and installed through Claude Code's own plugin CLI
with CLAUDE_CONFIG_DIR set per home (ADR 0048; ADR 0037 keeps enabledPlugins
and extraKnownMarketplaces out of the settings fragments). Only homes that
exist are touched, and only the user scope counts.

The shared set must work without per-home settings (ADR 0057): a declared
plugin whose `configure --json` schema has an option without a default is
reported, on every run (`claude plugin update` never passes through here).
A schema read is cached in the home's state file under the install's version
and lastUpdated, which an update moves; a plugin read from a folder is read
every time, since its folder can change under the same key.
`disabled` plugins are switched off on every run; each `retired` migration
switches its plugins off once per home and is then recorded in the home's
claude-plugins.sync-state.json, so a plugin the user enables later stays on.

An LSP plugin only names the command its server runs; the command itself has
to be on this machine (mise provides it, config/mise/config.toml). The command
comes from each home's marketplace manifest -- the published plugin spec that
`claude plugin validate` checks, located through `marketplace list --json`,
not Claude Code's runtime state -- and is checked once per machine: on PATH,
and answering its version query (rustup's proxy is on PATH yet runs nothing until
the component is added).

Functional core / imperative shell: the steps come from the declaration and the
CLI's own --json inventory; reconcile() runs them through an injected CLI and
reads the inventory again before judging. A marketplace step runs first, since
replacing a marketplace uninstalls its plugins. An inventory that cannot be read
stops that home, and is never taken for "missing". visit_home() owns the
state file around it.

Usage: claude_plugins.py [--check]   (--check reports without changing)
Prints doctor-style OK/WARN lines; exit 1 on a WARN.
"""

import json
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path

import claude_homes
from doctor_lines import fmt

ROOT = Path(__file__).resolve().parents[1]
NAME = "claude-plugins"
DECLARATION = ROOT / "dump/harness/claude-plugins.json"
MARKETPLACE_LIST = ["plugin", "marketplace", "list", "--json"]
PLUGIN_LIST = ["plugin", "list", "--json"]
STATE_FILE = "claude-plugins.sync-state.json"  # in each home, owned by dotfiles
SCHEMA_READERS = 8  # parallel `configure --json` reads, about a second each
PROBE_TIMEOUT = 10.0  # seconds for an LSP command to answer `--version`
# Commands that answer something other than `--version` (gopls: "unknown flag")
VERSION_ARGS: Mapping[str, tuple[str, ...]] = {"gopls": ("version",)}

Step = tuple[list[str], str]  # (claude argv, what is wrong until it runs)
Cli = Callable[[list[str]], str | None]  # claude argv -> stdout, None on failure
# plugin id -> {"key": "<version>|<lastUpdated>", "needed": [option names]}
Schemas = Mapping[str, Mapping[str, object]]


@dataclass(frozen=True)
class Declaration:
    marketplaces: Mapping[str, str]  # name -> "owner/repo#ref"
    plugins: tuple[str, ...]  # "plugin@marketplace"
    disabled: tuple[str, ...] = ()  # switched off on every run
    # migration id -> plugin ids switched off once per home
    retired: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


# ---- Functional core ----


def parse_source(source: str) -> tuple[str, str | None]:
    repo, _, ref = source.partition("#")
    return repo, ref or None


def resolve_source(source: str, root: Path) -> str:
    """A `./` source is a marketplace file in this repo; the CLI wants it absolute."""
    return str(root / source) if source.startswith("./") else source


def _is_current(source: str, current: Mapping[str, object]) -> bool:
    if Path(source).is_absolute():  # a local marketplace, listed by its path
        return isinstance(path := current.get("path"), str) and Path(path) == Path(
            source
        )
    repo, ref = parse_source(source)
    return current.get("repo") == repo and current.get("ref") == ref


def _version(ref: str | None) -> str | None:
    """The plugin version a release tag stands for (v1.0.6 -> 1.0.6)."""
    match = re.fullmatch(r"v?(\d+\.\d+\.\d+)", ref or "")
    return match[1] if match else None


def marketplace_steps(
    declared: Mapping[str, str], listed: Sequence[Mapping[str, object]]
) -> list[Step]:
    steps: list[Step] = []
    for name, source in declared.items():
        add = ["plugin", "marketplace", "add", source, "--scope", "user"]
        current = next((m for m in listed if m.get("name") == name), None)
        if current is None:
            steps.append((add, f"marketplace {name} is missing"))
        elif not _is_current(source, current):
            why = f"marketplace {name} is not {source}"
            remove = ["plugin", "marketplace", "remove", name, "--scope", "user"]
            steps += [(remove, why), (add, why)]
    return steps


def _user_install(
    pid: str, listed: Sequence[Mapping[str, object]]
) -> Mapping[str, object] | None:
    return next(
        (p for p in listed if p.get("id") == pid and p.get("scope") == "user"), None
    )


def plugin_steps(
    declaration: Declaration, listed: Sequence[Mapping[str, object]]
) -> list[Step]:
    steps: list[Step] = []
    for pid in declaration.plugins:
        install = ["plugin", "install", pid, "--scope", "user"]
        user = _user_install(pid, listed)
        source = declaration.marketplaces.get(pid.partition("@")[2], "")
        want = _version(parse_source(source)[1])
        if user is None:
            steps.append((install, f"{pid} is not installed for the user"))
        elif want and user.get("version") != want:
            why = f"{pid} is {user.get('version')}, not {want}"
            steps += [
                (["plugin", "uninstall", pid, "--scope", "user"], why),
                (install, why),
            ]
        elif user.get("enabled") is not True:
            steps.append(
                (["plugin", "enable", pid, "--scope", "user"], f"{pid} is disabled")
            )
    return steps


def _enabled_for_user(pid: str, listed: Sequence[Mapping[str, object]]) -> bool:
    user = _user_install(pid, listed)
    return user is not None and user.get("enabled") is True


def disable_steps(
    declaration: Declaration,
    evaluated: frozenset[str],
    listed: Sequence[Mapping[str, object]],
) -> list[Step]:
    """Switch off the disabled plugins, and those of a migration not yet
    evaluated in this home."""
    reasons = [(pid, f"{pid} is declared disabled") for pid in declaration.disabled]
    reasons += [
        (pid, f"{pid} is retired by {mid}")
        for mid, ids in declaration.retired.items()
        if mid not in evaluated
        for pid in ids
    ]
    return [
        (["plugin", "disable", pid, "--scope", "user"], why)
        for pid, why in reasons
        if _enabled_for_user(pid, listed)
    ]


def converged_migrations(
    retired: Mapping[str, Sequence[str]],
    evaluated: frozenset[str],
    listed: Sequence[Mapping[str, object]],
) -> set[str]:
    """The migrations not yet evaluated whose plugins are all off for the user."""
    return {
        mid
        for mid, ids in retired.items()
        if mid not in evaluated
        and not any(_enabled_for_user(pid, listed) for pid in ids)
    }


def settings_needed(schema: Mapping[str, object]) -> list[str]:
    """The options without a default. Such a plugin may need per-home settings;
    whether an option is really required is not judged (ADR 0057)."""
    return [
        name
        for name, spec in schema.items()
        if not (isinstance(spec, Mapping) and "default" in spec)
    ]


def _needed_from(out: str | None) -> list[str] | None:
    """settings_needed() of a `configure --json` answer; None when unreadable."""
    try:
        schema = json.loads(out or "")["schema"]
    except (ValueError, KeyError, TypeError):
        return None
    return settings_needed(schema) if isinstance(schema, Mapping) else None


def _cached_needed(hit: object, key: str | None) -> list[str] | None:
    if key is None or not isinstance(hit, Mapping) or hit.get("key") != key:
        return None
    names = hit.get("needed")
    if isinstance(names, list) and all(isinstance(n, str) for n in names):
        return names
    return None


def settings_problems(
    declaration: Declaration,
    listed: Sequence[Mapping[str, object]],
    cached: Schemas,
    read: Callable[[str], str | None],
) -> tuple[list[str], dict[str, Mapping[str, object]]]:
    """(problems, the cache to keep) for the declared plugins installed for the
    user. A cached answer is reused while its key holds; a plugin that is not
    installed is skipped (the install step reports it)."""

    def one(pid: str) -> tuple[str, str | None, list[str] | None]:
        user = _user_install(pid, listed)
        if user is None:
            return pid, None, []
        key = (
            None
            if user.get("readFromFolder")
            else f"{user.get('version')}|{user.get('lastUpdated')}"
        )
        hit = _cached_needed(cached.get(pid), key)
        return pid, key, hit if hit is not None else _needed_from(read(pid))

    with ThreadPoolExecutor(max_workers=SCHEMA_READERS) as pool:
        answers = list(pool.map(one, declaration.plugins))
    problems = [
        f"cannot read `claude plugin configure {pid} --json`"
        if names is None
        else (
            f"{pid} has options without a default ({', '.join(names)}); it may"
            " need per-home settings, so it stays out of the shared set (ADR 0057)"
        )
        for pid, _key, names in answers
        if names != []
    ]
    fresh: dict[str, Mapping[str, object]] = {
        pid: {"key": key, "needed": names}
        for pid, key, names in answers
        if key is not None and names is not None
    }
    return problems, fresh


def lsp_commands(entry: Mapping[str, object]) -> list[str]:
    """The commands a marketplace entry's LSP servers run (`lspServers` given
    inline; a path to a separate file is not followed)."""
    servers = entry.get("lspServers")
    if not isinstance(servers, Mapping):
        return []
    return [
        server["command"]
        for server in servers.values()
        if isinstance(server, Mapping) and isinstance(server.get("command"), str)
    ]


Manifests = Mapping[str, Mapping[str, object] | None]  # marketplace -> manifest


def lsp_problems(
    declaration: Declaration,
    homes: Sequence[Manifests | None],
    probe: Callable[[str], str | None],
) -> list[str]:
    """What keeps a declared plugin's LSP server from starting on this machine.

    The commands are gathered from every home's manifests, since homes keep
    their own marketplace copies; each command is probed once. `probe` says
    why a command is unusable, or None when it answers."""
    problems: list[str] = []
    needs: dict[str, set[str]] = {}
    for manifests in homes:
        if manifests is None:  # never taken for "no LSP plugins here"
            unreadable = f"cannot read `claude {' '.join(MARKETPLACE_LIST)}`"
            if unreadable not in problems:
                problems.append(unreadable)
            continue
        for pid in declaration.plugins:
            name, _, market = pid.partition("@")
            if market not in manifests:
                continue
            manifest = manifests[market]
            if manifest is None:
                unreadable = f"cannot read the {market} marketplace manifest"
                if unreadable not in problems:
                    problems.append(unreadable)
                continue
            entries = manifest.get("plugins")
            for entry in entries if isinstance(entries, list) else []:
                if isinstance(entry, Mapping) and entry.get("name") == name:
                    for command in lsp_commands(entry):
                        needs.setdefault(command, set()).add(pid)
    for command in sorted(needs):
        if (why := probe(command)) is not None:
            problems.append(
                f"{', '.join(sorted(needs[command]))} needs `{command}` for its LSP"
                f" server, but it {why}; provide it with mise (config/mise/config.toml)"
            )
    return problems


def _listed(out: str | None) -> list[dict] | None:
    try:
        listed = json.loads(out or "")
    except ValueError:
        return None
    if not isinstance(listed, list) or not all(isinstance(i, dict) for i in listed):
        return None
    return listed


def reconcile(
    declaration: Declaration,
    cli: Cli,
    *,
    check: bool,
    evaluated: frozenset[str] = frozenset(),
) -> tuple[list[str], list[str]]:
    """(what was fixed, what is still wrong) for one Claude home."""
    done: list[str] = []
    found: list[str] = []
    phases: list[tuple[list[str], Callable[[list[dict]], list[Step]]]] = [
        (
            MARKETPLACE_LIST,
            lambda listed: marketplace_steps(declaration.marketplaces, listed),
        ),
        (
            PLUGIN_LIST,
            lambda listed: (
                plugin_steps(declaration, listed)
                + disable_steps(declaration, evaluated, listed)
            ),
        ),
    ]
    for inventory, steps_for in phases:
        listed = _listed(cli(inventory))
        if listed is None:
            return done, [f"cannot read `claude {' '.join(inventory)}`"]
        steps = steps_for(listed)
        if check:
            found += [why for _, why in steps if why not in found]
            continue
        for argv, why in steps:
            if cli(argv) is None:
                return done, [f"`claude {' '.join(argv)}` failed ({why})"]
        if steps:
            listed = _listed(cli(inventory))
            if listed is None:
                return done, [f"cannot read `claude {' '.join(inventory)}`"]
            if left := steps_for(listed):
                return done, list(dict.fromkeys(why for _, why in left))
            # fixed only once the inventory read again confirms it
            done += [w for w in dict.fromkeys(w for _, w in steps) if w not in done]
    return done, found


# ---- Imperative shell ----


def load(path: Path, root: Path = ROOT) -> Declaration:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Declaration(
        marketplaces={
            name: resolve_source(source, root)
            for name, source in data["marketplaces"].items()
        },
        plugins=tuple(data["plugins"]),
        disabled=tuple(data.get("disabled", ())),
        retired={mid: tuple(ids) for mid, ids in data.get("retired", {}).items()},
    )


@dataclass(frozen=True)
class State:
    """A home's claude-plugins.sync-state.json."""

    evaluated: frozenset[str] = frozenset()  # retired migrations done here
    schemas: Schemas = field(default_factory=dict)  # settings_problems() cache


def read_state(home: Path) -> State | None:
    """None when the migration record is unreadable. A bad cache is only a
    cache: it is dropped, not reported."""
    path = home / STATE_FILE
    if not path.exists():
        return State()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    retired = data.get("retired", [])
    if not isinstance(retired, list) or not all(isinstance(m, str) for m in retired):
        return None
    schemas = data.get("schemas", {})
    return State(frozenset(retired), schemas if isinstance(schemas, dict) else {})


def visit_home(
    declaration: Declaration, cli: Cli, home: Path, *, check: bool
) -> tuple[list[str], list[str]]:
    """reconcile() with the home's state file around it, then the settings check.

    A migration is recorded once its plugins are confirmed off, whatever else
    is still wrong in the home. A broken record runs no migration and is left
    as it is, so it is never read as "evaluated" nor redone over a choice.
    Only an apply writes the file; --check reads the cache and nothing else."""
    state = read_state(home)
    broken = state is None
    if state is None:
        state = State()
        done, found = reconcile(replace(declaration, retired={}), cli, check=check)
        found = [f"cannot read ~/{home.name}/{STATE_FILE}", *found]
    else:
        done, found = reconcile(
            declaration, cli, check=check, evaluated=state.evaluated
        )
    listed = _listed(cli(PLUGIN_LIST))
    if listed is None:  # the settings check and the record both need it
        unreadable = f"cannot read `claude {' '.join(PLUGIN_LIST)}`"
        return done, list(dict.fromkeys([*found, unreadable]))

    def read(pid: str) -> str | None:
        return cli(["plugin", "configure", pid, "--json"])

    problems, schemas = settings_problems(declaration, listed, state.schemas, read)
    found = list(dict.fromkeys([*found, *problems]))
    if check or broken:
        return done, found
    new = converged_migrations(declaration.retired, state.evaluated, listed)
    if new or schemas != state.schemas:
        record = {"retired": sorted(state.evaluated | new), "schemas": schemas}
        (home / STATE_FILE).write_text(json.dumps(record) + "\n", encoding="utf-8")
    return done, found


def probe_command(
    command: str, path: str | None = None, timeout: float = PROBE_TIMEOUT
) -> str | None:
    """None when `command` is on PATH and answers its version query in time."""
    found = shutil.which(command, path=path)
    if found is None:
        return "is not on PATH"
    ask = [found, *VERSION_ARGS.get(command, ("--version",))]
    try:
        done = subprocess.run(
            ask,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return f"does not start (`{' '.join(ask)}`)"
    if done.returncode != 0:
        return f"does not start (`{' '.join(ask)}` exits {done.returncode})"
    return None


def read_manifests(cli: Cli) -> dict[str, Mapping[str, object] | None] | None:
    """Each marketplace's manifest, found through `marketplace list --json`;
    None for one that cannot be read, and None for all when the list itself
    cannot be read."""
    listed = _listed(cli(MARKETPLACE_LIST))
    if listed is None:
        return None
    manifests: dict[str, Mapping[str, object] | None] = {}
    for market in listed:
        name, path, root = (
            market.get("name"),
            market.get("path"),
            market.get("installLocation"),
        )
        if not isinstance(name, str):
            continue
        if isinstance(path, str):
            file = Path(path)
        elif isinstance(root, str):
            file = Path(root) / ".claude-plugin/marketplace.json"
        else:
            manifests[name] = None
            continue
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        manifests[name] = data if isinstance(data, dict) else None
    return manifests


def _cli(claude: str, home: Path, deadline: float | None) -> Cli:
    return claude_homes.runner(claude, home, deadline)


def main(argv: Sequence[str]) -> int:
    declaration = load(DECLARATION)

    def one(claude: str, home: Path, deadline: float | None) -> tuple[list, list]:
        return visit_home(declaration, _cli(claude, home, deadline), home, check=check)

    check = "--check" in argv
    # --check runs under doctor's wait: the LSP check shares visit()'s budget
    deadline = time.monotonic() + claude_homes.CHECK_BUDGET if check else None
    homes = claude_homes.existing(Path.home())
    found = claude_homes.visit(
        NAME,
        homes,
        one,
        check=check,
        recipe="just claude-plugins-install",
        summary=lambda n: f"{len(declaration.plugins)} plugin(s) in {n} Claude home(s)",
    )
    claude = shutil.which("claude")
    if claude is None:  # visit() has said so
        return found
    with ThreadPoolExecutor(max_workers=len(homes) or 1) as pool:
        manifests = list(
            pool.map(lambda home: read_manifests(_cli(claude, home, deadline)), homes)
        )

    def probe(command: str) -> str | None:
        left = claude_homes.call_timeout(deadline, time.monotonic())
        if left is None:
            return "was not checked (doctor's time budget ran out)"
        return probe_command(command, timeout=min(PROBE_TIMEOUT, left))

    lsp = lsp_problems(declaration, manifests, probe)
    for problem in lsp:
        print(fmt(("WARN", NAME, problem)))
    return 1 if lsp else found


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
