"""The orphan-snapshot GC's reach, where a tofu test cannot see it (Phase 6 plan D11).

tofu/exe-platform/tests/snapshot_gc.tofutest.hcl pins the GC's own grants. What
a tofu test cannot do is enumerate: "no binding anywhere gives L1 the snapshot
bucket" and "no RoleBinding names the GC's KSA" are statements about every
resource, including ones added later. So these tests scan the stacks' .tf files.

They also hold three definitions in step, across two stacks and the Go code:
the prefixes the GC may delete under (exe-platform), the atespace and snapshot
root AX's ActorTemplates use (exe-cluster), and Substrate's golden atespace
(tools/exe-reaper). A mismatch would not over-delete, since IAM refuses
anything outside the prefixes, but the GC would then 403 on the very prefixes
it exists to remove.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PLATFORM = REPO / "tofu" / "exe-platform"
CLUSTER = REPO / "tofu" / "exe-cluster"
GOLDEN_GO = REPO / "tools" / "exe-reaper" / "internal" / "substrate" / "substrate.go"


def blocks(stack: Path, kind: str) -> dict[str, str]:
    """Every `resource "<type matching kind>" "<name>" { ... }` in a stack, by address."""
    out: dict[str, str] = {}
    for tf in sorted(stack.glob("*.tf")):
        text = tf.read_text(encoding="utf-8")
        for m in re.finditer(r'resource "(' + kind + r')" "([\w-]+)" \{', text):
            depth, i = 1, m.end()
            while depth:
                depth += {"{": 1, "}": -1}.get(text[i], 0)
                i += 1
            out[f"{m.group(1)}.{m.group(2)}"] = text[m.end() : i - 1]
    return out


def test_the_scanner_finds_the_bindings_it_is_meant_to() -> None:
    found = blocks(PLATFORM, r"google_storage_bucket_iam_\w+")
    assert "google_storage_bucket_iam_member.reaper_ops" in found
    assert "google_storage_bucket_iam_member.atelet_snapshots_object_admin" in found
    assert "local.wi_reaper" in found["google_storage_bucket_iam_member.reaper_ops"]


def test_l1_holds_nothing_on_the_snapshot_bucket() -> None:
    # L1 runs every minute; the GC's delete stands on its own KSA precisely so
    # that a bad tick cannot reach a suspended task's snapshot (inbox M35).
    on_snapshots = {
        address: body
        for address, body in blocks(PLATFORM, r"google_storage_bucket_iam_\w+").items()
        if "google_storage_bucket.snapshots" in body
    }
    assert on_snapshots, "no binding on the snapshot bucket found: the scan is broken"
    offending = [a for a, body in on_snapshots.items() if "local.wi_reaper" in body]
    assert offending == [], offending


def test_l1_holds_no_project_wide_grant() -> None:
    # A project-level role would reach the snapshot bucket as well.
    found = blocks(PLATFORM, r"google_project_iam_\w+")
    assert found, "no project IAM found: the scan is broken"
    offending = [a for a, body in found.items() if "local.wi_reaper" in body]
    assert offending == [], offending


def test_no_role_binding_names_the_gcs_ksa() -> None:
    # It needs Workload Identity and the Control API's projected token only.
    found = blocks(CLUSTER, r"kubernetes_(?:cluster_)?role_binding_v1")
    assert found, "no RoleBinding found: the scan is broken"
    offending = [a for a, body in found.items() if "snapshot_gc" in body]
    assert offending == [], offending


def local_value(stack: Path, name: str) -> str:
    for tf in sorted(stack.glob("*.tf")):
        m = re.search(rf"^\s*{name}\s*=\s*(.+)$", tf.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1).strip()
    raise AssertionError(f"no local {name} in {stack.name}")


def test_the_gc_prefixes_are_the_actors_the_cluster_and_substrate_use() -> None:
    root = local_value(PLATFORM, "snapshot_gc_root")
    atespaces = set(
        re.findall(r'"([^"]+)"', local_value(PLATFORM, "snapshot_gc_atespaces"))
    )

    location = local_value(CLUSTER, "ax_snapshots_location")
    m = re.fullmatch(
        r'"gs://\$\{local\.platform\.bucket_snapshots\}/([^"]+)"', location
    )
    assert m, location
    assert root == f'"{m.group(1)}"'

    task_atespace = local_value(CLUSTER, "atespace")
    golden = re.search(
        r'GoldenAtespace = "([^"]+)"', GOLDEN_GO.read_text(encoding="utf-8")
    )
    assert golden
    assert atespaces == {task_atespace.strip('"'), golden.group(1)}
