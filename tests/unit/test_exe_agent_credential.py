"""No OpenTofu stack may hold the Claude token or grant anyone access to it.

Plan Q20: the token is added to Secret Manager by the operator and read at run
time by `ax-job` on the operator's own credentials. A secret *version* declared
in tofu would put the token in state and in every saved plan; an IAM grant on
the secret would let a workload identity, the node or the build account read
it. Neither can be asserted from inside `tofu test` (it cannot enumerate the
resource types a stack declares), so this scans the exe stacks' sources.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_STACKS = [_REPO_ROOT / "tofu" / "exe-platform", _REPO_ROOT / "tofu" / "exe-cluster"]

_FORBIDDEN = re.compile(
    r'^\s*resource\s+"(google_secret_manager_secret_version|google_secret_manager_secret_iam_\w+)"',
    re.MULTILINE,
)


def _declarations() -> list[str]:
    found: list[str] = []
    for stack in _STACKS:
        for tf in sorted(stack.glob("*.tf")):
            found += [
                f"{tf.relative_to(_REPO_ROOT)}: {m}"
                for m in _FORBIDDEN.findall(tf.read_text(encoding="utf-8"))
            ]
    return found


def test_no_stack_declares_a_secret_version_or_a_secret_grant() -> None:
    assert _declarations() == []


def test_the_scan_sees_the_secret_container_itself() -> None:
    # Guard against a scan that silently finds nothing because it reads the
    # wrong place: the container must be visible to the same glob.
    text = "".join(
        tf.read_text(encoding="utf-8")
        for tf in (_REPO_ROOT / "tofu" / "exe-platform").glob("*.tf")
    )
    assert 'resource "google_secret_manager_secret" "claude_oauth_token"' in text
