"""Unit tests for scripts/check_exe_pins.py.

The exe/ax migration pins three things that must move together: the google/ax
release, the Agent Substrate release (whose version string is also stamped on
every node as a Kubernetes label value), and the GKE release channel + cluster
minor. Nothing in the toolchain couples them -- OpenTofu plans just as happily
with a hardcoded "v0.1.0" in one stack and a jsondecode() of exe/versions.json
in another, `tofu validate` never evaluates values, and a stale literal does not
fail anything: it surfaces much later as a node whose substrate-version label
no longer matches what the selector looks for.

exe/versions.json is therefore declared the single pin source, and this gate is
what makes the declaration true. It pins the file's schema (a typo must not be
able to create a second pin), rejects any second substrate version literal in
it, rejects a patch-level GKE pin (GKE owns patches, we own the minor), holds
0.x providers to dependency class 2 (cooldown + changelog), greps every
existing tofu stack for a hardcoded pin or a missing jsondecode() reference, and
holds the mise ax pin -- the one copy of the tag the toolchain cannot read out
of a JSON file -- equal to ax.version.

Fixtures are real files under tmp_path -- no filesystem mocks. The upstream SHA
comparison takes a resolver argument so the gate never depends on the network:
the resolver main() passes is offline unless EXE_PINS_VERIFY_UPSTREAM=1, and
these tests pass pure stubs instead.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "check_exe_pins.py"
_REAL_PINS = _REPO_ROOT / "exe" / "versions.json"
_REAL_MISE_CONFIG = _REPO_ROOT / "config" / "mise" / "config.toml"

AX_SHA = "e70162a34037c221fe6fadefd98308c05a4ad8f3"
SUBSTRATE_SHA = "fa6d949685a6318940a9a0195c867c864009b820"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_exe_pins", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def _pins() -> dict[str, Any]:
    """A known-good pin document, freshly copied so tests can mutate it."""
    return copy.deepcopy(
        {
            "_source_of_truth": "the only place the exe pins live",
            "ax": {
                "version": "v0.3.1",
                "repo": "github.com/google/ax",
                "sha": AX_SHA,
            },
            "substrate": {
                "version": "v0.1.0",
                "repo": "github.com/agent-substrate/substrate",
                "sha": SUBSTRATE_SHA,
                "version_label_key": "ate.dev/substrate-version",
                "version_label_value": "v0.1.0",
                "_ax_gomod_pseudoversion_commit": "672533541dbf",
                "_ax_gomod_note": "go.mod commit diverges from tag v0.1.0",
            },
            "gke": {"release_channel": "RAPID", "cluster_minor": "1.37"},
            "providers": {"ko-build/ko": {"version": "0.0.21", "dependency_class": 2}},
            "stacks": ["tofu/exe-platform", "tofu/exe-cluster"],
        }
    )


CLEAN_TF = """
locals {
  pins = jsondecode(file("${path.module}/../../exe/versions.json"))
}

