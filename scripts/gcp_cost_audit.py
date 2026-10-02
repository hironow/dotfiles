#!/usr/bin/env python3
"""Ask a LIVE GCP project what it has that nothing bounds. Read-only.

`scripts/check_storage_bounds.py` stops this repo's OpenTofu from DECLARING an
unbounded sink. It cannot see a bucket someone made by hand, a disk a deleted VM
left behind, or a cleanup policy still in dry run -- and those are where a
personal project's bill actually comes from. Nothing fails, no alert fires: a
drip, not a spike.

So this asks the project. Every probe is a `list` with `--format=json`; there is
no verb here that changes anything, which is why it needs no change window and
why a test asserts it. The fix is never applied from here either -- it goes
through IaC, so that the next `tofu apply` does not quietly undo it.

The project id arrives as an ARGUMENT and is never written to a tracked file.
The report goes to stdout for the caller to keep locally; it names the project
only in the header, and only when asked.

Functional core / imperative shell: each rule is a pure function from parsed
gcloud JSON to doctor-style (level, name, detail) lines, so the rules are tested
with fixtures and no cloud access, and gather() is the only part that runs
anything.

Usage:
    just gcp-cost-audit <project> [--billing-account ID] [--location REGION]

A check the flags did not let it run is reported at WARN as "not verified", not
at OK: `OK budget - not checked` is read as a pass by anyone skimming for the
word WARN, and a pass is the one thing an audit that did not look must not give.

Exit code: 0 when every sink has a bound AND every check ran, 1 when something
has no bound or could not be verified (so it can gate a rollout step), 2 on a
usage error.
"""

from __future__ import annotations

import itertools
import json
import subprocess
import sys
from collections.abc import Mapping, Sequence

Line = tuple[str, str, str]  # (level, name, detail)

PROBE_TIMEOUT = 180.0

# Every probe is read-only, and every probe is `--quiet`. `{project}` and friends
# are substituted at run time; no id is ever a literal here.
# tests/unit/test_gcp_cost_audit.py asserts all three properties.
#
# --quiet is not tidiness. Without it, `gcloud sql instances list` against a
# project whose API is off asks "API [sqladmin.googleapis.com] not enabled …
# Would you like to enable and retry? (y/N)" -- a read-only audit must not be one
# keystroke away from enabling an API and its billing.
#
# The Artifact Registry policies need TWO calls: `repositories list` does not
# return `cleanupPolicies` at all, only `describe` does. Reading them off the list
# made the audit report two repositories with three policies each as having none.
PROBES: dict[str, list[str]] = {
    "artifact_registry": [
        "artifacts",
        "repositories",
        "list",
        "--project",
        "{project}",
        "--quiet",
    ],
    "artifact_registry_describe": [
        "artifacts",
        "repositories",
        "describe",
        "{repository}",
        "--location",
        "{location}",
        "--project",
        "{project}",
        "--quiet",
    ],
    "buckets": ["storage", "buckets", "list", "--project", "{project}", "--quiet"],
    "disks": ["compute", "disks", "list", "--project", "{project}", "--quiet"],
    "addresses": ["compute", "addresses", "list", "--project", "{project}", "--quiet"],
    "sql": ["sql", "instances", "list", "--project", "{project}", "--quiet"],
    "clusters": ["container", "clusters", "list", "--project", "{project}", "--quiet"],
    # `scheduler jobs list` REQUIRES --location; with none given the probe is
    # skipped and reported as "not verified" -- a WARN, because it did not run.
    "schedulers": [
        "scheduler",
        "jobs",
        "list",
        "--location",
        "{location}",
        "--project",
        "{project}",
        "--quiet",
    ],
    "budgets": [
        "billing",
        "budgets",
        "list",
        "--billing-account",
        "{billing}",
        "--quiet",
    ],
}

# A snapshot bucket must have NO delete lifecycle: a rule cannot tell a
# referenced snapshot from an abandoned one, and deleting a referenced one makes
# a suspended task impossible to resume (check_storage_bounds.py enforces the
# same thing on the tofu side, in both directions).
SNAPSHOT_MARKER = "snapshot"


# ---- Functional core ----


def _basename(resource: str) -> str:
    return resource.rstrip("/").rsplit("/", 1)[-1]


