"""Regression test for the MISE_DATA_DIR=/opt/mise relocation
required by ADR 0006 (Accepted 2026-05-02).

What this guards
----------------
The Coder workspace template binds `/home/<user>:/root` to
persist operator state across container restarts within a VM.
That bind-mount masks `$HOME/.local/share/mise/installs/` —
the default location where the dev container feature pre-installs
the pinned mise.toml tools. With the cache hidden, the workspace
falls back to runtime fetches from api.github.com / aqua-registry
on every start, defeating the whole point of pinning.

Per ADR 0006 decision detail 4, the data dir is relocated to
`/opt/mise`. `/opt` is outside the volume-mount path, so the
cache survives. This relocation is what unblocks
`MISE_OFFLINE=1` re-enable at workspace runtime (decision detail
5). FHS-wise `/opt` is the right home for add-on package trees.

These assertions live across four files:
- `.devcontainer/features/dotfiles-tools/install.sh`
  (build-time installs into /opt/mise)
- `.devcontainer/devcontainer.json`
  (containerEnv exposes MISE_DATA_DIR + shim PATH)
- `.devcontainer/post-create.sh`
  (post-create mise install honours the relocation)
- `exe/coder/templates/dotfiles-devcontainer/main.tf`
  (workspace agent startup_script propagates MISE_DATA_DIR + flips MISE_OFFLINE back to 1)

A regression that re-introduces /root/.local/share/mise anywhere
breaks the relocation contract; this test catches it at PR-review
time before the workspace boot fails three weeks later.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
FEATURE_INSTALL_SH = (
    ROOT / ".devcontainer" / "features" / "dotfiles-tools" / "install.sh"
)
DEVCONTAINER_JSON = ROOT / ".devcontainer" / "devcontainer.json"
POST_CREATE_SH = ROOT / ".devcontainer" / "post-create.sh"
WORKSPACE_TF = (
    ROOT / "exe" / "coder" / "templates" / "dotfiles-devcontainer" / "main.tf"
)


# ---------- feature install.sh ------------------------------------


def test_feature_install_creates_opt_mise() -> None:
    """The feature must `install -d` /opt/mise before mise install
    so the data dir actually exists at the expected location."""
    text = FEATURE_INSTALL_SH.read_text(encoding="utf-8")
    assert re.search(r"install\s+-d[^\n]*/opt/mise", text), (
        "feature install.sh must create /opt/mise (e.g. via "
        "`install -d -m 0755 /opt/mise`) before mise install."
    )


def test_feature_install_exports_mise_data_dir() -> None:
    """Build-time mise install must run with MISE_DATA_DIR=/opt/mise
    so installs end up there."""
    text = FEATURE_INSTALL_SH.read_text(encoding="utf-8")
    assert re.search(
        r"export\s+MISE_DATA_DIR=/opt/mise|MISE_DATA_DIR=/opt/mise\s+mise",
        text,
    ), (
        "feature install.sh must export MISE_DATA_DIR=/opt/mise before "
        "running `mise install`."
    )


def test_feature_install_does_not_use_home_share_mise() -> None:
    """No reference to /root/.local/share/mise or $HOME/.local/share/mise
    should remain in the feature install.sh after the relocation."""
    text = FEATURE_INSTALL_SH.read_text(encoding="utf-8")
    forbidden = [r"/root/\.local/share/mise", r"\$HOME/\.local/share/mise"]
    for pat in forbidden:
        assert not re.search(pat, text), (
            f"feature install.sh still references {pat}; relocation to "
            f"/opt/mise per ADR 0006 must remove all such references."
        )


def test_feature_install_writes_profile_d_with_data_dir() -> None:
    """The /etc/profile.d/dotfiles-mise.sh shipped by the feature must
    export MISE_DATA_DIR=/opt/mise. Inner one-shot containers spawned
    by the test fixture inherit env via login shell, not containerEnv."""
    text = FEATURE_INSTALL_SH.read_text(encoding="utf-8")
    profile_block = re.search(
        r"cat > /etc/profile\.d/dotfiles-mise\.sh <<'PROFILE'(.*?)PROFILE",
        text,
        re.DOTALL,
    )
    assert profile_block is not None, "could not locate the profile.d heredoc"
    body = profile_block.group(1)
    assert re.search(r"export\s+MISE_DATA_DIR=/opt/mise", body), (
        "/etc/profile.d/dotfiles-mise.sh must export MISE_DATA_DIR=/opt/mise."
    )
    assert "/opt/mise/shims" in body, (
        "/etc/profile.d/dotfiles-mise.sh must add /opt/mise/shims to PATH."
    )


# ---------- devcontainer.json -------------------------------------


def _load_devcontainer_json() -> dict:
    """devcontainer.json is JSON-with-comments. Strip them before
    json.loads."""
    text = DEVCONTAINER_JSON.read_text(encoding="utf-8")
    # Strip /* ... */ block comments and // line comments. Keep
    # // inside strings — but the codebase doesn't use protocol
    # URLs in this file so a simple regex is safe.
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"//[^\n]*$", "", text, flags=re.MULTILINE)
    # Strip trailing commas before } or ].
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return json.loads(text)


@pytest.fixture(scope="module")
def devcontainer_config() -> dict:
    return _load_devcontainer_json()


def test_devcontainer_containerenv_has_mise_data_dir(
    devcontainer_config: dict,
) -> None:
    """containerEnv must expose MISE_DATA_DIR=/opt/mise so processes
    spawned by the dev container (incl. pytest sub-containers via
    docker-outside-of-docker) inherit the relocation."""
    container_env = devcontainer_config.get("containerEnv", {})
    assert container_env.get("MISE_DATA_DIR") == "/opt/mise", (
        f"devcontainer.json containerEnv must set MISE_DATA_DIR=/opt/mise. "
        f"Found: {container_env.get('MISE_DATA_DIR')!r}"
    )


def test_devcontainer_path_uses_opt_mise_shims(
    devcontainer_config: dict,
) -> None:
    """containerEnv PATH must include /opt/mise/shims (not the old
    /root/.local/share/mise/shims)."""
    container_env = devcontainer_config.get("containerEnv", {})
    path = container_env.get("PATH", "")
    assert "/opt/mise/shims" in path, (
        f"devcontainer.json containerEnv PATH must include /opt/mise/shims. "
        f"Found PATH: {path!r}"
    )
    assert "/root/.local/share/mise/shims" not in path, (
        f"devcontainer.json containerEnv PATH still references the "
        f"old /root/.local/share/mise/shims; remove it after the "
        f"relocation. PATH={path!r}"
    )


# ---------- post-create.sh ----------------------------------------


def test_post_create_does_not_force_mise_offline_zero() -> None:
    """Per ADR 0006 decision 5, post-create's mise install no longer
    needs to flip MISE_OFFLINE to 0 — the cache is now reachable
    under /opt/mise regardless of the bind mount."""
    text = POST_CREATE_SH.read_text(encoding="utf-8")
    assert not re.search(r"\bMISE_OFFLINE=0\b", text), (
        "post-create.sh still forces MISE_OFFLINE=0; per ADR 0006 the "
        "data-dir relocation removes the need for this override."
    )


# ---------- workspace agent startup_script ------------------------


def test_workspace_startup_script_sets_mise_data_dir() -> None:
    """The agent startup_script must export MISE_DATA_DIR=/opt/mise
    so the runtime mise install reaches the relocated cache."""
    text = WORKSPACE_TF.read_text(encoding="utf-8")
    assert re.search(
        r"MISE_DATA_DIR=/opt/mise",
        text,
    ), (
        "main.tf agent startup_script must propagate "
        "MISE_DATA_DIR=/opt/mise to the workspace mise install."
    )


def test_workspace_startup_script_re_enables_mise_offline() -> None:
    """Per ADR 0006 decision 5, the workspace runtime mise install
    runs with MISE_OFFLINE=1 because the relocation makes the cache
    available without network."""
    text = WORKSPACE_TF.read_text(encoding="utf-8")
    # The relevant block lives in the agent startup_script heredoc.
    block = re.search(r"startup_script\s*=[^<]*<<-EOT(.*?)EOT", text, re.DOTALL)
    assert block is not None, "could not locate workspace startup_script"
    body = block.group(1)
    # Must invoke mise install with MISE_OFFLINE=1.
    assert re.search(r"MISE_OFFLINE=1\s+mise\s+install", body), (
        "main.tf agent startup_script should run `MISE_OFFLINE=1 mise install` "
        "now that the cache lives at /opt/mise."
    )
    # Must NOT contain MISE_OFFLINE=0 anymore.
    assert not re.search(r"MISE_OFFLINE=0\s+mise", body), (
        "main.tf agent startup_script still forces MISE_OFFLINE=0; "
        "remove it per ADR 0006 decision 5."
    )
