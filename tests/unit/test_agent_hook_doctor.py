"""Agent-hook doctor: pure reporting, then isolated executable fixtures."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import agent_hook_doctor as check
import agent_hook_release as release
import codex_shells
from _agent_hooks_go import STRICT_GO, why_go_cannot_build_the_module

ROOT = Path(__file__).resolve().parents[2]
REAL_GO = shutil.which("go")
REAL_BASH = shutil.which("bash")


PROGRAM = "/state/dotfiles/agent-hooks/releases/abcdef0123456789/agent-hook"
FRAGMENT = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": PROGRAM,
                        "args": ["claude", "pre", "--hook", "command-guard"],
                    }
                ],
            }
        ]
    }
}


def _wired(**changes: object) -> check.Home:
    return replace(
        check.Home(
            ".claude",
            "claude",
            managed=FRAGMENT["hooks"],
            binaries=(
                check.Binary(PROGRAM, PROGRAM, check.Render(check.Outcome(), FRAGMENT)),
            ),
        ),
        **changes,
    )


def _lines(facts: check.Facts, name: str) -> list[tuple[str, str]]:
    return [
        (level, detail)
        for level, key, detail in check.report(facts)
        if key == "agent-hook-" + name
    ]


def test_script_homes_share_one_informational_wiring_line() -> None:
    facts = check.Facts(
        homes=(
            check.Home(".claude", "claude", scripts=True),
            check.Home("Codex", "codex", scripts=True),
        )
    )
    assert check.report(facts) == [
        (
            "INFO",
            "agent-hook-wiring",
            "not wired: today's scripts run in .claude and Codex",
        )
    ]


def test_no_managed_block_is_a_fact_not_an_agent_hook_regression() -> None:
    lines = _lines(check.Facts(homes=(check.Home("Codex", "codex"),)), "wiring")
    assert lines[0][0] == "INFO"
    assert "no dotfiles hook registered in Codex" in lines[0][1]
    assert "not new" in lines[0][1]


@pytest.mark.parametrize(
    "scripts,paths",
    [(True, (PROGRAM,)), (False, (PROGRAM, PROGRAM.replace("abcdef", "fedcba")))],
)
def test_mixed_wiring_warns_and_names_sync(
    scripts: bool, paths: tuple[str, ...]
) -> None:
    home = _wired(
        scripts=scripts, binaries=tuple(check.Binary(path, path) for path in paths)
    )
    assert _lines(check.Facts(homes=(home,)), "wiring")[0][0] == "WARN"
    assert "just sync-agents" in _lines(check.Facts(homes=(home,)), "wiring")[0][1]


def test_matching_render_needs_no_registration_warning() -> None:
    assert _lines(check.Facts(homes=(_wired(),)), "registered") == []


@pytest.mark.parametrize(
    "actual,expected,path",
    [
        ({"event": [1]}, {"event": []}, "event[0]"),
        ({"event": []}, {"event": [1]}, "event[0]"),
        ({"value": True}, {"value": 1}, "value"),
    ],
)
def test_first_difference_preserves_list_lengths_and_json_types(
    actual: object, expected: object, path: str
) -> None:
    assert check.first_difference(actual, expected) == path


def test_registration_names_the_first_event_block_and_field_difference() -> None:
    changed = {
        "PreToolUse": [{**FRAGMENT["hooks"]["PreToolUse"][0], "matcher": "Write"}]
    }
    lines = _lines(check.Facts(homes=(_wired(managed=changed),)), "registered")
    assert lines[0][0] == "WARN"
    assert "PreToolUse[0].matcher" in lines[0][1]


def test_missing_or_non_release_binary_warns() -> None:
    home = _wired(binaries=(check.Binary(PROGRAM, None, problem="missing"),))
    lines = _lines(check.Facts(homes=(home,)), "binary")
    assert lines == [("WARN", f".claude: {PROGRAM}: missing")]


@pytest.mark.parametrize(
    "code,level,detail",
    [
        (0, "OK", "checkout"),
        (1, "WARN", "just sync-agents"),
        (3, "WARN", "sync never replaces a release in place"),
        (2, "INFO", "cannot check here"),
        (None, "INFO", "cannot check here"),
    ],
)
def test_freshness_preserves_each_check_outcome(
    code: int | None, level: str, detail: str
) -> None:
    outcome = check.Outcome(
        exit_code=code, reason="missing Go" if code is None else None
    )
    lines = _lines(
        check.Facts(
            homes=(_wired(),), releases=(check.Release(PROGRAM, outcome, checked=True),)
        ),
        "fresh",
    )
    assert lines[0][0] == level
    assert detail in lines[0][1]


@pytest.mark.parametrize("code", [0, 1, 3])
def test_only_the_checker_can_classify_release_freshness(code: int) -> None:
    release = check.Release(
        PROGRAM, check.Outcome(exit_code=code, reason="setup failed")
    )
    assert _lines(check.Facts(releases=(release,)), "fresh") == [
        ("INFO", f"release {PROGRAM}: cannot check here: setup failed")
    ]


def test_loss_lines_and_missing_formatter_tools_are_informational() -> None:
    rendered = check.Render(
        check.Outcome(),
        FRAGMENT,
        ({"level": "pending", "tool": "Example", "reason": "no captured payload"},),
    )
    home = _wired(binaries=(check.Binary(PROGRAM, PROGRAM, rendered),))
    facts = check.Facts(homes=(home,), tools=frozenset())
    assert _lines(facts, "loss") == [
        ("INFO", ".claude: pending Example: no captured payload")
    ]
    assert len(_lines(facts, "tools")) == 2
    assert all(level == "INFO" for level, _ in _lines(facts, "tools"))
    assert _lines(check.Facts(tools=frozenset()), "tools") == []


@pytest.mark.parametrize(
    "errors,mismatches,level",
    [
        ({}, {}, "INFO"),
        (
            {"input.unreadable": 1, "rewrite.dropped": 2, "tool.failed": 1, "usage": 1},
            {},
            "INFO",
        ),
        ({"shim.broken": 1}, {}, "WARN"),
        ({"hook.failed": 2}, {}, "WARN"),
        ({"hook.timeout": 1}, {}, "WARN"),
        ({"answer.failed": 1}, {}, "WARN"),
        ({}, {"input": 1}, "WARN"),
        ({}, {"other": 1}, "WARN"),
        ({"hook.failed": 0}, {"input": 0}, "INFO"),
    ],
)
def test_log_level_follows_actionable_counts(
    errors: dict[str, int], mismatches: dict[str, int], level: str
) -> None:
    summary = check.LogSummary(1, 8, 0, errors, mismatches)
    lines = _lines(
        check.Facts(
            homes=(_wired(),), logs=(check.Log(PROGRAM, check.Outcome(), summary),)
        ),
        "log",
    )
    assert lines[0][0] == level
    assert "8" in lines[0][1]
    assert "agent-hook log" in lines[0][1]


def test_unreadable_log_lines_are_an_additional_info_line() -> None:
    log = check.Log(PROGRAM, check.Outcome(), check.LogSummary(1, 8, 3, {}, {}))
    assert _lines(check.Facts(homes=(_wired(),), logs=(log,)), "log")[-1] == (
        "INFO",
        "3 unreadable log lines skipped",
    )


@pytest.mark.parametrize(
    "reason", ["missing", "exits 7", "timed out after 30 s", "output does not parse"]
)
def test_failed_render_and_log_warn_without_hiding_the_other_home(reason: str) -> None:
    failed = check.Outcome(exit_code=None, reason=reason)
    home = _wired(binaries=(check.Binary(PROGRAM, PROGRAM, check.Render(failed)),))
    facts = check.Facts(
        homes=(home, check.Home("Codex", "codex")), logs=(check.Log(PROGRAM, failed),)
    )
    lines = _lines(facts, "inspect")
    assert len(lines) == 2
    assert all(level == "WARN" and reason in detail for level, detail in lines)
    assert "render" in lines[0][1] and ".claude" in lines[0][1]
    assert "log" in lines[1][1]
    assert ".claude" in lines[1][1]
    assert _lines(facts, "log") == []
    assert "Codex" in _lines(facts, "wiring")[0][1]


@pytest.mark.parametrize(
    "login,system,paths,files,expected,kind",
    [
        ("/bin/zsh", "darwin", {}, {"/bin/zsh"}, "/bin/zsh", "zsh"),
        ("/bin/bash", "linux", {}, {"/bin/bash"}, "/bin/bash", "bash"),
        ("/bin/sh", "linux", {}, {"/bin/sh"}, "/bin/sh", "sh"),
        ("/bin/bash.exe", "linux", {}, {"/bin/bash.exe"}, "/bin/bash.exe", "bash"),
        ("/gone/zsh", "darwin", {"zsh": "/path/zsh"}, set(), "/path/zsh", "zsh"),
        ("/gone/zsh", "linux", {}, {"/bin/bash"}, "/bin/bash", "bash"),
        (
            "/usr/local/bin/fish",
            "darwin",
            {"zsh": "/path/zsh", "bash": "/path/bash"},
            set(),
            "/path/zsh",
            "zsh",
        ),
        (
            "/usr/local/bin/fish",
            "linux",
            {"zsh": "/path/zsh", "bash": "/path/bash"},
            set(),
            "/path/bash",
            "bash",
        ),
        ("", "darwin", {}, {"/bin/zsh"}, "/bin/zsh", "zsh"),
        ("", "linux", {}, {"/usr/bin/bash"}, "/usr/bin/bash", "bash"),
        (None, "linux", {}, {"/bin/sh"}, "/bin/sh", "sh"),
        (
            "/usr/bin/pwsh",
            "linux",
            {},
            {"/usr/bin/pwsh"},
            "/usr/bin/pwsh",
            "powershell",
        ),
        (
            "powershell.exe",
            "linux",
            {"pwsh": "/path/pwsh"},
            set(),
            "/path/pwsh",
            "powershell",
        ),
        ("cmd", "linux", {"cmd": "/path/cmd"}, set(), "/path/cmd", "cmd"),
        ("/bin/fish", "linux", {}, set(), None, "none"),
    ],
)
def test_session_shell_derivation_is_pure(
    login: str | None,
    system: str,
    paths: dict[str, str],
    files: set[str],
    expected: str | None,
    kind: str,
) -> None:
    choice = check.derive_session_shell(login, system, paths, frozenset(files))
    assert (choice.executable, choice.kind) == (expected, kind)
    if login and "fish" in login and expected:
        assert "not one Codex runs" in choice.reason and "falls back" in choice.reason


@pytest.mark.parametrize(
    "login,reason",
    [
        ("/gone/zsh", "login shell zsh not found"),
        (None, "login shell unavailable"),
        ("/gone/fish", "login shell fish is not one Codex runs"),
    ],
)
def test_session_fallback_names_why_the_login_shell_is_unavailable(
    login: str | None, reason: str
) -> None:
    choice = check.derive_session_shell(login, "linux", {}, frozenset({"/bin/bash"}))
    assert choice.reason == reason + "; it falls back to bash"


def test_shell_environment_default_is_bin_sh_with_login_arguments() -> None:
    choice = check.derive_login_shell(None, {}, frozenset({"/bin/sh"}))
    assert (choice.executable, choice.kind) == ("/bin/sh", "sh")
    assert choice.reason == "SHELL unset; /bin/sh -lc"
    assert check.probe_argv(choice, "token") == (
        "/bin/sh",
        "-lc",
        'IFS= read -r line; if [ "$line" = token ]; then printf %s token; else printf %s token:stdin; fi',
    )


def test_fish_gets_a_probe_in_its_own_syntax_that_reads_stdin() -> None:
    # fish cannot parse sh's `if ... fi`, yet it runs today's script hooks,
    # so it gets the stdin check in fish's syntax (checked with fish 4.9.3)
    assert check.shell_kind("/usr/local/bin/fish") == "fish"
    choice = check.ShellChoice(
        "$SHELL -lc", "/usr/local/bin/fish", "fish", "SHELL=/usr/local/bin/fish"
    )
    assert check.probe_argv(choice, "token") == (
        "/usr/local/bin/fish",
        "-lc",
        'read -l line; if test "$line" = token; printf %s token; else; printf %s token:stdin; end',
    )


def test_a_shell_of_another_kind_gets_the_token_probe_alone() -> None:
    # a shell whose syntax doctor does not know: the token alone, stdin unchecked
    choice = check.ShellChoice(
        "$SHELL -lc", "/usr/local/bin/nu", "other", "SHELL=/usr/local/bin/nu"
    )
    assert check.probe_argv(choice, "token") == (
        "/usr/local/bin/nu",
        "-lc",
        "printf %s token",
    )


@pytest.mark.skipif(shutil.which("fish") is None, reason="fish is not installed")
@pytest.mark.parametrize(
    "config,clean", [("", True), ("read -l taken\n", False)], ids=["clean", "reads"]
)
def test_real_fish_shows_a_config_that_reads_stdin(
    tmp_path: Path, config: str, clean: bool
) -> None:
    fish = str(shutil.which("fish"))
    (tmp_path / "config" / "fish").mkdir(parents=True)
    (tmp_path / "config" / "fish" / "config.fish").write_text(config, encoding="utf-8")
    env = {
        "HOME": str(tmp_path),
        "XDG_CONFIG_HOME": str(tmp_path / "config"),
        "XDG_DATA_HOME": str(tmp_path / "data"),
        "PATH": os.environ["PATH"],
    }
    choice = check.ShellChoice("$SHELL -lc", fish, "fish", f"SHELL={fish}")
    token = "agent-hook-probe-0123456789abcdef"
    outcome = release.run(
        check.probe_argv(choice, token),
        env=env,
        timeout=10,
        input=(token + "\n").encode("utf-8"),
    )
    assert check.Shell(choice, (), outcome, token).clean is clean, outcome


def test_empty_shell_environment_has_no_executable_and_warns() -> None:
    choice = check.derive_login_shell("", {"": "/bin/sh"}, frozenset({"/bin/sh"}))
    assert choice == check.ShellChoice("$SHELL -lc", None, "none", "SHELL is empty")
    shell = check.Shell(choice, (), check.Outcome(exit_code=None), "token")
    assert _lines(check.Facts(shells=(shell,)), "codex-shell") == [
        ("WARN", "$SHELL -lc: no shell found; SHELL is empty")
    ]


def _shell(
    kind: str = "bash", *, route: str = "session", outcome: check.Outcome | None = None
) -> check.Shell:
    choice = check.ShellChoice(route, "/bin/" + kind, kind, "login shell " + kind)
    return check.Shell(
        choice,
        check.probe_argv(choice, "token"),
        outcome or check.Outcome(stdout="token", stdout_bytes=5),
        "token",
    )


@pytest.mark.parametrize("kind", ["bash", "zsh", "sh", "dash", "ksh"])
def test_clean_supported_shells_are_information(kind: str) -> None:
    assert all(
        level == "INFO"
        for level, _ in _lines(check.Facts(shells=(_shell(kind),)), "codex-shell")
    )


def test_wired_claude_home_does_not_raise_codex_shell_levels() -> None:
    shell = _shell(
        "other", outcome=check.Outcome(stdout="noise token", stdout_bytes=11)
    )
    facts = check.Facts(
        homes=(_wired(guard=True), check.Home("Codex", "codex", scripts=True)),
        shells=(shell,),
    )
    assert all(level == "INFO" for level, _ in _lines(facts, "codex-shell"))


@pytest.mark.parametrize("wired,level", [(False, "INFO"), (True, "WARN")])
@pytest.mark.parametrize(
    "kind,route", [("other", "$SHELL -lc"), ("powershell", "session")]
)
def test_non_posix_shell_syntax_level_changes_only_when_codex_is_wired(
    wired: bool, level: str, kind: str, route: str
) -> None:
    home = check.Home(
        "Codex",
        "codex",
        binaries=(check.Binary(PROGRAM, PROGRAM),) if wired else (),
        scripts=not wired,
    )
    lines = _lines(
        check.Facts(homes=(home,), shells=(_shell(kind, route=route),)), "codex-shell"
    )
    assert (
        level,
        f"{route}: /bin/{kind} ({kind}) cannot read the agent-hook sh launcher; 3d will not wire Codex under it",
    ) in lines


@pytest.mark.parametrize("guard,level", [(False, "INFO"), (True, "WARN")])
@pytest.mark.parametrize(
    "outcome,detail",
    [
        (
            check.Outcome(stdout="hellotoken", stdout_bytes=10),
            "5 bytes come before every hook's answer",
        ),
        (check.Outcome(stdout=""), "exits 0 before the command runs"),
        (check.Outcome(exit_code=1), "exits 1"),
        (check.Outcome(exit_code=None, timed_out=True), "timed out"),
    ],
)
def test_bad_startup_level_depends_on_a_guard_even_for_script_hooks(
    guard: bool, level: str, outcome: check.Outcome, detail: str
) -> None:
    facts = check.Facts(
        homes=(check.Home("Codex", "codex", scripts=True, guard=guard),),
        shells=(_shell(outcome=outcome),),
    )
    assert any(
        found_level == level and detail in found_detail
        for found_level, found_detail in _lines(facts, "codex-shell")
    )


def test_fish_startup_output_is_checked_before_wiring_too() -> None:
    shell = _shell(
        "fish",
        route="$SHELL -lc",
        outcome=check.Outcome(stdout="hi token", stdout_bytes=8),
    )
    facts = check.Facts(
        homes=(check.Home("Codex", "codex", scripts=True, guard=True),), shells=(shell,)
    )
    assert any(
        level == "WARN" and "3 bytes" in detail
        for level, detail in _lines(facts, "codex-shell")
    )


def test_powershell_arguments_and_start_failure_are_visible() -> None:
    shell = _shell(
        "powershell",
        outcome=check.Outcome(exit_code=None, reason="cannot start: denied"),
    )
    assert shell.argv == (
        "/bin/powershell",
        "-NoProfile",
        "-Command",
        "$l = [Console]::In.ReadLine(); if ($l -ceq 'token') { [Console]::Out.Write('token') } else { [Console]::Out.Write('token:stdin') }",
    )
    assert _lines(check.Facts(shells=(shell,)), "inspect")[0][0] == "WARN"


def test_no_shell_is_a_warning_and_windows_has_no_shell_lines() -> None:
    choice = check.derive_session_shell(None, "linux", {}, frozenset())
    shell = check.Shell(
        choice, (), check.Outcome(exit_code=None, reason="missing"), "token"
    )
    assert _lines(check.Facts(shells=(shell,)), "codex-shell")[0][0] == "WARN"
    assert _lines(check.Facts(shells=(shell,), system="windows"), "codex-shell") == []


def _executable(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8", newline="\n")
    path.chmod(0o755)
    return path


def _fake_shell(path: Path, mode: str = "clean") -> Path:
    return _executable(
        path,
        f"""import re, sys, time
