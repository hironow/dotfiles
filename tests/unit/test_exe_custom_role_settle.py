"""Every binding of an exe-platform custom role waits for the role to be usable.

A custom role is not usable in a policy for a while after it is created: a
binding sent at once fails with "Role ... does not exist in the resource's
hierarchy". The snapshot GC's first apply failed halfway on exactly that
(manager-loop inbox M37), and every fresh environment would, since each role
and its first binding share one apply there. So tofu/exe-platform has one
terraform_data, custom_roles_settled, that sleeps whenever the set of custom
roles changes, and every binding of a custom role depends on it.

A tofu test cannot enumerate resources, so these tests scan the stack's .tf
files: a new custom role or a new binding that skips the wait fails here.
"""

from __future__ import annotations

import re
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[2] / "tofu" / "exe-platform"
SETTLED = "terraform_data.custom_roles_settled"


def blocks() -> dict[str, str]:
    """Every resource block in the stack, by address, body only."""
    out: dict[str, str] = {}
    for tf in sorted(PLATFORM.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(r'resource "([\w-]+)" "([\w-]+)" \{', text):
            depth, i = 1, m.end()
            while depth:
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                i += 1
            out[f"{m.group(1)}.{m.group(2)}"] = text[m.end() : i - 1]
    return out


def custom_roles() -> list[str]:
    return [a for a in blocks() if a.startswith("google_project_iam_custom_role.")]


def bindings_of_custom_roles() -> dict[str, str]:
    return {
        address: body
        for address, body in blocks().items()
        if re.search(
            r"^\s*role\s*=\s*google_project_iam_custom_role\.", body, re.MULTILINE
        )
    }


def test_the_scan_sees_the_roles_and_their_bindings() -> None:
    assert "google_project_iam_custom_role.reaper_tags" in custom_roles()
    assert "google_project_iam_custom_role.snapshot_gc_delete" in custom_roles()
    found = bindings_of_custom_roles()
    assert "google_artifact_registry_repository_iam_member.reaper_task_tags" in found
    assert "google_storage_bucket_iam_member.snapshot_gc_delete" in found


def test_every_custom_role_resets_the_wait() -> None:
    # A role missing here would be bound the moment it exists.
    settled = blocks()[SETTLED]
    missing = [
        r
        for r in custom_roles()
        if not re.search(re.escape(r) + r"(\[\*\])?\.id", settled)
    ]
    assert missing == [], missing


def test_every_binding_of_a_custom_role_waits() -> None:
    offending = [
        address
        for address, body in bindings_of_custom_roles().items()
        if not re.search(r"depends_on\s*=\s*\[[^\]]*" + re.escape(SETTLED), body)
    ]
    assert offending == [], offending


def test_the_wait_is_a_sleep_that_runs_once_per_change() -> None:
    settled = blocks()[SETTLED]
    assert "triggers_replace" in settled
    assert re.search(r'command\s*=\s*"sleep \d+"', settled)
