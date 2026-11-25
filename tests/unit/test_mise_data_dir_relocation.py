"""Regression test for the MISE_DATA_DIR=/opt/mise relocation
required by ADR 0006 (Accepted 2026-05-02).

What this guards
----------------
The retired Coder workspace template bound `/home/<user>:/root`
to persist operator state across container restarts within a VM.
That bind-mount masked `$HOME/.local/share/mise/installs/` —
the default location where the dev container feature pre-installs
the pinned mise.toml tools. With the cache hidden, a container
falls back to runtime fetches from api.github.com / aqua-registry
on every start, defeating the whole point of pinning.

Per ADR 0006 decision detail 4, the data dir is relocated to
`/opt/mise`. `/opt` is outside any mount over $HOME, so the cache
survives — which is what lets `MISE_OFFLINE=1` stay on at runtime
(decision detail 5). FHS-wise `/opt` is the right home for add-on
package trees.

These assertions live across three files:
- `.devcontainer/features/dotfiles-tools/install.sh`
  (build-time installs into /opt/mise)
- `.devcontainer/devcontainer.json`
  (containerEnv exposes MISE_DATA_DIR + shim PATH)
- `.devcontainer/post-create.sh`
  (post-create mise install honours the relocation)

A regression that re-introduces /root/.local/share/mise anywhere
breaks the relocation contract; this test catches it at PR-review
time rather than three weeks later, in a container that mounts
something over $HOME.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FEATURE_INSTALL_SH = (
    ROOT / ".devcontainer" / "features" / "dotfiles-tools" / "install.sh"
)
DEVCONTAINER_JSON = ROOT / ".devcontainer" / "devcontainer.json"
POST_CREATE_SH = ROOT / ".devcontainer" / "post-create.sh"


# ---------- feature install.sh ------------------------------------


def test_feature_install_creates_opt_mise() -> None:
    """The feature must `install -d` /opt/mise before mise install
    so the data dir actually exists at the expected location."""
    text = FEATURE_INSTALL_SH.read_text(encoding="utf-8")
    assert re.search(r"install\s+-d[^\n]*/opt/mise", text), (
        "feature install.sh must create /opt/mise (e.g. via "
        "`install -d -m 0755 /opt/mise`) before mise install."
    )


def test_feature_install_does_not_use_home_share_mise() -> None:
    """No command in the feature install.sh may use /root/.local/share/mise
    or $HOME/.local/share/mise after the relocation. Comment lines may name
    the old path: they explain why the data dir moved (ADR 0006)."""
    code = "\n".join(
        line
        for line in FEATURE_INSTALL_SH.read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )
    forbidden = [r"/root/\.local/share/mise", r"\$HOME/\.local/share/mise"]
    for pat in forbidden:
        assert not re.search(pat, code), (
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
    # Match quoted strings first: URI slashes, escaped quotes and comment
    # tokens inside strings are data, not JSONC syntax.
    quoted = r'"(?:\\.|[^"\\])*"'
    text = re.sub(
        quoted + r"|//[^\n]*|/\*.*?\*/",
        lambda match: match[0] if match[0].startswith('"') else " ",
        text,
        flags=re.DOTALL,
    )
    # Likewise, only remove trailing commas outside quoted strings.
    text = re.sub(
        f"({quoted})" + r"|,(\s*[}\]])",
        lambda match: match[1] if match[1] is not None else match[2],
        text,
    )
    return json.loads(text)


@pytest.fixture(scope="module")
def devcontainer_config() -> dict:
    return _load_devcontainer_json()


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
