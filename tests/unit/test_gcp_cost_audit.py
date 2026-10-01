"""`just gcp-cost-audit <project>` reads a GCP project and names what has no bound.

The thing being guarded against is not a spike; it is a drip. An Artifact
Registry repository with no DELETE policy, a bucket with no lifecycle, a disk
nobody attached, an address nobody routes: each costs a little, forever, and
nothing fails to draw attention to it. `scripts/check_storage_bounds.py` already
stops this repo's OpenTofu from DECLARING an unbounded sink; this tool asks a
LIVE project what it actually has, including everything created outside tofu.

Read-only, always: the audit runs `gcloud ... --format=json` list calls and
nothing else, so it can be pointed at a project without a change window. The
fix is never applied here -- it goes through IaC.

The project id arrives as an ARGUMENT and is never written to a tracked file,
which is why these tests use a placeholder and why the tool prints no banner
naming the project unless asked.

Functional core / imperative shell: every rule is a pure function from parsed
gcloud JSON to doctor-style (level, name, detail) lines, so the rules are tested
here with fixtures and no cloud access. The shell only runs gcloud.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gcp_cost_audit as audit

PROJECT = "a-project"


def _levels(lines: list[audit.Line]) -> dict[str, str]:
    return {name: level for level, name, _detail in lines}


def _detail(lines: list[audit.Line], name: str) -> str:
    return next(detail for _level, n, detail in lines if n == name)


# --- Artifact Registry -------------------------------------------------
#
# The two traps are in check_storage_bounds.py's docstring: KEEP beats DELETE,
# and `most_recent_versions` is a floor rather than a cap. A repository whose
# only policy is a most_recent_versions KEEP therefore deletes NOTHING, which is
# exactly the shape that reads as a bound and is not one.


def _repo(name: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": f"projects/{PROJECT}/locations/asia-northeast1/repositories/{name}",
        "format": "DOCKER",
        "cleanupPolicies": {
            "delete-old": {"id": "delete-old", "action": "DELETE"},
            "keep-recent": {"id": "keep-recent", "action": "KEEP"},
        },
        "cleanupPolicyDryRun": False,
    }
    return base | extra


def test_a_repository_with_a_delete_policy_out_of_dry_run_is_ok() -> None:
    lines = audit.artifact_registry([_repo("exe-task")])
    assert _levels(lines)["ar:exe-task"] == "OK"


def test_a_repository_with_no_cleanup_policy_at_all_warns() -> None:
    lines = audit.artifact_registry([_repo("loose", cleanupPolicies={})])
    assert _levels(lines)["ar:loose"] == "WARN"
    assert "no cleanup policy" in _detail(lines, "ar:loose")


def test_a_repository_whose_only_policy_keeps_warns() -> None:
    """A KEEP-only repository deletes nothing, forever -- the floor trap."""
    keep_only = {"keep-recent": {"id": "keep-recent", "action": "KEEP"}}
    lines = audit.artifact_registry([_repo("floor", cleanupPolicies=keep_only)])
    assert _levels(lines)["ar:floor"] == "WARN"
    assert "no DELETE" in _detail(lines, "ar:floor")


def test_a_repository_still_in_dry_run_warns() -> None:
    """Dry run is the policy that looks applied and deletes nothing."""
    lines = audit.artifact_registry([_repo("pretend", cleanupPolicyDryRun=True)])
    assert _levels(lines)["ar:pretend"] == "WARN"
    assert "dry run" in _detail(lines, "ar:pretend")


def test_no_repository_at_all_is_reported_as_nothing_to_bound() -> None:
    lines = audit.artifact_registry([])
    assert _levels(lines)["artifact-registry"] == "OK"


# --- Buckets -----------------------------------------------------------


def _bucket(name: str, **extra: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": name,
        "lifecycle": {
            "rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]
        },
    }
    return base | extra


def test_a_bucket_with_a_delete_lifecycle_is_ok() -> None:
    lines = audit.buckets([_bucket("tidy")], project=PROJECT)
    assert _levels(lines)["bucket:tidy"] == "OK"


def test_a_bucket_with_no_lifecycle_warns() -> None:
    lines = audit.buckets([_bucket("forever", lifecycle={})], project=PROJECT)
    assert _levels(lines)["bucket:forever"] == "WARN"
    assert "no lifecycle" in _detail(lines, "bucket:forever")


def test_a_snapshot_bucket_must_not_have_a_delete_lifecycle() -> None:
    """Both directions, as check_storage_bounds enforces on the tofu side: a
    lifecycle rule cannot tell a referenced snapshot from an abandoned one, and
    deleting a referenced one makes a suspended task impossible to resume."""
    bounded = audit.buckets([_bucket("exe-snapshots")], project=PROJECT)
    assert _levels(bounded)["bucket:exe-snapshots"] == "WARN"
    assert "must NOT" in _detail(bounded, "bucket:exe-snapshots")

    unbounded = audit.buckets([_bucket("exe-snapshots", lifecycle={})], project=PROJECT)
    assert _levels(unbounded)["bucket:exe-snapshots"] == "OK"


def test_the_cloud_build_default_bucket_is_called_out_by_name() -> None:
    """Cloud Build's default source bucket keeps every upload forever, and it is
    created behind your back on the first build."""
    lines = audit.buckets(
        [_bucket(f"{PROJECT}_cloudbuild", lifecycle={})], project=PROJECT
    )
    name = f"bucket:{PROJECT}_cloudbuild"
    assert _levels(lines)[name] == "WARN"
    assert "Cloud Build" in _detail(lines, name)


# --- Things that bill while idle ---------------------------------------


def test_an_unattached_disk_warns_and_an_attached_one_does_not() -> None:
    lines = audit.idle_resources(
        disks=[
            {"name": "orphan", "sizeGb": "50", "users": []},
            {"name": "in-use", "sizeGb": "50", "users": ["…/instances/vm"]},
        ],
        addresses=[],
        sql=[],
    )
    assert _levels(lines)["disk:orphan"] == "WARN"
    assert "disk:in-use" not in _levels(lines)


def test_a_reserved_but_unused_address_warns() -> None:
    lines = audit.idle_resources(
        disks=[],
        addresses=[
            {"name": "parked", "status": "RESERVED"},
            {"name": "routed", "status": "IN_USE"},
        ],
        sql=[],
    )
    assert _levels(lines)["address:parked"] == "WARN"
    assert "address:routed" not in _levels(lines)


def test_a_stopped_sql_instance_still_warns_because_storage_bills() -> None:
    """The trap: "stopped" reads as "free". Its disk and its backups are not."""
    lines = audit.idle_resources(
        disks=[],
        addresses=[],
        sql=[
            {
                "name": "mothballed",
                "state": "STOPPED",
                "settings": {"dataDiskSizeGb": "10"},
            }
        ],
    )
    assert _levels(lines)["sql:mothballed"] == "WARN"
    assert "STOPPED" in _detail(lines, "sql:mothballed")


def test_nothing_idle_is_one_ok_line() -> None:
    lines = audit.idle_resources(disks=[], addresses=[], sql=[])
    assert _levels(lines) == {"idle-resources": "OK"}


# --- The brakes: budget, nodes, schedulers ------------------------------


def test_no_budget_warns_and_one_budget_is_ok() -> None:
    assert _levels(audit.budgets([]))["budget"] == "WARN"
    assert _levels(audit.budgets([{"displayName": "exe"}]))["budget"] == "OK"


def test_without_a_billing_account_the_budget_is_not_claimed_either_way() -> None:
    """A billing account id is a forbidden token here, so it arrives as an
    argument or not at all -- and "not checked" must not read as "fine"."""
    lines = audit.budgets(None)
    assert _levels(lines)["budget"] == "OK"
    assert "not checked" in _detail(lines, "budget")


def test_running_nodes_are_the_money_signal() -> None:
    awake = audit.clusters(
        [{"name": "c", "currentNodeCount": 2, "nodePools": [{}, {}]}]
    )
    assert _levels(awake)["gke:c"] == "WARN"
    assert "2 node" in _detail(awake, "gke:c")

    asleep = audit.clusters([{"name": "c", "currentNodeCount": 0, "nodePools": [{}]}])
    assert _levels(asleep)["gke:c"] == "OK"


def test_a_scheduler_job_whose_last_attempt_failed_warns() -> None:
    """A scheduler job is often the only thing that turns something off. One
    that has been failing is an unattended brake nobody is holding."""
    lines = audit.schedulers(
        [
            {"name": "…/jobs/stop", "state": "ENABLED", "status": {"code": 2}},
            {"name": "…/jobs/wake", "state": "ENABLED", "status": {}},
        ]
    )
    assert _levels(lines)["scheduler:stop"] == "WARN"
    assert _levels(lines)["scheduler:wake"] == "OK"


def test_a_paused_scheduler_job_warns() -> None:
    lines = audit.schedulers([{"name": "…/jobs/stop", "state": "PAUSED", "status": {}}])
    assert _levels(lines)["scheduler:stop"] == "WARN"
    assert "PAUSED" in _detail(lines, "scheduler:stop")


# --- The tool as a whole ------------------------------------------------


def test_every_gcloud_call_is_read_only() -> None:
    """The audit must be safe to point at a project with no change window. Any
    verb but a list/describe would make that false."""
    allowed = {"list", "describe"}
    for argv in audit.PROBES.values():
        verbs = [
            token
            for token in argv
            if token
            in {"list", "describe", "create", "delete", "update", "patch", "set"}
        ]
        assert verbs, f"no verb found in {argv}"
        assert set(verbs) <= allowed, f"{argv} is not read-only"


def test_the_project_is_never_baked_into_the_probes() -> None:
    """It arrives as an argument. A probe carrying a literal project id would put
    it in a tracked file, which is the one thing that must not happen."""
    for argv in audit.PROBES.values():
        assert all("PROJECT" not in token or token == "{project}" for token in argv)
        joined = " ".join(argv)
        assert "--project" in joined or "--billing-account" in joined, joined


def test_a_probe_that_cannot_run_is_reported_not_treated_as_empty() -> None:
    """An API that is off, or a permission we lack, must not read as "nothing
    there" -- that is how an audit says a project is clean when it is blind."""
    lines = audit.report({"artifact_registry": None}, project=PROJECT, billing=None)
    assert _levels(lines)["artifact-registry"] == "WARN"
    assert "could not be read" in _detail(lines, "artifact-registry")


