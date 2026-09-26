#!/usr/bin/env python3
"""Summarise a saved OpenTofu plan by ACTION and ADDRESS, never by value.

A plan against a private project is dense with identifiers: project ids and
numbers, bucket paths, service-account emails, a billing account. `tofu show`
prints all of them, which makes the normal way of reviewing a plan -- read it,
paste the interesting part into the PR -- the single most likely way for one to
escape a public repo.

So this prints only what review actually needs: for each resource change, the
action and the CONFIG ADDRESS (`google_storage_bucket.snapshots`), which is
written in the .tf files and therefore already public. No attribute values, no
`before`/`after`, not even a resource's computed name.

That is enough to answer the two questions that matter before an apply:

  1. Does this plan only CREATE, or does it also change or destroy something?
     On a shared project, an unexpected update or delete is the failure mode --
     a name collision with a neighbouring stack makes tofu adopt and rewrite a
     resource somebody else owns.
  2. Is every address one of ours? `--expect-prefix` asserts that every changed
     address belongs to the stack under review, and exits non-zero if not.

Reads `tofu show -json <planfile>` on stdin. Exit 0 = summary printed and every
assertion held; 1 = an assertion failed (details on stderr). Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Sequence
from typing import Any

EXIT_OK = 0
EXIT_FAIL = 1

# tofu encodes a change as a list of actions; these are the combinations that
# matter to a reviewer, mapped to a one-character marker.
_MARKERS: dict[tuple[str, ...], str] = {
    ("create",): "+",
    ("delete",): "-",
    ("update",): "~",
    ("delete", "create"): "-/+",  # replace
    ("create", "delete"): "+/-",  # replace, create first
    ("read",): "<",
    ("no-op",): " ",
}

# Actions a reviewer must be told about loudly, because on a shared project they
# mean this stack is touching something that already existed.
_DESTRUCTIVE = {"delete", "update"}


def load_plan(text: str) -> dict[str, Any]:
    plan = json.loads(text)
    if not isinstance(plan, dict):
        raise ValueError("plan JSON must be an object")
    return plan


def marker(actions: Sequence[str]) -> str:
    return _MARKERS.get(tuple(actions), "/".join(actions))


def changes(plan: dict[str, Any]) -> list[tuple[str, list[str]]]:
    """(address, actions) for every non-no-op resource change, sorted."""
    out: list[tuple[str, list[str]]] = []
    for change in plan.get("resource_changes", []):
        if not isinstance(change, dict):
            continue
        address = change.get("address")
        actions = change.get("change", {}).get("actions", [])
        if not isinstance(address, str) or not isinstance(actions, list):
            continue
        if actions == ["no-op"]:
            continue
        out.append((address, [a for a in actions if isinstance(a, str)]))
    return sorted(out)


def _strip_index(address: str) -> str:
    """Drop a trailing `["key"]` / `[0]`.

    Load-bearing: a for_each key is often itself dotted
    (`google_project_service.enabled["compute.googleapis.com"]`), so splitting on
    "." before removing the index reads `googleapis` as the resource type and
    `com"]` as its name.
    """
    if address.endswith("]"):
        bracket = address.rfind("[")
        if bracket != -1:
            return address[:bracket]
    return address


def split_address(address: str) -> tuple[str, str]:
    """(type, name) for an address, module prefixes and index removed."""
    parts = _strip_index(address).split(".")
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return address, address


def resource_type(address: str) -> str:
    """`module.a.google_storage_bucket.x[0]` -> `google_storage_bucket`."""
    return split_address(address)[0]


def resource_name(address: str) -> str:
    """`google_project_service.enabled["compute.googleapis.com"]` -> `enabled`."""
    return split_address(address)[1]


def unexpected_addresses(
    entries: Sequence[tuple[str, list[str]]], prefixes: Sequence[str]
) -> list[str]:
    """Addresses whose resource NAME starts with none of `prefixes`.

    Matches on the resource name (the part the .tf file chose), not the type, so
    `google_storage_bucket.snapshots` is checked against "snapshots".
    """
    if not prefixes:
        return []
    bad: list[str] = []
    for address, _ in entries:
        name = resource_name(address)
        if not any(name.startswith(prefix) for prefix in prefixes):
            bad.append(address)
    return bad


def render(entries: Sequence[tuple[str, list[str]]]) -> list[str]:
    lines: list[str] = []
    by_type: Counter[str] = Counter()
    by_action: Counter[str] = Counter()
    for address, actions in entries:
        by_type[resource_type(address)] += 1
        by_action[marker(actions)] += 1
        lines.append(f"  {marker(actions):>3}  {address}")

    summary = ", ".join(
        f"{count} {mark!r}" for mark, count in sorted(by_action.items())
    )
    header = [
        f"plan summary: {len(entries)} resource change(s) [{summary}]",
        "(addresses only -- no attribute values are printed, deliberately)",
        "",
    ]
    footer = ["", "by resource type:"]
    footer += [f"  {count:>3}  {name}" for name, count in sorted(by_type.items())]
    return header + lines + footer


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--expect-prefix",
        action="append",
        default=[],
        help=(
            "Require every changed resource NAME to start with this prefix "
            "(repeatable). Use it to prove a plan touches only its own stack."
        ),
    )
    parser.add_argument(
        "--creates-only",
        action="store_true",
        help="Fail if the plan updates or destroys anything (a first apply should only create).",
    )
    args = parser.parse_args(argv)

    plan = load_plan(sys.stdin.read())
    entries = changes(plan)
    for line in render(entries):
        print(line)

    violations: list[str] = []

    if args.creates_only:
        risky = [
            f"{marker(actions)} {address}"
            for address, actions in entries
            if _DESTRUCTIVE.intersection(actions)
        ]
        if risky:
            violations.append(
                "plan is not create-only; on a shared project an update or "
                "delete means this stack is touching a resource that already "
                "exists:\n" + "\n".join(f"    {r}" for r in risky)
            )

    bad = unexpected_addresses(entries, args.expect_prefix)
    if bad:
        violations.append(
            "resource name(s) outside the expected prefixes "
            f"{args.expect_prefix}:\n" + "\n".join(f"    {a}" for a in bad)
        )

    if violations:
        print("summarize-tofu-plan: FAILED", file=sys.stderr)
        for violation in violations:
            print(f"  - {violation}", file=sys.stderr)
        return EXIT_FAIL
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