resource "null_resource" "node" {
  triggers = {
    substrate = local.pins.substrate.version
    minor     = local.pins.gke.cluster_minor
  }
}
"""


def _write_stack(root: Path, rel: str, body: str) -> Path:
    """Create a synthetic tofu stack dir with one .tf file in it."""
    stack = root / rel
    stack.mkdir(parents=True, exist_ok=True)
    (stack / "main.tf").write_text(body)
    return stack


# --- check 1: schema --------------------------------------------------------


def test_good_pins_pass_the_schema() -> None:
    assert mod.check_schema(_pins()) == []


def test_missing_required_top_level_key_is_flagged() -> None:
    pins = _pins()
    del pins["gke"]
    assert mod.check_schema(pins)


def test_missing_required_substrate_key_is_flagged() -> None:
    pins = _pins()
    del pins["substrate"]["version_label_key"]
    assert mod.check_schema(pins)


def test_unknown_top_level_key_is_flagged() -> None:
    pins = _pins()
    pins["stackz"] = ["tofu/typo"]
    assert mod.check_schema(pins)


def test_unknown_underscore_top_level_key_is_allowed() -> None:
    """`_`-prefixed keys carry prose, so they are never "a second pin"."""
    pins = _pins()
    pins["_note"] = "free-form prose"
    assert mod.check_schema(pins) == []


def test_unknown_key_inside_a_pin_block_is_flagged() -> None:
    pins = _pins()
    pins["ax"]["versoin"] = "v0.3.1"
    assert mod.check_schema(pins)


def test_wrong_type_for_stacks_is_flagged() -> None:
    pins = _pins()
    pins["stacks"] = "tofu/exe-platform"
    assert mod.check_schema(pins)


def test_non_semver_ax_version_is_flagged() -> None:
    pins = _pins()
    pins["ax"]["version"] = "0.3"
    assert mod.check_schema(pins)


# --- check 2: exactly one substrate version reference ----------------------


def test_single_substrate_ref_is_clean() -> None:
    assert mod.check_single_substrate_ref(_pins()) == []


def test_label_value_differing_from_substrate_version_is_flagged() -> None:
    pins = _pins()
    pins["substrate"]["version_label_value"] = "v0.1.1"
    assert mod.check_single_substrate_ref(pins)


def test_stray_second_substrate_version_literal_is_flagged() -> None:
    pins = _pins()
    pins["substrate"]["fallback_version"] = "v0.0.9"
    assert mod.check_single_substrate_ref(pins)


def test_underscore_note_mentioning_the_tag_is_not_a_second_ref() -> None:
    pins = _pins()
    pins["substrate"]["_ax_gomod_note"] = "go.mod diverges from the v0.1.0 tag"
    assert mod.check_single_substrate_ref(pins) == []


# --- check 3: SHA shape, and match against a resolver ----------------------


def test_good_shas_have_a_clean_shape() -> None:
    assert mod.check_sha_shapes(_pins()) == []


def test_thirty_nine_char_sha_is_flagged() -> None:
    pins = _pins()
    pins["ax"]["sha"] = AX_SHA[:-1]
    assert mod.check_sha_shapes(pins)


def test_uppercase_sha_is_flagged() -> None:
    pins = _pins()
    pins["substrate"]["sha"] = SUBSTRATE_SHA.upper()
    assert mod.check_sha_shapes(pins)


def test_non_hex_sha_is_flagged() -> None:
    pins = _pins()
    pins["ax"]["sha"] = "z" * 40
    assert mod.check_sha_shapes(pins)


def _offline_resolver(repo: str, tag: str) -> str | None:
    """Stands in for the network being unavailable (or opt-in not set)."""
    return None


def _disagreeing_resolver(repo: str, tag: str) -> str | None:
    return "0" * 40


def _agreeing_resolver(repo: str, tag: str) -> str | None:
    table = {
        ("github.com/google/ax", "v0.3.1"): AX_SHA,
        ("github.com/agent-substrate/substrate", "v0.1.0"): SUBSTRATE_SHA,
    }
    return table.get((repo, tag))


def test_verify_shas_reports_skipped_when_the_resolver_is_offline() -> None:
    result = mod.verify_shas(_pins(), _offline_resolver)
    assert result.violations == []
    assert len(result.skipped) == 2


def test_verify_shas_flags_a_mismatch() -> None:
    result = mod.verify_shas(_pins(), _disagreeing_resolver)
    assert len(result.violations) == 2
    assert result.skipped == []


def test_verify_shas_is_clean_when_upstream_agrees() -> None:
    result = mod.verify_shas(_pins(), _agreeing_resolver)
    assert result.violations == []
    assert result.skipped == []


def test_default_resolver_is_offline_without_the_opt_in(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("EXE_PINS_VERIFY_UPSTREAM", raising=False)
    assert mod.default_resolver("github.com/google/ax", "v0.3.1") is None


# --- check 4: Kubernetes label validity ------------------------------------


def test_good_label_key_and_value_are_clean() -> None:
    assert mod.check_labels(_pins()) == []


def test_substrate_version_label_key_is_a_valid_label_key() -> None:
    assert mod.is_valid_label_key("ate.dev/substrate-version")


def test_invalid_label_keys_are_rejected() -> None:
    assert not mod.is_valid_label_key("ate.dev/substrate version")
    assert not mod.is_valid_label_key("ate.dev/-substrate")
    assert not mod.is_valid_label_key("ATE.DEV/substrate-version")
    assert not mod.is_valid_label_key("a/b/c")
    assert not mod.is_valid_label_key("ate.dev/" + "a" * 64)
    assert not mod.is_valid_label_key("")


def test_invalid_label_key_in_pins_is_flagged() -> None:
    pins = _pins()
    pins["substrate"]["version_label_key"] = "ate.dev/substrate version"
    assert mod.check_labels(pins)


def test_label_value_over_63_chars_is_rejected() -> None:
    assert mod.is_valid_label_value("v0.1.0")
    assert not mod.is_valid_label_value("v" + "0" * 63)
    assert not mod.is_valid_label_value("v0.1.0-")


def test_invalid_label_value_in_pins_is_flagged() -> None:
    pins = _pins()
    pins["substrate"]["version_label_value"] = "v0.1.0-"
    assert mod.check_labels(pins)


# --- check 5: GKE channel + minor-only pin ---------------------------------


def test_good_gke_pin_is_clean() -> None:
    assert mod.check_gke(_pins()) == []


def test_unknown_release_channel_is_flagged() -> None:
    pins = _pins()
    pins["gke"]["release_channel"] = "rapid"
    assert mod.check_gke(pins)


def test_every_real_release_channel_is_accepted() -> None:
    for channel in ("RAPID", "REGULAR", "STABLE", "EXTENDED"):
        pins = _pins()
        pins["gke"]["release_channel"] = channel
        assert mod.check_gke(pins) == [], channel


def test_patch_level_cluster_minor_is_flagged() -> None:
    """GKE manages patches; pinning one guarantees drift on the next upgrade."""
    pins = _pins()
    pins["gke"]["cluster_minor"] = "1.37.0-gke.3503000"
    assert mod.check_gke(pins)


# --- check 6: dependency class of 0.x providers ---------------------------


def test_zero_x_provider_with_class_two_is_clean() -> None:
    assert mod.check_providers(_pins()) == []


def test_zero_x_provider_with_class_one_is_flagged() -> None:
    pins = _pins()
    pins["providers"]["ko-build/ko"]["dependency_class"] = 1
    assert mod.check_providers(pins)


def test_zero_x_provider_without_a_class_is_flagged() -> None:
    pins = _pins()
    del pins["providers"]["ko-build/ko"]["dependency_class"]
    assert mod.check_providers(pins)


def test_one_x_provider_without_a_class_is_clean() -> None:
    pins = _pins()
    pins["providers"] = {"hashicorp/google": {"version": "7.4.0"}}
    assert mod.check_providers(pins) == []


# --- check 7: every stack resolves the same pin file -----------------------


def test_stack_reading_versions_json_is_clean(tmp_path: Path) -> None:
    pins = _pins()
    pins["stacks"] = ["tofu/exe-platform"]
    _write_stack(tmp_path, "tofu/exe-platform", CLEAN_TF)
    assert mod.check_stacks(tmp_path, pins) == []


def test_stack_hardcoding_the_substrate_version_is_flagged(tmp_path: Path) -> None:
    pins = _pins()
    pins["stacks"] = ["tofu/exe-cluster"]
    _write_stack(
        tmp_path,
        "tofu/exe-cluster",
        CLEAN_TF + '\nvariable "v" {\n  default = "v0.1.0"\n}\n',
    )
    assert mod.check_stacks(tmp_path, pins)


def test_stack_hardcoding_the_cluster_minor_is_flagged(tmp_path: Path) -> None:
    pins = _pins()
    pins["stacks"] = ["tofu/exe-cluster"]
    _write_stack(
        tmp_path,
        "tofu/exe-cluster",
        CLEAN_TF + '\nlocals {\n  minor = "1.37"\n}\n',
    )
    assert mod.check_stacks(tmp_path, pins)


def test_stack_hardcoding_a_pin_in_a_heredoc_is_flagged(tmp_path: Path) -> None:
    """The ate-setup VERSION argument lives in a startup-script heredoc."""
    pins = _pins()
    pins["stacks"] = ["tofu/exe-cluster"]
    body = CLEAN_TF + "\nlocals {\n  script = <<-EOT\n    VERSION=v0.1.0\n  EOT\n}\n"
    _write_stack(tmp_path, "tofu/exe-cluster", body)
    assert mod.check_stacks(tmp_path, pins)


def test_stack_hardcoding_a_pin_inside_a_url_is_flagged(tmp_path: Path) -> None:
    """The '//' of https:// must not be mistaken for the start of a comment.

    A hardcoded release-download URL is the single most likely place for a
    stale substrate version to hide, so the comment stripper has to be
    string-aware or this exact violation goes unseen.
    """
    pins = _pins()
    pins["stacks"] = ["tofu/exe-cluster"]
    body = (
        CLEAN_TF + "\nlocals {\n  url = "
        '"https://github.com/agent-substrate/substrate/releases/download/'
        'v0.1.0/ate-setup"\n}\n'
    )
    _write_stack(tmp_path, "tofu/exe-cluster", body)
    assert mod.check_stacks(tmp_path, pins)


def test_a_comment_mentioning_a_pin_is_not_flagged(tmp_path: Path) -> None:
    """Comments are not evaluated, so they are documentation, not a pin."""
    pins = _pins()
    pins["stacks"] = ["tofu/exe-platform"]
    body = CLEAN_TF + "\n# substrate is pinned at v0.1.0 in exe/versions.json\n"
    _write_stack(tmp_path, "tofu/exe-platform", body)
    assert mod.check_stacks(tmp_path, pins) == []


def test_stack_without_any_jsondecode_reference_is_flagged(tmp_path: Path) -> None:
    pins = _pins()
    pins["stacks"] = ["tofu/exe-platform"]
    _write_stack(tmp_path, "tofu/exe-platform", 'locals {\n  prefix = "exe"\n}\n')
    assert mod.check_stacks(tmp_path, pins)


def test_two_stacks_reading_different_pin_files_are_flagged(tmp_path: Path) -> None:
    pins = _pins()
    pins["stacks"] = ["tofu/exe-platform", "tofu/exe-cluster"]
    _write_stack(tmp_path, "tofu/exe-platform", CLEAN_TF)
    _write_stack(
        tmp_path,
        "tofu/exe-cluster",
        'locals {\n  pins = jsondecode(file("${path.module}/'
        '../../other/exe/versions.json"))\n}\n',
    )
    assert mod.check_stacks(tmp_path, pins)


def test_two_stacks_reading_the_same_pin_file_are_clean(tmp_path: Path) -> None:
    pins = _pins()
    _write_stack(tmp_path, "tofu/exe-platform", CLEAN_TF)
    _write_stack(tmp_path, "tofu/exe-cluster", CLEAN_TF)
    assert mod.check_stacks(tmp_path, pins) == []


def test_declared_stack_that_does_not_exist_yet_is_skipped(tmp_path: Path) -> None:
    """Later phases create the stacks; a declaration alone must not fail."""
    pins = _pins()
    assert mod.check_stacks(tmp_path, pins) == []


def test_empty_stacks_list_is_flagged(tmp_path: Path) -> None:
    pins = _pins()
    pins["stacks"] = []
    assert mod.check_stacks(tmp_path, pins)


# --- check 8: the mise pin mirrors ax.version ------------------------------

MISE_AX_KEY = "go:github.com/google/ax/cmd/ax"


def _write_mise_config(root: Path, body: str) -> Path:
    """Create a synthetic config/mise/config.toml under `root`."""
    path = root / "config" / "mise" / "config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _mise_body(value: str) -> str:
    """A [tools] table declaring the ax CLI as the raw TOML `value`."""
    return f'[tools]\ngo = "latest"\n"{MISE_AX_KEY}" = {value}\n'


def test_mise_bare_string_pin_matching_ax_version_is_clean(tmp_path: Path) -> None:
    config = _write_mise_config(tmp_path, _mise_body('"v0.3.1"'))
    assert mod.check_mise_pin(config, _pins()) == []


def test_mise_table_pin_matching_ax_version_is_clean(tmp_path: Path) -> None:
    """mise's table form carries options (here the os gate) beside the version."""
    config = _write_mise_config(
        tmp_path, _mise_body('{ version = "v0.3.1", os = ["linux", "macos"] }')
    )
    assert mod.check_mise_pin(config, _pins()) == []


