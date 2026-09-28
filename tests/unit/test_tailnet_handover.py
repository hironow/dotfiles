"""The tailnet's ACL changes owner without ever having two, or none (Phase 7).

The retired Coder stack (tofu/exe) owned the ACL, with prevent_destroy on it.
Its destroy (7.7) must not take the policy with it, and the new tofu/tailnet
must not fight it for the policy. So, in this order:

  7.4  tofu/exe drops the ACL from its state and keeps it live: a `removed`
       block with destroy = false replaces the resource;
  7.3  tofu/tailnet imports the live ACL and updates it;
  7.7  tofu/exe is destroyed, with nothing of the ACL left in it.

These read the stacks' files: a tofu test can see neither lifecycle blocks nor
imports. The ACL's content is tofu/tailnet/tests/acl.tofutest.hcl's.

7.5's IaC half is here too: the old stack's Cloud SQL instance loses both of
its deletion protections, so the destroy can take it once its 30-day copy is
made.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TAILNET = REPO / "tofu" / "tailnet"
OLD = REPO / "tofu" / "exe"


def stack_text(stack: Path) -> str:
    return "\n".join(tf.read_text() for tf in sorted(stack.glob("*.tf")))


def block(text: str, header: str) -> str:
    """The body of the first block whose header matches `header` (a regex)."""
    m = re.search(header + r"\s*\{", text)
    assert m, f"no block matching {header!r}"
    depth, i = 1, m.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[m.end() : i - 1]


def test_the_new_stack_imports_the_live_acl() -> None:
    body = block(stack_text(TAILNET), r"\bimport")
    assert re.search(r"to\s*=\s*tailscale_acl\.this\b", body)
    assert re.search(r"for_each\s*=\s*var\.adopt_live_acl\b", body)


def test_the_new_stack_cannot_destroy_the_acl() -> None:
    body = block(stack_text(TAILNET), r'resource "tailscale_acl" "this"')
    assert re.search(r"prevent_destroy\s*=\s*true", body)
    assert re.search(r'acl\s*=\s*file\("\$\{path\.module\}/acl\.hujson"\)', body)


def test_the_old_stack_lets_go_of_the_acl_without_destroying_it() -> None:
    text = stack_text(OLD)
    assert not re.search(r'resource "tailscale_acl"', text), (
        "tofu/exe must not manage the ACL any more: tofu/tailnet owns it"
    )
    removed = block(text, r"\bremoved")
    assert re.search(r"from\s*=\s*tailscale_acl\.this\b", removed)
    assert re.search(r"destroy\s*=\s*false", removed), (
        "without destroy = false, dropping the resource would delete the live ACL"
    )
    rest = text.replace(removed, "")
    assert "tailscale_acl.this" not in rest, (
        "nothing in tofu/exe may refer to the ACL it no longer manages"
    )


def test_the_old_stacks_database_can_be_deleted() -> None:
    body = block(stack_text(OLD), r'resource "google_sql_database_instance" "coder"')
    assert re.search(r"(?m)^\s*deletion_protection\s*=\s*false", body)
    assert re.search(r"deletion_protection_enabled\s*=\s*false", body)


def test_deleting_the_database_keeps_a_30_day_copy() -> None:
    # The plan's 30-day copy (7.5), the cheaper of an export and a final
    # backup: Cloud SQL takes a final backup when the destroy deletes the
    # instance, and keeps it 30 days after the instance is gone.
    body = block(stack_text(OLD), r'resource "google_sql_database_instance" "coder"')
    final = block(body, r"final_backup_config")
    assert re.search(r"enabled\s*=\s*true", final)
    assert re.search(r"retention_days\s*=\s*30\b", final)
