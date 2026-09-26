"""Static invariants of `tofu/exe-platform` that `tofu test` cannot observe.

An OpenTofu `run` block asserts on planned VALUES; it never sees the
configuration text. So some properties of the stack are invisible to
`tofu/exe-platform/tests/` however the assertions are written:

- creation ORDER. `depends_on` changes when a resource is created, not what it
  looks like, and the first real apply failed on ordering alone: every
  Workload Identity binding was sent before the cluster that creates its pool.
- provider configuration. The quota-project settings the Billing Budgets API
  demands of user credentials live on the provider block, which no run block
  can read.

These tests read the source instead, through the storage-bounds gate's HCL
scanner (comment-, string- and heredoc-aware), so a `depends_on` inside a
comment or a heredoc never counts as the real thing.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
STACK = ROOT / "tofu" / "exe-platform"
_SCANNER = ROOT / "scripts" / "check_storage_bounds.py"

CLUSTER = "google_container_cluster.exe"

# A member naming a Workload Identity principal: through the locals that build
# them, or spelled out.
_PRINCIPAL_MARKERS = ("local.wi_", "principal://", "principalSet://")

# The seven principal bindings the stack declares today. Pinned so the scanner
# is proven to SEE them: a parser regression that found none would otherwise
# pass the ordering check vacuously. A new binding only has to wait for the
# cluster; it does not have to be added here.
KNOWN_PRINCIPAL_BINDINGS = frozenset(
    {
        "google_storage_bucket_iam_member.atelet_snapshots_object_admin",
        "google_storage_bucket_iam_member.atelet_snapshots_bucket_viewer",
        "google_storage_bucket_iam_member.api_server_snapshots_object_admin",
        "google_storage_bucket_iam_member.api_server_snapshots_bucket_viewer",
        "google_storage_bucket_iam_member.reaper_ops",
        "google_artifact_registry_repository_iam_member.atelet_task_reader",
        "google_artifact_registry_repository_iam_member.reaper_task_writer",
    }
)

_DEPENDS_ON = re.compile(r"(?m)^[ \t]*depends_on[ \t]*=[ \t]*\[([^\]]*)\]")


def _load_scanner() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_storage_bounds", _SCANNER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hcl = _load_scanner()


def _stack_text() -> str:
    """Every .tf file of the stack, scrubbed and concatenated."""
    files = sorted(STACK.glob("*.tf"))
    assert files, f"no .tf files under {STACK}"
    return "\n".join(hcl.scrub(path.read_text(encoding="utf-8")) for path in files)


def resources(text: str) -> dict[str, str]:
    """address -> body for every resource block in already-scrubbed HCL."""
    return {
        f"{block.labels[0]}.{block.labels[1]}": block.body
        for block in hcl.iter_blocks(text)
        if block.kind == "resource" and len(block.labels) == 2
    }


def depends_on(body: str) -> set[str]:
    """The references named by a resource body's own `depends_on` list."""
    match = _DEPENDS_ON.search(hcl.strip_sub_blocks(body))
    if match is None:
        return set()
    return {ref.strip() for ref in match.group(1).split(",") if ref.strip()}


def principal_bindings(text: str) -> tuple[list[str], list[str]]:
    """(every principal binding, the ones that do not wait for the cluster)."""
    found: list[str] = []
    racing: list[str] = []
    for address, body in resources(text).items():
        member = hcl.read_attribute(body, "member")
        if member is None or not any(mark in member for mark in _PRINCIPAL_MARKERS):
            continue
        found.append(address)
        if CLUSTER not in depends_on(body):
            racing.append(address)
    return found, racing


# --- Workload Identity bindings wait for the cluster -------------------------


def test_every_workload_identity_binding_waits_for_the_cluster() -> None:
    """The pool a principal:// member names (<project>.svc.id.goog) is created
    with the first Workload-Identity-enabled cluster. Nothing in the member
    string references the cluster, so without an explicit `depends_on` the
    binding races it and IAM answers "Identity Pool does not exist" -- which is
    how all seven failed on the first apply."""
    found, racing = principal_bindings(_stack_text())
    missing = KNOWN_PRINCIPAL_BINDINGS - set(found)
    assert not missing, (
        f"the scanner no longer sees these principal bindings: {sorted(missing)}"
    )
    assert racing == [], (
        f"principal bindings without depends_on = [{CLUSTER}]: {racing}. "
        "They are created before the Workload Identity pool exists and fail "
        "with 'Identity Pool does not exist'."
    )


def test_the_ordering_check_flags_a_binding_that_does_not_wait() -> None:
    """The checker itself, both ways, on synthetic HCL: a principal binding
    with the dependency passes, one without it is flagged even when a comment
    claims otherwise, and a plain service-account member is not a principal
    binding at all."""
    text = hcl.scrub(
        """
resource "google_storage_bucket_iam_member" "waits" {
  member = local.wi_atelet
  depends_on = [
    google_project_service.enabled,
    google_container_cluster.exe,
  ]
}

resource "google_storage_bucket_iam_member" "races" {
  member = "principal://iam.googleapis.com/projects/1/locations/global/workloadIdentityPools/p.svc.id.goog/subject/ns/a/sa/b"
  # depends_on = [google_container_cluster.exe]
  depends_on = [google_project_service.enabled]
}

resource "google_storage_bucket_iam_member" "service_account" {
  member = "serviceAccount:someone@example.invalid"
}
"""
    )
    found, racing = principal_bindings(text)
    assert found == [
        "google_storage_bucket_iam_member.waits",
        "google_storage_bucket_iam_member.races",
    ]
    assert racing == ["google_storage_bucket_iam_member.races"]


# --- the quota project for user credentials ----------------------------------


def test_the_provider_names_this_project_as_the_quota_project() -> None:
    """The operator applies with user ADC, and the Billing Budgets API refuses
    user credentials without an explicit quota project (403). The provider's
    google_billing_budget docs require exactly these two settings."""
    text = hcl.scrub((STACK / "main.tf").read_text(encoding="utf-8"))
    providers = [
        block
        for block in hcl.iter_blocks(text)
        if block.kind == "provider" and block.labels == ("google",)
    ]
    assert len(providers) == 1, (
        f"expected exactly one default google provider block, got {len(providers)}"
    )
    body = providers[0].body
    assert hcl.literal_bool(hcl.read_attribute(body, "user_project_override")) is True
    assert hcl.read_attribute(body, "billing_project") == "var.gcp_project_id", (
        "billing_project must be var.gcp_project_id: the quota project is this "
        "project, never whichever project the operator's ADC defaults to"
    )


# --- the Scheduler-failure alert waits for its metric -------------------------


def test_the_scheduler_failure_alert_is_created_after_the_l3_job() -> None:
    """Cloud Monitoring registers a new log-based metric asynchronously -- "it
    could take up to 10 minutes to become available" -- and the provider does
    not retry that 404. Ordering the alert after the L3 job puts the whole
    cluster build between the metric and the policy that reads it."""
    bodies = resources(_stack_text())
    alert = bodies["google_monitoring_alert_policy.scheduler_failure"]
    assert "google_cloud_scheduler_job.l3_daily_stop" in depends_on(alert), (
        "the scheduler-failure alert must depend on the L3 job, so it is not "
        "created in the seconds after its log-based metric, before Cloud "
        "Monitoring can see it"
    )