def test_the_exit_code_is_non_zero_when_something_has_no_bound() -> None:
    assert audit.exit_code([("OK", "a", "")]) == 0
    assert audit.exit_code([("OK", "a", ""), ("WARN", "b", "")]) == 1


@pytest.mark.parametrize("name", ["artifact_registry", "buckets", "disks", "addresses"])
def test_the_probes_cover_what_the_plan_names(name: str) -> None:
    assert name in audit.PROBES


# --- What the REAL gcloud returns, learned by running it ----------------
#
# Every case below is a false positive or a hazard the first live run produced.
# Fixtures written from a plan or from memory would not have caught any of them.


def test_the_policies_come_from_describe_because_list_omits_them() -> None:
    """`gcloud artifacts repositories list` returns no `cleanupPolicies` at all
    -- only `describe` does. Reading them off the list made the audit report two
    repositories with three policies each as having none, which is the worst kind
    of wrong: it calls a bounded sink unbounded."""
    assert "artifact_registry_describe" in audit.PROBES
    argv = audit.PROBES["artifact_registry_describe"]
    assert "describe" in argv
    assert "{repository}" in argv and "{location}" in argv


def test_a_bucket_lifecycle_is_read_from_the_key_gcloud_actually_uses() -> None:
    """`gcloud storage buckets list --format=json` emits `lifecycle_config`,
    snake_case, not `lifecycle`. Reading the wrong key made every bucket in the
    project look unbounded."""
    aged = {
        "name": "bounded",
        "lifecycle_config": {
            "rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]
        },
    }
    assert _levels(audit.buckets([aged], project=PROJECT))["bucket:bounded"] == "OK"

    generations = {
        "name": "capped",
        "lifecycle_config": {
            "rule": [
                {
                    "action": {"type": "Delete"},
                    "condition": {"isLive": False, "numNewerVersions": 5},
                }
            ]
        },
    }
    assert (
        _levels(audit.buckets([generations], project=PROJECT))["bucket:capped"] == "OK"
    )


