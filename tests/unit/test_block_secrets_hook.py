"""Unit tests for the PreToolUse hook ROOT_AGENTS_hooks_block-secrets.sh.

The hook receives Write|Edit tool input as JSON on stdin and blocks (exit 2)
when the written content looks like a live credential. It is deliberately a
minimal defense-in-depth net — the primary wall is a real secret scanner in
CI — but the shapes it does claim to catch must actually be caught.

Token fixtures are assembled by concatenation so this file never contains a
contiguous credential shape itself (otherwise the very hook under test —
and any real secret scanner — would flag the test file).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[2] / "ROOT_AGENTS_hooks_block-secrets.sh"

EXIT_ALLOW = 0
EXIT_BLOCK = 2

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="hook needs bash + jq on PATH",
)


def _run_hook(content: str) -> int:
    payload = json.dumps({"tool_input": {"file_path": "config.py", "content": content}})
    result = subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


@pytest.mark.parametrize(
    "token",
    [
        # pre-existing shapes (pin)
        "sk-" + "abcdefghijklmnopqrstu123",
        "ghp_" + "a" * 36,
        "AKIA" + "A" * 16,
        "-----BEGIN RSA " + "PRIVATE KEY-----",
        # Slack bot/user tokens
        "xoxb-" + "1234567890-abcDEF123456",
        "xoxp-" + "9876543210-zyxWVU987654",
        # GitLab personal access tokens
        "glpat-" + "x" * 20,
        # Google API keys
        "AIza" + "B" * 35,
    ],
)
def test_credential_shapes_are_blocked(token: str) -> None:
    assert _run_hook(f"value = '{token}'") == EXIT_BLOCK


@pytest.mark.parametrize(
    "content",
    [
        "plain configuration text, nothing secret",
        # prefixes alone (or too-short tails) must not false-trigger
        "the slack token prefix is xoxb- followed by the workspace id",
        "set GITLAB_TOKEN to your glpat- token from the UI",
        "AIzaSyExample is far too short to be a real key",
        "doc: AWS access key ids start with AKIA",
    ],
)
def test_benign_content_is_allowed(content: str) -> None:
    assert _run_hook(content) == EXIT_ALLOW
