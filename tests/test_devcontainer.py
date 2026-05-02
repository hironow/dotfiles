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

The trailing `@pytest.mark.devcontainer_up` block adds runtime
smoke tests that exercise the actual `devcontainer up` lifecycle
against a built image — closing the prod-equivalence gap that the
plain `docker run` fixture in test_just_sandbox.py cannot cover.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DEVCONTAINER_JSON = ROOT / ".devcontainer" / "devcontainer.json"
IMAGE = "dotfiles-just-sandbox:latest"


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


# ---------------------------------------------------------------------------
# Runtime smoke tests on the saved image. These verify that what the
# structural assertions above SAY is in devcontainer.json actually
# materialised as expected baked-in state. They cover three gaps the
# raw `docker run` fixture in test_just_sandbox.py does not:
#   A) the `devcontainer up` lifecycle path actually completes
#      (the same path local IDE / Coder workspace / CI all use)
#   B) trust-boundary scoping is in effect at runtime — not just in
#      the JSON file (a future revert to `/root` or `*` would be
#      caught even if the JSON is otherwise updated)
#   C) every tool the local feature claims to install is on PATH and
#      version-responds (a single source of truth for "feature
#      install.sh actually worked")
# All gated by image presence: skipped when the saved image is not
# available locally.
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    return (
        subprocess.run(["docker", "info"], capture_output=True, text=True).returncode
        == 0
    )


def _image_exists(image: str) -> bool:
    return (
        subprocess.run(
            ["docker", "image", "inspect", image], capture_output=True, text=True
        ).returncode
        == 0
    )


