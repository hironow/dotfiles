"""tofu/exe-cluster's Kubernetes providers mint their credential at run time.

A saved plan carries the values of every data source it read. When the
kubernetes and kubectl providers took `data.google_client_config.access_token`,
each saved plan carried a Google access token that expires after an hour, and a
plan applied later failed half-way with "the server has asked for the client to
provide credentials" (2026-09-27: the store move's first apply, after the
install step's state record was already gone). With an `exec` block,
gke-gcloud-auth-plugin mints the token when the apply talks to the cluster, so a
saved plan's age no longer matters to the cluster calls.

Provider configuration is invisible to `tofu test` assertions, so this reads the
stack's source.
"""

from __future__ import annotations

import re
from pathlib import Path

_PLATFORM_TF = (
    Path(__file__).resolve().parents[2] / "tofu" / "exe-cluster" / "platform.tf"
)


def _provider_block(name: str) -> str:
    text = _PLATFORM_TF.read_text()
    start = re.search(rf'^provider "{name}" \{{\s*$', text, re.MULTILINE)
    assert start, f'provider "{name}" not found in {_PLATFORM_TF.name}'
    depth, i = 0, start.start()
    for i in range(start.start(), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                break
    return text[start.start() : i + 1]


def _uncommented(block: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in block.splitlines())


def test_kubernetes_provider_execs_the_gke_auth_plugin() -> None:
    block = _uncommented(_provider_block("kubernetes"))
    assert re.search(r'command\s*=\s*"gke-gcloud-auth-plugin"', block), block
    assert not re.search(r"^\s*token\s*=", block, re.MULTILINE), block


def test_kubectl_provider_execs_the_gke_auth_plugin() -> None:
    block = _uncommented(_provider_block("kubectl"))
    assert re.search(r'command\s*=\s*"gke-gcloud-auth-plugin"', block), block
    assert not re.search(r"^\s*token\s*=", block, re.MULTILINE), block


def test_no_planned_access_token_is_read() -> None:
    assert "google_client_config" not in _uncommented(_PLATFORM_TF.read_text())
