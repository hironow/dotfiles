"""The file and secret guards also read Codex's apply_patch edits.

Codex hands a PreToolUse hook `{"tool_name": "apply_patch", "tool_input":
{"command": "<the whole patch>"}}` (codex-rs core/src/tools/handlers/
apply_patch.rs), with no file_path or content. Without reading the patch both
guards saw an empty input and allowed every Codex edit. The paths come from the
Add File / Update File / Move to headers, the content from the added lines.
"""

import json
import shutil
from pathlib import Path

import pytest
from _bash_hook import run_bash

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / "ROOT_AGENTS_hooks_block-prohibited-files.sh"
SECRETS = ROOT / "ROOT_AGENTS_hooks_block-secrets.sh"
EXIT_ALLOW, EXIT_BLOCK = 0, 2

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="hook needs bash + jq on PATH",
)


def _patch(*sections: str) -> str:
    return "*** Begin Patch\n" + "".join(sections) + "*** End Patch\n"


def _run(hook: Path, patch: str) -> int:
    payload = json.dumps({"tool_name": "apply_patch", "tool_input": {"command": patch}})
    result = run_bash(
        hook,
        cwd=hook.parent,
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


@pytest.mark.parametrize(
    "patch",
    [
        _patch("*** Add File: .github/workflows/ci.yml\n+on: push\n"),
        _patch(
            "*** Update File: deploy/app.yaml\n*** Move to: deploy/app.yml\n@@\n-a\n+b\n"
        ),
        _patch("*** Add File: docker-compose.yaml\n+services: {}\n"),
        _patch("*** Add File: ok.yaml\n+a: 1\n", "*** Add File: bad.yml\n+b: 2\n"),
    ],
)
def test_a_patch_that_creates_a_prohibited_name_is_blocked(patch: str) -> None:
    assert _run(FILES, patch) == EXIT_BLOCK


@pytest.mark.parametrize(
    "patch",
    [
        _patch(
            "*** Add File: compose.yaml\n+services: {}\n",
            "*** Update File: src/app.py\n@@\n-a\n+b\n",
        ),
        _patch("*** Delete File: old.yml\n"),
        _patch(
            "*** Update File: docs/agents/enforcement.md\n@@\n-x\n+mentions ci.yml\n"
        ),
    ],
)
def test_a_patch_with_allowed_names_passes(patch: str) -> None:
    assert _run(FILES, patch) == EXIT_ALLOW


def test_a_secret_added_by_a_patch_is_blocked() -> None:
    token = "sk-ant-" + "a" * 30
    patch = _patch(f"*** Add File: config.py\n+KEY = '{token}'\n")
    assert _run(SECRETS, patch) == EXIT_BLOCK


def test_a_secret_removed_by_a_patch_is_not_blocked() -> None:
    # Only added lines are new content; removing a leaked key must stay possible
    token = "ghp_" + "a" * 36
    patch = _patch(
        f"*** Update File: config.py\n@@\n-KEY = '{token}'\n+KEY = os.environ['KEY']\n"
    )
    assert _run(SECRETS, patch) == EXIT_ALLOW


def test_a_patch_without_secrets_passes() -> None:
    assert _run(SECRETS, _patch("*** Add File: notes.md\n+hello\n")) == EXIT_ALLOW
