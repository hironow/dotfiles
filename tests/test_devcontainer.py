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
    "ghcr.io/devcontainers/features/docker-outside-of-docker:1",
    "ghcr.io/devcontainers/features/python:1",
    "ghcr.io/devcontainers/features/node:1",
    # Local feature: build-time installer for gcloud/mise/uv/just/sheldon.
    # Required because lifecycle commands (onCreate/postCreate) under
    # devcontainers/ci do NOT commit back to the saved image, so
    # build-time installation is the only way to ensure these tools
    # appear in the test sandbox image.
    "./features/dotfiles-tools",
}


def test_devcontainer_declares_required_features(devcontainer: dict) -> None:
    """All declared features MUST be Microsoft-curated
    (`ghcr.io/devcontainers/features/*`). Community features
    (devcontainers-extra, dhoeric, jdx, va-h, etc.) are blocked by
    repo policy — see
    docs/adr/0001-devcontainer-debian-features.md and the
    `feedback_no_community_devcontainer_features` user memory.
    Non-feature tools (gcloud, just, mise, uv, sheldon) are
    installed by .devcontainer/post-create.sh from vendor-official
    artifacts (apt repos with GPG, GitHub releases with SHA256)."""
    features = devcontainer.get("features", {})
    missing = REQUIRED_FEATURES - set(features.keys())
    assert not missing, (
        "devcontainer.json is missing features:\n  - "
        + "\n  - ".join(sorted(missing))
        + "\nDeclared:\n  - "
        + "\n  - ".join(sorted(features.keys()))
    )

    # Trust-boundary guard: only Microsoft-curated features OR
    # local in-repo features (./<path>) allowed. Local features run
    # the install script from this repo and are auditable in PR
    # review, so they sit inside the trust boundary.
    bad = [
        f
        for f in features
        if not f.startswith("ghcr.io/devcontainers/features/")
        and not f.startswith("./")
    ]
    assert not bad, (
        "devcontainer.json declares non-Microsoft, non-local features:\n  - "
        + "\n  - ".join(bad)
        + "\nOnly `ghcr.io/devcontainers/features/*` (Microsoft) or "
        "`./<repo-path>` (local feature) is allowed; community feature "
        "registries are out of scope."
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


def test_devcontainer_oncreate_invokes_post_create_script(
    devcontainer: dict,
) -> None:
    """onCreate delegates to .devcontainer/post-create.sh, which
    installs vendor-official tools (gcloud / mise / uv / just /
    sheldon) and resolves mise.toml. Keeping the long install logic
    in a shell file under shellcheck/CI makes it auditable; the
    JSON only references it."""
    cmd = devcontainer.get("onCreateCommand", "")
    assert "post-create.sh" in cmd, (
        f"onCreateCommand must invoke post-create.sh, got: {cmd!r}"
    )

    post_create = ROOT / ".devcontainer" / "post-create.sh"
    assert post_create.exists(), f"post-create.sh missing at {post_create}"
    body = post_create.read_text()
    assert "mise install" in body, (
        "post-create.sh must run `mise install` to resolve mise.toml tools."
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


def test_dotfiles_tools_feature_files_exist() -> None:
    """The local feature must ship both the manifest and the
    install script. devcontainer CLI silently ignores a feature
    whose folder is missing one or the other."""
    feature_dir = ROOT / ".devcontainer" / "features" / "dotfiles-tools"
    manifest = feature_dir / "devcontainer-feature.json"
    script = feature_dir / "install.sh"
    assert manifest.is_file(), f"missing {manifest}"
    assert script.is_file(), f"missing {script}"
    # The script must be exec-bit set (devcontainer CLI calls it
    # directly, not via `bash <path>`).
    assert script.stat().st_mode & 0o100, (
        f"{script} must be executable; run `chmod +x` on it."
    )


def test_mise_trusted_paths_are_scoped(devcontainer: dict) -> None:
    """containerEnv MISE_TRUSTED_CONFIG_PATHS must NOT be a broad
    ancestor like '/root' — that exposes the entire HOME tree as a
    trusted mise config root (GHSA-436v-8fw5-4mj8 / CVE-2026-35533).
    The migration scopes it to specific paths used by tests and the
    workspace."""
    paths = devcontainer.get("containerEnv", {}).get("MISE_TRUSTED_CONFIG_PATHS", "")
    assert paths, "containerEnv must declare MISE_TRUSTED_CONFIG_PATHS"
    assert paths != "/root", (
        "MISE_TRUSTED_CONFIG_PATHS=/root is too broad (security regression). "
        "Scope to /root/dotfiles and /root/sandbox/dotfiles-fresh."
    )
    for entry in paths.split(":"):
        assert entry.startswith("/root/"), (
            f"unexpected mise trust path {entry!r}; "
            f"must be under /root/. Got {paths!r}."
        )
