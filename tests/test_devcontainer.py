"""Structural assertions on .devcontainer/devcontainer.json.

The devcontainer.json file is the *single source of truth* shared by
three consumers:
  1. local IDE  (VS Code / Cursor / JetBrains "Reopen in Container")
  2. CI test    (devcontainers/ci action in .github/workflows/test-just.yaml)
  3. Coder workspace (envbuilder reads it on workspace VM boot)

Migrating it once moves all three together. These tests pin the
*structure* — base image and required features — so accidental edits
that drop, say, google-cloud-cli, surface as a unit-test failure long
before the Coder workspace stops booting.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER_JSON = ROOT / ".devcontainer" / "devcontainer.json"


def _load_devcontainer() -> dict:
    """devcontainer.json allows `// line` and `/* block */` comments
    (jsonc). Strip them before json.loads."""
    raw = DEVCONTAINER_JSON.read_text(encoding="utf-8")
    # Strip /* ... */ and // ... comments. Naïve but sufficient for
    # the well-formed file we maintain.
    raw = re.sub(r"/\*.*?\*/", "", raw, flags=re.DOTALL)
    raw = re.sub(r"^\s*//.*$", "", raw, flags=re.MULTILINE)
    # Trailing-comma safe-strip (jsonc allows; json.loads doesn't).
    raw = re.sub(r",(\s*[}\]])", r"\1", raw)
    return json.loads(raw)


@pytest.fixture(scope="module")
def devcontainer() -> dict:
    if not DEVCONTAINER_JSON.exists():
        pytest.fail(f"devcontainer.json missing at {DEVCONTAINER_JSON}")
    return _load_devcontainer()


def test_devcontainer_uses_image_not_build(devcontainer: dict) -> None:
    """We migrated away from `build.dockerfile: ../tests/docker/...`
    to a declarative `image:` reference. This forces all consumers
    (devcontainer CLI, envbuilder, devcontainers/ci action) to derive
    the same image graph from the same base."""
    assert "image" in devcontainer, (
        "devcontainer.json must declare `image:` (image-only form). "
        "Got keys: " + ", ".join(sorted(devcontainer.keys()))
    )
    assert "build" not in devcontainer, (
        "devcontainer.json must NOT declare `build:` — that re-introduces "
        "the alpine Dockerfile divergence. Use features instead."
    )


def test_devcontainer_image_is_debian_bookworm(devcontainer: dict) -> None:
    """Base image is the Microsoft-published debian-12 (bookworm)
    devcontainer base. glibc-native, no compat shim required."""
    assert devcontainer["image"] == "mcr.microsoft.com/devcontainers/base:bookworm", (
        f"Unexpected base image: {devcontainer['image']!r}. "
        "Expected mcr.microsoft.com/devcontainers/base:bookworm."
    )


REQUIRED_FEATURES = {
    "ghcr.io/devcontainers/features/common-utils:2",
    "ghcr.io/devcontainers/features/github-cli:1",
    "ghcr.io/devcontainers/features/google-cloud-cli:1",
    "ghcr.io/devcontainers/features/docker-outside-of-docker:1",
    "ghcr.io/devcontainers/features/python:1",
    "ghcr.io/devcontainers/features/node:1",
    "ghcr.io/devcontainers-extra/features/just:1",
    "ghcr.io/jdx/devcontainer-mise:0",
    "ghcr.io/va-h/devcontainers-features/uv:1",
}


def test_devcontainer_declares_required_features(devcontainer: dict) -> None:
    features = devcontainer.get("features", {})
    missing = REQUIRED_FEATURES - set(features.keys())
    assert not missing, (
        "devcontainer.json is missing features:\n  - "
        + "\n  - ".join(sorted(missing))
        + "\nDeclared:\n  - "
        + "\n  - ".join(sorted(features.keys()))
    )


def test_devcontainer_remote_user_is_root(devcontainer: dict) -> None:
    """remoteUser=root is intentional for this PR: tests, install.sh
    deploy logic, and Coder workspace all assume HOME=/root and
    /root/dotfiles workspace path. Switching to vscode user is a
    separate follow-up PR."""
    assert devcontainer.get("remoteUser") == "root", (
        f"remoteUser must be 'root', got {devcontainer.get('remoteUser')!r}. "
        "Switching to non-root requires updating ~30 test assertions."
    )


def test_devcontainer_workspace_folder_is_root_dotfiles(devcontainer: dict) -> None:
    assert devcontainer.get("workspaceFolder") == "/root/dotfiles", (
        f"workspaceFolder must be '/root/dotfiles', "
        f"got {devcontainer.get('workspaceFolder')!r}."
    )


def test_devcontainer_oncreate_runs_mise_install(devcontainer: dict) -> None:
    """mise install is called once at container creation. Without
    this, MISE_OFFLINE=1 callers (lint/test) fail because the
    bind-mounted host repo intentionally omits mise.lock."""
    cmd = devcontainer.get("onCreateCommand", "")
    assert "mise" in cmd and "install" in cmd, (
        f"onCreateCommand must run `mise install`, got: {cmd!r}"
    )


def test_devcontainer_postcreate_wires_prek_hooks(devcontainer: dict) -> None:
    """install-hooks wires prek into .git/hooks for this clone.
    Lives in postCreateCommand because it touches the bind-mounted
    workspace, which only exists after onCreate runs."""
    cmd = devcontainer.get("postCreateCommand", "")
    assert "install-hooks" in cmd, (
        f"postCreateCommand must run `just install-hooks`, got: {cmd!r}"
    )


def test_devcontainer_no_build_arg_references_alpine(devcontainer: dict) -> None:
    """Belt-and-braces: even if someone re-adds build.args, ensure
    no alpine reference sneaks back in."""
    text = DEVCONTAINER_JSON.read_text(encoding="utf-8")
    assert "alpine" not in text.lower(), (
        "devcontainer.json contains an 'alpine' reference. "
        "The base image migrated to debian-12; remove alpine."
    )


def test_devcontainer_does_not_reference_justsandbox_dockerfile(
    devcontainer: dict,
) -> None:
    """JustSandbox.Dockerfile is being removed in stage E; this
    assertion fails fast if devcontainer.json still points at it."""
    text = DEVCONTAINER_JSON.read_text(encoding="utf-8")
    assert "JustSandbox.Dockerfile" not in text, (
        "devcontainer.json still references JustSandbox.Dockerfile; "
        "the file is removed in stage E of the migration."
    )
