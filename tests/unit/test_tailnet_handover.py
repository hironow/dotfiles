"""The tailnet's ACL has exactly one owner, and that owner cannot destroy it.

The ACL changed hands without ever having two owners or none: the retired Coder
stack dropped it from its state and left it live (a `removed` block with
destroy = false), then tofu/tailnet imported it, and only then was the old stack
destroyed. That sequence is history now and its first half cannot be re-tested --
the stack it belonged to is gone (tests/unit/test_no_exe_residue.py pins its
absence by path).

What remains is the standing half: tofu/tailnet still holds the ACL by import,
and still refuses to destroy it. A destroy would put the tailnet back on
Tailscale's default policy, where every device reaches every other, or lock the
owner out.

These read the stack's files: a tofu test can see neither lifecycle blocks nor
imports. The ACL's content is tofu/tailnet/tests/acl.tofutest.hcl's.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TAILNET = REPO / "tofu" / "tailnet"


def stack_text(stack: Path) -> str:
    return "\n".join(tf.read_text() for tf in sorted(stack.glob("*.tf")))


def block(text: str, header: str, contains: str = "") -> str:
    """The body of the first block whose header matches `header` (a regex).

    `contains` (also a regex) picks between same-headed blocks.
    """
    for m in re.finditer(header + r"\s*\{", text):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[m.end() : i - 1]
        if not contains or re.search(contains, body):
            return body
    raise AssertionError(f"no block matching {header!r} containing {contains!r}")


def test_the_new_stack_imports_the_live_acl() -> None:
    body = block(stack_text(TAILNET), r"\bimport")
    assert re.search(r"to\s*=\s*tailscale_acl\.this\b", body)
    assert re.search(r"for_each\s*=\s*var\.adopt_live_acl\b", body)


def test_the_new_stack_cannot_destroy_the_acl() -> None:
    body = block(stack_text(TAILNET), r'resource "tailscale_acl" "this"')
    assert re.search(r"prevent_destroy\s*=\s*true", body)
    assert re.search(r'acl\s*=\s*file\("\$\{path\.module\}/acl\.hujson"\)', body)
