"""Unit tests for the shared plugin scope hook (plugins/_shared/check-scope.sh).

The canonical script lives in plugins/_shared/ and is copied into each
auto-loop plugin (autoresearch / autodesign / autoreview) by
`just sync-plugin-scope-hook` — installed plugins only ship their own
directory, so the per-plugin copies are distribution artifacts that cannot
reference a shared file at runtime. These tests gate drift between the
copies and the canonical, verify the sync recipe actually propagates, and
pin the hook's scope decision: exit 0 with empty stdout allows the edit;
a hookSpecificOutput JSON with permissionDecision=ask escalates it.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CANONICAL = REPO / "plugins" / "_shared" / "check-scope.sh"
LOOP_PLUGINS = ["autoresearch", "autodesign", "autoreview"]

# Args mirroring the autoresearch hooks.json wiring.
ARGS = [
    "experiment-config.yaml",
    "target_files",
    "results.tsv run.log",
    "outside experiment scope (test reason)",
]

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None,
    reason="hook needs bash on PATH",
)


def _plugin_copy(plugin: str) -> Path:
    return REPO / "plugins" / plugin / "hooks" / "scripts" / "check-scope.sh"


def _run_hook(
    cwd: Path,
    file_path: str,
    config: str | None = None,
    args: list[str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the canonical hook in cwd with a PreToolUse payload."""
    if config is not None:
        (cwd / ARGS[0]).write_text(config)
    payload = json.dumps({"tool_input": {"file_path": file_path}})
    return subprocess.run(
        ["bash", str(CANONICAL), *(args or ARGS)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False,
    )


CONFIG_BASIC = 'target_files:\n  - "src/algo.py"\neval_command: "just test"\n'


# --- drift gate -------------------------------------------------------------


def test_canonical_exists() -> None:
    assert CANONICAL.is_file(), "canonical plugins/_shared/check-scope.sh is missing"


@pytest.mark.parametrize("plugin", LOOP_PLUGINS)
def test_plugin_copy_matches_canonical(plugin: str) -> None:
    copy = _plugin_copy(plugin)
    assert copy.is_file(), f"{plugin} is missing its check-scope.sh copy"
    assert copy.read_bytes() == CANONICAL.read_bytes(), (
        f"plugins/{plugin}/hooks/scripts/check-scope.sh has drifted from the "
        "canonical plugins/_shared/check-scope.sh — edit the canonical and run "
        "`just sync-plugin-scope-hook`"
    )


def _just_parses_this_justfile() -> bool:
    """just older than 1.27 cannot parse the repo justfile ([group])."""
    if shutil.which("just") is None:
        return False
    result = subprocess.run(
        ["just", "--list"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    return result.returncode == 0


@pytest.mark.skipif(
    not _just_parses_this_justfile(),
    reason="recipe test needs a just that can parse the repo justfile (>= 1.27)",
)
def test_sync_recipe_propagates_canonical(tmp_path: Path) -> None:
    """`just sync-plugin-scope-hook` must copy the canonical into all plugins."""
    # given: a minimal repo copy (justfile + canonical + per-plugin copies)
    shutil.copy(REPO / "justfile", tmp_path / "justfile")
    shared = tmp_path / "plugins" / "_shared"
    shared.mkdir(parents=True)
    marker = "# sync-recipe-test-marker\n"
    shutil.copy(CANONICAL, shared / "check-scope.sh")
    (shared / "check-scope.sh").write_text(CANONICAL.read_text() + marker)
    for plugin in LOOP_PLUGINS:
        dest = tmp_path / "plugins" / plugin / "hooks" / "scripts"
        dest.mkdir(parents=True)
        shutil.copy(CANONICAL, dest / "check-scope.sh")

    # when
    result = subprocess.run(
        ["just", "sync-plugin-scope-hook"],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )

    # then
    assert result.returncode == 0, result.stderr
    for plugin in LOOP_PLUGINS:
        copied = tmp_path / "plugins" / plugin / "hooks" / "scripts" / "check-scope.sh"
        assert copied.read_text().endswith(marker), (
            f"recipe did not propagate the canonical to {plugin}"
        )


# --- scope decision behavior -------------------------------------------------


def test_no_config_allows_silently(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, "anything/at/all.py")
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_in_scope_target_allows_silently(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, "/repo/src/algo.py", config=CONFIG_BASIC)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_out_of_scope_target_asks_with_reason(tmp_path: Path) -> None:
    result = _run_hook(tmp_path, "/repo/README.md", config=CONFIG_BASIC)
    assert result.returncode == 0
    output = json.loads(result.stdout)
    hook_output = output["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert hook_output["permissionDecision"] == "ask"
    assert hook_output["permissionDecisionReason"] == ARGS[3]


@pytest.mark.parametrize("artifact", ["results.tsv", "run.log"])
def test_whitelisted_artifacts_allow_silently(tmp_path: Path, artifact: str) -> None:
    result = _run_hook(tmp_path, f"/repo/{artifact}", config=CONFIG_BASIC)
    assert result.returncode == 0
    assert result.stdout.strip() == ""


def test_empty_file_path_allows_silently(tmp_path: Path) -> None:
    (tmp_path / ARGS[0]).write_text(CONFIG_BASIC)
    payload = json.dumps({"tool_input": {"command": "echo no file_path here"}})
    result = subprocess.run(
        ["bash", str(CANONICAL), *ARGS],
        input=payload,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# --- structured input parsing (jq) -------------------------------------------


def _decision(result: subprocess.CompletedProcess[str]) -> str:
    """'allow' for silent exit, 'ask' when the hook emits a decision JSON."""
    if result.stdout.strip() == "":
        return "allow"
    return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]


def test_content_key_before_file_path_is_not_misparsed(tmp_path: Path) -> None:
    """A Write payload whose content mentions "file_path" must not shadow the
    real tool_input.file_path (the old grep parser took the first match)."""
    (tmp_path / ARGS[0]).write_text(CONFIG_BASIC)
    payload = (
        '{"tool_input":{"content":"see \\"file_path\\": \\"/bogus/out.md\\" in docs",'
        '"file_path":"/repo/src/algo.py"}}'
    )
    result = subprocess.run(
        ["bash", str(CANONICAL), *ARGS],
        input=payload,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert _decision(result) == "allow"


def test_escaped_quote_in_file_path_is_decoded(tmp_path: Path) -> None:
    config = 'target_files:\n  - we"ird.py\neval_command: "x"\n'
    result = _run_hook(tmp_path, '/repo/we"ird.py', config=config)
    assert _decision(result) == "allow"


def test_missing_jq_fails_open(tmp_path: Path) -> None:
    """Without jq the guard deliberately disables itself (fail-open) instead
    of producing constant asks; the setup skills preflight jq for this."""
    (tmp_path / ARGS[0]).write_text(CONFIG_BASIC)
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ["cat", "basename", "sed", "awk", "grep", "head"]:
        path = shutil.which(tool)
        assert path is not None
        (bindir / tool).symlink_to(path)
    bash = shutil.which("bash")
    assert bash is not None
    payload = json.dumps({"tool_input": {"file_path": "/repo/not-in-scope.md"}})
    result = subprocess.run(
        [bash, str(CANONICAL), *ARGS],
        input=payload,
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={"PATH": str(bindir)},
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""


# --- anchored scope matching --------------------------------------------------


@pytest.mark.parametrize(
    ("entry", "file_path", "expected"),
    [
        # file entries match exactly or at a path-segment boundary…
        ("src/algo.py", "/repo/src/algo.py", "allow"),
        ("src/algo.py", "src/algo.py", "allow"),
        # …but not as bare substrings (the old parser allowed both of these)
        ("algo.py", "/repo/myalgo.py", "ask"),
        ("src/foo.go", "/repo/src/foo.gold", "ask"),
        ("src/foo.go", "/repo/src/foo_generated.go", "ask"),
        # leading ./ in the entry is normalized away
        ("./src/foo.go", "/tmp/repo/src/foo.go", "allow"),
        # directory entries (trailing /) match by prefix or path segment
        ("src/", "src/sub/file.py", "allow"),
        ("src/", "/repo/src/sub/file.py", "allow"),
        ("src/", "/repo/src2/file.py", "ask"),
    ],
)
def test_anchored_matching(
    tmp_path: Path, entry: str, file_path: str, expected: str
) -> None:
    config = f'target_files:\n  - "{entry}"\neval_command: "x"\n'
    result = _run_hook(tmp_path, file_path, config=config)
    assert _decision(result) == expected, (entry, file_path)


# --- config list extraction ----------------------------------------------------


def test_unquoted_entry_is_honored(tmp_path: Path) -> None:
    config = "target_files:\n  - src/algo.py\neval_command: x\n"
    result = _run_hook(tmp_path, "/repo/src/algo.py", config=config)
    assert _decision(result) == "allow"


def test_comment_and_blank_lines_do_not_end_the_list(tmp_path: Path) -> None:
    config = 'target_files:\n  # primary target\n\n  - "src/algo.py"\neval_command: x\n'
    result = _run_hook(tmp_path, "/repo/src/algo.py", config=config)
    assert _decision(result) == "allow"


def test_list_at_end_of_file_keeps_its_last_entry(tmp_path: Path) -> None:
    """The old sed-range parser unconditionally dropped the last line, losing
    the final entry when the list closes the file."""
    config = 'eval_command: x\ntarget_files:\n  - "src/algo.py"\n'
    result = _run_hook(tmp_path, "/repo/src/algo.py", config=config)
    assert _decision(result) == "allow"


def test_empty_list_treats_everything_as_out_of_scope(tmp_path: Path) -> None:
    config = "target_files:\neval_command: x\n"
    result = _run_hook(tmp_path, "/repo/src/algo.py", config=config)
    assert _decision(result) == "ask"


def test_malformed_input_fails_open(tmp_path: Path) -> None:
    """Garbage on stdin must not surface a jq error (and must never become
    exit 2 = block); the guard fails open like the no-jq case."""
    (tmp_path / ARGS[0]).write_text(CONFIG_BASIC)
    result = subprocess.run(
        ["bash", str(CANONICAL), *ARGS],
        input="not json at all",
        capture_output=True,
        text=True,
        cwd=tmp_path,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == ""
    assert result.stderr.strip() == ""


@pytest.mark.parametrize(
    ("config", "case"),
    [
        ("target_files:\n  - 'src/algo.py'\neval_command: x\n", "single-quoted"),
        (
            "target_files:\n  - src/algo.py  # main target\neval_command: x\n",
            "inline-comment",
        ),
        ('target_files :\n  - "src/algo.py"\neval_command: x\n', "space-before-colon"),
    ],
)
def test_common_yaml_spellings_are_in_scope(
    tmp_path: Path, config: str, case: str
) -> None:
    """The config is hand-editable YAML; ordinary valid spellings must not
    push a listed target out of scope."""
    result = _run_hook(tmp_path, "/repo/src/algo.py", config=config)
    assert _decision(result) == "allow", case


# --- jq preflight in the setup skills ------------------------------------------


@pytest.mark.parametrize(
    "skill",
    [
        "plugins/autoresearch/skills/setup-experiment/SKILL.md",
        "plugins/autodesign/skills/setup-design/SKILL.md",
        "plugins/autoreview/skills/setup-review/SKILL.md",
    ],
)
def test_setup_skill_preflights_jq(skill: str) -> None:
    """Fail-open without jq is a conscious tradeoff only if setup surfaces it."""
    text = (REPO / skill).read_text()
    assert "command -v jq" in text, (
        f"{skill} must preflight jq availability (the scope hook silently "
        "disables itself without jq)"
    )