def test_mise_list_pin_matching_ax_version_is_clean(tmp_path: Path) -> None:
    """mise also accepts a list of versions; one entry, equal to the pin, is fine."""
    config = _write_mise_config(tmp_path, _mise_body('["v0.3.1"]'))
    assert mod.check_mise_pin(config, _pins()) == []


def test_mise_table_pin_with_a_different_version_is_flagged(tmp_path: Path) -> None:
    config = _write_mise_config(
        tmp_path, _mise_body('{ version = "v0.3.0", os = ["linux", "macos"] }')
    )
    violations = mod.check_mise_pin(config, _pins())
    assert len(violations) == 1
    assert "v0.3.0" in violations[0]
    assert "v0.3.1" in violations[0]
    assert "exe/versions.json" in violations[0]


def test_mise_bare_string_pin_with_a_different_version_is_flagged(
    tmp_path: Path,
) -> None:
    config = _write_mise_config(tmp_path, _mise_body('"v0.2.0"'))
    violations = mod.check_mise_pin(config, _pins())
    assert len(violations) == 1
    assert "v0.2.0" in violations[0]
    assert "v0.3.1" in violations[0]


def test_mise_list_pin_carrying_a_second_version_is_flagged(tmp_path: Path) -> None:
    """A second installed version is a second ax build, so the mirror is broken."""
    config = _write_mise_config(tmp_path, _mise_body('["v0.3.1", "v0.2.0"]'))
    violations = mod.check_mise_pin(config, _pins())
    assert violations
    assert any("v0.2.0" in violation for violation in violations)