def artifact_registry(repos: Sequence[Mapping[str, object]]) -> list[Line]:
    """Every repository needs a DELETE policy that is actually applied.

    Two shapes read as a bound and are not: a repository whose only policy is a
    KEEP (`most_recent_versions` is a floor, "never delete the newest N", not a
    cap) deletes nothing forever; and a policy still in dry run deletes nothing
    while reporting what it would have done.
    """
    if not repos:
        return [("OK", "artifact-registry", "no repository in this project")]
    lines: list[Line] = []
    for repo in repos:
        label = f"ar:{_basename(str(repo.get('name', '?')))}"
        policies = repo.get("cleanupPolicies")
        policies = policies if isinstance(policies, dict) else {}
        actions = {
            str(policy.get("action", "")).upper()
            for policy in policies.values()
            if isinstance(policy, dict)
        }
        if not policies:
            lines.append(
                ("WARN", label, "no cleanup policy: every version is kept forever")
            )
        elif "DELETE" not in actions:
            lines.append(
                (
                    "WARN",
                    label,
                    (
                        f"{len(policies)} policy(ies) but no DELETE: a KEEP-only "
                        "repository deletes nothing, forever"
                    ),
                )
            )
        elif repo.get("cleanupPolicyDryRun") is True:
            lines.append(
                ("WARN", label, "policies are in dry run: they report, delete nothing")
            )
        else:
            lines.append(("OK", label, f"{len(policies)} policy(ies), DELETE applied"))
    return lines


def _has_delete_lifecycle(bucket: Mapping[str, object]) -> bool:
    """`gcloud storage buckets list --format=json` emits `lifecycle_config`,
    snake_case. The camelCase name belongs to the older surfaces, and reading
    only that one made every bucket in a project look unbounded."""
    lifecycle = bucket.get("lifecycle_config") or bucket.get("lifecycle")
    rules = lifecycle.get("rule") if isinstance(lifecycle, dict) else None
    if not isinstance(rules, list):
        return False
    for rule in rules:
        action = rule.get("action") if isinstance(rule, dict) else None
        if isinstance(action, dict) and str(action.get("type", "")).lower() == "delete":
            return True
    return False


def _soft_delete_seconds(bucket: Mapping[str, object]) -> int:
    policy = bucket.get("soft_delete_policy") or bucket.get("softDeletePolicy")
    raw = policy.get("retentionDurationSeconds") if isinstance(policy, dict) else None
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return 0


def buckets(found: Sequence[Mapping[str, object]], *, project: str) -> list[Line]:
    """Every bucket needs a bound, except a snapshot bucket, which must not."""
    if not found:
        return [("OK", "buckets", "no bucket in this project")]
    lines: list[Line] = []
    for bucket in found:
        name = str(bucket.get("name", "?"))
        label = f"bucket:{name}"
        bounded = _has_delete_lifecycle(bucket)
        # Soft delete defaults to keeping every deleted object for 7 days as
        # billed storage. Nobody asks for it and nobody sees it.
        seconds = _soft_delete_seconds(bucket)
        if seconds:
            lines.append(
                (
                    "WARN",
                    f"soft-delete:{name}",
                    (
                        f"deleted objects are kept {seconds // 86400} day(s) as billed "
                        "storage; set soft_delete_policy deliberately or to 0"
                    ),
                )
            )
        if SNAPSHOT_MARKER in name:
            if bounded:
                lines.append(
                    (
                        "WARN",
                        label,
                        (
                            "a snapshot bucket must NOT have a delete lifecycle: a rule "
                            "cannot tell a referenced snapshot from an abandoned one"
                        ),
                    )
                )
            else:
                lines.append(
                    ("OK", label, "no delete lifecycle, which is correct here")
                )
        elif bounded:
            lines.append(("OK", label, "delete lifecycle present"))
        elif name == f"{project}_cloudbuild":
            lines.append(
                (
                    "WARN",
                    label,
                    (
                        "no lifecycle: this is Cloud Build's default source bucket, "
                        "created on the first build and never pruned"
                    ),
                )
            )
        else:
            lines.append(
                ("WARN", label, "no lifecycle rule: objects accumulate forever")
            )
    return lines