mode = {mode!r}
if mode == 'timeout': time.sleep(5)
if mode == 'exit1': sys.exit(1)
if mode == 'exit0': sys.exit(0)
if mode == 'run':
    import os
    os.execv('/bin/sh', ['/bin/sh', '-c', sys.argv[-1]])
if mode == 'stdin':
    sys.stdin.read()
    import subprocess
    sys.exit(subprocess.call(['/bin/sh', '-c', sys.argv[-1]]))
token = re.search(r'agent-hook-probe-[a-f0-9]{{16}}', sys.argv[-1])[0]
sys.stdout.write(('日本' if mode == 'output' else '') + token)
""",
    )


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    if os.name == "nt":
        pytest.skip("executable fixtures use POSIX shebangs")
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, value in {
        "HOME": home,
        "CODEX_HOME": home / "custom-codex",
        "XDG_STATE_HOME": tmp_path / "state",
        "XDG_DATA_HOME": tmp_path / "data",
        "PATH": bin_dir,
        "SHELL": bin_dir / "zsh",
    }.items():
        monkeypatch.setenv(name, str(value))
    for name in ("BASH_ENV", "ENV", "ZDOTDIR", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(name, raising=False)
    shell = _fake_shell(bin_dir / "zsh")
    monkeypatch.setattr(codex_shells, "_login_shell", lambda: str(shell), raising=False)
    return home


@pytest.mark.parametrize("guard,level", [(False, "INFO"), (True, "WARN")])
def test_probe_detects_startup_consuming_hook_stdin(
    isolated: Path, guard: bool, level: str
) -> None:
    _fake_shell(Path(os.environ["SHELL"]), "stdin")
    shells = check.gather_shells(sys.platform, dict(os.environ))
    facts = check.Facts(
        homes=(check.Home("Codex", "codex", scripts=True, guard=guard),), shells=shells
    )
    assert all(not shell.clean for shell in shells)
    assert all(shell.outcome.stdout == shell.token + ":stdin" for shell in shells)
    details = [
        line for line in _lines(facts, "codex-shell") if "loses its input" in line[1]
    ]
    assert len(details) == 2
    assert all(found_level == level for found_level, _ in details)
    assert all(
        "a startup file reads stdin, so each hook loses its input" in detail
        for _, detail in details
    )


def _fragment(binary: Path, harness: str) -> dict:
    # Exercise the real render shape, including Codex's quoting and fallback.
    corpus = ROOT / "tools/agent-hooks/internal/rendercorpus/render.jsonl"
    case = f"render/{harness}/darwin/{'sh' if harness == 'codex' else 'default'}/stable/plain"
    row = next(
        json.loads(raw)
        for raw in corpus.read_text(encoding="utf-8").splitlines()
        if json.loads(raw)["case"] == case
    )
    old = row["args"][row["args"].index("--binary") + 1]
    replacement = (
        str(binary).replace("'", "'\\''") if harness == "codex" else str(binary)
    )
    text = row["stdout"].replace(old, json.dumps(replacement, ensure_ascii=False)[1:-1])
    return json.loads(text)


STABLE = re.compile(r".*/dotfiles/agent-hooks/current/[a-z0-9-]+/agent-hook")
# A path no test uses, which the fake agent-hook replaces with its --binary.
MARK = "/mark/dotfiles/agent-hooks/current/mark/agent-hook"


def _registered(home: Path, harness: str) -> Path:
    """The stable link _register writes into home's registration."""
    key = "codex" if harness == "codex" else home.name.removeprefix(".claude-")
    return (
        home.parent
        / "data/dotfiles/agent-hooks/current"
        / key.strip(".")
        / "agent-hook"
    )