def test_mise_config_without_the_ax_tool_key_is_flagged(tmp_path: Path) -> None:
    """The CLI must be pinned somewhere mechanical, and [tools] is that place."""
    config = _write_mise_config(tmp_path, '[tools]\ngo = "latest"\n')
    violations = mod.check_mise_pin(config, _pins())
    assert len(violations) == 1
    assert MISE_AX_KEY in violations[0]
    assert "exe/versions.json" in violations[0]


def test_mise_config_without_a_tools_table_is_flagged(tmp_path: Path) -> None:
    config = _write_mise_config(tmp_path, "[settings]\npin = true\n")
    violations = mod.check_mise_pin(config, _pins())
    assert len(violations) == 1
    assert MISE_AX_KEY in violations[0]
    assert "exe/versions.json" in violations[0]


def test_missing_mise_config_is_skipped(tmp_path: Path) -> None:
    """A checkout without the mise config must not fail the gate."""
    absent = tmp_path / "config" / "mise" / "config.toml"
    assert not absent.exists()
    assert mod.check_mise_pin(absent, _pins()) == []


def test_mise_pin_of_an_unrecognised_shape_is_flagged(tmp_path: Path) -> None:
    config = _write_mise_config(tmp_path, _mise_body("3"))
    violations = mod.check_mise_pin(config, _pins())
    assert len(violations) == 1
    assert MISE_AX_KEY in violations[0]


