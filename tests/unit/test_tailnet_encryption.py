"""Run the IaC encryption checks with local OpenTofu state."""

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LINEAGE = "0ea236f7-40bc-4f81-9ec5-8be1094de25a"
CONFIDENTIAL = "synthetic-confidential-state-output"


@pytest.fixture
def encryption_checks(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "tailnet_iac_under_test", ROOT / "tests/iac/test_tailnet.py"
    )
    assert spec and spec.loader
    sandbox = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sandbox)
    program = tmp_path / "encryption.py"
    program.write_text(sandbox._TAILNET_ENCRYPTION, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(
        "tailnet_encryption_under_test", program
    )
    assert spec and spec.loader
    checks = importlib.util.module_from_spec(spec)
    vars(checks)["json"] = json
    spec.loader.exec_module(checks)
    return checks


@pytest.fixture
def tofu(tmp_path):
    executable = shutil.which("tofu")
    if executable is None:
        pytest.skip("needs OpenTofu for local encryption and backend probes")
    mirror = tmp_path / "empty-mirror"
    mirror.mkdir()
    config = tmp_path / "tofurc"
    config.write_text(
        "disable_checkpoint = true\nprovider_installation {\n"
        f'  filesystem_mirror {{ path = "{mirror.as_posix()}" }}\n}}\n',
        encoding="utf-8",
    )
    env = {k: os.environ[k] for k in ("PATH", "SystemRoot") if k in os.environ}
    env.update(
        HOME=str(tmp_path),
        TF_CLI_CONFIG_FILE=str(config),
        TF_IN_AUTOMATION="1",
        CHECKPOINT_DISABLE="1",
    )

    def run(directory, *args):
        done = subprocess.run(
            [executable, *args],
            cwd=directory,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=30,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        return done

    return run


def test_tailnet_encrypted_state_allows_plaintext_metadata(
    encryption_checks, tofu, tmp_path
):
    (tmp_path / "main.tf").write_text(
        """terraform {
  encryption {
    key_provider "pbkdf2" "default" {
      passphrase = "fixture-passphrase-with-no-private-key"
    }
    method "aes_gcm" "default" {
      keys = key_provider.pbkdf2.default
    }
    state {
      method = method.aes_gcm.default
      enforced = true
    }
  }
}
""",
        encoding="utf-8",
    )
    state = {
        "version": 4,
        "terraform_version": json.loads(tofu(tmp_path, "version", "-json").stdout)[
            "terraform_version"
        ],
        "serial": 1,
        "lineage": LINEAGE,
        "outputs": {
            "confidential": {"value": CONFIDENTIAL, "type": "string", "sensitive": True}
        },
        "resources": [],
    }
    (tmp_path / "seed.json").write_text(json.dumps(state), encoding="utf-8")
    tofu(tmp_path, "init", "-input=false")
    tofu(tmp_path, "state", "push", "-force", "-lock=false", "seed.json")
    pulled = json.loads(tofu(tmp_path, "state", "pull").stdout)
    raw = (tmp_path / "terraform.tfstate").read_bytes()

    assert pulled["lineage"] == LINEAGE
    assert pulled["outputs"]["confidential"]["value"] == CONFIDENTIAL
    encryption_checks.assert_encrypted_state(raw, pulled)


@pytest.mark.parametrize(
    "stored",
    [
        {"encrypted_data": "ciphertext", "leaked": CONFIDENTIAL},
        {"outputs": {}},
        {"encrypted_data": "ciphertext", "leaked": "fixture-passphrase"},
    ],
    ids=["confidential-output", "missing-ciphertext", "passphrase"],
)
def test_tailnet_encrypted_state_rejects_exposed_payload(encryption_checks, stored):
    state = {"outputs": {"confidential": {"value": CONFIDENTIAL}}}
    with pytest.raises(AssertionError):
        encryption_checks.assert_encrypted_state(json.dumps(stored).encode(), state)


@pytest.mark.parametrize("section", ["state", "plan"])
def test_tailnet_enforcement_probes_initialize_local_backends(
    encryption_checks, tofu, tmp_path, section
):
    probe = tmp_path / section
    probe.mkdir()
    (probe / "main.tf").write_text(
        'terraform {\n  backend "gcs" {}\n}\n', encoding="utf-8"
    )
    encryption_checks.write_local_backend_override(probe)

    tofu(probe, "init", "-input=false", "-lockfile=readonly")