def _register(home: Path, harness: str, binary: Path) -> dict:
    """Register binary in home as sync wires it: through the home's stable
    link, current/<key>/agent-hook, unless binary is such a link already.
    For Codex that is agent-hook's guards only (G, PR 3d.2)."""
    from agent_hook_codex_plan import codex_guards

    home.mkdir(parents=True, exist_ok=True)
    if not STABLE.fullmatch(str(binary)):
        link = _registered(home, harness)
        link.parent.mkdir(parents=True, exist_ok=True)
        if not link.is_symlink():
            link.symlink_to(binary)
        binary = link
    doc = _fragment(binary, harness)
    if harness == "codex":
        doc = {"hooks": codex_guards(doc["hooks"])}
    (home / ("hooks.json" if harness == "codex" else "settings.json")).write_text(
        json.dumps(doc), encoding="utf-8"
    )
    return doc


def _fake_agent(
    home: Path, *, render: str = "ok", log: str = "ok", name: str = "abcdef0123456789"
) -> Path:
    binary = (
        home.parent / "a b'$" / "dotfiles/agent-hooks/releases" / name / "agent-hook"
    )
    # Like agent-hook render, it writes the --binary it is given, quoted for
    # the harness's form.
    fragments = {
        harness: _fragment(Path(MARK), harness) for harness in ("claude", "codex")
    }
    return _executable(
        binary,
        f"""import json, os, sys, time
with open(os.environ['HOME'] + '/calls.jsonl', 'a', encoding='utf-8') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
mode = {render!r} if sys.argv[1] == 'render' else {log!r}
if mode == 'timeout': time.sleep(5)
if mode == 'exit': sys.exit(7)
if mode == 'bad': print('not json'); sys.exit(0)
if mode == 'shape': print('{{}}'); sys.exit(0)
if mode == 'oversized': print('x' * 65537); sys.exit(0)
if sys.argv[1] == 'render':
    harness = sys.argv[sys.argv.index('--harness') + 1]
    given = sys.argv[sys.argv.index('--binary') + 1]
    quoted = given.replace("'", "'\\''") if harness == 'codex' else given
    text = json.dumps({fragments!r}[harness], ensure_ascii=False)
    print(text.replace({MARK!r}, json.dumps(quoted, ensure_ascii=False)[1:-1]))
else:
    print(json.dumps({{'days': 1, 'lines': 8, 'unreadable': 1, 'errors': {{'hook.failed': 2}}, 'mismatches': {{}}}}))
""",
    )