def test_mise_check_does_not_double_report_a_missing_ax_version(
    tmp_path: Path,
) -> None:
    """A missing ax.version is check_schema's violation; report it once, there."""
    pins = _pins()
    del pins["ax"]["version"]
    config = _write_mise_config(tmp_path, _mise_body('"v0.3.1"'))
    assert mod.check_mise_pin(config, pins) == []
    assert mod.check_schema(pins)


# --- loading ---------------------------------------------------------------


def test_missing_versions_json_is_a_violation(tmp_path: Path) -> None:
    pins, violations = mod.load_pins(tmp_path)
    assert pins is None
    assert violations


def test_unparsable_versions_json_is_a_violation(tmp_path: Path) -> None:
    (tmp_path / "exe").mkdir()
    (tmp_path / "exe" / "versions.json").write_text("{ not json")
    pins, violations = mod.load_pins(tmp_path)
    assert pins is None
    assert violations


def test_load_pins_returns_the_document(tmp_path: Path) -> None:
    (tmp_path / "exe").mkdir()
    (tmp_path / "exe" / "versions.json").write_text(json.dumps(_pins()))
    pins, violations = mod.load_pins(tmp_path)
    assert violations == []
    assert pins is not None
    assert pins["substrate"]["version"] == "v0.1.0"


# --- the committed pin file must itself pass the gate ----------------------


def test_real_versions_json_keeps_one_substrate_reference() -> None:
    pins = json.loads(_REAL_PINS.read_text())
    substrate = pins["substrate"]
    assert substrate["version_label_value"] == substrate["version"]
    assert substrate["version_label_key"] == "ate.dev/substrate-version"


def test_real_mise_config_mirrors_the_real_ax_pin() -> None:
    """The committed mise pin and the committed ax.version must agree."""
    assert _REAL_MISE_CONFIG.is_file(), _REAL_MISE_CONFIG
    assert (_REPO_ROOT / mod.MISE_CONFIG_REL).resolve() == _REAL_MISE_CONFIG.resolve()
    pins = json.loads(_REAL_PINS.read_text())
    assert mod.check_mise_pin(_REAL_MISE_CONFIG, pins) == []


def test_repo_pins_pass_the_gate() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
