"""Static invariants for the tofu/exe stack_mode (mothball) design.

Why text-level assertions: `tofu validate` does not evaluate values and
no CI gate plans the tofu/exe config, so the two classes of bug this
design can regress into are invisible to existing gates:

1. an output that interpolates a counted resource attribute directly in
   a string template ("http://${resource.attr}") evaluates to an error
   when count=0 — plan breaks only in mothballed mode (verified against
   OpenTofu 1.12: "Cannot include a null value in a string template");
2. a mode-gating expression (count / activation_policy) silently dropped
   or inverted flips live infra on the next apply.

These tests pin the shape of the HCL and the justfile transition
recipes. See ADR 0034 and exe/docs/runbook.md § Mothball / wake.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
TOFU_EXE: Path = REPO_ROOT / "tofu" / "exe"

COUNT_GATE: str = 'count = var.stack_mode == "active" ? 1 : 0'


def _read(name: str) -> str:
    return (TOFU_EXE / name).read_text(encoding="utf-8")


def _block(text: str, header: str) -> str:
    """Return the body of the top-level HCL block whose opening line
    matches ``header`` (regex, anchored at line start), brace-balanced."""
    match = re.search(rf"^{header}\s*\{{", text, flags=re.MULTILINE)
    assert match, f"block not found: {header}"
    depth = 0
    for i in range(match.end() - 1, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[match.start() : i + 1]
    raise AssertionError(f"unbalanced braces after: {header}")


# ----- stack_mode variable -------------------------------------------


def test_stack_mode_variable_has_no_default_and_validates_modes() -> None:
    block = _block(_read("variables.tf"), r'variable "stack_mode"')
    assert not re.search(r"^\s*default\s*=", block, flags=re.MULTILINE), (
        "stack_mode must have NO default: the operator states intent in tfvars"
    )
    assert '"active"' in block and '"mothballed"' in block
    assert "validation" in block


# ----- mode gating: count on VM / uptime / alert ---------------------


def test_control_plane_vm_is_gated_on_stack_mode() -> None:
    block = _block(_read("coder.tf"), r'resource "google_compute_instance" "exe_coder"')
    assert COUNT_GATE in block


def test_uptime_check_and_alert_are_gated_on_stack_mode() -> None:
    monitoring = _read("monitoring.tf")
    uptime = _block(
        monitoring,
        r'resource "google_monitoring_uptime_check_config" "exe_coder_healthz"',
    )
    alert = _block(
        monitoring,
        r'resource "google_monitoring_alert_policy" "exe_coder_healthz_down"',
    )
    assert COUNT_GATE in uptime
    assert COUNT_GATE in alert


def test_alert_filter_references_indexed_uptime_check() -> None:
    alert = _block(
        _read("monitoring.tf"),
        r'resource "google_monitoring_alert_policy" "exe_coder_healthz_down"',
    )
    assert (
        "google_monitoring_uptime_check_config.exe_coder_healthz[0].uptime_check_id"
        in alert
    )


# ----- Cloud SQL activation derived from stack_mode ------------------


def test_cloud_sql_activation_policy_derived_from_stack_mode() -> None:
    instance = _block(
        _read("cloudsql.tf"), r'resource "google_sql_database_instance" "coder"'
    )
    assert (
        'activation_policy = var.stack_mode == "active" ? "ALWAYS" : "NEVER"'
        in instance
    )


# ----- outputs must be null-safe when count=0 ------------------------


def test_outputs_never_dereference_counted_resources_directly() -> None:
    outputs = _read("outputs.tf")
    for counted in (
        r"google_compute_instance\.exe_coder\.",
        r"google_monitoring_uptime_check_config\.exe_coder_healthz\.",
        r"google_monitoring_alert_policy\.exe_coder_healthz_down\.",
    ):
        hits = re.findall(counted, outputs)
        assert not hits, (
            f"direct attribute access on counted resource ({counted}): "
            "use one(resource[*].attr) or one([for i in resource : ...]) — "
            "direct access breaks plan when count=0"
        )


def test_coder_internal_url_uses_null_safe_comprehension() -> None:
    # `"http://${one(...[*].name)}:7080"` is NOT safe: one() returns null
    # at count=0 and null cannot be interpolated into a string template.
    block = _block(_read("outputs.tf"), r'output "coder_internal_url"')
    assert re.search(r"one\(\s*\[\s*for\s", block), (
        "coder_internal_url must build the URL inside a comprehension, "
        'e.g. one([for i in google_compute_instance.exe_coder : "http://${i.name}:7080"])'
    )


# ----- Artifact Registry retention (ADR 0034) ------------------------


def test_ar_cleanup_keeps_three_recent_plus_main_and_deletes_stale() -> None:
    repo = _block(
        _read("artifact_registry.tf"),
        r'resource "google_artifact_registry_repository" "dotfiles"',
    )
    assert "keep_count = 3" in repo
    # main must survive even when no push happens for >30 days —
    # workspaces pull :main, so deleting it breaks workspace creation.
    assert '"keep-main-tag"' in repo
    assert 'tag_prefixes = ["main"]' in repo
    assert '"delete-stale"' in repo
    assert 'tag_state  = "ANY"' in repo
    assert '"2592000s"' in repo


# ----- justfile transition recipes ------------------------------------


def test_justfile_defines_mothball_transition_recipes() -> None:
    justfile = (REPO_ROOT / "justfile").read_text(encoding="utf-8")
    targets = re.search(
        r'^_exe_mothball_targets\s*:=\s*"(?P<v>[^"]+)"', justfile, flags=re.MULTILINE
    )
    assert targets, "_exe_mothball_targets missing"
    for target in (
        "-target=google_sql_database_instance.coder",
        "-target=google_artifact_registry_repository.dotfiles",
        "-target=google_monitoring_uptime_check_config.exe_coder_healthz",
        "-target=google_monitoring_alert_policy.exe_coder_healthz_down",
    ):
        assert target in targets.group("v")
    assert re.search(r"^exe-plan-mothball:", justfile, flags=re.MULTILINE)
    assert re.search(r"^exe-apply-mothball:", justfile, flags=re.MULTILINE)
    assert re.search(r"^exe-apply-wake:", justfile, flags=re.MULTILINE)
    # plan is written to a file and apply consumes that exact file, so
    # what was reviewed is what is applied.
    assert "-out=mothball.tfplan" in justfile
    assert "tofu apply mothball.tfplan" in justfile


def test_tfvars_example_documents_stack_mode() -> None:
    example = _read("terraform.tfvars.example")
    assert "stack_mode" in example