def _run_in_image(script: str) -> subprocess.CompletedProcess:
    """One-shot `docker run` against the saved image. Mirrors
    test_just_sandbox.run_in_sandbox but without the bind mount —
    these tests only inspect baked-in image state."""
    return subprocess.run(
        ["docker", "run", "--rm", IMAGE, "bash", "-lc", script],
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def saved_image() -> str:
    if not _docker_available():
        pytest.skip("Docker is not available; skipping runtime smoke tests.")
    if not _image_exists(IMAGE):
        pytest.skip(
            f"Image {IMAGE!r} is not present. Build it first with "
            "`devcontainer build --workspace-folder . --image-name "
            f"{IMAGE}` or run via the devcontainers/ci CI step."
        )
    return IMAGE


REQUIRED_TOOLS = (
    ("bash", "--version"),
    ("git", "--version"),
    ("gcloud", "--version"),
    ("mise", "--version"),
    ("uv", "--version"),
    ("just", "--version"),
    ("sheldon", "--version"),
    ("shellcheck", "--version"),
    ("jq", "--version"),
)


@pytest.mark.parametrize(
    "tool, flag",
    REQUIRED_TOOLS,
    ids=[t for t, _ in REQUIRED_TOOLS],
)
def test_image_provides_tool(saved_image: str, tool: str, flag: str) -> None:
    """Every tool the local feature install.sh claims to install
    must be on PATH and version-respond inside the saved image.
    A single source of truth: if the install.sh silently failed for
    one tool, this assertion catches it before any downstream test."""
    result = _run_in_image(f"command -v {tool} && {tool} {flag}")
    assert result.returncode == 0, (
        f"{tool} not found or not runnable inside saved image.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_image_git_safe_directory_is_scoped(saved_image: str) -> None:
    """`/etc/gitconfig` must list ONLY the specific paths the dev
    container needs, NOT '*'. Catches a future revert that
    re-introduces the CWE-bypass scope hole."""
    result = _run_in_image("git config --system --get-all safe.directory || true")
    assert result.returncode == 0, (
        f"failed to read system gitconfig:\nstderr:\n{result.stderr}"
    )
    entries = [line for line in result.stdout.splitlines() if line.strip()]
    assert "*" not in entries, (
        "git safe.directory '*' detected in /etc/gitconfig — this disables "
        "dubious-ownership protection globally. Scope to /root/dotfiles "
        "and /root/sandbox/dotfiles-fresh."
    )
    assert "/root/dotfiles" in entries, (
        f"missing /root/dotfiles in safe.directory list. Got: {entries!r}"
    )
    assert "/root/sandbox/dotfiles-fresh" in entries, (
        f"missing /root/sandbox/dotfiles-fresh in safe.directory list. Got: {entries!r}"
    )


def test_image_profile_d_mise_env_is_scoped(saved_image: str) -> None:
    """The /etc/profile.d/dotfiles-mise.sh shipped by the local
    feature must scope MISE_TRUSTED_CONFIG_PATHS, not allowlist /root.
    A login shell sources it and then any mise process inherits the
    scoped value."""
    # Source the file in a sub-shell and print ONLY the resolved
    # variable. Greping the file body would false-match comments
    # that mention earlier revisions of the value.
    result = _run_in_image(
        ". /etc/profile.d/dotfiles-mise.sh && "
        'printf "%s\\n" "$MISE_TRUSTED_CONFIG_PATHS"'
    )
    assert result.returncode == 0, (
        f"failed to source profile.d:\nstderr:\n{result.stderr}"
    )
    resolved = result.stdout.strip()
    assert resolved, (
        "profile.d/dotfiles-mise.sh did not export MISE_TRUSTED_CONFIG_PATHS."
    )
    # Catch a regression to the broader value.
    assert resolved != "/root", (
        "MISE_TRUSTED_CONFIG_PATHS regressed to /root in profile.d. "
        "GHSA-436v-8fw5-4mj8 / CVE-2026-35533 — keep the scoping tight."
    )
    entries = resolved.split(":")
    assert "/root/dotfiles" in entries, (
        f"profile.d/dotfiles-mise.sh missing /root/dotfiles. Resolved: {resolved!r}"
    )
    assert "/root/sandbox/dotfiles-fresh" in entries, (
        f"profile.d/dotfiles-mise.sh missing /root/sandbox/dotfiles-fresh. "
        f"Resolved: {resolved!r}"
    )
    for entry in entries:
        assert entry.startswith("/root/"), (
            f"unexpected mise trust path {entry!r}; must be under /root/. "
            f"Resolved: {resolved!r}"
        )


def test_image_devcontainer_metadata_smoke(saved_image: str) -> None:
    """Smoke-check: the saved image embeds a label that
    devcontainers/ci writes during build. Without this, the
    `imageName: dotfiles-just-sandbox` step did not actually run a
    devcontainer build (someone might have built a plain Dockerfile
    image with the same tag), and the rest of the suite is testing
    a different image than prod."""
    result = subprocess.run(
        [
            "docker",
            "image",
            "inspect",
            "--format={{json .Config.Labels}}",
            IMAGE,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"failed to inspect image:\nstderr:\n{result.stderr}"
    labels_json = result.stdout.strip()
    # devcontainers/ci writes labels under the
    # `devcontainer.metadata` key; bare `docker build` omits this.
    assert "devcontainer.metadata" in labels_json, (
        "saved image lacks the devcontainer.metadata label that "
        "devcontainers/ci writes; the runtime smoke tests above were "
        "exercising an image NOT built through the dev container "
        "pipeline.\n"
        f"labels: {labels_json}"
    )


# ---------- ADR 0006 runtime: /opt/mise relocation ----------------


def test_image_mise_data_dir_is_opt_mise(saved_image: str) -> None:
    """A login shell must resolve MISE_DATA_DIR=/opt/mise (set by
    /etc/profile.d/dotfiles-mise.sh) and the directory must exist
    with the build-time installs/ tree underneath it.

    This is the runtime invariant ADR 0006 decision detail 4 names
    explicitly. A regression that relocates back to
    $HOME/.local/share/mise breaks the gcp-vm-container template's
    /home/<user>:/root volume mount contract: the cache disappears
    on first workspace boot."""
    result = _run_in_image(
        ". /etc/profile.d/dotfiles-mise.sh && "
        'printf "MISE_DATA_DIR=%s\\n" "$MISE_DATA_DIR" && '
        "test -d /opt/mise/installs && "
        "test -d /opt/mise/shims && "
        'echo "installs+shims present"'
    )
    assert result.returncode == 0, (
        f"runtime check for /opt/mise failed.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "MISE_DATA_DIR=/opt/mise" in result.stdout, (
        f"profile.d did not export MISE_DATA_DIR=/opt/mise.\nstdout:\n{result.stdout}"
    )
    assert "installs+shims present" in result.stdout, (
        "Either /opt/mise/installs or /opt/mise/shims is missing in the "
        "saved image. Build-time `mise install` did not write to the "
        "expected data dir."
    )


def test_image_mise_offline_install_works(saved_image: str) -> None:
    """`MISE_OFFLINE=1 mise install` against the workspace mise.toml
    must succeed inside the saved image. This proves that the build-
    time-baked /opt/mise cache covers every pinned tool — the
    prerequisite for ADR 0006 decision detail 5 (workspace runtime
    MISE_OFFLINE=1 re-enable).

    The saved image does NOT contain /root/dotfiles (that's a
    runtime bind-mount when the dev container is up). We synthesise
    a minimal mise.toml inside /tmp/mise-runtime-check, override
    MISE_TRUSTED_CONFIG_PATHS to include that path, and run `mise
    install` against it offline."""
    # Read the canonical mise.toml from the working tree and embed
    # it via heredoc so the test stays SoT-aware: any pin change in
    # the workspace mise.toml is reflected automatically.
    mise_toml = (Path(__file__).resolve().parents[1] / "mise.toml").read_text(
        encoding="utf-8"
    )
    script = (
        ". /etc/profile.d/dotfiles-mise.sh && "
        "rm -rf /tmp/mise-runtime-check && "
        "mkdir -p /tmp/mise-runtime-check && "
        "cat > /tmp/mise-runtime-check/mise.toml <<'MISE_TOML_EOF'\n"
        f"{mise_toml}\n"
        "MISE_TOML_EOF\n"
        "cd /tmp/mise-runtime-check && "
        # Override the trusted-paths scope just for this invocation
        # so mise reads the synthetic mise.toml. The image's default
        # scope (/root/dotfiles + /root/sandbox/...) is untouched.
        'MISE_TRUSTED_CONFIG_PATHS="/tmp/mise-runtime-check" '
        "MISE_OFFLINE=1 mise install 2>&1"
    )
    result = _run_in_image(script)
    assert result.returncode == 0, (
        f"`MISE_OFFLINE=1 mise install` failed inside the saved image. "
        f"This means at least one pinned tool is missing from "
        f"/opt/mise/installs — workspace runtime would fail too.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # mise prints "Installing ..." for tools it would fetch — under
    # MISE_OFFLINE=1 it should not print that for any of them, since
    # all are already cached.
    assert "Installing" not in result.stdout, (
        f"mise tried to fetch a tool under MISE_OFFLINE=1; that means "
        f"the build-time prebuild missed it. mise output:\n{result.stdout}"
    )