def _fake_go(
    home: Path,
    code: int,
    *,
    mise: bool = True,
    build_fails: bool = False,
    stderr: str = "",
) -> Path:
    bin_dir = Path(os.environ["PATH"])
    chosen = home.parent / "chosen-go/go" if mise else bin_dir / "go"
    record = home / "release-calls.jsonl"
    recorder = f"""import json, os, shutil, sys
with open({str(record)!r}, 'a', encoding='utf-8') as stream:
    stream.write(json.dumps({{'argv': sys.argv[1:], 'cwd': os.getcwd(), 'go': shutil.which('go')}}) + '\\n')
"""
    checker = f"#!{sys.executable}\n{recorder}\nsys.stderr.write({stderr!r})\nsys.exit({code})\n"
    go = _executable(
        chosen,
        recorder
        + (
            "\nsys.exit(1)"
            if build_fails
            else f"""
from pathlib import Path
target = Path(sys.argv[sys.argv.index('-o') + 1])
target.write_text({checker!r}, encoding='utf-8')
target.chmod(0o755)
"""
        ),
    )
    if mise:
        _executable(bin_dir / "go", "raise SystemExit('wrong Go')")
        _executable(
            bin_dir / "mise",
            f"import sys\nassert sys.argv[1:] == ['which', 'go']\nprint({str(go)!r})",
        )
    return go


@pytest.mark.parametrize("call", ["render", "log"])
def test_oversized_inspection_reports_the_limit_before_parsing(
    isolated: Path, call: str
) -> None:
    binary = _fake_agent(isolated, render="oversized", log="oversized")
    inspection = (
        check._render(str(binary), "claude", sys.platform)
        if call == "render"
        else check._log(str(binary))
    )
    assert inspection.outcome.reason == "output exceeds 65536 bytes"
    assert not inspection.outcome.ok


