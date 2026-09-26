"""Unit tests for scripts/summarize_tofu_plan.py.

Reviewing a plan against a private project is the single most likely way for one
of its identifiers to escape into a public repo: the normal workflow is read the
plan, paste the interesting part somewhere. So the summariser prints CONFIG
ADDRESSES and nothing else, and the first test below is the one that matters --
no attribute value from the plan may appear in its output, ever.

The other half is the two questions worth asking before an apply on a SHARED
project: is this plan create-only (an update or delete means it is touching
something that already exists, most likely a name collision with a neighbouring
stack), and does every address belong to the stack under review.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "summarize_tofu_plan.py"

# A value that must never survive into the output: stands in for a project id,
# a bucket path or a service-account email in a real plan.
SECRET_VALUE = "zz-synthetic-secret-value"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("summarize_tofu_plan", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def _plan(*entries: tuple[str, list[str]]) -> str:
    """A minimal `tofu show -json` shape, with a secret in every attribute slot."""
    return json.dumps(
        {
            "format_version": "1.2",
            "resource_changes": [
                {
                    "address": address,
                    "type": address.split(".", 1)[0],
                    "change": {
                        "actions": actions,
                        "before": None if "create" in actions else {"n": SECRET_VALUE},
                        "after": {"name": SECRET_VALUE, "project": SECRET_VALUE},
                    },
                }
                for address, actions in entries
            ],
        }
    )


def _run(plan_json: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        input=plan_json,
        capture_output=True,
        text=True,
    )


def test_no_attribute_value_reaches_the_output() -> None:
    result = _run(
        _plan(
            ("google_storage_bucket.snapshots", ["create"]),
            ("google_container_cluster.exe", ["create"]),
        )
    )
    assert result.returncode == 0, result.stderr
    combined = result.stdout + result.stderr
    assert SECRET_VALUE not in combined
    assert "google_storage_bucket.snapshots" in result.stdout


def test_counts_and_markers_are_reported() -> None:
    result = _run(
        _plan(
            ("google_storage_bucket.ops", ["create"]),
            ("google_compute_network.exe", ["update"]),
            ("google_service_account.node", ["delete", "create"]),
        )
    )
    assert "3 resource change(s)" in result.stdout
    assert "+" in result.stdout
    assert "~" in result.stdout
    assert "-/+" in result.stdout


def test_no_op_changes_are_not_listed() -> None:
    result = _run(
        _plan(
            ("google_storage_bucket.ops", ["no-op"]),
            ("google_storage_bucket.build", ["create"]),
        )
    )
    assert "1 resource change(s)" in result.stdout
    assert "google_storage_bucket.ops" not in result.stdout


def test_creates_only_passes_on_a_first_apply() -> None:
    result = _run(
        _plan(("google_storage_bucket.ops", ["create"])),
        "--creates-only",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("actions", [["update"], ["delete"], ["delete", "create"]])
def test_creates_only_rejects_touching_an_existing_resource(actions: list[str]) -> None:
    result = _run(_plan(("google_compute_network.exe", actions)), "--creates-only")
    assert result.returncode == 1
    assert "not create-only" in result.stderr
    assert "google_compute_network.exe" in result.stderr


def test_expected_prefix_accepts_matching_names() -> None:
    result = _run(
        _plan(("google_storage_bucket.snapshots", ["create"])),
        "--expect-prefix",
        "snapshots",
    )
    assert result.returncode == 0, result.stderr


def test_expected_prefix_flags_a_foreign_name() -> None:
    result = _run(
        _plan(
            ("google_storage_bucket.snapshots", ["create"]),
            ("google_compute_network.someone_elses", ["create"]),
        ),
        "--expect-prefix",
        "snapshots",
    )
    assert result.returncode == 1
    assert "someone_elses" in result.stderr


def test_indexed_addresses_are_matched_on_the_resource_name() -> None:
    """`google_project_service.enabled["compute.googleapis.com"]` -> `enabled`."""
    plan = _plan(
        ('google_project_service.enabled["compute.googleapis.com"]', ["create"])
    )
    assert _run(plan, "--expect-prefix", "enabled").returncode == 0
    assert _run(plan, "--expect-prefix", "nope").returncode == 1


def test_resource_type_is_extracted_for_the_type_tally() -> None:
    assert mod.resource_type("google_storage_bucket.ops") == "google_storage_bucket"
    assert (
        mod.resource_type('google_project_service.enabled["compute.googleapis.com"]')
        == "google_project_service"
    )
    assert (
        mod.resource_type("module.net.google_compute_network.exe")
        == "google_compute_network"
    )


def test_an_empty_plan_is_reported_as_zero_not_as_success_noise() -> None:
    result = _run(json.dumps({"resource_changes": []}), "--creates-only")
    assert result.returncode == 0
    assert "0 resource change(s)" in result.stdout