def test_every_probe_is_quiet_so_none_can_prompt() -> None:
    """Without --quiet, `gcloud sql instances list` against a project whose API
    is off asks "Would you like to enable and retry? (y/N)". A read-only audit
    must not be one keystroke away from enabling an API."""
    for name, argv in audit.PROBES.items():
        assert "--quiet" in argv, f"{name} can prompt"


def test_a_scheduler_probe_with_no_location_is_not_checked() -> None:
    """`gcloud scheduler jobs list` REQUIRES --location; without one it always
    fails, and "could not be read" would read as a finding rather than as a
    missing argument."""
    lines = audit.report(
        {"schedulers": None}, project=PROJECT, billing=None, location=None
    )
    assert _levels(lines)["scheduler"] == "OK"
    assert "not checked" in _detail(lines, "scheduler")


def test_soft_delete_retention_is_a_cost_and_is_reported() -> None:
    """Its default keeps every deleted object for 7 days as billed storage.
    Nobody asks for it and nobody sees it; the spoke names it, so the tool has
    to find it."""
    on = {
        "name": "soft",
        "lifecycle_config": {
            "rule": [{"action": {"type": "Delete"}, "condition": {"age": 7}}]
        },
        "soft_delete_policy": {"retentionDurationSeconds": "604800"},
    }
    assert _levels(audit.buckets([on], project=PROJECT))["soft-delete:soft"] == "WARN"

    off = {**on, "soft_delete_policy": {"retentionDurationSeconds": "0"}}
    assert "soft-delete:soft" not in _levels(audit.buckets([off], project=PROJECT))