@pytest.mark.parametrize("code", [0, 1, 2, 3])
@pytest.mark.parametrize("mise", [True, False])
def test_gather_renders_each_home_but_builds_and_checks_each_release_once(
    isolated: Path, code: int, mise: bool
) -> None:
    binary = _fake_agent(isolated)
    expected = _register(isolated / ".claude", "claude", binary)
    _register(Path(os.environ["CODEX_HOME"]), "codex", binary)
    go = _fake_go(isolated, code, mise=mise)
    facts = check.gather(isolated)
    assert [home.harness for home in facts.homes] == ["claude", "codex"]
    assert facts.homes[0].managed == expected["hooks"]
    for home in facts.homes:
        rendered = home.binaries[0].render
        assert rendered is not None and rendered.outcome.ok, rendered
    assert facts.homes[1].guard
    assert len(facts.releases) == 1 and facts.releases[0].outcome.exit_code == code
    summary = facts.logs[0].summary
    assert summary is not None and summary.lines == 8
    assert _lines(facts, "registered") == []
    calls = [
        json.loads(line)
        for line in (isolated / "release-calls.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(calls) == 2
    assert all(
        call["cwd"] == str(ROOT / "tools/agent-hooks") and call["go"] == str(go)
        for call in calls
    )
    assert calls[0]["argv"] == ["build", "-o", calls[0]["argv"][2], "./cmd/hookrelease"]
    assert calls[1]["argv"] == ["check", str(binary.resolve())]
    calls = [
        json.loads(line)
        for line in (isolated / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert calls[0] == [
        "render",
        "--harness",
        "claude",
        "--os",
        sys.platform,
        "--binary",
        str(_registered(isolated / ".claude", "claude")),
    ]
    assert calls[1] == [
        "render",
        "--harness",
        "codex",
        "--os",
        sys.platform,
        "--shell",
        "sh",
        "--binary",
        str(_registered(Path(os.environ["CODEX_HOME"]), "codex")),
    ]
    assert calls[2] == ["log", "--summary", "--days", "1"]


def test_unwired_gather_never_builds_or_reads_a_log(isolated: Path) -> None:
    home = isolated / ".claude-work-a"
    home.mkdir()
    doc = {
        "hooks": {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'bash "{home}/hooks/block-prohibited-files.sh"',
                        }
                    ]
                }
            ]
        }
    }
    (home / "settings.json").write_text(json.dumps(doc), encoding="utf-8")
    _fake_go(isolated, 0)
    facts = check.gather(isolated)
    assert facts.homes[0].scripts
    assert not facts.releases and not facts.logs
    assert not (isolated / "release-calls.jsonl").exists()
    assert not Path(os.environ["XDG_STATE_HOME"]).exists()


def test_gather_stops_after_the_first_binary_answers_the_log(isolated: Path) -> None:
    first = _fake_agent(isolated)
    other = _fake_agent(isolated, name="fedcba9876543210", log="exit")
    _register(isolated / ".claude", "claude", first)
    _register(isolated / ".claude-work-a", "claude", other)
    facts = check.gather(isolated)
    assert len(facts.logs) == 1
    assert facts.logs[0].binary == str(_registered(isolated / ".claude", "claude"))
    assert facts.logs[0].outcome.ok
    calls = [
        json.loads(line)
        for line in (isolated / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [call for call in calls if call[0] == "log"] == [
        ["log", "--summary", "--days", "1"]
    ]


@pytest.mark.parametrize("custom", [False, True])
def test_absent_codex_home_has_no_home_lines_or_shell_probes(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, custom: bool
) -> None:
    if not custom:
        monkeypatch.delenv("CODEX_HOME")
    shell = Path(os.environ["SHELL"])
    _executable(shell, "raise SystemExit('shell probe must not run')")
    facts = check.gather(isolated)
    assert not facts.homes and not facts.shells
    # doctor.sh reads exit 0 with no line as a run that failed
    assert check.report(facts) == [
        ("INFO", "agent-hook-wiring", "no Claude or Codex home found; nothing to check")
    ]


def test_the_checker_prints_one_line_where_there_is_no_agent_home(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # given a machine with no Claude home and no Codex home
    monkeypatch.delenv("CODEX_HOME")
    # when doctor runs the checker, then it prints one INFO line and exits 0
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "agent_hook_doctor.py")],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == [
        "INFO agent-hook-wiring - no Claude or Codex home found; nothing to check"
    ]


def test_gather_feeds_each_probe_its_token_on_stdin(isolated: Path) -> None:
    # given a shell that runs the probe for real, which prints the token only
    # after it reads that token from stdin
    _fake_shell(Path(os.environ["SHELL"]), "run")
    # when doctor probes Codex's two shells, then both are clean
    shells = check.gather_shells(sys.platform, dict(os.environ))
    assert len(shells) == 2
    assert all(shell.clean for shell in shells), shells


@pytest.mark.parametrize("custom", [False, True])
def test_existing_codex_home_without_hooks_keeps_wiring_and_shell_facts(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, custom: bool
) -> None:
    if not custom:
        monkeypatch.delenv("CODEX_HOME")
    codex = Path(os.environ.get("CODEX_HOME", isolated / ".codex"))
    codex.mkdir()
    facts = check.gather(isolated)
    assert facts.homes == (check.Home("Codex", "codex", key="codex"),)
    assert len(facts.shells) == 2
    assert _lines(facts, "wiring") == [
        ("INFO", "no dotfiles hook registered in Codex (not new with agent-hook)")
    ]


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("exit", "exits 7"),
        ("timeout", "timed out"),
        ("bad", "does not parse"),
        ("shape", "does not parse"),
    ],
)
def test_failed_render_and_log_leave_other_homes_inspectable(
    isolated: Path, monkeypatch: pytest.MonkeyPatch, mode: str, reason: str
) -> None:
    binary = _fake_agent(isolated, render=mode, log=mode)
    _register(isolated / ".claude", "claude", binary)
    other = _fake_agent(isolated, name="fedcba9876543210")
    _register(isolated / ".claude-work-a", "claude", other)
    _fake_go(isolated, 0)
    monkeypatch.setattr(check, "PROGRAM_TIMEOUT", 1)
    facts = check.gather(isolated)
    rendered, other_render = (home.binaries[0].render for home in facts.homes[:2])
    assert rendered is not None and reason in (rendered.outcome.reason or "")
    assert other_render is not None and other_render.outcome.ok
    assert len(facts.logs) == 2 and not facts.logs[0].outcome.ok
    summary = facts.logs[1].summary
    assert summary is not None and summary.lines == 8
    assert len(_lines(facts, "inspect")) == 2


@pytest.mark.parametrize("kind", ["missing", "directory", "symlink-loop"])
def test_unresolved_binary_has_one_warning_and_no_render_or_log(
    isolated: Path,
    kind: str,
) -> None:
    binary = isolated / "dotfiles/agent-hooks/releases/abcdef0123456789/agent-hook"
    if kind == "directory":
        binary.mkdir(parents=True)
    elif kind == "symlink-loop":
        binary.parent.mkdir(parents=True)
        binary.symlink_to(binary)
    _register(isolated / ".claude", "claude", binary)
    link = _registered(isolated / ".claude", "claude")
    facts = check.gather(isolated)
    binary_lines = [line for line in check.report(facts) if str(link) in line[2]]
    assert len(binary_lines) == 1 and binary_lines[0][:2] == (
        "WARN",
        "agent-hook-binary",
    )
    assert facts.homes[0].binaries[0].render is None
    assert not facts.logs
    assert _lines(facts, "inspect") == []
    assert _lines(facts, "log") == []


def test_existing_non_release_file_still_renders_and_reads_its_log(
    isolated: Path,
) -> None:
    binary = _fake_agent(isolated)
    loose = isolated / "agent-hook-copy"
    binary.rename(loose)
    binary.symlink_to(loose)
    _register(isolated / ".claude", "claude", binary)
    facts = check.gather(isolated)
    found = facts.homes[0].binaries[0]
    assert found.release is None and found.problem
    assert found.render is not None and found.render.outcome.ok
    assert len(facts.logs) == 1 and facts.logs[0].outcome.ok


