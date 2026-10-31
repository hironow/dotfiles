"""Every Claude home gets the shared plugin set (ADR 0048, ADR 0056).

j-cc hands Codex work to `codex:codex-rescue`, which only exists with the Codex
plugin; jev-claude-verify stayed BLOCKED on hosts without it. The plugins are
declared in dump/harness/claude-plugins.json (marketplaces pinned to a tag,
except the untagged official one and this repo's own `./` marketplace) and
installed through Claude Code's own plugin CLI. The steps come from that CLI's
--json inventory; a fake CLI with real state checks the whole round trip:
replacing a marketplace drops its plugins, a second run changes nothing, and
an unreadable inventory is never read as "missing".
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import claude_homes
import claude_plugins as plugins

ROOT = Path(__file__).resolve().parents[2]
DECLARED = plugins.Declaration(
    marketplaces={"openai-codex": "openai/codex-plugin-cc#v1.0.6"},
    plugins=("codex@openai-codex",),
)


def test_the_repo_declares_the_codex_plugin_pinned_to_a_tag() -> None:
    declared = plugins.load(ROOT / "dump/harness/claude-plugins.json")
    assert "codex@openai-codex" in declared.plugins
    repo, ref = plugins.parse_source(declared.marketplaces["openai-codex"])
    assert repo == "openai/codex-plugin-cc"
    assert ref is not None and ref.startswith("v")


# ADR 0056: official has no tags and the CLI clones `--branch <ref>`, so it
# cannot take a commit SHA; a `./` source is this repo's own tracked content
UNPINNED = {"claude-plugins-official"}


def test_every_remote_marketplace_is_pinned_to_a_tag_but_the_unpinned_one() -> None:
    raw = json.loads(
        (ROOT / "dump/harness/claude-plugins.json").read_text(encoding="utf-8")
    )
    for name, source in raw["marketplaces"].items():
        if source.startswith("./"):
            assert (ROOT / source).is_file(), name
            continue
        ref = plugins.parse_source(source)[1]
        if name in UNPINNED:
            assert ref is None, name
        else:
            assert ref is not None and plugins._version(ref), name


def test_the_unpinned_exception_names_a_declared_marketplace() -> None:
    # a stale exception would let a later marketplace of that name go unpinned
    raw = json.loads(
        (ROOT / "dump/harness/claude-plugins.json").read_text(encoding="utf-8")
    )
    assert set(raw["marketplaces"]) >= UNPINNED


def test_every_declared_plugin_comes_from_a_declared_marketplace() -> None:
    declared = plugins.load(plugins.DECLARATION)
    assert len(declared.plugins) == len(set(declared.plugins))
    for pid in declared.plugins:
        assert pid.partition("@")[2] in declared.marketplaces, pid


def test_pyright_is_never_declared() -> None:
    # ADR 0044: ty is the only Python type checker
    declared = plugins.load(plugins.DECLARATION)
    assert not [pid for pid in declared.plugins if "pyright" in pid]


def test_egm_only_never_reconciles_other_plugins_or_probes_lsp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / ".claude"
    home.mkdir()
    personal = {"id": "personal@elsewhere", "scope": "user", "enabled": True}
    fake = FakeClaude(
        [], [personal.copy()], names={"google/elephant-goldfish-model#v0.1.0": "egm"}
    )
    cache = {"personal@elsewhere": {"key": "local", "needed": []}}
    (home / plugins.STATE_FILE).write_text(
        json.dumps({"retired": ["previous-migration"], "schemas": cache}),
        encoding="utf-8",
    )

    def cli(args: list[str]) -> str | None:
        result = fake(args)
        if args[:3] == ["plugin", "install", "egm@egm"]:
            fake.installed[-1]["version"] = "0.1.0"
        return result

    monkeypatch.setattr(plugins.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(claude_homes.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(plugins, "_cli", lambda *_args: cli)
    monkeypatch.setattr(
        plugins, "read_manifests", lambda *_args: pytest.fail("unrelated LSP probe")
    )
    assert plugins.main(["--egm-only"]) == 0
    assert fake.mutations == [
        [
            "plugin",
            "marketplace",
            "add",
            "google/elephant-goldfish-model#v0.1.0",
            "--scope",
            "user",
        ],
        ["plugin", "install", "egm@egm", "--scope", "user"],
    ]
    assert fake.schema_reads == ["egm@egm"]
    assert personal in fake.installed
    state = json.loads((home / plugins.STATE_FILE).read_text(encoding="utf-8"))
    assert state["schemas"]["personal@elsewhere"] == cache["personal@elsewhere"]
    assert state["retired"] == ["previous-migration"]
    fake.mutations.clear()
    assert plugins.main(["--egm-only"]) == 0
    assert fake.mutations == []


def test_a_source_splits_into_repo_and_ref() -> None:
    assert plugins.parse_source("o/r#v1.2.3") == ("o/r", "v1.2.3")
    assert plugins.parse_source("o/r") == ("o/r", None)


class FakeClaude:
    """`claude plugin ...` against in-memory state, as the real CLI behaves."""

    def __init__(
        self,
        markets: list[dict],
        installed: list[dict],
        names: dict[str, str] | None = None,  # declared source -> marketplace name
    ) -> None:
        self.markets, self.installed = markets, installed
        self.names = names or {"openai/codex-plugin-cc#v1.0.6": "openai-codex"}
        # plugin id -> `configure --json` schema; None makes the read fail
        self.schemas: dict[str, dict | None] = {}
        self.schema_reads: list[str] = []
        # successful `plugin list --json` reads before they start to fail
        self.plugin_lists_left: int | None = None
        self.mutations: list[list[str]] = []
        self.readable = True
        self.failing: list[str] | None = None  # e.g. ["marketplace", "add"]

    def __call__(self, args: list[str]) -> str | None:
        if args[:2] == ["plugin", "configure"]:
            self.schema_reads.append(args[2])
            schema = self.schemas.get(args[2], {})
            return None if schema is None else json.dumps({"schema": schema})
        if args[-1] == "--json":
            if not self.readable:
                return None
            if args == plugins.PLUGIN_LIST and self.plugin_lists_left is not None:
                if self.plugin_lists_left == 0:
                    return None
                self.plugin_lists_left -= 1
            return json.dumps(self.markets if "marketplace" in args else self.installed)
        self.mutations.append(args)
        if self.failing and args[1:3] == self.failing:
            return None
        match args[1:]:
            case ["marketplace", "add", source, "--scope", "user"]:
                name = self.names[source]
                if Path(source).is_absolute():
                    self.markets.append(
                        {"name": name, "source": "file", "path": source}
                    )
                else:
                    repo, ref = plugins.parse_source(source)
                    self.markets.append({"name": name, "repo": repo, "ref": ref})
            case ["marketplace", "remove", name, "--scope", "user"]:
                # removing a marketplace uninstalls what came from it
                self.markets = [m for m in self.markets if m["name"] != name]
                self.installed = [
                    p for p in self.installed if not p["id"].endswith("@" + name)
                ]
            case ["install", pid, "--scope", "user"]:
                self.installed.append(
                    {"id": pid, "version": "1.0.6", "scope": "user", "enabled": True}
                )
            case ["uninstall", pid, "--scope", "user"]:
                self.installed = [
                    p
                    for p in self.installed
                    if not (p["id"] == pid and p["scope"] == "user")
                ]
            case ["enable" | "disable" as verb, pid, "--scope", "user"]:
                for p in self.installed:
                    if p["id"] == pid and p["scope"] == "user":
                        p["enabled"] = verb == "enable"
            case _:
                raise AssertionError(f"unexpected claude {args}")
        return ""


MARKET = {"name": "openai-codex", "repo": "openai/codex-plugin-cc", "ref": "v1.0.6"}
PLUGIN = {
    "id": "codex@openai-codex",
    "version": "1.0.6",
    "scope": "user",
    "enabled": True,
}


def _run(cli: FakeClaude, *, check: bool = False) -> tuple[list[str], list[str]]:
    return plugins.reconcile(DECLARED, cli, check=check)


def test_an_empty_home_gets_the_marketplace_and_the_plugin_once() -> None:
    cli = FakeClaude([], [])
    _done, problems = _run(cli)
    assert problems == []
    assert [m[1:3] for m in cli.mutations] == [
        ["marketplace", "add"],
        ["install", "codex@openai-codex"],
    ]
    cli.mutations.clear()
    assert _run(cli) == ([], [])
    assert cli.mutations == []


def test_a_marketplace_at_another_ref_is_replaced_and_the_plugin_reinstalled() -> None:
    old = {**MARKET, "ref": "v1.0.5"}
    cli = FakeClaude([old], [{**PLUGIN, "version": "1.0.5"}])
    done, problems = _run(cli)
    assert problems == []
    assert len(done) == len(set(done))  # remove and add share one reason
    assert cli.markets == [MARKET]
    assert cli.installed == [PLUGIN]


@pytest.mark.parametrize(
    ("installed", "steps"),
    [
        ([{**PLUGIN, "enabled": False}], [["enable", "codex@openai-codex"]]),
        # a project or local install does not count for the user
        ([{**PLUGIN, "scope": "project"}], [["install", "codex@openai-codex"]]),
        (
            [{**PLUGIN, "version": "1.0.4"}],
            [["uninstall", "codex@openai-codex"], ["install", "codex@openai-codex"]],
        ),
    ],
)
def test_the_plugin_converges_on_the_declared_user_install(
    installed: list[dict], steps: list[list[str]]
) -> None:
    cli = FakeClaude([dict(MARKET)], installed)
    assert _run(cli)[1] == []
    assert [m[1:3] for m in cli.mutations] == steps
    assert all(m[-2:] == ["--scope", "user"] for m in cli.mutations)


def test_an_unreadable_inventory_is_reported_never_acted_on() -> None:
    cli = FakeClaude([], [])
    cli.readable = False
    done, problems = _run(cli)
    assert done == []
    assert cli.mutations == []
    assert problems and "cannot read" in problems[0]


def test_check_reports_without_changing_anything() -> None:
    cli = FakeClaude([], [])
    _done, problems = _run(cli, check=True)
    assert cli.mutations == []
    assert any("openai-codex" in p for p in problems)
    assert any("codex@openai-codex" in p for p in problems)


def test_a_complete_home_has_no_steps() -> None:
    cli = FakeClaude([dict(MARKET)], [dict(PLUGIN)])
    assert _run(cli, check=True) == ([], [])


def test_doctor_checks_and_deploy_installs_the_plugins() -> None:
    import ai_tools_check

    assert "claude_plugins.py" in ai_tools_check.CHECKERS["claude"][1]
    justfile = (ROOT / "justfile").read_text(encoding="utf-8")
    assert "claude-plugins-install *args:" in justfile
    deploy = (ROOT / "scripts/deploy.sh").read_text(encoding="utf-8")
    # one of the agent steps every OS runs (test_deploy_pi_extensions)
    assert "claude_plugins.py claude-plugins-install" in deploy


@pytest.mark.parametrize(
    "fragment",
    sorted(
        [*(ROOT / ".claude").glob("settings.shared*.json")]
        + [*(ROOT / ".claude/settings.profiles").glob("*.json")]
    ),
    ids=lambda path: path.name,
)
def test_no_settings_fragment_claims_the_plugin_keys(fragment: Path) -> None:
    # The plugin CLI owns them (ADR 0037, ADR 0048): a fragment declaring them
    # would replace what claude_plugins.py installed on every sync
    data = json.loads(fragment.read_text(encoding="utf-8"))
    sections = [data, data.get("settings", {})]
    for key in ("enabledPlugins", "extraKnownMarketplaces"):
        assert all(key not in section for section in sections)


def test_main_prints_each_home_then_the_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in (".claude", ".claude-work-b"):
        (tmp_path / name).mkdir()
    results = {
        ".claude": (["marketplace openai-codex is missing"], []),
        ".claude-work-b": ([], ["cannot read `claude plugin list --json`"]),
    }
    monkeypatch.setattr(plugins.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(claude_homes.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(
        plugins, "visit_home", lambda _d, _cli, home, *, check: results[home.name]
    )
    monkeypatch.setattr(
        plugins, "_cli", lambda _c, home, _deadline: type("C", (), {"home": home})()
    )
    monkeypatch.setattr(plugins, "read_manifests", lambda _cli: {})  # no LSP here
    assert plugins.main(["--check"]) == 1
    assert capsys.readouterr().out.splitlines() == [
        "OK   claude-plugins - ~/.claude: fixed: marketplace openai-codex is missing",
        (
            "WARN claude-plugins - ~/.claude-work-b: cannot read `claude plugin list --json`:"
            " just claude-plugins-install"
        ),
    ]
    results[".claude-work-b"] = ([], [])
    assert plugins.main([]) == 0
    # a count, not every id: the declaration is too long for one doctor line
    count = len(plugins.load(plugins.DECLARATION).plugins)
    assert capsys.readouterr().out.splitlines()[-1] == (
        f"OK   claude-plugins - {count} plugin(s) in 2 Claude home(s)"
    )


def test_a_repair_that_fails_halfway_is_not_reported_as_done() -> None:
    # remove succeeds, add fails: the marketplace is now missing, not fixed
    cli = FakeClaude([{**MARKET, "ref": "v1.0.5"}], [])
    cli.failing = ["marketplace", "add"]
    done, problems = _run(cli)
    assert done == []
    assert problems and "failed" in problems[0]


def test_a_relative_source_resolves_against_the_repo_root(tmp_path: Path) -> None:
    # a local marketplace is listed by its absolute path, which differs per
    # checkout and OS, so the declaration names it relative to the repo
    local = "./.claude-plugin/marketplace.json"
    assert plugins.resolve_source(local, tmp_path) == str(
        tmp_path / ".claude-plugin/marketplace.json"
    )
    assert plugins.resolve_source("o/r#v1.2.3", tmp_path) == "o/r#v1.2.3"
    declaration = tmp_path / "claude-plugins.json"
    declaration.write_text(
        json.dumps({"marketplaces": {"local": local}, "plugins": ["p@local"]}),
        encoding="utf-8",
    )
    loaded = plugins.load(declaration, tmp_path)
    assert loaded.marketplaces == {"local": str(tmp_path / local)}


def _local(path: Path) -> dict:
    return {"name": "hironow-plugins", "source": "file", "path": str(path)}


def test_a_local_marketplace_at_the_declared_path_has_no_steps(tmp_path: Path) -> None:
    path = tmp_path / ".claude-plugin/marketplace.json"
    declared = {"hironow-plugins": str(path)}
    assert plugins.marketplace_steps(declared, [_local(path)]) == []


def test_a_local_marketplace_at_another_path_is_replaced(tmp_path: Path) -> None:
    # e.g. registered from an old checkout or a worktree
    path = tmp_path / "dotfiles/.claude-plugin/marketplace.json"
    old = tmp_path / "old/.claude-plugin/marketplace.json"
    steps = plugins.marketplace_steps({"hironow-plugins": str(path)}, [_local(old)])
    assert [argv for argv, _ in steps] == [
        ["plugin", "marketplace", "remove", "hironow-plugins", "--scope", "user"],
        ["plugin", "marketplace", "add", str(path), "--scope", "user"],
    ]


def test_an_unpinned_marketplace_matches_a_listing_without_a_ref() -> None:
    # claude-plugins-official has no tags (ADR 0056); the CLI lists no ref key
    listed = [
        {
            "name": "claude-plugins-official",
            "source": "github",
            "repo": "anthropics/claude-plugins-official",
        }
    ]
    declared = {"claude-plugins-official": "anthropics/claude-plugins-official"}
    assert plugins.marketplace_steps(declared, listed) == []


def test_a_local_marketplace_and_its_plugin_converge_once(tmp_path: Path) -> None:
    path = str(tmp_path / ".claude-plugin/marketplace.json")
    declared = plugins.Declaration(
        marketplaces={"hironow-plugins": path}, plugins=("grilling@hironow-plugins",)
    )
    old = {**_local(tmp_path / "old.json")}
    cli = FakeClaude([old], [], names={path: "hironow-plugins"})
    assert plugins.reconcile(declared, cli, check=False)[1] == []
    assert cli.markets == [_local(Path(path))]
    assert [p["id"] for p in cli.installed] == ["grilling@hironow-plugins"]
    cli.mutations.clear()
    assert plugins.reconcile(declared, cli, check=False) == ([], [])
    assert cli.mutations == []


# ---- ADR 0057: per-home settings, disabled and retired plugins ----

FIRESTORE = "firestore-native@claude-plugins-official"
BIGQUERY = "bigquery-data-analytics@claude-plugins-official"
PYRIGHT = "pyright-lsp@claude-plugins-official"
GCP = "2026-10-16-gcp-per-home-settings"
# firestore-native as the CLI reports it: the database is described as
# optional, yet it has no default either
FIRESTORE_SCHEMA = {
    "firestore_project": {"type": "string", "title": "Project ID"},
    "firestore_database": {
        "type": "string",
        "title": "Database ID",
        "description": "(Optional) ID of the Firestore database",
    },
}


def _user(pid: str, *, enabled: bool = True) -> dict:
    return {"id": pid, "version": "1.0.0", "scope": "user", "enabled": enabled}


def test_an_option_without_a_default_may_need_per_home_settings() -> None:
    # conservative: whether the option is really required is not judged
    assert plugins.settings_needed(FIRESTORE_SCHEMA) == [
        "firestore_project",
        "firestore_database",
    ]
    with_defaults = {"track": {"type": "string", "default": "auto"}}
    assert plugins.settings_needed(with_defaults) == []
    assert plugins.settings_needed({}) == []


@pytest.mark.parametrize("check", [True, False])
def test_a_declared_plugin_needing_per_home_settings_is_reported(
    check: bool, tmp_path: Path
) -> None:
    # doctor (check) too: `claude plugin update` never passes through reconcile
    cli = FakeClaude([dict(MARKET)], [dict(PLUGIN)])
    cli.schemas["codex@openai-codex"] = FIRESTORE_SCHEMA
    _done, problems = plugins.visit_home(DECLARED, cli, tmp_path, check=check)
    assert len(problems) == 1
    assert "codex@openai-codex" in problems[0]
    assert "firestore_project, firestore_database" in problems[0]
    assert "ADR 0057" in problems[0]


def test_an_unreadable_settings_schema_is_reported_never_passed(
    tmp_path: Path,
) -> None:
    cli = FakeClaude([dict(MARKET)], [dict(PLUGIN)])
    cli.schemas["codex@openai-codex"] = None
    assert plugins.visit_home(DECLARED, cli, tmp_path, check=True)[1] == [
        "cannot read `claude plugin configure codex@openai-codex --json`"
    ]
    # nothing is cached for a read that failed
    plugins.visit_home(DECLARED, cli, tmp_path, check=False)
    state = tmp_path / plugins.STATE_FILE
    assert not state.exists() or "codex@openai-codex" not in state.read_text(
        encoding="utf-8"
    )


def _codex(**changes: object) -> dict:
    return {**PLUGIN, "lastUpdated": "2026-10-16T00:00:00Z", **changes}


def test_an_unchanged_plugin_reuses_its_cached_schema(tmp_path: Path) -> None:
    cli = FakeClaude([dict(MARKET)], [_codex()])
    plugins.visit_home(DECLARED, cli, tmp_path, check=False)
    assert cli.schema_reads == ["codex@openai-codex"]
    cli.schema_reads.clear()
    assert plugins.visit_home(DECLARED, cli, tmp_path, check=True) == ([], [])
    assert cli.schema_reads == []
    # `claude plugin update` moves lastUpdated: read again, even in doctor
    cli.installed = [_codex(lastUpdated="2026-10-17T00:00:00Z")]
    cli.schemas["codex@openai-codex"] = FIRESTORE_SCHEMA
    _done, problems = plugins.visit_home(DECLARED, cli, tmp_path, check=True)
    assert cli.schema_reads == ["codex@openai-codex"]
    assert problems and "ADR 0057" in problems[0]


def test_check_reads_the_cache_but_never_writes_it(tmp_path: Path) -> None:
    cli = FakeClaude([dict(MARKET)], [_codex()])
    plugins.visit_home(DECLARED, cli, tmp_path, check=False)
    before = (tmp_path / plugins.STATE_FILE).read_text(encoding="utf-8")
    cli.installed = [_codex(lastUpdated="2026-10-17T00:00:00Z")]
    plugins.visit_home(DECLARED, cli, tmp_path, check=True)
    assert (tmp_path / plugins.STATE_FILE).read_text(encoding="utf-8") == before


def test_a_plugin_read_from_a_folder_is_read_every_time(tmp_path: Path) -> None:
    # its schema can change in the folder while version and lastUpdated stay
    cli = FakeClaude([dict(MARKET)], [_codex(readFromFolder=str(tmp_path / "p"))])
    plugins.visit_home(DECLARED, cli, tmp_path, check=False)
    plugins.visit_home(DECLARED, cli, tmp_path, check=True)
    assert cli.schema_reads == ["codex@openai-codex", "codex@openai-codex"]


def test_a_state_holding_only_the_cache_is_not_broken(tmp_path: Path) -> None:
    (tmp_path / plugins.STATE_FILE).write_text('{"schemas": {}}', encoding="utf-8")
    assert plugins.read_state(tmp_path) is not None


def test_a_failed_final_inventory_is_reported_and_records_nothing(
    tmp_path: Path,
) -> None:
    # reconcile reads the inventory fine; the read after it fails
    cli = FakeClaude([dict(MARKET)], [_codex(), _user(FIRESTORE)])
    declaration = _gcp_declaration()
    for check in (True, False):
        # check: the plugin phase; apply: that and its re-read after disabling
        cli.plugin_lists_left = 1 if check else 2
        _done, problems = plugins.visit_home(declaration, cli, tmp_path, check=check)
        assert "cannot read `claude plugin list --json`" in problems
    assert not (tmp_path / plugins.STATE_FILE).exists()


def _gcp_declaration() -> plugins.Declaration:
    return plugins.Declaration(
        marketplaces=DECLARED.marketplaces,
        plugins=DECLARED.plugins,
        disabled=(PYRIGHT,),
        retired={GCP: (BIGQUERY, FIRESTORE)},
    )


def test_a_disabled_plugin_is_disabled_on_every_run() -> None:
    declaration = _gcp_declaration()
    listed = [_user(PYRIGHT)]
    steps = plugins.disable_steps(declaration, frozenset({GCP}), listed)
    assert [argv for argv, _ in steps] == [
        ["plugin", "disable", PYRIGHT, "--scope", "user"]
    ]
    for already in ([_user(PYRIGHT, enabled=False)], []):
        assert plugins.disable_steps(declaration, frozenset(), already) == []


def test_a_retired_plugin_is_disabled_until_its_migration_is_evaluated() -> None:
    declaration = _gcp_declaration()
    listed = [_user(FIRESTORE), _user(BIGQUERY, enabled=False)]
    steps = plugins.disable_steps(declaration, frozenset(), listed)
    assert [argv for argv, _ in steps] == [
        ["plugin", "disable", FIRESTORE, "--scope", "user"]
    ]
    # evaluated once: what the user enables afterwards is theirs
    assert plugins.disable_steps(declaration, frozenset({GCP}), listed) == []


def test_a_migration_converges_when_none_of_its_plugins_is_enabled() -> None:
    retired = {GCP: (BIGQUERY, FIRESTORE)}
    assert plugins.converged_migrations(retired, frozenset(), []) == {GCP}
    on = [_user(FIRESTORE)]
    assert plugins.converged_migrations(retired, frozenset(), on) == set()
    assert plugins.converged_migrations(retired, frozenset({GCP}), []) == set()


def _state(home: Path) -> dict:
    return json.loads((home / plugins.STATE_FILE).read_text(encoding="utf-8"))


def test_a_home_records_a_migration_once_and_keeps_a_later_enable(
    tmp_path: Path,
) -> None:
    declaration = _gcp_declaration()
    cli = FakeClaude([dict(MARKET)], [dict(PLUGIN), _user(FIRESTORE)])
    assert plugins.visit_home(declaration, cli, tmp_path, check=False)[1] == []
    assert next(p for p in cli.installed if p["id"] == FIRESTORE)["enabled"] is False
    assert _state(tmp_path)["retired"] == [GCP]
    # the user configures firestore-native in this home and enables it again
    next(p for p in cli.installed if p["id"] == FIRESTORE)["enabled"] = True
    cli.mutations.clear()
    assert plugins.visit_home(declaration, cli, tmp_path, check=False) == ([], [])
    assert cli.mutations == []


def test_an_unrelated_problem_does_not_hold_back_a_converged_migration(
    tmp_path: Path,
) -> None:
    declaration = _gcp_declaration()
    cli = FakeClaude([dict(MARKET)], [dict(PLUGIN), _user(FIRESTORE)])
    cli.schemas["codex@openai-codex"] = None  # a WARN that has nothing to do with it
    _done, problems = plugins.visit_home(declaration, cli, tmp_path, check=False)
    assert problems and "configure" in problems[0]
    assert _state(tmp_path)["retired"] == [GCP]
    next(p for p in cli.installed if p["id"] == FIRESTORE)["enabled"] = True
    plugins.visit_home(declaration, cli, tmp_path, check=False)
    assert next(p for p in cli.installed if p["id"] == FIRESTORE)["enabled"] is True


def test_check_reports_a_pending_migration_and_writes_no_state(tmp_path: Path) -> None:
    cli = FakeClaude([dict(MARKET)], [dict(PLUGIN), _user(FIRESTORE)])
    _done, problems = plugins.visit_home(_gcp_declaration(), cli, tmp_path, check=True)
    assert any(FIRESTORE in p for p in problems)
    assert cli.mutations == []
    assert not (tmp_path / plugins.STATE_FILE).exists()


def test_a_broken_state_file_is_reported_and_runs_no_migration(tmp_path: Path) -> None:
    # never read a broken record as "evaluated", nor redo what it may hold
    (tmp_path / plugins.STATE_FILE).write_text("{not json", encoding="utf-8")
    cli = FakeClaude([dict(MARKET)], [dict(PLUGIN), _user(FIRESTORE)])
    _done, problems = plugins.visit_home(_gcp_declaration(), cli, tmp_path, check=False)
    assert any(plugins.STATE_FILE in p for p in problems)
    assert next(p for p in cli.installed if p["id"] == FIRESTORE)["enabled"] is True
    state = (tmp_path / plugins.STATE_FILE).read_text(encoding="utf-8")
    assert state == "{not json"


def test_the_repo_declares_nothing_both_shared_and_switched_off() -> None:
    declared = plugins.load(plugins.DECLARATION)
    off = set(declared.disabled) | {
        pid for ids in declared.retired.values() for pid in ids
    }
    assert PYRIGHT in declared.disabled
    assert not off & set(declared.plugins)


# ---- LSP servers need their command on this machine ----

GOPLS = "gopls-lsp@claude-plugins-official"
TSLS = "typescript-lsp@claude-plugins-official"
OFFICIAL = "claude-plugins-official"


def _manifest(*entries: dict) -> dict:
    return {"name": OFFICIAL, "plugins": list(entries)}


def _lsp(name: str, command: str) -> dict:
    return {"name": name, "lspServers": {name: {"command": command}}}


def _lsp_declaration(*pids: str) -> plugins.Declaration:
    return plugins.Declaration(marketplaces={OFFICIAL: "o/r"}, plugins=pids)


def test_an_lsp_entry_names_the_commands_it_runs() -> None:
    entry = {
        "name": "typescript-lsp",
        "lspServers": {"typescript": {"command": "typescript-language-server"}},
    }
    assert plugins.lsp_commands(entry) == ["typescript-language-server"]
    assert plugins.lsp_commands({"name": "code-review"}) == []
    assert plugins.lsp_commands({"lspServers": "./lsp.json"}) == []
    assert plugins.lsp_commands({"lspServers": {"x": {"args": []}}}) == []


def test_a_missing_or_broken_lsp_command_is_reported_once() -> None:
    manifest = _manifest(_lsp("gopls-lsp", "gopls"), _lsp("typescript-lsp", "tsls"))
    probed: list[str] = []

    def probe(command: str) -> str | None:
        probed.append(command)
        return {"gopls": "is not on PATH", "tsls": None}[command]

    homes = [{OFFICIAL: manifest}, {OFFICIAL: manifest}]
    problems = plugins.lsp_problems(_lsp_declaration(GOPLS, TSLS), homes, probe)
    assert len(problems) == 1
    assert GOPLS in problems[0] and "`gopls`" in problems[0]
    assert "is not on PATH" in problems[0] and "mise" in problems[0]
    assert sorted(probed) == ["gopls", "tsls"]  # once per command, not per home


def test_a_command_only_a_later_home_asks_for_is_checked() -> None:
    # homes keep their own copy of a marketplace, and it can differ (ADR 0057)
    homes = [
        {OFFICIAL: _manifest({"name": "gopls-lsp"})},
        {OFFICIAL: _manifest(_lsp("gopls-lsp", "gopls"))},
    ]
    problems = plugins.lsp_problems(
        _lsp_declaration(GOPLS), homes, lambda _cmd: "does not start"
    )
    assert problems and "`gopls`" in problems[0]


def test_an_unreadable_marketplace_manifest_is_reported() -> None:
    problems = plugins.lsp_problems(
        _lsp_declaration(GOPLS), [{OFFICIAL: None}], lambda _cmd: None
    )
    assert problems == [f"cannot read the {OFFICIAL} marketplace manifest"]


def test_probe_reports_a_command_found_but_failing(tmp_path: Path) -> None:
    # rustup's proxy: on PATH, yet `Unknown binary 'rust-analyzer'` on any call
    broken = tmp_path / "rust-analyzer"
    broken.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    broken.chmod(0o755)
    working = tmp_path / "gopls"
    working.write_text("#!/bin/sh\necho v1\n", encoding="utf-8")
    working.chmod(0o755)
    path = str(tmp_path)
    if sys.platform == "win32":
        pytest.skip("sh stubs need a Unix shell")
    assert plugins.probe_command("rust-analyzer", path) is not None
    assert plugins.probe_command("gopls", path) is None
    assert plugins.probe_command("no-such-lsp", path) == "is not on PATH"


def test_probe_asks_gopls_with_its_own_subcommand(tmp_path: Path) -> None:
    # gopls rejects `--version` ("unknown flag") and answers `gopls version`
    if sys.platform == "win32":
        pytest.skip("sh stubs need a Unix shell")
    gopls = tmp_path / "gopls"
    gopls.write_text(
        '#!/bin/sh\n[ "$1" = version ] && echo v0.24.0 && exit 0\nexit 2\n',
        encoding="utf-8",
    )
    gopls.chmod(0o755)
    assert plugins.probe_command("gopls", str(tmp_path)) is None


def test_an_unreadable_marketplace_list_is_reported_not_skipped() -> None:
    # a home whose list cannot be read must not pass for "no LSP plugins here"
    assert plugins.read_manifests(lambda _argv: None) is None
    problems = plugins.lsp_problems(_lsp_declaration(GOPLS), [None], lambda _c: None)
    assert problems == ["cannot read `claude plugin marketplace list --json`"]


def test_probe_gives_up_within_its_timeout(tmp_path: Path) -> None:
    if sys.platform == "win32":
        pytest.skip("sh stubs need a Unix shell")
    slow = tmp_path / "gopls"
    slow.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
    slow.chmod(0o755)
    why = plugins.probe_command("gopls", str(tmp_path), timeout=0.2)
    assert why is not None and "does not start" in why


def test_the_lsp_check_shares_doctors_time_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # --check runs under doctor's wait: every claude call gets a deadline
    (tmp_path / ".claude").mkdir()
    deadlines: list[float | None] = []

    def cli(_claude: str, _home: Path, deadline: float | None):
        deadlines.append(deadline)
        return lambda _argv: None

    monkeypatch.setattr(plugins.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(claude_homes.shutil, "which", lambda _: "claude")
    monkeypatch.setattr(plugins, "visit_home", lambda *_a, **_k: ([], []))
    monkeypatch.setattr(plugins, "_cli", cli)
    assert plugins.main(["--check"]) == 1  # the list cannot be read: a WARN
    assert deadlines and all(d is not None for d in deadlines)
