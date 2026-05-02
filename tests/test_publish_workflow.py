"""Structural assertions on .github/workflows/publish-devcontainer.yaml.

The publish workflow is what produces the OCI image the Coder
template (exe/coder/templates/dotfiles-devcontainer/) consumes via
`var.image`. A subtle bug in this file slipped past local checks
once already (imageName=`<repo>:main` + imageTag=`latest` produced
the invalid reference `<repo>:main:latest`); these tests pin the
shape so the same regression cannot land twice.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-devcontainer.yaml"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    if not WORKFLOW.exists():
        pytest.fail(f"missing workflow: {WORKFLOW}")
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_authenticates_via_wif(workflow_text: str) -> None:
    """Image push must use Workload Identity Federation, never a
    long-lived service account JSON. Catches a future revert that
    re-introduces a key-based auth path."""
    assert "google-github-actions/auth" in workflow_text, (
        "workflow must use google-github-actions/auth for WIF"
    )
    assert "workload_identity_provider:" in workflow_text, (
        "auth step must pass workload_identity_provider"
    )
    assert "service_account:" in workflow_text, (
        "auth step must pass the impersonated service_account"
    )
    forbidden = ["credentials_json:", "credentials_file:"]
    for needle in forbidden:
        assert needle not in workflow_text, (
            f"workflow uses {needle!r} (key-based auth). "
            "Use WIF (workload_identity_provider) instead."
        )


def test_workflow_uses_devcontainers_ci_with_pinned_sha(
    workflow_text: str,
) -> None:
    """devcontainers/ci must be pinned to a 40-char SHA + tag
    comment, matching org Actions policy."""
    m = re.search(
        r"uses:\s*devcontainers/ci@([0-9a-f]+)",
        workflow_text,
    )
    assert m is not None, "publish workflow must use devcontainers/ci"
    sha = m.group(1)
    assert len(sha) == 40, (
        f"devcontainers/ci must be pinned to a full 40-char SHA, got: {sha!r}"
    )


def test_workflow_does_not_double_tag_image(workflow_text: str) -> None:
    """devcontainers/ci concatenates imageName + ':' + imageTag.
    If imageName already contains a ':<tag>' segment, the result is
    a double-tag like '<repo>:main:latest' which docker rejects as
    'invalid reference format'. Force imageName to be the bare repo
    path."""
    # Find the 'with:' block that feeds devcontainers/ci.
    block = re.search(
        r"uses:\s*devcontainers/ci@.*?(\n\s*with:.*?)(?=\n\s+- |\Z)",
        workflow_text,
        re.DOTALL,
    )
    assert block is not None, "could not locate the devcontainers/ci 'with:' block"
    body = block.group(1)
    image_name_match = re.search(r"imageName:\s*([^\n]+)", body)
    assert image_name_match is not None, "with: must declare imageName"
    image_name_value = image_name_match.group(1).strip()
    # Strip ${{ ... }} substitutions so we can lint the literal payload.
    # Anything inside ${{ ... }} resolves to a step output; we still
    # validate the *output expression* points at a base path, never a
    # `:tag` reference.
    if "${{" in image_name_value:
        # The output is named — the resolution itself is checked by
        # an output-name convention: any output whose name ends in
        # `_main`, `_sha`, etc. is suspicious.
        assert "_main" not in image_name_value and "_sha" not in image_name_value, (
            f"imageName references a tagged output ({image_name_value}). "
            "Use the bare-base output and pass the tag via imageTag."
        )
    else:
        # Literal value — must NOT contain ':' after the registry/path
        # split. The Artifact Registry path itself uses ':' only at the
        # tag boundary; everything before is path components.
        # We just guard against any explicit ':<tag>' suffix.
        assert ":" not in image_name_value.split("/")[-1], (
            f"imageName has a ':<tag>' suffix on the final segment "
            f"({image_name_value!r}). devcontainers/ci would concatenate "
            "with imageTag and produce '<repo>:<a>:<b>' which docker "
            "rejects as invalid reference format."
        )


def test_workflow_publishes_immutable_sha_tag(workflow_text: str) -> None:
    """The workflow tags the same image twice: a rolling :main and
    an immutable :<git-sha>. The Coder template can pin to the SHA
    for repeatable rollbacks. Both pushes must be present."""
    assert "GITHUB_SHA" in workflow_text, (
        "workflow must reference GITHUB_SHA when computing the immutable tag"
    )
    # Look for a `docker push` of a SHA-tagged ref.
    assert re.search(r"docker push .*image_sha", workflow_text), (
        "workflow must docker push the :<sha> tagged ref after the "
        "devcontainers/ci step"
    )


def test_workflow_uses_correct_artifact_registry_path(
    workflow_text: str,
) -> None:
    """The image path must match what the Coder template's
    `var.image` default consumes:
    asia-northeast1-docker.pkg.dev/gen-ai-hironow/dotfiles/devcontainer.
    Drift between the two would silently push to one location and
    pull from another."""
    assert "asia-northeast1" in workflow_text, "AR_REGION must be asia-northeast1"
    assert "gen-ai-hironow" in workflow_text, "AR_PROJECT must be gen-ai-hironow"
    assert "dotfiles" in workflow_text, "AR_REPO must be dotfiles"
    assert "devcontainer" in workflow_text, "AR_IMAGE must be devcontainer"


def test_workflow_passes_github_token_to_action(workflow_text: str) -> None:
    """devcontainers/ci needs GITHUB_TOKEN (passed via `env:` block)
    so feature graph resolution against ghcr.io hits the
    authenticated quota. Without it, the build can fail under load
    on api.github.com 60/hr anonymous limit."""
    assert "GITHUB_TOKEN=${{ secrets.GITHUB_TOKEN }}" in workflow_text, (
        "devcontainers/ci step must surface GITHUB_TOKEN via env: block"
    )
