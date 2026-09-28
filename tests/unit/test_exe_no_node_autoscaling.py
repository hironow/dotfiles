"""Nothing in tofu/exe-platform may scale nodes on demand.

The auto-sleep owns the node pool's running size: `exe-reaper wake` takes it
to one, and L1, L2 and L3 take it back to zero. That is only true while no
autoscaler can add a node on its own, and one thing in the cluster now asks for
one every minute: L1's CronJob (tofu/exe-cluster/reaper.tf). While the pool
sleeps, its tick's pod has no node and stays Pending, which is harmless exactly
because nothing answers a Pending pod with a node. Give the pool an
`autoscaling` block, or the cluster `cluster_autoscaling` (node
auto-provisioning) or Autopilot, and that Pending pod scales a node up every
night: the cluster never sleeps, at about 500 JPY a day (inbox M28).

So this reads every .tf file of the stack as text and fails on any of the
three. horizontal_pod_autoscaling is a different thing (pods, not nodes) and
is allowed.

Stdlib + pytest only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
EXE_PLATFORM: Final = _REPO_ROOT / "tofu" / "exe-platform"

#: A node autoscaler, in any form the google provider offers: a node pool's
#: `autoscaling { ... }`, the cluster's `cluster_autoscaling { ... }`, or an
#: Autopilot cluster. Anchored at the start of a line (after indentation), so
#: `horizontal_pod_autoscaling {` does not match.
_NODE_AUTOSCALER: Final = re.compile(
    r"(?m)^\s*(?:(?:cluster_)?autoscaling\s*\{|enable_autopilot\s*=\s*true\b)"
)


def node_autoscalers(text: str) -> list[str]:
    """Every node-autoscaler declaration in one .tf file, comments stripped."""
    code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    return [m.group(0).strip() for m in _NODE_AUTOSCALER.finditer(code)]


def test_the_scanner_sees_each_form_and_ignores_pod_autoscaling() -> None:
    assert node_autoscalers("  autoscaling {\n    min_node_count = 0\n  }\n")
    assert node_autoscalers("  cluster_autoscaling {\n    enabled = true\n  }\n")
    assert node_autoscalers("  enable_autopilot = true\n")
    assert not node_autoscalers(
        "    horizontal_pod_autoscaling {\n      disabled = false\n    }\n"
    )
    assert not node_autoscalers("  # autoscaling { would go here, and must not\n")
    assert not node_autoscalers("  enable_autopilot = false\n")


def test_nothing_in_exe_platform_scales_nodes_on_demand() -> None:
    found = {
        tf.name: hits
        for tf in sorted(EXE_PLATFORM.glob("*.tf"))
        if (hits := node_autoscalers(tf.read_text(encoding="utf-8")))
    }
    assert not found, (
        f"node autoscaling in tofu/exe-platform: {found}. L1's CronJob leaves a "
        "Pending pod every minute while the pool sleeps, and an autoscaler "
        "answers it with a node: the cluster would never sleep."
    )