@pytest.mark.parametrize("build_fails", [False, True])
def test_missing_go_or_a_failed_build_is_cannot_check(
    isolated: Path, build_fails: bool
) -> None:
    binary = _fake_agent(isolated)
    _register(isolated / ".claude", "claude", binary)
    if build_fails:
        _fake_go(isolated, 0, build_fails=True)
    facts = check.gather(isolated)
    assert _lines(facts, "fresh")[0][0] == "INFO"
    assert "cannot check here" in _lines(facts, "fresh")[0][1]


def test_mise_exit_one_is_informational(isolated: Path) -> None:
    binary = _fake_agent(isolated)
    _register(isolated / ".claude", "claude", binary)
    _executable(Path(os.environ["PATH"]) / "mise", "raise SystemExit(1)")
    facts = check.gather(isolated)
    assert _lines(facts, "fresh") == [
        ("INFO", f"release {binary}: cannot check here: mise which go: exits 1")
    ]


@pytest.mark.parametrize(
    "code,stderr,level,message",
    [
        (
            1,
            "release IDs: old != new",
            "WARN",
            "is not what this checkout builds ({stderr}); run just sync-agents",
        ),
        (
            3,
            "SHA-256: aaa != bbb",
            "WARN",
            "differs from the build its release ID names ({stderr}); sync never replaces a release in place: remove {directory} and run just sync-agents",
        ),
        (2, "cannot read release", "INFO", ": cannot check here: exits 2: {stderr}"),
    ],
)
def test_checker_diagnostics_and_recovery_are_preserved(
    isolated: Path, code: int, stderr: str, level: str, message: str
) -> None:
    binary = _fake_agent(isolated)
    _fake_go(isolated, code, stderr=stderr + "\n")
    releases = check._release_checks((str(binary),), dict(os.environ))
    separator = "" if message.startswith(":") else " "
    assert _lines(check.Facts(releases=releases), "fresh") == [
        (
            level,
            f"release {binary}{separator}"
            + message.format(stderr=stderr, directory=binary.parent),
        )
    ]


@pytest.mark.parametrize(
    "mode,clean,code",
    [
        ("clean", True, 0),
        ("output", False, 0),
        ("exit1", False, 1),
        ("exit0", False, 0),
        ("timeout", False, None),
    ],
)
def test_gather_runs_both_shell_paths_with_unique_tokens(
    isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    clean: bool,
    code: int | None,
) -> None:
    Path(os.environ["CODEX_HOME"]).mkdir()
    _fake_shell(Path(os.environ["SHELL"]), mode)
    monkeypatch.setattr(codex_shells, "SHELL_TIMEOUT", 1)
    facts = check.gather(isolated)
    assert len(facts.shells) == 2
    assert len({shell.token for shell in facts.shells}) == 2
    assert all(
        re.fullmatch(r"agent-hook-probe-[a-f0-9]{16}", shell.token)
        for shell in facts.shells
    )
    assert all(
        shell.clean == clean and shell.outcome.exit_code == code
        for shell in facts.shells
    )
    assert facts.shells[0].argv[1] == "-c" and facts.shells[1].argv[1] == "-lc"
    if mode == "output":
        assert all(
            shell.outcome.stdout_bytes == len(shell.token) + 6 for shell in facts.shells
        )


def test_guard_detection_uses_managed_scripts_and_ignores_third_party_blocks(
    isolated: Path,
) -> None:
    codex = Path(os.environ["CODEX_HOME"])
    codex.mkdir()
    doc = {
        "hooks": {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'bash "{codex}/hooks/block-prohibited-files-codex.sh"',
                        }
                    ]
                },
                {"hooks": [{"type": "command", "command": "echo third-party"}]},
            ]
        }
    }
    (codex / "hooks.json").write_text(json.dumps(doc), encoding="utf-8")
    facts = check.gather(isolated)
    assert facts.homes[0].guard and facts.homes[0].scripts
    assert len(facts.homes[0].managed["PreToolUse"]) == 1


def test_post_tool_guard_does_not_count_as_a_pre_tool_guard(isolated: Path) -> None:
    codex = Path(os.environ["CODEX_HOME"])
    codex.mkdir()
    hook = {
        "type": "command",
        "command": f'bash "{codex}/hooks/block-prohibited-files-codex.sh"',
    }
    assert check._has_guard(hook)
    (codex / "hooks.json").write_text(
        json.dumps({"hooks": {"PostToolUse": [{"hooks": [hook]}]}}), encoding="utf-8"
    )
    home = check.gather(isolated).homes[0]
    assert home.managed and home.scripts
    assert not home.guard


def test_bad_registration_is_an_inspection_failure_and_does_not_stop_gather(
    isolated: Path,
) -> None:
    Path(os.environ["CODEX_HOME"]).mkdir()
    claude = isolated / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text("{broken", encoding="utf-8")
    facts = check.gather(isolated)
    assert len(facts.homes) == 2 and len(facts.shells) == 2
    assert _lines(facts, "inspect")[0][0] == "WARN"


