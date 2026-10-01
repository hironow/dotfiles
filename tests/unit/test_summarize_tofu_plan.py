"""Unit tests for scripts/summarize_tofu_plan.py.

Reviewing a plan against a private project is the single most likely way for one
of its identifiers to escape into a public repo: the normal workflow is read the
plan, paste the interesting part somewhere. So the summariser prints CONFIG
ADDRESSES and nothing else, and the first test below is the one that matters --
no attribute value from the plan may appear in its output, ever.

The other half is the questions worth asking before an apply on a SHARED
project: is this plan create-only (an update or delete means it is touching
something that already exists, most likely a name collision with a neighbouring
stack), does every address belong to the stack under review, and -- once the
stack is past its first apply and a plan legitimately contains updates -- is the
set of changes EXACTLY the set that was reviewed.

That last one is `--expect-changes`, and it has to fail in both directions. An
unexpected change is the obvious danger. A silently ABSENT expected change is the
quieter one: the reviewer approved "the cluster gets deletion protection and the
L2 job appears", the plan contained only the job, and nobody noticed that half of
what was signed off never happened.
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
        encoding="utf-8",
        errors="replace",
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


def test_a_plan_that_is_not_an_object_is_a_type_error() -> None:
    with pytest.raises(TypeError, match="object"):
        mod.load_plan("[]")


# --- --expect-changes -------------------------------------------------------
#
# The gate for a plan that legitimately contains updates, which `--creates-only`
# cannot review at all: it would reject the whole plan for containing the one
# update the reviewer asked for. An expectation file names each change as the
# `<action> <address>` pair the summary already prints, so what gets approved is
# literally what gets asserted.
#
# Addresses are what the .tf files chose, so an expectation file is as public as
# the config -- no identifier can reach it, which is why this gate can be tracked
# while the plan it checks cannot.


def _expect_file(tmp_path: Path, body: str) -> str:
    path = tmp_path / "expected-changes.txt"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_expect_changes_accepts_an_exact_match(tmp_path: Path) -> None:
    result = _run(
        _plan(
            ("google_cloud_run_v2_job.l2_enforcer", ["create"]),
            ("google_container_cluster.exe", ["update"]),
        ),
        "--expect-changes",
        _expect_file(
            tmp_path,
            "+ google_cloud_run_v2_job.l2_enforcer\n~ google_container_cluster.exe\n",
        ),
    )
    assert result.returncode == 0, result.stderr


def test_expect_changes_names_a_change_nobody_asked_for(tmp_path: Path) -> None:
    """The danger case: something in the plan that was never reviewed."""
    result = _run(
        _plan(
            ("google_cloud_run_v2_job.l2_enforcer", ["create"]),
            ("google_storage_bucket.snapshots", ["delete"]),
        ),
        "--expect-changes",
        _expect_file(tmp_path, "+ google_cloud_run_v2_job.l2_enforcer\n"),
    )
    assert result.returncode == 1
    assert "google_storage_bucket.snapshots" in result.stderr
    # ...and it must not merely say "3 unexpected": the address is the finding.
    assert "google_cloud_run_v2_job.l2_enforcer" not in result.stderr


def test_expect_changes_names_an_expected_change_that_is_not_happening(
    tmp_path: Path,
) -> None:
    """The quiet case: half of what was approved is silently absent."""
    result = _run(
        _plan(("google_cloud_run_v2_job.l2_enforcer", ["create"])),
        "--expect-changes",
        _expect_file(
            tmp_path,
            "+ google_cloud_run_v2_job.l2_enforcer\n~ google_container_cluster.exe\n",
        ),
    )
    assert result.returncode == 1
    assert "google_container_cluster.exe" in result.stderr


def test_expect_changes_matches_on_the_action_too(tmp_path: Path) -> None:
    """An address alone is not the approval; `~` where `+` was expected is news."""
    result = _run(
        _plan(("google_container_cluster.exe", ["delete", "create"])),
        "--expect-changes",
        _expect_file(tmp_path, "~ google_container_cluster.exe\n"),
    )
    assert result.returncode == 1
    assert "-/+ google_container_cluster.exe" in result.stderr
    assert "~ google_container_cluster.exe" in result.stderr


def test_expect_changes_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    body = """\
# Phase 3 plan, reviewed 2026-09-27.

# L2 -- the out-of-cluster enforcer and its tick.
+ google_cloud_run_v2_job.l2_enforcer
+ google_cloud_scheduler_job.l2_tick

   # indented comment, and trailing whitespace on the next line
~ google_container_cluster.exe

"""
    result = _run(
        _plan(
            ("google_cloud_run_v2_job.l2_enforcer", ["create"]),
            ("google_cloud_scheduler_job.l2_tick", ["create"]),
            ("google_container_cluster.exe", ["update"]),
        ),
        "--expect-changes",
        _expect_file(tmp_path, body),
    )
    assert result.returncode == 0, result.stderr


def test_expect_changes_reports_an_indexed_address_verbatim(tmp_path: Path) -> None:
    """for_each instances are listed one per line, on purpose: each is a change."""
    address = 'google_project_service.enabled["run.googleapis.com"]'
    result = _run(
        _plan((address, ["create"])),
        "--expect-changes",
        _expect_file(tmp_path, f"+ {address}\n"),
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    ("bad_line", "needle"),
    [
        ("google_container_cluster.exe", "google_container_cluster.exe"),
        ("~", "~"),
        ("? google_container_cluster.exe", "?"),
        ("~ google_container_cluster.exe extra", "extra"),
    ],
)
def test_expect_changes_rejects_a_malformed_line(
    tmp_path: Path, bad_line: str, needle: str
) -> None:
    result = _run(
        _plan(("google_container_cluster.exe", ["update"])),
        "--expect-changes",
        _expect_file(tmp_path, f"# header\n{bad_line}\n"),
    )
    assert result.returncode == 1
    # The line NUMBER is the point -- an expectation file is edited by hand.
    assert "line 2" in result.stderr
    assert needle in result.stderr


def test_expect_changes_reports_a_missing_expectation_file(tmp_path: Path) -> None:
    result = _run(
        _plan(("google_container_cluster.exe", ["update"])),
        "--expect-changes",
        str(tmp_path / "nope.txt"),
    )
    assert result.returncode == 1
    assert "nope.txt" in result.stderr


def test_expect_changes_still_prints_no_attribute_values(tmp_path: Path) -> None:
    """The one property that must survive every new mode."""
    result = _run(
        _plan(("google_container_cluster.exe", ["update"])),
        "--expect-changes",
        _expect_file(tmp_path, "+ google_storage_bucket.snapshots\n"),
    )
    assert result.returncode == 1
    assert SECRET_VALUE not in result.stdout + result.stderr


def test_expect_changes_parser_is_exercisable_on_its_own() -> None:
    parsed = mod.parse_expectations("# c\n\n+ a.b\n~ c.d\n", "expected.txt")
    assert parsed == {("+", "a.b"), ("~", "c.d")}
    with pytest.raises(mod.ExpectationError) as excinfo:
        mod.parse_expectations("+ a.b\nnonsense\n", "expected.txt")
    assert "expected.txt" in str(excinfo.value)
    assert "line 2" in str(excinfo.value)