def idle_resources(
    *,
    disks: Sequence[Mapping[str, object]],
    addresses: Sequence[Mapping[str, object]],
    sql: Sequence[Mapping[str, object]],
) -> list[Line]:
    """What bills while nothing uses it. "Stopped" is the trap: a stopped SQL
    instance still pays for its data disk and its backups."""
    lines: list[Line] = []
    for disk in disks:
        if not disk.get("users"):
            lines.append(
                (
                    "WARN",
                    f"disk:{_basename(str(disk.get('name', '?')))}",
                    f"{disk.get('sizeGb', '?')} GiB attached to nothing, billed monthly",
                )
            )
    for address in addresses:
        if str(address.get("status", "")).upper() == "RESERVED":
            lines.append(
                (
                    "WARN",
                    f"address:{_basename(str(address.get('name', '?')))}",
                    "reserved and unused, which is the case that is charged",
                )
            )
    for instance in sql:
        settings = instance.get("settings")
        size = (
            (settings or {}).get("dataDiskSizeGb", "?")
            if isinstance(settings, dict)
            else "?"
        )
        lines.append(
            (
                "WARN",
                f"sql:{_basename(str(instance.get('name', '?')))}",
                (
                    f"state {instance.get('state', '?')}: an instance bills for its "
                    f"{size} GiB disk and its backups even STOPPED"
                ),
            )
        )
    return lines or [("OK", "idle-resources", "no idle disk, address or SQL instance")]


def budgets(found: Sequence[Mapping[str, object]] | None) -> list[Line]:
    """A budget is the only thing that notices a drip nobody is looking at.

    `None` means the audit had no billing account to ask with. That is not a
    pass: it is reported at WARN so that the exit code and the summary count it
    among the things nobody has verified.
    """
    if found is None:
        return [
            (
                "WARN",
                "budget",
                (
                    "not verified: pass --billing-account to look (find it with "
                    "`gcloud billing projects describe <project> "
                    "--format='value(billingAccountName)'`; the id is an "
                    "argument, never a tracked value)"
                ),
            )
        ]
    if not found:
        return [("WARN", "budget", "no budget on this billing account")]
    names = ", ".join(str(b.get("displayName", "?")) for b in found)
    return [("OK", "budget", f"{len(found)} budget(s): {names}")]


def clusters(found: Sequence[Mapping[str, object]]) -> list[Line]:
    """Running nodes are the money signal; a cluster at zero is nearly free."""
    if not found:
        return [("OK", "gke", "no cluster in this project")]
    lines: list[Line] = []
    for cluster in found:
        name = _basename(str(cluster.get("name", "?")))
        nodes = cluster.get("currentNodeCount") or 0
        pools = cluster.get("nodePools")
        pool_count = len(pools) if isinstance(pools, list) else 0
        if nodes:
            lines.append(
                (
                    "WARN",
                    f"gke:{name}",
                    f"{nodes} node(s) up across {pool_count} pool(s): billed per hour",
                )
            )
        else:
            lines.append(
                ("OK", f"gke:{name}", f"0 nodes up, {pool_count} pool(s) declared")
            )
    return lines


def schedulers(found: Sequence[Mapping[str, object]]) -> list[Line]:
    """A scheduler job is often the only thing that turns something OFF.

    One that is paused, or whose last attempt failed, is an unattended brake
    nobody is holding -- and its failure is silent by construction.
    """
    if not found:
        return [("OK", "scheduler", "no scheduler job in this project")]
    lines: list[Line] = []
    for job in found:
        name = _basename(str(job.get("name", "?")))
        state = str(job.get("state", "?")).upper()
        status = job.get("status")
        code = status.get("code") if isinstance(status, dict) else None
        if state != "ENABLED":
            lines.append(("WARN", f"scheduler:{name}", f"state {state}, not ENABLED"))
        elif code:
            lines.append(
                (
                    "WARN",
                    f"scheduler:{name}",
                    f"last attempt failed (status code {code})",
                )
            )
        else:
            lines.append(("OK", f"scheduler:{name}", "enabled, last attempt clean"))
    return lines


_UNREADABLE = {
    "artifact_registry": "artifact-registry",
    "buckets": "buckets",
    "sql": "idle-resources",
    "clusters": "gke",
    "schedulers": "scheduler",
}


