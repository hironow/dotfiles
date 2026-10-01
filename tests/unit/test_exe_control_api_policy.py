"""The Control API policy admits the labels its callers really carry (plan F5).

tofu/exe-cluster/control_api.tf admits the API's port only from named pods.
Admission is by label, so a label renamed on one side and not the other
silently cuts the caller off, and L1's tick, the snapshot GC or AX stop
working. For the callers this repo deploys, the tofu test cannot see the
mismatch, since it plans with mock providers. So this test reads the policy
and the manifests that set the labels.
"""

from __future__ import annotations

import re
from pathlib import Path

CLUSTER = Path(__file__).resolve().parents[2] / "tofu" / "exe-cluster"


def block(text: str, header: str) -> str:
    """The body of the first `header {` block in text, braces balanced."""
    start = text.index(header)
    i = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
    return text[start:i]


def admitted() -> dict[str, str]:
    """The policy's callers map, namespace expression => its values list."""
    callers = block(
        (CLUSTER / "control_api.tf").read_text(encoding="utf-8"),
        "control_api_callers = {",
    )
    return dict(
        re.findall(
            r"\(([^)]+)\) = \{\s*key\s*=\s*\"[^\"]+\"\s*values\s*=\s*(\[[^\]]*\])",
            callers,
        )
    )


def test_the_policy_is_read() -> None:
    got = admitted()
    assert "local.substrate_namespace" in got
    assert "kubernetes_namespace_v1.ax.metadata[0].name" in got
    assert "kubernetes_namespace_v1.ops.metadata[0].name" in got


def test_the_ax_controller_is_admitted_by_the_label_its_pods_carry() -> None:
    manifest = block(
        (CLUSTER / "ax.tf").read_text(encoding="utf-8"),
        'resource "kubectl_manifest" "ax_controller"',
    )
    template = manifest[manifest.index("template") :]
    labels = set(re.findall(r'"app\.kubernetes\.io/name" = "([^"]+)"', template))
    assert labels == {"ax-controller"}, labels
    assert (
        admitted()["kubernetes_namespace_v1.ax.metadata[0].name"] == '["ax-controller"]'
    )


def test_l1_and_the_gc_are_admitted_by_the_locals_their_pods_carry() -> None:
    assert (
        admitted()["kubernetes_namespace_v1.ops.metadata[0].name"]
        == "[local.reaper_app, local.snapshot_gc_app]"
    )
    for tf, local in (
        ("reaper.tf", "local.reaper_app"),
        ("snapshot_gc.tf", "local.snapshot_gc_app"),
    ):
        text = (CLUSTER / tf).read_text(encoding="utf-8")
        pod_labels = re.findall(
            r'labels\s+=\s+merge\(local\.common_labels, \{ "app\.kubernetes\.io/name" = ([\w.]+) \}\)',
            text,
        )
        # the CronJob's own labels and its pod template's
        assert pod_labels == [local, local], (tf, pod_labels)
