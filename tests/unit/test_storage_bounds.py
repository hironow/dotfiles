"""Unit tests for scripts/check_storage_bounds.py.

Every storage sink in a personal GCP project needs an explicitly declared
bound, because an unbounded sink is how a project quietly accumulates cost: no
alert fires, nothing breaks, the bill just grows. Artifact Registry makes that
worse with two traps that read as protection and are not -- KEEP beats DELETE
when both policies match a version, and `most_recent_versions` is a floor, not
a cap, so a repository whose only policy is a `most_recent_versions` KEEP
deletes nothing at all. Google also rejects a policy block that mixes a
`condition` with `most_recent_versions`, which turns a plausible-looking
consolidation into an apply-time error.

So the gate reads the HCL instead of trusting the review that wrote it. These
tests drive the pure functions directly and exercise every rule in both
directions: the compliant shape must pass, and the broken shape must be flagged
with a message that names the specific trap. The fixtures are real `.tf` files
written under tmp_path -- no filesystem mocks, no provider, no network.

The parser tests matter as much as the rules. A block scanner that loses brace
depth inside a string, a comment or a heredoc does not fail loudly; it stops
seeing resources and reports a clean scan, which is the one failure mode this
gate cannot afford. Hence the fixtures that hide an unbalanced `{` in a string,
a `}` in a comment and a `{` in a heredoc, each followed by a genuinely broken
bucket that must still be caught.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_storage_bounds.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_storage_bounds", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


# --- fixtures ---------------------------------------------------------------


def _policy(policy_id: str, action: str, inner: str) -> str:
    """One cleanup policy block, spelled the way the provider spells it."""
    return (
        "  cleanup_policies {\n"
        f'    id     = "{policy_id}"\n'
        f'    action = "{action}"\n'
        f"{inner}"
        "  }\n"
    )


_KEEP_TAGGED = _policy(
    "keep-inuse",
    "KEEP",
    '    condition {\n      tag_state    = "TAGGED"\n'
    '      tag_prefixes = ["inuse-"]\n    }\n',
)
_KEEP_RECENT = _policy(
    "keep-recent",
    "KEEP",
    "    most_recent_versions {\n      keep_count = 2\n    }\n",
)
_DELETE_OLD = _policy(
    "delete-stale",
    "DELETE",
    '    condition {\n      older_than = "1209600s"\n    }\n',
)
_MIXED_KEEP = _policy(
    "keep-mixed",
    "KEEP",
    '    condition {\n      tag_state = "TAGGED"\n    }\n'
    "    most_recent_versions {\n      keep_count = 2\n    }\n",
)


def _repository(
    *,
    label: str = "task",
    dry_run: str | None = "false",
    policies: Sequence[str] = (_KEEP_TAGGED, _KEEP_RECENT, _DELETE_OLD),
    extra: str = "",
) -> str:
    """An Artifact Registry repository; every knob a rule covers is a parameter."""
    body = f'resource "google_artifact_registry_repository" "{label}" {{\n'
    body += f'  repository_id = "exe-{label}"\n'
    body += '  format        = "DOCKER"\n'
    if dry_run is not None:
        body += f"  cleanup_policy_dry_run = {dry_run}\n"
    return body + extra + "".join(policies) + "}\n"


_DELETE_RULE = (
    "  lifecycle_rule {\n"
    '    action {\n      type = "Delete"\n    }\n'
    "    condition {\n      age = 30\n    }\n"
    "  }\n"
)
_GENERATION_RULE = (
    "  lifecycle_rule {\n"
    '    action {\n      type          = "SetStorageClass"\n'
    '      storage_class = "NEARLINE"\n    }\n'
    "    condition {\n      num_newer_versions = 5\n    }\n"
    "  }\n"
)


def _bucket(
    *,
    label: str = "ops",
    name: str | None = '"exe-ops"',
    ubla: str | None = "true",
    public_access: str | None = '"enforced"',
    soft_delete: str | None = "0",
    rules: Sequence[str] = (_DELETE_RULE,),
    extra: str = "",
) -> str:
    """A GCS bucket; `None` omits the attribute or block entirely."""
    body = f'resource "google_storage_bucket" "{label}" {{\n'
    if name is not None:
        body += f"  name     = {name}\n"
    body += '  location = "US"\n'
    if ubla is not None:
        body += f"  uniform_bucket_level_access = {ubla}\n"
    if public_access is not None:
        body += f"  public_access_prevention    = {public_access}\n"
    if soft_delete is not None:
        body += (
            "  soft_delete_policy {\n"
            f"    retention_duration_seconds = {soft_delete}\n"
            "  }\n"
        )
    return body + extra + "".join(rules) + "}\n"


def _scan(root: Path, body: str, rel: str = "tofu/exe-test/main.tf") -> Any:
    """Write `body` as a real .tf under `root` and scan the tree."""
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return mod.scan_tofu(root)


def _violations(root: Path, body: str) -> list[str]:
    return list(_scan(root, body).violations)


def _flagged(violations: Sequence[str], needle: str) -> bool:
    return any(needle in violation for violation in violations)


# --- rule 1: cleanup_policy_dry_run must be present and false ---------------


def test_compliant_repository_is_clean(tmp_path: Path) -> None:
    """The exe-task shape from the plan: tag KEEP + version KEEP + age DELETE."""
    assert _violations(tmp_path, _repository()) == []


def test_repository_without_cleanup_policy_dry_run_is_flagged(tmp_path: Path) -> None:
    violations = _violations(tmp_path, _repository(dry_run=None))
    assert _flagged(violations, "cleanup_policy_dry_run")
    assert _flagged(violations, "absent")


def test_repository_with_dry_run_true_is_flagged(tmp_path: Path) -> None:
    """dry-run leaves every policy inert, so the declared bound is fiction."""
    violations = _violations(tmp_path, _repository(dry_run="true"))
    assert _flagged(violations, "cleanup_policy_dry_run")


def test_repository_dry_run_from_a_variable_cannot_be_evaluated(
    tmp_path: Path,
) -> None:
    violations = _violations(tmp_path, _repository(dry_run="var.dry_run"))
    assert _flagged(violations, "cannot evaluate")
    assert _flagged(violations, "cleanup_policy_dry_run")


# --- rules 2, 3, 5: a DELETE policy and a KEEP policy ------------------------


def test_repository_without_a_delete_policy_is_flagged(tmp_path: Path) -> None:
    violations = _violations(tmp_path, _repository(policies=(_KEEP_TAGGED,)))
    assert _flagged(violations, 'action = "DELETE"')


def test_repository_without_a_keep_policy_is_flagged(tmp_path: Path) -> None:
    """Without a KEEP, the in-use tag has nothing protecting it from DELETE."""
    violations = _violations(tmp_path, _repository(policies=(_DELETE_OLD,)))
    assert _flagged(violations, 'action = "KEEP"')


def test_repository_with_no_policies_at_all_is_flagged(tmp_path: Path) -> None:
    violations = _violations(tmp_path, _repository(policies=()))
    assert _flagged(violations, 'action = "DELETE"')
    assert _flagged(violations, 'action = "KEEP"')


def test_most_recent_versions_keep_alone_names_the_floor_trap(
    tmp_path: Path,
) -> None:
    """keep_count is a floor: with no DELETE the repository deletes nothing."""
    violations = _violations(tmp_path, _repository(policies=(_KEEP_RECENT,)))
    assert _flagged(violations, "floor, not a cap")
    assert _flagged(violations, "deletes nothing")


def test_most_recent_versions_keep_with_a_delete_is_clean(tmp_path: Path) -> None:
    """The exe-platform shape: a version floor plus an age-based DELETE."""
    body = _repository(policies=(_KEEP_RECENT, _DELETE_OLD))
    assert _violations(tmp_path, body) == []


# --- rule 4: condition and most_recent_versions never share a policy --------


def test_policy_mixing_condition_and_most_recent_versions_is_flagged(
    tmp_path: Path,
) -> None:
    """Artifact Registry rejects the mix, so tofu apply fails, not tofu plan."""
    body = _repository(policies=(_MIXED_KEEP, _DELETE_OLD))
    violations = _violations(tmp_path, body)
    assert _flagged(violations, "most_recent_versions")
    assert _flagged(violations, "condition")
    assert _flagged(violations, "keep-mixed")


def test_condition_and_most_recent_versions_in_separate_policies_are_clean(
    tmp_path: Path,
) -> None:
    body = _repository(policies=(_KEEP_TAGGED, _KEEP_RECENT, _DELETE_OLD))
    assert _violations(tmp_path, body) == []


# --- rule 6: the per-repository policy limit --------------------------------


def test_ten_cleanup_policies_are_within_the_limit(tmp_path: Path) -> None:
    assert mod.MAX_CLEANUP_POLICIES == 10
    policies = [_policy(f"keep-{n}", "KEEP", "") for n in range(9)]
    body = _repository(policies=[*policies, _DELETE_OLD])
    assert _violations(tmp_path, body) == []


def test_eleven_cleanup_policies_are_flagged_with_the_limit(tmp_path: Path) -> None:
    policies = [_policy(f"keep-{n}", "KEEP", "") for n in range(10)]
    body = _repository(policies=[*policies, _DELETE_OLD])
    violations = _violations(tmp_path, body)
    assert _flagged(violations, "11")
    assert _flagged(violations, str(mod.MAX_CLEANUP_POLICIES))


# --- rule 7: uniform bucket level access ------------------------------------


def test_compliant_bucket_is_clean(tmp_path: Path) -> None:
    assert _violations(tmp_path, _bucket()) == []


def test_bucket_without_uniform_bucket_level_access_is_flagged(
    tmp_path: Path,
) -> None:
    violations = _violations(tmp_path, _bucket(ubla=None))
    assert _flagged(violations, "uniform_bucket_level_access")


def test_bucket_with_uniform_bucket_level_access_false_is_flagged(
    tmp_path: Path,
) -> None:
    violations = _violations(tmp_path, _bucket(ubla="false"))
    assert _flagged(violations, "uniform_bucket_level_access")


def test_bucket_ubla_from_a_variable_cannot_be_evaluated(tmp_path: Path) -> None:
    """An unevaluatable bound is an unproven bound, never a silent pass."""
    violations = _violations(tmp_path, _bucket(ubla="var.ubla"))
    assert _flagged(violations, "cannot evaluate")
    assert _flagged(violations, "uniform_bucket_level_access")
    assert _flagged(violations, "var.ubla")


# --- rule 8: public access prevention ---------------------------------------


def test_bucket_without_public_access_prevention_is_flagged(tmp_path: Path) -> None:
    violations = _violations(tmp_path, _bucket(public_access=None))
    assert _flagged(violations, "public_access_prevention")


def test_bucket_with_inherited_public_access_prevention_is_flagged(
    tmp_path: Path,
) -> None:
    violations = _violations(tmp_path, _bucket(public_access='"inherited"'))
    assert _flagged(violations, "public_access_prevention")
    assert _flagged(violations, "enforced")


# --- rule 9: soft delete is billed storage nobody asked for -----------------


def test_bucket_without_a_soft_delete_policy_is_flagged(tmp_path: Path) -> None:
    violations = _violations(tmp_path, _bucket(soft_delete=None))
    assert _flagged(violations, "soft_delete_policy")


def test_bucket_with_the_default_seven_day_soft_delete_is_flagged(
    tmp_path: Path,
) -> None:
    violations = _violations(tmp_path, _bucket(soft_delete="604800"))
    assert _flagged(violations, "retention_duration_seconds")
    assert _flagged(violations, "604800")


def test_bucket_soft_delete_from_a_variable_cannot_be_evaluated(
    tmp_path: Path,
) -> None:
    violations = _violations(tmp_path, _bucket(soft_delete="var.soft_delete"))
    assert _flagged(violations, "cannot evaluate")
    assert _flagged(violations, "retention_duration_seconds")


# --- rule 10: every non-snapshot bucket carries a bound ---------------------


def test_bucket_without_any_lifecycle_rule_is_flagged(tmp_path: Path) -> None:
    violations = _violations(tmp_path, _bucket(rules=()))
    assert _flagged(violations, "unbounded")


def test_bucket_bounded_only_by_num_newer_versions_is_clean(tmp_path: Path) -> None:
    """A generation cap is a bound even when the action is not Delete."""
    body = _bucket(rules=(_GENERATION_RULE,))
    assert _violations(tmp_path, body) == []


def test_bucket_bounded_only_by_a_non_delete_rule_is_flagged(tmp_path: Path) -> None:
    """A storage-class transition alone bounds cost nowhere: it still accrues."""
    rule = (
        "  lifecycle_rule {\n"
        '    action {\n      type          = "SetStorageClass"\n'
        '      storage_class = "COLDLINE"\n    }\n'
        "    condition {\n      age = 90\n    }\n"
        "  }\n"
    )
    violations = _violations(tmp_path, _bucket(rules=(rule,)))
    assert _flagged(violations, "unbounded")


# --- rule 11: the snapshot exception, both directions ----------------------


def test_snapshot_bucket_without_a_delete_lifecycle_is_clean(tmp_path: Path) -> None:
    """Substrate GCs unreferenced snapshots; a lifecycle rule cannot tell."""
    body = _bucket(label="snapshots", name='"exe-snapshots"', rules=())
    assert _violations(tmp_path, body) == []


def test_snapshot_bucket_with_a_delete_lifecycle_is_flagged(tmp_path: Path) -> None:
    body = _bucket(label="snapshots", name='"exe-snapshots"', rules=(_DELETE_RULE,))
    violations = _violations(tmp_path, body)
    assert _flagged(violations, "snapshot")
    assert _flagged(violations, "resume")


def test_snapshot_bucket_recognised_by_its_name_attribute_is_flagged(
    tmp_path: Path,
) -> None:
    """The resource label need not say it; the bucket name is enough."""
    body = _bucket(label="archive", name='"exe-Snapshot-store"', rules=(_DELETE_RULE,))
    violations = _violations(tmp_path, body)
    assert _flagged(violations, "snapshot")


def test_snapshot_markers_match_case_insensitively() -> None:
    assert mod.SNAPSHOT_BUCKET_MARKERS == ("snapshot",)
    assert mod.is_snapshot_bucket("exe_SNAPSHOTS", None)
    assert mod.is_snapshot_bucket("archive", '"exe-Snapshots"')
    assert not mod.is_snapshot_bucket("ops", '"exe-ops"')
    assert not mod.is_snapshot_bucket("ops", None)


# --- the block scanner: strings, comments, heredocs -------------------------


def test_brace_inside_a_double_quoted_string_does_not_break_detection(
    tmp_path: Path,
) -> None:
    """An unbalanced `{` in a string must not shift depth and hide what follows."""
    body = (
        _bucket(extra='  labels = { note = "unbalanced { brace" }\n')
        + "\n"
        + _bucket(label="broken", name='"exe-broken"', ubla="false")
    )
    result = _scan(tmp_path, body)
    assert result.buckets == 2
    assert _flagged(result.violations, "uniform_bucket_level_access")


def test_hash_comment_containing_a_brace_does_not_break_detection(
    tmp_path: Path,
) -> None:
    body = (
        _bucket(extra="  # a stray } lives in this comment\n")
        + "\n"
        + _bucket(label="broken", name='"exe-broken"', ubla="false")
    )
    result = _scan(tmp_path, body)
    assert result.buckets == 2
    assert _flagged(result.violations, "uniform_bucket_level_access")


def test_heredoc_containing_braces_does_not_break_detection(
    tmp_path: Path,
) -> None:
    """Startup scripts live in heredocs, and shell braces are rarely balanced."""
    body = (
        'resource "google_storage_bucket_object" "script" {\n'
        '  name    = "startup.sh"\n'
        "  content = <<-EOT\n"
        "    if true; then printf '{'\n"
        "    # a } in the script body\n"
        "  EOT\n"
        "}\n\n" + _bucket(label="broken", name='"exe-broken"', ubla="false")
    )
    result = _scan(tmp_path, body)
    assert result.buckets == 1
    assert _flagged(result.violations, "uniform_bucket_level_access")


def test_commented_out_cleanup_policy_does_not_count(tmp_path: Path) -> None:
    """A policy in a comment protects nothing, so it must not satisfy a rule."""
    commented = (
        "  # cleanup_policies {\n"
        '  #   id     = "keep-recent"\n'
        '  #   action = "KEEP"\n'
        "  #   most_recent_versions {\n"
        "  #     keep_count = 2\n"
        "  #   }\n"
        "  # }\n"
    )
    body = _repository(policies=(_DELETE_OLD,), extra=commented)
    violations = _violations(tmp_path, body)
    assert _flagged(violations, 'action = "KEEP"')


def test_block_commented_out_policy_does_not_count(tmp_path: Path) -> None:
    """Same for a /* */ block comment, which spans the braces it contains."""
    commented = (
        "  /* cleanup_policies {\n"
        '       id     = "keep-recent"\n'
        '       action = "KEEP"\n'
        "       most_recent_versions { keep_count = 2 }\n"
        "     } */\n"
    )
    body = _repository(policies=(_DELETE_OLD,), extra=commented)
    violations = _violations(tmp_path, body)
    assert _flagged(violations, 'action = "KEEP"')


def test_double_slash_comment_does_not_hide_a_resource(tmp_path: Path) -> None:
    body = "// cleanup note: the bucket below is deliberately broken }\n" + _bucket(
        label="broken", name='"exe-broken"', ubla="false"
    )
    result = _scan(tmp_path, body)
    assert result.buckets == 1
    assert _flagged(result.violations, "uniform_bucket_level_access")


def test_url_in_a_string_is_not_read_as_a_comment(tmp_path: Path) -> None:
    """The `//` of https:// must not swallow the rest of the line."""
    body = _bucket(
        extra='  labels = { doc = "https://cloud.google.com/storage" }\n',
        ubla="false",
    )
    result = _scan(tmp_path, body)
    assert result.buckets == 1
    assert _flagged(result.violations, "uniform_bucket_level_access")


