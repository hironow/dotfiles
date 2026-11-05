"""What `agent-hook render` writes, sync owns, and it runs today's hooks.

The render corpus (tools/agent-hooks/internal/rendercorpus/render.jsonl,
rewritten by `just agent-hooks-render-corpus`) records every form the binary
renders and every path it refuses. The Go side checks that the binary still
gives those answers. This side checks the other half of the contract
(docs/plan/agent-hooks-go.md, PR 3b):

- every rendered handler is one sync owns for its harness, and not for the
  other harness, so a revert plus a sync replaces it with no duplicate;
- every path the renderer refuses, written by hand into the same form, is not
  owned either, so the two rules agree in both directions;
- the rendered blocks run the same hooks, on the same events and matchers, in
  the same order, as the scripts registered from .claude/settings.hooks.json.
"""

import json
import re
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_agents
from sync_agents import AgentTarget, codex_fragment_from_claude

CORPUS = ROOT / "tools/agent-hooks/internal/rendercorpus/render.jsonl"
SOURCE = ROOT / ".claude/settings.hooks.json"

# Each script registered today, by the agent-hook id that replaces it.
SCRIPT_HOOKS = {
    "block-prohibited-files.sh": "files-guard",
    "block-secrets.sh": "secrets-guard",
    "block-prohibited-commands.sh": "command-guard",
    "rtk-hook-claude.sh": "rtk",
    "rtk-hook-codex.sh": "rtk",
    "format-after-edit.sh": "formatter",
}


def _claude(home: Path) -> AgentTarget:
    return AgentTarget(directory=home, name="Claude", key="claude", receives_hooks=True)


def _codex(home: Path) -> AgentTarget:
    return AgentTarget(
        directory=home, name="Codex", key="codex", receives_codex_hooks=True
    )


AGENTS: dict[str, Callable[[Path], AgentTarget]] = {"claude": _claude, "codex": _codex}


def _cases() -> list[dict]:
    with CORPUS.open(encoding="utf-8") as corpus:
        return [json.loads(line) for line in corpus]


def _flag(args: list[str], name: str) -> str:
    """The value of --name, or "" without one."""
    return args[args.index(name) + 1] if name in args else ""


def _rendered() -> Iterator[dict]:
    yield from (case for case in _cases() if case["exit"] == 0)


# A refused path, as opposed to a refused shell or a usage error: the case
# names a form (refuse/<harness>/<os>/<shell or default>/<kind>).
_SHELL_REFUSALS = re.compile(r"shell-|missing-shell|empty-shell")


def _path_refusals() -> Iterator[dict]:
    for case in _cases():
        parts = case["case"].split("/")
        if (
            case["exit"] == 2
            and parts[0] == "refuse"
            and len(parts) == 5
            and not _SHELL_REFUSALS.match(parts[4])
        ):
            yield case


def test_the_corpus_holds_every_form_and_refusal() -> None:
    forms = {
        (
            _flag(c["args"], "--harness"),
            _flag(c["args"], "--os"),
            _flag(c["args"], "--shell"),
        )
        for c in _rendered()
    }
    assert {
        ("claude", "darwin", ""),
        ("claude", "linux", ""),
        ("claude", "windows", ""),
        ("codex", "darwin", "sh"),
        ("codex", "linux", "sh"),
        ("codex", "windows", "powershell"),
        ("codex", "windows", "cmd"),
    } <= forms
    assert sum(1 for _ in _path_refusals()) > 100


@pytest.mark.parametrize("case", list(_rendered()), ids=lambda case: case["case"])
def test_sync_owns_what_render_writes_for_its_harness_only(
    tmp_path: Path, case: dict
) -> None:
    harness = _flag(case["args"], "--harness")
    other = "codex" if harness == "claude" else "claude"
    own, others = AGENTS[harness](tmp_path / "own"), AGENTS[other](tmp_path / "other")
    fragment = json.loads(case["stdout"])
    blocks = [block for event in fragment["hooks"].values() for block in event]
    assert blocks
    for block in blocks:
        assert sync_agents._is_managed_hook_block(block, own), block
        assert not sync_agents._is_managed_hook_block(block, others), block


def _by_hand(harness: str, shell: str, path: str) -> dict:
    """A path written into the form render would use, without render's checks."""
    if harness == "claude":
        return {"type": "command", "command": path, "args": ["claude", "pre"]}
    if shell == "powershell":
        quoted = "& '" + path.replace("'", "''") + "'"
    elif shell == "cmd":
        quoted = '"' + path + '"'
    else:
        quoted = "'" + path.replace("'", "'\\''") + "'"
    return {"type": "command", "command": quoted + " codex pre --hook files-guard"}


@pytest.mark.parametrize("case", list(_path_refusals()), ids=lambda case: case["case"])
def test_a_path_render_refuses_is_not_owned_either(tmp_path: Path, case: dict) -> None:
    args = case["args"]
    harness = _flag(args, "--harness")
    shell = _flag(args, "--shell") or ("sh" if _flag(args, "--os") != "windows" else "")
    hook = _by_hand(harness, shell, _flag(args, "--binary"))
    block = {"matcher": "Bash", "hooks": [hook]}
    assert not sync_agents._is_managed_hook_block(
        block, AGENTS[harness](tmp_path / "home")
    )


def _script_blocks(fragment: dict) -> list[tuple[str, str, list[str]]]:
    """(event, matcher, hook ids) for each block of a scripts fragment."""
    blocks = []
    for event, event_blocks in fragment["hooks"].items():
        for block in event_blocks:
            ids = []
            for hook in block["hooks"]:
                scripts = re.findall(r"[\w.-]+\.sh", hook["command"])
                ids.append(SCRIPT_HOOKS[scripts[-1]])
            blocks.append((event, block["matcher"], ids))
    return blocks


def _rendered_blocks(fragment: dict) -> list[tuple[str, str, list[str]]]:
    """(event, matcher, hook ids) for each block of a rendered fragment."""
    blocks = []
    for event, event_blocks in fragment["hooks"].items():
        for block in event_blocks:
            ids = []
            for hook in block["hooks"]:
                if "args" in hook:
                    ids.append(hook["args"][hook["args"].index("--hook") + 1])
                else:
                    # The id is the manifest's (lowercase, digits, `-`); in the
                    # PowerShell form a `;` follows it.
                    match = re.search(r"--hook ([a-z0-9-]+)", hook["command"])
                    assert match is not None, hook["command"]
                    ids.append(match[1])
            blocks.append((event, block["matcher"], ids))
    return blocks


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_the_rendered_blocks_run_todays_hooks_in_todays_order(harness: str) -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    today = source if harness == "claude" else codex_fragment_from_claude(source)
    for case in _rendered():
        if _flag(case["args"], "--harness") == harness:
            assert _rendered_blocks(json.loads(case["stdout"])) == _script_blocks(today)