def report(
    probed: Mapping[str, object],
    *,
    project: str,
    billing: str | None,
    location: str | None = None,
) -> list[Line]:
    """Every rule's lines, in reading order.

    A probe that answered `None` could not be read -- an API that is off, or a
    permission we lack. That is reported, never treated as "nothing there": an
    audit that cannot see must not say a project is clean.

    The scheduler is the one exception, and for a different reason: its probe
    REQUIRES a location, so with none given it was never asked. That is reported
    as "not verified" rather than as "could not be read" -- a missing argument,
    not a blind probe -- but still at WARN, because both leave the same hole.
    """
    lines: list[Line] = []

    def answered(key: str) -> list[Mapping[str, object]] | None:
        value = probed.get(key)
        if value is None:
            return None
        return list(value) if isinstance(value, list) else []

    if not location:
        lines.append(
            (
                "WARN",
                "scheduler",
                (
                    "not verified: pass --location, which `gcloud scheduler jobs "
                    "list` requires"
                ),
            )
        )

    for key, label in _UNREADABLE.items():
        if key == "schedulers" and not location:
            continue
        if key in probed and probed[key] is None:
            lines.append(
                (
                    "WARN",
                    label,
                    (
                        f"`gcloud {key.replace('_', ' ')} list` could not be read: "
                        "the API may be disabled or the identity may lack the role"
                    ),
                )
            )

    repos = answered("artifact_registry")
    if repos is not None:
        lines += artifact_registry(repos)
    found = answered("buckets")
    if found is not None:
        lines += buckets(found, project=project)
    disks, addresses, sql = (
        answered("disks"),
        answered("addresses"),
        answered("sql"),
    )
    if None not in (disks, addresses, sql):
        lines += idle_resources(
            disks=disks or [], addresses=addresses or [], sql=sql or []
        )
    lines += budgets(answered("budgets") if billing else None)
    gke = answered("clusters")
    if gke is not None:
        lines += clusters(gke)
    jobs = answered("schedulers")
    if location and jobs is not None:
        lines += schedulers(jobs)
    return lines


def exit_code(lines: Sequence[Line]) -> int:
    return 1 if any(level == "WARN" for level, _name, _detail in lines) else 0


# ---- Imperative shell ----


def _gcloud(argv: list[str]) -> object | None:
    try:
        done = subprocess.run(
            ["gcloud", *argv, "--format=json"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=PROBE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    try:
        return json.loads(done.stdout or "[]")
    except json.JSONDecodeError:
        return None


def _repo_location(resource: str) -> str:
    """The location out of `projects/P/locations/L/repositories/R`."""
    parts = resource.split("/")
    return parts[parts.index("locations") + 1] if "locations" in parts else ""


def _with_policies(
    repos: Sequence[Mapping[str, object]], project: str
) -> list[Mapping[str, object]] | None:
    """Each repository, with the cleanup policies only `describe` returns.

    A describe that fails drops the whole answer rather than that one repository:
    a partial list would under-report, which for this tool means calling an
    unbounded sink bounded by omission.
    """
    enriched: list[Mapping[str, object]] = []
    for repo in repos:
        resource = str(repo.get("name", ""))
        argv = [
            token.replace("{project}", project)
            .replace("{repository}", _basename(resource))
            .replace("{location}", _repo_location(resource))
            for token in PROBES["artifact_registry_describe"]
        ]
        described = _gcloud(argv)
        if not isinstance(described, dict):
            return None
        enriched.append({**repo, **described})
    return enriched


def gather(
    project: str, billing: str | None, location: str | None = None
) -> dict[str, object]:
    probed: dict[str, object] = {}
    for key, template in PROBES.items():
        if "{repository}" in template:
            continue  # driven per repository below, not on its own
        if "{billing}" in template and not billing:
            continue
        if "{location}" in template and not location:
            continue
        argv = [
            token.replace("{project}", project)
            .replace("{billing}", billing or "")
            .replace("{location}", location or "")
            for token in template
        ]
        probed[key] = _gcloud(argv)
    repos = probed.get("artifact_registry")
    if isinstance(repos, list):
        probed["artifact_registry"] = _with_policies(repos, project)
    return probed


def main(argv: Sequence[str]) -> int:
    args = list(argv)
    if not args or args[0].startswith("-"):
        print(
            "usage: gcp_cost_audit.py <project> [--billing-account ID] "
            "[--location REGION]",
            file=sys.stderr,
        )
        return 2
    project = args[0]
    billing = location = None
    for flag, value in itertools.pairwise(args):
        if flag == "--billing-account":
            billing = value
        elif flag == "--location":
            location = value
    lines = report(
        gather(project, billing, location),
        project=project,
        billing=billing,
        location=location,
    )
    for level, name, detail in lines:
        print(f"{level:<4} {name} - {detail}")
    warns = sum(1 for level, _n, _d in lines if level == "WARN")
    print(f"\n{len(lines)} check(s), {warns} unbounded or not verified.")
    return exit_code(lines)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