def test_the_go_version_probe_runs_in_the_temporary_home(
    isolated: Path, tmp_path: Path
) -> None:
    # Go can open its telemetry counters under the user's config directory,
    # even for `go env`: the probe must run with the test's temporary home.
    seen = tmp_path / "seen.json"
    names = ("HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "GOCACHE", "GOTOOLCHAIN")
    fake = _executable(
        tmp_path / "fake-go" / "go",
        "import json, os; "
        f"json.dump({{n: os.environ.get(n) for n in {names!r}}}, "
        f"open({str(seen)!r}, 'w', encoding='utf-8')); "
        "print('go1.999.0')",
    )
    assert why_go_cannot_build_the_module(str(fake), isolated) == ""
    env = json.loads(seen.read_text(encoding="utf-8"))
    assert env.pop("GOTOOLCHAIN") == "local"
    assert all(value and value.startswith(str(isolated)) for value in env.values()), env


def test_real_hookrelease_rebuilds_a_real_temporary_release(
    isolated: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    why = why_go_cannot_build_the_module(REAL_GO, isolated)
    if why:
        if STRICT_GO:
            pytest.fail(why)
        pytest.skip(why)
    # Every Go run stays in the temporary home, telemetry included.
    monkeypatch.setenv("XDG_CONFIG_HOME", str(isolated / ".config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(isolated / ".cache"))
    assert REAL_GO is not None
    bin_dir = Path(os.environ["PATH"])
    (bin_dir / "go").symlink_to(REAL_GO)
    monkeypatch.setenv("GOCACHE", str(isolated / "go-cache"))
    monkeypatch.setenv("GOPATH", str(isolated / "go"))
    monkeypatch.setenv(
        "GOMODCACHE", os.environ.get("GOMODCACHE", str(isolated / "go-mod"))
    )
    monkeypatch.setenv("GOTOOLCHAIN", "local")
    module = ROOT / "tools/agent-hooks"
    helper = isolated / "hookrelease"
    built = subprocess.run(
        [REAL_GO, "build", "-o", str(helper), "./cmd/hookrelease"],
        cwd=module,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    assert built.returncode == 0, built.stderr
    release = subprocess.run(
        [
            str(helper),
            "build",
            "--into",
            str(isolated / "dotfiles/agent-hooks/releases"),
        ],
        cwd=module,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    assert release.returncode == 0, release.stderr
    path = Path(release.stdout.strip())
    assert path.is_file() and path.stat().st_size > 0
    checked = check._release_checks((str(path),), dict(os.environ))
    assert checked[0].outcome.ok, checked[0].outcome


@pytest.mark.skipif(REAL_BASH is None, reason="Bash is missing")
@pytest.mark.parametrize(
    "mode,counts",
    [
        ("lines", "counts 1 1 1 1"),
        ("crash", "counts 0 1 0 0"),
        ("silent", "counts 0 1 0 0"),
        ("missing", "counts 0 1 0 0"),
    ],
)
def test_doctor_section_counts_lines_and_warns_when_the_checker_did_not_run(
    isolated: Path, mode: str, counts: str
) -> None:
    assert REAL_BASH is not None
    text = (ROOT / "scripts/doctor.sh").read_text(encoding="utf-8")
    block = re.search(r"(?ms)^# Agent-hook:.*?^fi$", text)
    assert block is not None
    assert (
        text.index("# AI tooling:") < block.start() < text.index("# Canonical Ollama")
    )
    bin_dir = Path(os.environ["PATH"])
    (bin_dir / "dirname").symlink_to("/usr/bin/dirname")
    (bin_dir / "tail").symlink_to("/usr/bin/tail")
    if mode != "missing":
        _executable(
            bin_dir / "uv",
            f"""import sys
assert sys.argv[1:3] == ['run', '--frozen']
assert sys.argv[3].endswith('/agent_hook_doctor.py')
mode = {mode!r}
if mode == 'lines': print('OK   one - ok\\nWARN two - warn\\nERR  three - err\\nINFO four - info')
if mode == 'crash': print('failed', file=sys.stderr); sys.exit(2)
""",
        )
    script = isolated / "doctor.sh"
    script.write_text(
        """set -euo pipefail
ok=0; warn=0; err=0; info=0
has() { command -v "$1" >/dev/null 2>&1; }
log_warn() { warn=$((warn+1)); printf 'WARN %s - %s\\n' "$1" "$2"; }
"""
        + block[0]
        + '\nprintf "counts %s %s %s %s\\n" "$ok" "$warn" "$err" "$info"\n',
        encoding="utf-8",
    )
    done = subprocess.run(
        [REAL_BASH, str(script)],
        env=dict(os.environ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert counts in done.stdout
    assert ("WARN agent-hook -" in done.stdout) == (mode != "lines")


@pytest.mark.parametrize(
    "document", [[], ["hooks"], None, {"hooks": []}, {"hooks": {"PreToolUse": [None]}}]
)
def test_invalid_registration_shapes_are_inspection_failures(
    isolated: Path, document: object
) -> None:
    home = isolated / ".claude"
    home.mkdir()
    (home / "settings.json").write_text(json.dumps(document), encoding="utf-8")
    assert _lines(check.gather(isolated), "inspect")


def test_a_timeout_returns_even_when_a_child_inherits_output_pipes(
    isolated: Path,
) -> None:
    program = _executable(
        isolated / "spawn",
        f"""import subprocess, time
subprocess.Popen([{sys.executable!r}, '-c', 'import time; time.sleep(5)'])
time.sleep(5)
""",
    )
    started = time.monotonic()
    outcome = release.run([str(program)], timeout=0.5)
    assert outcome.timed_out
    assert time.monotonic() - started < 3, (
        "descendant held the output pipe past the timeout"
    )


def test_two_stable_links_to_one_release_are_checked_once(isolated: Path) -> None:
    binary = _fake_agent(isolated)
    for name, harness in (("claude", "claude"), ("codex", "codex")):
        link = isolated / "dotfiles/agent-hooks/current" / name / "agent-hook"
        link.parent.mkdir(parents=True)
        link.symlink_to(binary)
        home = (
            isolated / ".claude"
            if harness == "claude"
            else Path(os.environ["CODEX_HOME"])
        )
        _register(home, harness, link)
    _fake_go(isolated, 0)
    facts = check.gather(isolated)
    assert len(facts.releases) == 1
    assert facts.releases[0].path == str(binary.resolve())
    assert len({home.binaries[0].path for home in facts.homes}) == 2


@pytest.mark.parametrize("name", ["abcdef012345", "ABCDEF0123456789"])
def test_a_link_to_a_directory_hookrelease_never_makes_is_not_a_release(
    isolated: Path, name: str
) -> None:
    # given a link to releases/<name>/agent-hook, where hookrelease names
    # each release by 16 lowercase hex digits
    _register(isolated / ".claude", "claude", _fake_agent(isolated, name=name))
    # when doctor gathers, then the binary is no release
    facts = check.gather(isolated)
    assert "no release" in _lines(facts, "binary")[0][1]
    assert not facts.releases


def test_a_current_path_resolving_outside_releases_is_not_a_release(
    isolated: Path,
) -> None:
    loose = _fake_agent(isolated)
    moved = loose.rename(isolated / "loose-program")
    loose.symlink_to(moved)
    _register(isolated / ".claude", "claude", loose)
    facts = check.gather(isolated)
    assert "no release" in _lines(facts, "binary")[0][1]
    assert not facts.releases


@pytest.mark.parametrize("bad_loss", [False, True])
def test_render_loss_json_lines_are_parsed_or_reported_as_failed(
    isolated: Path, bad_loss: bool
) -> None:
    loss = {"level": "pending", "tool": "Example", "reason": "no payload"}
    binary = _executable(
        isolated / "render",
        f"""import sys
print({json.dumps(FRAGMENT)!r})
print({("bad json" if bad_loss else json.dumps(loss))!r}, file=sys.stderr)
""",
    )
    rendered = check._render(str(binary), "claude", sys.platform)
    assert rendered.outcome.ok == (not bad_loss)
    assert rendered.losses == (() if bad_loss else (loss,))


def test_guard_detection_tolerates_a_null_args_member_in_old_script_hooks(
    isolated: Path,
) -> None:
    home = isolated / ".claude"
    home.mkdir()
    doc = {
        "hooks": {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": f'bash "{home}/hooks/block-secrets.sh"',
                            "args": None,
                        }
                    ]
                }
            ]
        }
    }
    (home / "settings.json").write_text(json.dumps(doc), encoding="utf-8")
    facts = check.gather(isolated)
    assert facts.homes[0].guard


# ---- Guards against drift between doctor and what it reads ----


def test_the_log_codes_doctor_accepts_are_the_binarys() -> None:
    """The summary names only the binary's fixed codes (and "other"): a code
    added in Go without this side would read as "output does not parse"."""
    logline = ROOT / "tools/agent-hooks/internal/logline/line.go"
    outcome = ROOT / "tools/agent-hooks/internal/ir/outcome.go"
    line_go = logline.read_text(encoding="utf-8")
    # Some codes are the ir package's rule names, given by reference.
    rules = dict(
        re.findall(
            r'\b(Rule[A-Za-z]+)\s*=\s*"([^"]+)"', outcome.read_text(encoding="utf-8")
        )
    )

    def values(prefix: str) -> set[str]:
        found = re.findall(
            rf'\b{prefix}[A-Za-z]+\s*=\s*(?:"([^"]+)"|ir\.(Rule[A-Za-z]+))', line_go
        )
        return {literal or rules[name] for literal, name in found}

    errors = values("Err")
    mismatches = values("Mismatch")
    assert errors, "no error code found in line.go"
    assert mismatches, "no mismatch found in line.go"
    assert check.ERROR_CODES == errors | {"other"}
    assert check.MISMATCHES == mismatches | {"other"}


def test_every_claude_home_doctor_reads_is_one_sync_knows() -> None:
    """gather() looks each home up among sync's agents by its directory name."""
    import claude_homes
    import sync_agents

    agents = {a.directory.name for a in sync_agents.AGENTS if a.receives_hooks}
    assert set(claude_homes.NAMES) <= agents


# ---- PR 3d.1: the uninstall mark and unfinished changes ----


def test_an_uninstalled_home_says_how_to_wire_it_again() -> None:
    # given a home uninstalled with just agent-hooks-uninstall, running the scripts
    home = check.Home(".claude-work-a", "claude", scripts=True, key="work-a")
    facts = check.Facts(homes=(home,), marks=frozenset({"work-a"}))
    # then one INFO line says so, and the home is not among the unwired ones
    assert _lines(facts, "wiring") == [
        (
            "INFO",
            (
                "agent-hook uninstalled in work-a: today's scripts run; "
                "just agent-hooks-install work-a wires it again"
            ),
        )
    ]


def test_a_mark_beside_a_wired_registration_is_a_warning() -> None:
    # given an uninstall mark, yet the home's managed blocks run the binary
    facts = check.Facts(
        homes=(replace(_wired(), key="claude"),), marks=frozenset({"claude"})
    )
    # then it is a WARN naming both ways out
    assert _lines(facts, "wiring") == [
        (
            "WARN",
            (
                "claude: uninstalled, yet wired; run just agent-hooks-uninstall claude "
                "or just agent-hooks-install claude"
            ),
        )
    ]


def test_an_unfinished_change_is_a_warning() -> None:
    facts = check.Facts(journals=("switch-work-b.json",))
    assert _lines(facts, "wiring") == [
        (
            "WARN",
            (
                "a registration change is unfinished (switch-work-b.json); "
                "run just sync-agents to finish or restore it"
            ),
        )
    ]


def test_gather_reads_the_marks_and_journals_sync_writes(isolated: Path) -> None:
    import agent_hook_wiring as wiring

    # given a mark and a journal where sync writes them
    roots = wiring.Roots.from_env(dict(os.environ))
    roots.mark("work-a").parent.mkdir(parents=True)
    roots.mark("work-a").write_bytes(b"")
    roots.journal("claude").write_text("{}", encoding="utf-8")
    (isolated / ".claude-work-a").mkdir()
    # when doctor gathers, then it has both, and each home its key
    facts = check.gather(isolated)
    assert facts.marks == frozenset({"work-a"})
    assert facts.journals == ("switch-claude.json",)
    assert [home.key for home in facts.homes if home.harness == "claude"] == ["work-a"]


# ---- PR 3d.2: the Codex home, its scripts beside agent-hook's guards ----

_CODEX_CORPUS = next(
    case
    for case in map(
        json.loads,
        (ROOT / "tools/agent-hooks/internal/rendercorpus/render.jsonl")
        .read_text(encoding="utf-8")
        .splitlines(),
    )
    if case["case"] == "render/codex/darwin/sh/stable/plain"
)
CODEX_RENDER = json.loads(_CODEX_CORPUS["stdout"])
CODEX_LINK = _CODEX_CORPUS["args"][_CODEX_CORPUS["args"].index("--binary") + 1]
SCRIPT_GROUP = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "command": 'bash "/h/.codex/hooks/guard-codex.sh" block-prohibited-commands.sh',
        }
    ],
}


def _codex_wired(guards: list[dict]) -> check.Home:
    """A Codex home as PR 3d.2 leaves it: a script group, then G."""
    return check.Home(
        "Codex",
        "codex",
        scripts=True,
        managed={"PreToolUse": [SCRIPT_GROUP, *guards]},
        binaries=(
            check.Binary(
                CODEX_LINK, PROGRAM, check.Render(check.Outcome(), CODEX_RENDER)
            ),
        ),
        key="codex",
    )


def _guards() -> list[dict]:
    pre = CODEX_RENDER["hooks"]["PreToolUse"]
    return [pre[0], pre[1]]  # files-guard and secrets-guard, then command-guard


def test_a_codex_home_with_scripts_beside_its_guards_is_not_mixed() -> None:
    facts = check.Facts(homes=(_codex_wired(_guards()),))
    assert _lines(facts, "wiring") == []
    # and only G is compared with the render: its rtk and formatter groups
    # wait for PR 5, and the scripts are sync's own
    assert _lines(facts, "registered") == []


def test_a_codex_guard_that_differs_from_the_render_is_a_warning() -> None:
    first, second = _guards()
    changed = {**second, "hooks": [{**second["hooks"][0], "timeout": 99}]}
    facts = check.Facts(homes=(_codex_wired([first, changed]),))
    lines = _lines(facts, "registered")
    assert len(lines) == 1 and lines[0][0] == "WARN"
    assert "Codex: managed blocks differ from render at PreToolUse[" in lines[0][1]
    assert lines[0][1].endswith(".hooks[0].timeout; run just sync-agents")


def test_the_order_of_codex_guard_groups_is_not_a_difference() -> None:
    # Codex runs every matching handler, and keys trust by position, so sync
    # leaves an unchanged group where it is, in whatever order that leaves G
    first, second = _guards()
    facts = check.Facts(homes=(_codex_wired([second, first]),))
    assert _lines(facts, "registered") == []


def test_a_claude_home_with_scripts_and_a_binary_is_still_mixed() -> None:
    home = _wired(scripts=True)
    assert _lines(check.Facts(homes=(home,)), "wiring")[0][0] == "WARN"


def test_gather_reads_the_codex_mark(isolated: Path) -> None:
    import agent_hook_wiring as wiring

    roots = wiring.Roots.from_env(dict(os.environ))
    roots.mark("codex").parent.mkdir(parents=True)
    roots.mark("codex").write_bytes(b"")
    (isolated / "custom-codex").mkdir()
    facts = check.gather(isolated)
    assert facts.marks == frozenset({"codex"})