# --- scanning the tree ------------------------------------------------------


def test_nested_stack_directories_are_scanned(tmp_path: Path) -> None:
    body = _bucket(ubla="false")
    result = _scan(tmp_path, body, rel="tofu/exe-cluster/modules/state/main.tf")
    assert result.buckets == 1
    assert _flagged(result.violations, "uniform_bucket_level_access")


def test_tf_files_outside_tofu_are_not_scanned(tmp_path: Path) -> None:
    result = _scan(tmp_path, _bucket(ubla="false"), rel="templates/example/main.tf")
    assert result.buckets == 0
    assert result.violations == []


def test_zero_sinks_is_clean_but_says_so(tmp_path: Path) -> None:
    """An empty scan must never read as a passing one."""
    result = mod.scan_tofu(tmp_path)
    assert result.violations == []
    assert result.repositories == 0
    assert result.buckets == 0
    assert "no storage sinks" in mod.summary_line(result)


def test_summary_counts_both_sink_kinds(tmp_path: Path) -> None:
    result = _scan(tmp_path, _repository() + "\n" + _bucket())
    assert result.repositories == 1
    assert result.buckets == 1
    summary = mod.summary_line(result)
    assert "1 repositor" in summary
    assert "1 bucket" in summary


def test_violations_name_the_file_and_the_resource(tmp_path: Path) -> None:
    violations = _violations(tmp_path, _bucket(label="ops", ubla="false"))
    assert _flagged(violations, "tofu/exe-test/main.tf")
    assert _flagged(violations, 'google_storage_bucket "ops"')


def test_unreadable_tf_file_is_a_violation_not_a_silent_skip(tmp_path: Path) -> None:
    """A file the scanner cannot decode is an unchecked sink, so it must fail."""
    path = tmp_path / "tofu" / "exe-test" / "main.tf"
    path.parent.mkdir(parents=True)
    path.write_bytes(
        b'resource "google_storage_bucket" "b" {\n  name = "\xff\xfe"\n}\n'
    )
    result = mod.scan_tofu(tmp_path)
    assert result.violations


# --- the real repo must pass the gate --------------------------------------


def test_real_repo_passes_the_gate() -> None:
    """Whatever tofu/ holds today must already be bounded (zero sinks is OK)."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("check-storage-bounds: OK")
